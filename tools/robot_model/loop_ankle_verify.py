"""Does the closed-loop 2-RSU ankle do what the real one does? Plain-MuJoCo checks + videos.

Checks (left leg, shin welded to the world so only the ankle moves):
  1. closure      |rod end - foot ball| stays ~0 through every motion (the connect holds)
  2. transmission crank (A, B) -> foot (pitch, roll): a grid sweep, the map, and the lever
                  ratio at the centre (CAD / docs/74 expectation ~1.25 pitch per crank)
  3. reach        can the cranks put the foot at pitch -50/+30 and roll +-20 (the design
                  ROM) - the crank angles that is needed, and closure error there
  4. ground       shin held 0.47 m up, foot on a plane under gravity: with cranks held the
                  sole must settle flat (4 box-corner contacts), and modulating the cranks
                  must pitch/roll the foot against the ground without the loop coming apart
Videos (no GL here: mesh projection with matplotlib, stitched with ffmpeg):
  docs/video/loop_ankle_pitch.mp4    both cranks together  -> foot pitches
  docs/video/loop_ankle_roll.mp4     cranks in opposition   -> foot rolls
  docs/video/loop_ankle_ground.mp4   foot on the floor, cranks modulated, contacts drawn
Usage: loop_ankle_verify.py [--tag=pygmalion_v3_printed_loop] [--fast]   (mjlab .venv python)
"""
import json
import os
import subprocess
import sys

import numpy as np
import mujoco

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
XMLS = f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls'
IMG = f'{REPO}/docs/img'
VID = f'{REPO}/docs/video'
KP, KD = 22.3, 1.41            # crank servo: ankle 28.5/1.81 mapped through the 1.25 lever (docs/90)
DT = 0.001


def load(tag, weld_shin=True, floor=False):
    spec = mujoco.MjSpec.from_file(f'{XMLS}/{tag}.xml')
    if floor:
        spec.worldbody.add_geom(name='floor', type=mujoco.mjtGeom.mjGEOM_PLANE, size=[2, 2, 0.1],
                                rgba=[0.8, 0.8, 0.8, 1])
        spec.option.gravity[:] = [0, 0, -9.81]
    if weld_shin:
        # the weld is taken at the compile pose (qpos0), so put the base at the home height
        # FIRST - otherwise home() lifts the robot and the weld drags the shin back to z~-0.5
        # (first video frames showed the leg, later ones empty: 2026-08-23). No gravity when
        # hanging: the rest of the robot would swing from the free knee.
        spec.body('base_link').pos[2] = 1.5
        spec.option.gravity[:] = [0, 0, 0]
        w = spec.add_equality()
        w.type = mujoco.mjtEq.mjEQ_WELD
        w.objtype = mujoco.mjtObj.mjOBJ_BODY
        w.name1 = 'L_shin_link'
        w.name = 'hold_shin'
    for t in 'AB':                      # crank servos, like the RS03 position loop
        a = spec.add_actuator()
        a.name = f'L_crank_{t}_servo'
        a.trntype = mujoco.mjtTrn.mjTRN_JOINT
        a.target = f'L_crank_{t}_joint'
        a.gaintype = mujoco.mjtGain.mjGAIN_FIXED
        a.biastype = mujoco.mjtBias.mjBIAS_AFFINE
        a.gainprm[0] = KP
        a.biasprm[1] = -KP
        a.biasprm[2] = -KD
        a.forcerange[:] = [-60, 60]
        a.forcelimited = True
    spec.option.timestep = DT
    m = spec.compile()
    return m


def home(m, d, base_z=1.5):
    d.qpos[:] = m.qpos0
    d.qpos[2] = base_z
    mujoco.mj_forward(m, d)


def jid(m, n):
    return m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, n)]


def closure_err(m, d, s='L'):
    return max(np.linalg.norm(d.site_xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, f'{s}_rod_{t}_end')]
                              - d.site_xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, f'{s}_ball_{t}')]) for t in 'AB')


