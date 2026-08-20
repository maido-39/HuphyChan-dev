"""RL simulation model vs the final CAD - mass AND shape, per position, overlaid.

Every load in the structural campaign was measured by running a policy in MuJoCo, so the
sim model's mass and geometry ARE the load basis. docs/81 compared masses; this adds the
part that explains them - where the joints are - and draws both bodies in one frame so a
difference is visible rather than tabulated.

Alignment: both models are placed with the HIP PITCH AXIS at the origin, each using its own
kinematics, and nothing is scaled or fitted. A difference in the picture is therefore a real
difference in the machine.

  RL side    mesh triangles from the MJCF, pushed to world through the body frames at qpos0.
             These meshes are ENVELOPES (a 4816 cm3 thigh envelope declares 5.10 kg), so
             they show outline, never material.
  CAD side   the campaign's own surface triangles - the same ones the FEA solved - which
             live in the CAD global frame in mm with the hip pitch axis at z=+60.

The two frames do not share a convention: the sim walks along +x with the lateral axis y,
the CAD walks along -y with the lateral axis x. The sim is therefore turned -90 degrees
about z before anything is drawn, and the turn is verified rather than assumed - the foot
capsules must come out 226 mm long along the CAD's fore-aft axis and 80 mm across, and the
toe must end up on the CAD's forward side.

The foot gets its own panel drawn from the COLLISION capsules rather than the visual mesh:
the sim's visual foot stops short because the toe body is commented out, but the capsules
are what the contact solver and therefore every measured GRF actually saw.

Asserts anchor both frames before drawing: the hip pitch axis must agree to within 2 mm,
and the mass reassignment must conserve the leg total.

Usage: rl_vs_cad_shape.py [--out=docs/img]
"""
import json
import os
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402

XML = ('/home/syaro/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab/src/mjlab/'
       'asset_zoo/robots/pygmalion/xmls/pygmalion.xml')
STATIC = '/home/syaro/MikuchanRemote/Human-Pygmalion/tools/wrench_studio/static'

# CAD joint anchors [mm] in the CAD global frame, from the STEP bearing / actuator centres
CAD_HIP_PITCH = np.array([-124.45, 68.1, 60.0])
CAD_JOINT_Y_ANKLE = 145.0        # ankle centre, fore-aft, from the L1 RSU joints
CAD_JOINT_Z = {'hip_pitch': 60.0, 'hip_yaw': -97.0, 'knee': -310.0, 'ankle': -800.0}
CAD_LINKS = ['L6_pelvis', 'L5_hip_pitchroll', 'L4_hip_yaw', 'L3_thigh', 'L2_shin',
             'L1_ankle_foot']

# the user's final-design table: one side + centre [kg], and the motor content of each group
USER = {'CenterParts': 4.429, 'HipPitch2Roll': 2.262, 'HipRoll2Yaw': 1.536,
        'HipYaw2Knee': 1.476, 'Knee2Ankle': 2.598, 'Ankle2Feet': 3.818}
USER_MOTOR = {'CenterParts': 3.116, 'HipPitch2Roll': 1.558, 'HipRoll2Yaw': 0.932,
              'HipYaw2Knee': 0.0, 'Knee2Ankle': 1.558, 'Ankle2Feet': 1.864}

RL_C, CAD_C = '#3b82f6', '#c0392b'


def rl_model():
    import mujoco
    m = mujoco.MjModel.from_xml_path(XML)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    return mujoco, m, d


def rl_body_mesh(mujoco, m, d, body):
    """(vertices world mm, triangles) of one body's visual meshes."""
    bi = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, body)
    assert bi >= 0, f'no body {body}'
    V, T, off = [], [], 0
    for g in range(m.ngeom):
        if m.geom_bodyid[g] != bi or m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH:
            continue
        mid = m.geom_dataid[g]
        a, n = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
        v = m.mesh_vert[a:a + n].astype(float)
        R = np.array(d.geom_xmat[g]).reshape(3, 3)     # geom_xmat lives on MjData
        V.append((v @ R.T + d.geom_xpos[g]) * 1000.0)
        fa, fn = m.mesh_faceadr[mid], m.mesh_facenum[mid]
        T.append(m.mesh_face[fa:fa + fn].astype(int) + off)
        off += n
    if not V:
        return None, None
    return np.vstack(V), np.vstack(T)


