"""Find the joint limits the HARDWARE actually allows, by turning each joint until the CAD
geometry collides.

The ranges v2 inherited came from the old MJCF and are not this machine's. This sweeps every
joint through a wide span and reports the first angle at which two bodies that are NOT already
touching at zero start to interfere.

Fidelity matters here, twice over. One convex proxy per body reports a collision long before
the real parts touch (a hip yoke is a fork, not a blob), and so does one convex hull per
SOLID - a single yoke solid is itself a fork, and a motor turning inside it shows a growing
hull overlap where the hardware has clearance. So the proxies are the ACTUAL triangle meshes
of every CAD solid, tested mesh-to-mesh through FCL's BVH. Whether that was necessary is
visible in the run itself: with real meshes the parts that "overlap" at q=0 should be few and
shallow, where convex hulls reported 105 mm of built-in interference between thigh and shin.

Pairs already interfering at q=0 are recorded first and excluded: the CAD nests motor housings
inside yokes by construction, and that is not a limit.

Usage: rom_check.py [--step=0.5]
"""
import json
import os
import sys

import numpy as np
import trimesh
import mujoco

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
XML = f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/pygmalion_v2.xml'
PIECES = '/home/syaro/pyg_fea/fusion/rom_pieces.npz'
JOINTS = ['hip_pitch', 'hip_roll', 'hip_yaw', 'knee', 'ankle_pitch', 'ankle_roll',
          'waist_yaw', 'shoulder_pitch', 'shoulder_roll']
CENTRE = {'waist_yaw'}                 # on the centreline: no L_/R_ prefix
# how far to look, per joint (deg) - wider than any plausible design range
SPAN = {'hip_pitch': (-150, 60), 'hip_roll': (-120, 60), 'hip_yaw': (-90, 90),
        'knee': (-160, 20), 'ankle_pitch': (-80, 60), 'ankle_roll': (-45, 45),
        'waist_yaw': (-120, 120), 'shoulder_pitch': (-200, 90), 'shoulder_roll': (-120, 60)}
BODIES = ['base_link', 'torso_link'] + [f'{s}_{b}' for s in 'LR' for b in
                                        ('hip_pitch_link', 'hip_roll_link', 'thigh_link',
                                         'shin_link', 'foot_link', 'shoulder_pitch_link',
                                         'arm_link')]
DEPTH_TOL = 1.0e-3        # m of EXTRA penetration beyond the q=0 baseline
# The ankle is a CLOSED 2-RSU chain modelled here as a serial pitch-then-roll pair: the
# cranks and push rods are rigidly on the shin, so turning the serial ankle drives the foot
# straight into rods that would really have followed it. Any number this sweep prints for
# the ankle is that artifact, not hardware - the ankle range comes from the mechanism
# (docs/71 s8g, docs/76 s12: pitch -50/+30; docs/74: roll +-20, +-15 recommended).
CLOSED_CHAIN = {'ankle_pitch', 'ankle_roll'}
TRUNK = {'base_link', 'torso_link'}
SRC = {'base_link': 'pelvis', 'hip_pitch_link': 'hip_pitch_link',
       'hip_roll_link': 'hip_roll_link', 'thigh_link': 'thigh', 'shin_link': 'shin',
       'foot_link': 'foot', 'torso_link': 'torso',
       'shoulder_pitch_link': 'shoulder_pitch_link', 'arm_link': 'arm'}
# the upper body has no STEP: its pieces come from the STLs the Fusion fetch wrote, split
# back into connected components so a torso frame is many hulls rather than one blob
UPPER_STL = {'torso': ('torso', 'torso_shpitch'), 'shoulder_pitch_link':
             ('shoulder_pitch_link',), 'arm': ('arm',)}
MESHDIR = f'{REPO}/pygmalion_locomotion/assets/pygmalion_v2/meshes'