def settle(m, d, cA, cB, steps=600):
    """Ramp the crank targets over the first half, hold, return the ankle angles."""
    aA = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, 'L_crank_A_servo')
    aB = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, 'L_crank_B_servo')
    c0 = np.array([d.ctrl[aA], d.ctrl[aB]])
    for k in range(steps):
        f = min(1.0, k / (steps / 2))
        d.ctrl[aA], d.ctrl[aB] = c0 + f * (np.array([cA, cB]) - c0)
        mujoco.mj_step(m, d)
    return (np.degrees(d.qpos[jid(m, 'L_ankle_pitch_joint')]),
            np.degrees(d.qpos[jid(m, 'L_ankle_roll_joint')]),
            np.degrees(d.qpos[jid(m, 'L_crank_A_joint')]), np.degrees(d.qpos[jid(m, 'L_crank_B_joint')]))


# ---------------------------------------------------------------- drawing --
def frame(m, d, ax, bodies, view='side', every=3, contacts=True, title=''):
    from matplotlib.collections import PolyCollection
    import matplotlib.pyplot as plt
    polys, cols, dep = [], [], []
    cm = plt.get_cmap('tab20')
    for g in range(m.ngeom):
        bn = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, m.geom_bodyid[g])
        if bn not in bodies or m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH or m.geom_group[g] != 2:
            continue
        mid = m.geom_dataid[g]
        V = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]]
        F = m.mesh_face[m.mesh_faceadr[mid]:m.mesh_faceadr[mid] + m.mesh_facenum[mid]][::every]
        R = d.geom_xmat[g].reshape(3, 3)
        W = V @ R.T + d.geom_xpos[g]
        P = W[:, [0, 2]] if view == 'side' else W[:, [1, 2]]
        depth = W[:, 1] if view == 'side' else -W[:, 0]
        n = np.cross(W[F[:, 1]] - W[F[:, 0]], W[F[:, 2]] - W[F[:, 0]])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        lam = np.clip(0.35 + 0.65 * np.abs(n @ np.array([0.3, -0.8, 0.5])), 0, 1)
        base = np.array(cm(m.geom_bodyid[g] % 20)[:3])
        polys.append(P[F])
        cols.append(np.clip(base * lam[:, None], 0, 1))
        dep.append(depth[F].mean(1))
    P = np.vstack(polys)
    C = np.vstack(cols)
    o = np.argsort(np.concatenate(dep))
    ax.add_collection(PolyCollection(P[o], facecolors=C[o], edgecolors='none', rasterized=True))
    # the loop: rod end sites and foot balls
    for s_ in ('L_rod_A_end', 'L_rod_B_end'):
        p = d.site_xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, s_)]
        ax.plot(p[0] if view == 'side' else p[1], p[2], 'o', color='red', ms=4)
    if contacts:
        for i in range(d.ncon):
            c = d.contact[i]
            if 'floor' not in (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, c.geom1) or '',
                               mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, c.geom2) or ''):
                continue
            f = np.zeros(6)
            mujoco.mj_contactForce(m, d, i, f)
            p = c.pos
            ax.plot(p[0] if view == 'side' else p[1], p[2], '^', color='lime', ms=6 + min(f[0] / 30, 8))
    ax.set_aspect('equal')
    ax.set_title(title, fontsize=9)


def video(name, frames_fn, n, fps=25):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    os.makedirs(f'{VID}/_frames_{name}', exist_ok=True)
    for k in range(n):
        fig, axes = plt.subplots(1, 2, figsize=(9, 4.6), dpi=90)
        frames_fn(k, axes)
        fig.tight_layout()
        fig.savefig(f'{VID}/_frames_{name}/{k:04d}.png')
        plt.close(fig)
    out = f'{VID}/{name}.mp4'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(fps),
                    '-i', f'{VID}/_frames_{name}/%04d.png', '-pix_fmt', 'yuv420p',
                    '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', out], check=True)
    subprocess.run(['rm', '-r', f'{VID}/_frames_{name}'])
    print(f'-> {out}')