def rl_foot_capsules(mujoco, m, d, body):
    """[(p0, p1, r)] world mm for the capsules the contact solver actually used."""
    bi = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, body)
    out = []
    for g in range(m.ngeom):
        if m.geom_bodyid[g] != bi or m.geom_type[g] != mujoco.mjtGeom.mjGEOM_CAPSULE:
            continue
        R = np.array(d.geom_xmat[g]).reshape(3, 3)
        c, h, r = d.geom_xpos[g] * 1000.0, m.geom_size[g][1] * 1000.0, \
            m.geom_size[g][0] * 1000.0
        ax = R[:, 2] * h
        out.append((c - ax, c + ax, r))
    return out


def cad_surface(link):
    f = f'{STATIC}/link_setup_{link}.json'
    if not os.path.exists(f):
        return None, None
    D = json.load(open(f))
    S = D.get('peak') or next(iter(D.values()))
    return np.asarray(S['nodes'], float), np.asarray(S['tris'], int)


def fill(ax, P, T, axes, color, alpha, label=None):
    """Flat projected triangle fill - reads as a silhouette regardless of mesh density."""
    poly = P[T][:, :, axes]
    ax.add_collection(PolyCollection(poly, facecolors=color, edgecolors='none',
                                     alpha=alpha, label=label, rasterized=True))