def build_pieces():
    """Convex pieces per body, in body-local sim frames, from the per-solid CAD meshes."""
    import gmsh
    sys.path.insert(0, f'{REPO}/tools/robot_model')
    from meshes_step import (solid_meshes, ORIGIN, R_SIM, GROUP_BODY, JMC, ANKLE_Z, STEPS)
    gmsh.initialize()
    gmsh.option.setNumber('General.Terminal', 0)
    out = {}

    def add(body, m):
        v = (m.vertices - ORIGIN[body]) @ R_SIM.T / 1000.0
        t = trimesh.Trimesh(v, m.faces, process=True)
        if len(t.faces) >= 4 and t.scale > 1e-4:
            out.setdefault(body, []).append(t)

    for grp, body in GROUP_BODY.items():
        for m, com in solid_meshes(f'{STEPS}/link_{grp}.step', 8.0):
            b = body
            vol = abs(m.volume) / 1000.0 if m.is_watertight else 0.0
            if grp == 'L3_thigh' and 65 < vol < 75 and np.linalg.norm(com - [-123.7, 70.0, -100.2]) < 3:
                b = 'hip_roll_link'
            if grp == 'L5_hip_pitchroll' and 35 < vol < 45 and np.linalg.norm(com - [-56.3, 72.7, 79.8]) < 3:
                b = 'pelvis'
            add(b, m)
    for m, com in solid_meshes(f'{STEPS}/link_L1_ankle_foot.step', 8.0):
        rod = any(np.linalg.norm(com - (np.array(u) + np.array(d)) / 2) < 1.5 for u, d in JMC.values())
        add('shin' if (rod or com[2] > ANKLE_Z + 0.5) else 'foot', m)
    for body, files in UPPER_STL.items():
        for f in files:
            # process=True merges the duplicated STL vertices; without it every triangle
            # is its own connected component and split() returns rubble
            m = trimesh.load(f'{MESHDIR}/{f}.stl', process=True)
            m.merge_vertices()
            for part in m.split(only_watertight=False):
                if len(part.faces) >= 4:
                    out.setdefault(body, []).append(part)
    gmsh.finalize()
    np.savez_compressed(
        PIECES,
        **{f'{b}|{i}|v': h.vertices for b, hs in out.items() for i, h in enumerate(hs)},
        **{f'{b}|{i}|f': h.faces for b, hs in out.items() for i, h in enumerate(hs)})
    print(f'built {sum(len(v) for v in out.values())} solid meshes '
          f'({sum(len(h.faces) for v in out.values() for h in v)} triangles) '
          f'over {len(out)} bodies', flush=True)
    return out


def load_pieces():
    if not os.path.exists(PIECES):
        return build_pieces()
    z = np.load(PIECES)
    out = {}
    for k in z.files:
        if not k.endswith('|v'):
            continue
        b, i, _ = k.split('|')
        out.setdefault(b, []).append(trimesh.Trimesh(z[k], z[f'{b}|{i}|f'], process=False))
    return out


def limb(body):
    """Which limb a body belongs to - the trunk counts as everyone's neighbour."""
    if body in TRUNK:
        return None
    side = body[0] if body[:2] in ('L_', 'R_') else '?'
    kind = 'arm' if ('arm' in body or 'shoulder' in body) else 'leg'
    return f'{kind}_{side}'