def main():
    tag = next((a.split('=')[1] for a in sys.argv if a.startswith('--tag=')), 'pygmalion_v3_printed_loop')
    fast = '--fast' in sys.argv
    os.makedirs(VID, exist_ok=True)
    rep = {}
    LEG = {'L_shin_link', 'L_ankle_pitch_link', 'L_foot_link', 'L_crank_A', 'L_crank_B', 'L_rod_A', 'L_rod_B'}

    # ---- 1+2: transmission map on a crank grid (shin welded, no floor) ----
    m = load(tag, weld_shin=True)
    d = mujoco.MjData(m)
    home(m, d)
    grid = np.radians(np.arange(-40, 41, 10 if fast else 5))
    T = {}
    worst = 0.0
    for cA in grid:
        for cB in grid:
            home(m, d)
            p, r, a, b = settle(m, d, cA, cB, 500)
            e = closure_err(m, d)
            worst = max(worst, e)
            T[(round(np.degrees(cA)), round(np.degrees(cB)))] = (p, r, a, b, e)
    rep['closure_worst_mm'] = worst * 1000
    # lever ratio at the centre: both cranks +-10 deg
    pP = T[(10, 10)][0] - T[(-10, -10)][0]
    rR = T[(10, -10)][1] - T[(-10, 10)][1]
    rep['pitch_per_crank_deg'] = pP / 20.0
    rep['roll_per_crank_diff_deg'] = rR / 20.0
    print(f'closure worst over the {len(T)}-point grid: {worst * 1000:.3f} mm')
    print(f'transmission at the centre: pitch/crank(common) = {pP / 20:.3f}, roll/crank(differential) = {rR / 20:.3f}')
    # did any target fail to track (crank not at target -> linkage jam / singularity)?
    jam = [(k, v) for k, v in T.items() if abs(v[2] - k[0]) > 3 or abs(v[3] - k[1]) > 3]
    print(f'crank targets not reached within 3 deg (jam/singular/limit): {len(jam)}')
    for k, v in jam[:8]:
        print(f'   target A{k[0]:+d} B{k[1]:+d} -> got A{v[2]:+.1f} B{v[3]:+.1f}  (pitch {v[0]:+.1f} roll {v[1]:+.1f})')
    rep['jams'] = [(list(k), [round(float(x), 2) for x in v]) for k, v in jam]

    # ---- 3: reach the design ROM corners ----
    print('\nreach (crank angles that put the foot at the design ROM):')
    reach = {}
    for lab, (tp, tr) in (('pitch -50', (-50, 0)), ('pitch +30', (30, 0)), ('roll -20', (0, -20)),
                          ('roll +20', (0, 20)), ('pitch -50 & roll +20', (-50, 20)), ('pitch +30 & roll -20', (30, -20))):
        # invert the map numerically: nearest grid point then refine with a few PD settles
        best = min(T.items(), key=lambda kv: (kv[1][0] - tp) ** 2 + (kv[1][1] - tr) ** 2)
        cA, cB = np.radians(best[0])
        home(m, d)
        for _ in range(6):
            p, r, a, b = settle(m, d, cA, cB, 400)
            # Jacobian from the local map (finite differences on the grid spacing)
            J = np.array([[rep['pitch_per_crank_deg'] / 2, rep['pitch_per_crank_deg'] / 2],
                          [rep['roll_per_crank_diff_deg'] / 2, -rep['roll_per_crank_diff_deg'] / 2]])
            dc = np.linalg.solve(J, np.array([tp - p, tr - r]))
            cA += np.radians(np.clip(dc[0], -8, 8))
            cB += np.radians(np.clip(dc[1], -8, 8))
        p, r, a, b = settle(m, d, cA, cB, 400)
        e = closure_err(m, d)
        ok = abs(p - tp) < 2 and abs(r - tr) < 2
        reach[lab] = dict(target=[tp, tr], got=[round(p, 1), round(r, 1)], cranks=[round(a, 1), round(b, 1)],
                          closure_mm=round(e * 1000, 3), reached=bool(ok))
        print(f"  {lab:22s} -> pitch {p:+6.1f} roll {r:+6.1f}  cranks A {a:+6.1f} B {b:+6.1f}  closure {e * 1000:.3f} mm  {'OK' if ok else 'NOT REACHED'}")
    rep['reach'] = reach

    # ---- 4: on the ground ----
    mg = load(tag, weld_shin=True, floor=True)
    dg = mujoco.MjData(mg)
    home(mg, dg, base_z=1.0)
    # put the sole ~1 mm above the floor: the shin is welded where it is at home, so raise
    # the whole robot so the foot box bottom sits at z = +0.001 (box bottom = ankle - 0.043)
    fid = mujoco.mj_name2id(mg, mujoco.mjtObj.mjOBJ_BODY, 'L_foot_link')
    dg.qpos[2] += 0.001 + 0.043 - dg.xpos[fid][2]
    mujoco.mj_forward(mg, dg)
    # re-weld at this pose: the weld equality stored the pose at compile time, so rebuild
    mg = load(tag, weld_shin=False, floor=True)
    dg2 = mujoco.MjData(mg)
    dg2.qpos[:] = dg.qpos
    mujoco.mj_forward(mg, dg2)
    spec = mujoco.MjSpec.from_file(f'{XMLS}/{tag}.xml')
    # simpler: freeze the free joint instead of welding - hold base with a stiff spring
    mg.body_gravcomp[:] = 0
    mocap = None
    # hold base_link by pinning the free joint with a strong PD each step
    qb = dg2.qpos[:7].copy()
    ground_log = []
    for k in range(3000):
        cA = np.radians(12 * np.sin(2 * np.pi * k / 1500)) if k > 800 else 0.0
        cB = np.radians(12 * np.sin(2 * np.pi * k / 1500)) if k > 800 else 0.0
        if 2200 < k:
            cB = -cA                                    # roll against the ground
        for t, c in (('A', cA), ('B', cB)):
            dg2.ctrl[mujoco.mj_name2id(mg, mujoco.mjtObj.mjOBJ_ACTUATOR, f'L_crank_{t}_servo')] = c
        # pin the base: overwrite its free-joint state (a kinematic hold)
        dg2.qpos[:7] = qb
        dg2.qvel[:6] = 0
        mujoco.mj_step(mg, dg2)
        if k % 10 == 0:
            nf = sum(1 for i in range(dg2.ncon) if 'floor' in (mujoco.mj_id2name(mg, mujoco.mjtObj.mjOBJ_GEOM, dg2.contact[i].geom1) or '',
                                                                mujoco.mj_id2name(mg, mujoco.mjtObj.mjOBJ_GEOM, dg2.contact[i].geom2) or ''))
            fz = 0.0
            for i in range(dg2.ncon):
                f = np.zeros(6)
                mujoco.mj_contactForce(mg, dg2, i, f)
                fz += f[0]
            ground_log.append((k * DT, nf, fz, closure_err(mg, dg2) * 1000,
                               np.degrees(dg2.qpos[jid(mg, 'L_ankle_pitch_joint')]), np.degrees(dg2.qpos[jid(mg, 'L_ankle_roll_joint')])))
    gl = np.array(ground_log)
    print(f'\nground: contacts with the floor over time: min {int(gl[:, 1].min())} max {int(gl[:, 1].max())}  '
          f'normal force {gl[:, 2].min():.0f}..{gl[:, 2].max():.0f} N  closure worst {gl[:, 3].max():.3f} mm  '
          f'pitch {gl[:, 4].min():+.1f}..{gl[:, 4].max():+.1f}  roll {gl[:, 5].min():+.1f}..{gl[:, 5].max():+.1f} deg')
    rep['ground'] = dict(contacts_min=int(gl[:, 1].min()), contacts_max=int(gl[:, 1].max()),
                         fz_range=[float(gl[:, 2].min()), float(gl[:, 2].max())], closure_worst_mm=float(gl[:, 3].max()))
    json.dump(rep, open(f'{REPO}/tools/robot_model/loop_ankle_verify.json', 'w'), indent=1)

    # ---- figure: transmission map ----
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    g = np.degrees(grid)
    Pm = np.array([[T[(round(a), round(b))][0] for b in g] for a in g])
    Rm = np.array([[T[(round(a), round(b))][1] for b in g] for a in g])
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.6))
    for a_, Z, t in ((ax[0], Pm, 'foot pitch [deg]'), (ax[1], Rm, 'foot roll [deg]')):
        im = a_.imshow(Z, origin='lower', extent=[g[0], g[-1], g[0], g[-1]], cmap='coolwarm', aspect='equal')
        cs = a_.contour(g, g, Z, levels=10, colors='k', linewidths=0.5)
        a_.clabel(cs, fontsize=7, fmt='%d')
        a_.set_xlabel('crank B [deg]')
        a_.set_ylabel('crank A [deg]')
        a_.set_title(f'{t}  (closure worst {worst * 1000:.3f} mm)', fontsize=10)
        plt.colorbar(im, ax=a_, shrink=0.8)
    fig.suptitle('2-RSU ankle in MuJoCo: crank angles -> passive foot angles (shin welded, PD on the cranks)', fontsize=10.5)
    fig.tight_layout()
    fig.savefig(f'{IMG}/loop_ankle_transmission.png', dpi=130)
    print(f'-> {IMG}/loop_ankle_transmission.png')

    # ---- videos ----
    NF = 60 if fast else 120
    def sweep_video(name, mode):
        m = load(tag, weld_shin=True)
        d = mujoco.MjData(m)
        home(m, d)
        aA = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, 'L_crank_A_servo')
        aB = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, 'L_crank_B_servo')
        steps_per_frame = 40
        def fr(k, axes):
            ph = 2 * np.pi * k / NF
            cA = np.radians(30 * np.sin(ph))
            cB = cA if mode == 'pitch' else -cA
            for _ in range(steps_per_frame):
                d.ctrl[aA], d.ctrl[aB] = cA, cB
                mujoco.mj_step(m, d)
            p = np.degrees(d.qpos[jid(m, 'L_ankle_pitch_joint')]); r = np.degrees(d.qpos[jid(m, 'L_ankle_roll_joint')])
            ttl = f'crank A {np.degrees(cA):+5.1f}  B {np.degrees(cB):+5.1f} deg  ->  foot pitch {p:+5.1f}  roll {r:+5.1f}   closure {closure_err(m, d) * 1000:.2f} mm'
            frame(m, d, axes[0], LEG, 'side', title='side view (x-z)')
            frame(m, d, axes[1], LEG, 'front', title='front view (y-z)')
            axes[0].text(0.01, 0.98, ttl, transform=axes[0].transAxes, fontsize=7.5, va='top')
            for a_ in axes:
                a_.set_xlim(-0.35, 0.35); a_.set_ylim(0.45, 1.25)
        video(name, fr, NF)
    sweep_video('loop_ankle_pitch', 'pitch')
    sweep_video('loop_ankle_roll', 'roll')

    def ground_video(name):
        m = load(tag, weld_shin=False, floor=True)
        d = mujoco.MjData(m)
        d.qpos[:] = dg2.qpos
        d.qpos[:7] = qb
        mujoco.mj_forward(m, d)
        aA = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, 'L_crank_A_servo')
        aB = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, 'L_crank_B_servo')
        def fr(k, axes):
            for s_ in range(25):
                kk = k * 25 + s_
                cA = np.radians(12 * np.sin(2 * np.pi * kk / 1500)) if kk > 800 else 0.0
                cB = (-cA if kk > 2200 else cA)
                d.ctrl[aA], d.ctrl[aB] = cA, cB
                d.qpos[:7] = qb
                d.qvel[:6] = 0
                mujoco.mj_step(m, d)
            nf = sum(1 for i in range(d.ncon) if 'floor' in (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, d.contact[i].geom1) or '',
                                                              mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, d.contact[i].geom2) or ''))
            p = np.degrees(d.qpos[jid(m, 'L_ankle_pitch_joint')]); r = np.degrees(d.qpos[jid(m, 'L_ankle_roll_joint')])
            ttl = f't={k * 25 * DT:4.2f}s  crank A {np.degrees(d.ctrl[aA]):+5.1f} B {np.degrees(d.ctrl[aB]):+5.1f}  foot pitch {p:+5.1f} roll {r:+5.1f}  floor contacts {nf}  closure {closure_err(m, d) * 1000:.2f} mm'
            frame(m, d, axes[0], LEG, 'side', title='side view - green = floor contact (size ~ force)')
            frame(m, d, axes[1], LEG, 'front', title='front view')
            axes[0].text(0.01, 0.98, ttl, transform=axes[0].transAxes, fontsize=7, va='top')
            for a_ in axes:
                a_.axhline(0, color='k', lw=1)
                a_.set_xlim(-0.35, 0.35); a_.set_ylim(-0.05, 0.75)
        video(name, fr, 120)
    ground_video('loop_ankle_ground')


if __name__ == '__main__':
    main()