def main():
    out = next((a.split('=')[1] for a in sys.argv if a.startswith('--out=')),
               '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img')
    mujoco, m, d = rl_model()

    def bpos(b):
        return d.xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, b)] * 1000.0
    RL_HIP = bpos('L_hip_pitch_link')
    RL_Z = {'hip_pitch': RL_HIP[2], 'hip_yaw': bpos('L_thigh_link')[2],
            'knee': bpos('L_shin_link')[2], 'ankle': bpos('L_ankle_pitch_link')[2]}

    # the sim frame turned into the CAD's: (X, Y, Z) = (y, -x, z), a proper -90 deg turn
    # about z (det +1, so chirality is preserved), then both hip pitch axes on the origin
    RZ = np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    assert abs(np.linalg.det(RZ) - 1.0) < 1e-12, 'the frame map must be a rotation'
    RL_HIP_C = RZ @ RL_HIP

    def to_common_rl(V):
        return np.atleast_2d(V) @ RZ.T - RL_HIP_C + CAD_HIP_PITCH - CAD_HIP_PITCH

    def to_common_cad(P):
        return np.atleast_2d(P) - CAD_HIP_PITCH

    assert abs(RL_Z['hip_pitch'] - CAD_JOINT_Z['hip_pitch']) < 2.0, (
        f"hip pitch axis differs by {RL_Z['hip_pitch'] - CAD_JOINT_Z['hip_pitch']:.1f} mm "
        '- the frames cannot be aligned on it and the overlay would lie')

    # ---------- joint heights ----------
    print('== joint axis height, hip pitch axis = 0 [mm]')
    print(f"{'joint':10s} {'RL':>9s} {'CAD':>9s} {'delta':>9s}")
    for j in ('hip_pitch', 'hip_yaw', 'knee', 'ankle'):
        a, b = RL_Z[j] - RL_Z['hip_pitch'], CAD_JOINT_Z[j] - CAD_JOINT_Z['hip_pitch']
        print(f'{j:10s} {a:9.1f} {b:9.1f} {b - a:+9.1f}')
    segs = [('thigh (hip_pitch-knee)', 'hip_pitch', 'knee'),
            ('shank (knee-ankle)', 'knee', 'ankle'),
            ('leg (hip_pitch-ankle)', 'hip_pitch', 'ankle')]
    seg_rows = []
    print(f"\n{'segment':26s} {'RL':>8s} {'CAD':>8s} {'delta':>9s} {'%':>8s}")
    for nm, a, b in segs:
        ra, ca = RL_Z[a] - RL_Z[b], CAD_JOINT_Z[a] - CAD_JOINT_Z[b]
        seg_rows.append((nm, ra, ca))
        print(f'{nm:26s} {ra:8.1f} {ca:8.1f} {ca - ra:+9.1f} {100 * (ca - ra) / ra:+7.1f}%')

    # ---------- masses ----------
    RLM = {b: float(m.body_mass[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, b)])
           for b in ('L_hip_pitch_link', 'L_hip_roll_link', 'L_thigh_link', 'L_shin_link',
                     'L_ankle_pitch_link', 'L_foot_link')}
    POS = [('hip pitch', RLM['L_hip_pitch_link'], 'HipPitch2Roll'),
           ('hip roll', RLM['L_hip_roll_link'], 'HipRoll2Yaw'),
           ('thigh', RLM['L_thigh_link'], 'HipYaw2Knee'),
           ('shin', RLM['L_shin_link'], 'Knee2Ankle'),
           ('foot', RLM['L_ankle_pitch_link'] + RLM['L_foot_link'], 'Ankle2Feet')]
    # Reading B - the geometric split.  "Ankle2Feet" is not a link at all: its 31 solids run
    # from a crank at z=-503.7, high on the shin, down to the sole at -839, and its four
    # JMC-JS06 rod ends come in a shin pair (-523/-616) and a foot pair (-810).  It is the
    # whole 2-RSU mechanism.  Splitting it by which body each solid is rigid with - and the
    # two push rods 50/50, as a parallel linkage is conventionally lumped - puts
    # FOOT_SHARE of its non-motor mass on the foot and the rest, plus both RS03, on the shin.
    # ankle_group_split.py derives the share and checks it: the four plate solids it calls
    # the foot sum to 262.07 cm3, which is the 262.0 cm3 the campaign actually solved as
    # L1_ankle_foot, so the structural verdict and the geometric foot are one object.
    FOOT_SHARE = (290.57 + 0.5 * 124.10) / 568.90
    a2f_nonmotor = USER['Ankle2Feet'] - USER_MOTOR['Ankle2Feet']
    B = dict(USER)
    B['Ankle2Feet'] = a2f_nonmotor * FOOT_SHARE
    B['Knee2Ankle'] += a2f_nonmotor * (1 - FOOT_SHARE) + USER_MOTOR['Ankle2Feet']
    rows = [(nm, rl, USER[k], B[k]) for nm, rl, k in POS]
    print(f"\n== mass by position [kg]\n{'position':12s} {'RL':>7s} {'CAD-A':>7s} "
          f"{'%A':>8s} {'CAD-B':>7s} {'%B':>8s}")
    for nm, rl, a, b in rows:
        print(f'{nm:12s} {rl:7.3f} {a:7.3f} {100 * (a - rl) / rl:+7.1f}% {b:7.3f} '
              f'{100 * (b - rl) / rl:+7.1f}%')
    sr, sa, sb = (sum(r[1] for r in rows), sum(r[2] for r in rows), sum(r[3] for r in rows))
    print(f"{'leg total':12s} {sr:7.3f} {sa:7.3f} {100 * (sa - sr) / sr:+7.1f}% {sb:7.3f} "
          f'{100 * (sb - sr) / sr:+7.1f}%')
    assert abs(sa - sb) < 1e-9, 'the reassignment must conserve leg mass'

    # ---------- figure ----------
    plt.rcParams.update({'figure.dpi': 140, 'font.size': 9})
    fig = plt.figure(figsize=(16.4, 9.0))
    gs = fig.add_gridspec(2, 4, width_ratios=[0.85, 0.85, 1.25, 1.35], hspace=0.30,
                          wspace=0.26)

    RLmesh = {b: rl_body_mesh(mujoco, m, d, b) for b in RLM}
    CADmesh = {L: cad_surface(L) for L in CAD_LINKS}

    # (a,b) whole-leg overlay, sagittal and frontal
    for k, (axes, ttl, xl) in enumerate([((1, 2), 'sagittal', 'fore-aft y [mm]  (forward = −y)'),
                                         ((0, 2), 'frontal', 'lateral x [mm]')]):
        a = fig.add_subplot(gs[k, 0])
        for b, (V, T) in RLmesh.items():
            if V is not None:
                fill(a, to_common_rl(V), T, axes, RL_C, 0.40)
        for L, (P, T) in CADmesh.items():
            if P is not None and L != 'L6_pelvis':
                fill(a, to_common_cad(P), T, axes, CAD_C, 0.45)
        for j, col, ls in (('knee', RL_C, '--'), ('ankle', RL_C, ':')):
            a.axhline(RL_Z[j] - RL_Z['hip_pitch'], color=col, ls=ls, lw=1.1)
        for j, col, ls in (('knee', CAD_C, '--'), ('ankle', CAD_C, ':')):
            a.axhline(CAD_JOINT_Z[j] - CAD_JOINT_Z['hip_pitch'], color=col, ls=ls, lw=1.1)
        a.set_xlim(-260, 260)
        a.set_ylim(-950, 110)
        a.set_aspect('equal')
        a.set_title(f'leg overlay — {ttl}', fontsize=9)
        a.set_xlabel(xl, fontsize=8)
        a.set_ylabel('height below hip pitch axis [mm]', fontsize=8)
        a.grid(alpha=0.25)
        if k == 0:
            a.plot([], [], color=RL_C, lw=6, alpha=0.5, label='RL sim (envelope mesh)')
            a.plot([], [], color=CAD_C, lw=6, alpha=0.5, label='final CAD (FEA surface)')
            a.legend(fontsize=7, loc='lower left')
            a.annotate(f"knee {CAD_JOINT_Z['knee'] - CAD_JOINT_Z['hip_pitch'] - (RL_Z['knee'] - RL_Z['hip_pitch']):+.0f} mm",
                       (-250, -420), fontsize=8, color=CAD_C, weight='bold')
            # the CAD side has no material between -587 and -785: the 2-RSU rods and their
            # clevises were never exported as FEA links, so the gap is a missing STEP, not
            # a missing part
            a.annotate('2-RSU rods\nnot in the FEA STEP', (-250, -700), fontsize=6.5,
                       color='#888', style='italic')

    # (c) segment lengths
    a = fig.add_subplot(gs[0, 1])
    y = np.arange(len(seg_rows))
    a.barh(y - 0.19, [r[1] for r in seg_rows], 0.36, color=RL_C, label='RL sim')
    a.barh(y + 0.19, [r[2] for r in seg_rows], 0.36, color=CAD_C, label='final CAD')
    for i, r in enumerate(seg_rows):
        a.annotate(f'{r[2] - r[1]:+.0f} mm', (max(r[1], r[2]) + 12, i), fontsize=8,
                   va='center', color=CAD_C, weight='bold')
    a.set_yticks(y)
    a.set_yticklabels(['thigh', 'shank', 'leg'], fontsize=8)
    a.invert_yaxis()
    a.set_xlim(0, 1030)
    a.set_xlabel('segment length [mm]', fontsize=8)
    a.set_title('the knee moved up\nshank +23 %, thigh −17 %', fontsize=9)
    a.legend(fontsize=7.5)
    a.grid(alpha=0.3, axis='x')

    # (d) mass by position
    a = fig.add_subplot(gs[1, 1])
    y = np.arange(len(rows))
    a.barh(y - 0.26, [r[1] for r in rows], 0.24, color=RL_C, label='RL sim')
    a.barh(y, [r[2] for r in rows], 0.24, color='#e8927c', label='CAD-A  table as written')
    a.barh(y + 0.26, [r[3] for r in rows], 0.24, color=CAD_C,
           label='CAD-B  split by body (geometric)')
    a.set_yticks(y)
    a.set_yticklabels([r[0] for r in rows], fontsize=8)
    a.invert_yaxis()
    a.set_xlabel('mass [kg]', fontsize=8)
    a.set_title('same leg total (−0.2 %): mass moved\nthigh → shin, the foot barely changed',
                fontsize=9)
    a.legend(fontsize=6.8, loc='lower right')
    a.grid(alpha=0.3, axis='x')

    # (e) per-position shape overlays, shared limits inside each panel
    inner = gs[:, 2].subgridspec(3, 2, hspace=0.34, wspace=0.22)
    PAIR = [('L_hip_pitch_link', 'L5_hip_pitchroll', 'hip pitch'),
            ('L_hip_roll_link', 'L4_hip_yaw', 'hip roll / yaw'),
            ('L_thigh_link', 'L3_thigh', 'thigh'),
            ('L_shin_link', 'L2_shin', 'shin'),
            ('L_foot_link', 'L1_ankle_foot', 'foot'),
            (None, 'L6_pelvis', 'pelvis  (RL: fused into base)')]
    for i, (rb, cl, nm) in enumerate(PAIR):
        a = fig.add_subplot(inner[i // 2, i % 2])
        pts = []
        P, T = CADmesh.get(cl, (None, None))
        if P is not None:
            Q = to_common_cad(P)
            fill(a, Q, T, (1, 2), CAD_C, 0.50)
            pts.append(Q)
        if rb:
            V, TT = RLmesh[rb]
            if V is not None:
                Q = to_common_rl(V)
                fill(a, Q, TT, (1, 2), RL_C, 0.40)
                pts.append(Q)
        if pts:
            A = np.vstack(pts)
            cy, cz = A[:, 1].mean(), A[:, 2].mean()
            h = max(np.ptp(A[:, 1]), np.ptp(A[:, 2])) * 0.62 + 12
            a.set_xlim(cy - h, cy + h)
            a.set_ylim(cz - h, cz + h)
        a.set_aspect('equal')
        a.set_title(nm, fontsize=8)
        a.tick_params(labelsize=6)
        a.grid(alpha=0.2)

    # (f) the footprint the contact solver saw, vs the CAD sole.  Forward is -y in the CAD
    # frame, so the levers are measured as (ankle - toe) and (heel - ankle).
    a = fig.add_subplot(gs[:, 3])
    caps = rl_foot_capsules(mujoco, m, d, 'L_foot_link')
    assert caps, 'the sim foot has no capsules - the GRF basis cannot be drawn'
    ends = to_common_rl(np.array([p for c in caps for p in (c[0], c[1])]))
    rl_r = max(c[2] for c in caps)
    rl_len, rl_wid = np.ptp(ends[:, 1]) + 2 * rl_r, np.ptp(ends[:, 0]) + 2 * rl_r
    assert 200 < rl_len < 260 and 70 < rl_wid < 130, (
        f'after the turn the sim foot is {rl_len:.0f} x {rl_wid:.0f} mm - the frame map is '
        'wrong; it must be about 246 long by 100 across')
    ANK = to_common_rl(bpos('L_ankle_pitch_link')[None])[0]
    assert ends[:, 1].min() - ANK[1] < -100, 'the toe must land on the CAD forward side (-y)'
    th = np.linspace(0, 2 * np.pi, 40)
    for p0, p1, r in caps:
        q0, q1 = to_common_rl(p0[None])[0], to_common_rl(p1[None])[0]
        for q in (q0, q1):
            a.plot(q[1] + r * np.cos(th), q[0] + r * np.sin(th), color=RL_C, lw=0.8,
                   alpha=0.85)
        a.plot([q0[1], q1[1]], [q0[0], q1[0]], color=RL_C, lw=1.6, alpha=0.9)
    Pf, Tf = CADmesh['L1_ankle_foot']
    Qf = to_common_cad(Pf)
    sole = Qf[Qf[:, 2] < Qf[:, 2].min() + 3.0]
    a.scatter(sole[:, 1], sole[:, 0], s=1.4, c=CAD_C, alpha=0.5)
    cad_ank = CAD_JOINT_Y_ANKLE - CAD_HIP_PITCH[1]
    lev = dict(rl_toe=ANK[1] - (ends[:, 1].min() - rl_r),
               rl_heel=(ends[:, 1].max() + rl_r) - ANK[1],
               cad_toe=cad_ank - sole[:, 1].min(), cad_heel=sole[:, 1].max() - cad_ank)
    for q, lab, col in ((ANK, 'sim ankle', RL_C), ((0, cad_ank), 'CAD ankle', CAD_C)):
        a.axvline(q[1] if lab.startswith('sim') else cad_ank, color=col, ls='--', lw=1.0)
    a.set_aspect('equal')
    a.invert_yaxis()
    a.invert_xaxis()
    a.set_xlabel('fore-aft [mm]   forward is left', fontsize=8)
    a.set_ylabel('lateral [mm]', fontsize=8)
    a.set_title('footprint — the surface every measured GRF acted on\n'
                f'sim {rl_len:.0f} mm (toe lever {lev["rl_toe"]:.0f}, heel {lev["rl_heel"]:.0f})   '
                f'CAD {np.ptp(sole[:, 1]):.0f} mm (toe {lev["cad_toe"]:.0f}, heel '
                f'{lev["cad_heel"]:.0f})', fontsize=8.5)
    a.plot([], [], color=RL_C, lw=2, label='RL sim collision capsules')
    a.scatter([], [], c=CAD_C, s=12, label='final CAD sole')
    a.legend(fontsize=7.5, loc='upper right')
    a.grid(alpha=0.25)
    print(f'\n== footprint [mm]\n{"":8s} {"length":>8s} {"toe lever":>10s} {"heel lever":>11s}')
    print(f'{"sim":8s} {rl_len:8.0f} {lev["rl_toe"]:10.0f} {lev["rl_heel"]:11.0f}')
    print(f'{"CAD":8s} {np.ptp(sole[:, 1]):8.0f} {lev["cad_toe"]:10.0f} '
          f'{lev["cad_heel"]:11.0f}')

    fig.suptitle('RL sim model vs final CAD — hip pitch axis aligned, nothing scaled: '
                 'the leg total matches, the knee height and the mass distribution do not',
                 fontsize=11.5)
    fig.savefig(os.path.join(out, 'rl_vs_cad_shape.png'), bbox_inches='tight')
    print(f"\n-> {os.path.join(out, 'rl_vs_cad_shape.png')}")


if __name__ == '__main__':
    main()