def main():
    step = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--step=')), 0.5))
    P = load_pieces()
    m = mujoco.MjModel.from_xml_path(XML)
    d = mujoco.MjData(m)

    # one collision manager, transforms updated in place - rebuilding it per sample costs
    # more than the whole sweep
    cm = trimesh.collision.CollisionManager()
    names = []
    for bn in BODIES:
        key = SRC[bn[2:] if bn[:2] in ('L_', 'R_') else bn]
        for i, h in enumerate(P[key]):
            cm.add_object(f'{bn}#{i}', h)
            names.append((f'{bn}#{i}', bn, i, key))

    pose = {}

    def place():
        for bn in BODIES:
            bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, bn)
            T = np.eye(4)
            T[:3, :3] = d.xmat[bid].reshape(3, 3)
            T[:3, 3] = d.xpos[bid]
            if bn.startswith('R_'):
                M = np.eye(4)
                M[1, 1] = -1
                T = T @ M
            pose[bn] = T
        for nm, bn, i, key in names:
            cm.set_transform(nm, pose[bn])

    def rel(a, b):
        return np.linalg.inv(pose[a]) @ pose[b]

    def depths():
        """{hull pair -> deepest penetration}, cross-body pairs only."""
        hit, nm, data = cm.in_collision_internal(return_names=True, return_data=True)
        out = {}
        if not hit:
            return out
        for c in data:
            a, b = sorted(c.names)
            if a.split('#')[0] == b.split('#')[0]:
                continue
            out[(a, b)] = max(out.get((a, b), 0.0), float(c.depth))
        return out

    def bodies_of(pair):
        return tuple(sorted(x.split('#')[0] for x in pair))

    def moved(bp):
        """Did the swept joint change how these two bodies sit relative to each other?"""
        return np.abs(rel(*bp) - rel0[bp]).max() > 1e-9

    def constrains_joint(pair):
        a, b = bodies_of(pair)
        la, lb = limb(a), limb(b)
        return la is None or lb is None or la == lb

    def set_q(vals):
        d.qpos[:] = 0
        d.qpos[2] = 1.0
        d.qpos[3] = 1.0
        for jn, v in vals.items():
            jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn)
            d.qpos[m.jnt_qposadr[jid]] = np.radians(v)
        mujoco.mj_forward(m, d)
        place()

    set_q({})
    base = depths()
    rel0 = {(a, b): rel(a, b) for a in BODIES for b in BODIES if a < b}
    bp = sorted({bodies_of(p) for p in base})
    print(f'hull pairs overlapping at q=0 (built-in nesting, used as the baseline): '
          f'{len(base)} over {len(bp)} body pairs')
    for p in bp:
        n = [v for k, v in base.items() if bodies_of(k) == p]
        print(f'    {p[0]:22s} <-> {p[1]:22s} {len(n):3d} pairs, deepest '
              f'{max(n) * 1000:5.2f} mm')

    res = {}
    print(f"\n{'joint':15s} {'searched':>14s} {'free (deg)':>18s}   what stops it")
    for j in JOINTS:
        jname = f'{j}_joint' if j in CENTRE else f'L_{j}_joint'
        if mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jname) < 0:
            continue
        lo, hi = SPAN[j]
        found, cross = {}, {}
        for sgn, end in ((+1, hi), (-1, lo)):
            blocked, who, q = None, None, 0.0
            while (q <= end if sgn > 0 else q >= end):
                set_q({jname: q})
                deep = [(p, v) for p, v in depths().items()
                        if v > base.get(p, 0.0) + DEPTH_TOL and moved(bodies_of(p))]
                intra = sorted((p for p, v in deep if constrains_joint(p)))
                if intra:
                    blocked, who = q, bodies_of(intra[0])
                    break
                rest = sorted((p for p, v in deep if not constrains_joint(p)))
                if rest and cross.get(sgn) is None:
                    cross[sgn] = (q, bodies_of(rest[0]))
                q += sgn * step
            found['hi' if sgn > 0 else 'lo'] = (blocked, who)
        hb, hw = found['hi']
        lb, lw = found['lo']
        free = (round(lb + step, 1) if lb is not None else lo,
                round(hb - step, 1) if hb is not None else hi)
        res[j] = dict(searched=[lo, hi], free_deg=list(free),
                      blocked_lo=None if lb is None else round(lb, 1),
                      blocked_hi=None if hb is None else round(hb, 1),
                      blocker_lo=' ~ '.join(lw) if lw else None,
                      blocker_hi=' ~ '.join(hw) if hw else None,
                      cross_limb={('hi' if k > 0 else 'lo'):
                                  dict(deg=round(v[0], 1), pair=' ~ '.join(v[1]))
                                  for k, v in cross.items() if v})
        bl = []
        if lw:
            bl.append(f'{lb:+.1f} {lw[0]}~{lw[1]}')
        if hw:
            bl.append(f'{hb:+.1f} {hw[0]}~{hw[1]}')
        cx = '  '.join(f"cross{'+' if k > 0 else '-'} {v[0]:+.1f} {v[1][0]}~{v[1][1]}"
                       for k, v in cross.items() if v)
        res[j]['closed_chain'] = j in CLOSED_CHAIN
        note = ('  <- CLOSED CHAIN: serial-model artifact, use the mechanism range'
                if j in CLOSED_CHAIN else '')
        print(f'{j:15s} [{lo:5.0f},{hi:5.0f}]  [{free[0]:7.1f},{free[1]:7.1f}]   '
              + ('   '.join(bl) or 'nothing in the searched span')
              + ('   | ' + cx if cx else '') + note)
    # MERGE, never overwrite: re-measuring one joint used to wipe the other eight out of
    # the file, and build_robot.py then silently fell back to inherited ranges for them.
    out = '/home/syaro/pyg_fea/fusion/rom_measured.json'
    prev = json.load(open(out)) if os.path.exists(out) else {}
    prev.update(res)
    json.dump(prev, open(out, 'w'), indent=1)
    print('\n-> /home/syaro/pyg_fea/fusion/rom_measured.json')


if __name__ == '__main__':
    main()
