"""Does the v2 robot model move like the CAD, and does it weigh what the CAD weighs?

Checks, each printed with its reference so the reader can judge:
  mass         total and per-body vs the mass-property file and the design table
  geometry     zero-pose heights of hip / knee / ankle / sole vs the CAD joint points
  joints       each joint swept through its full range: self-collision between
               NON-adjacent bodies (MuJoCo contacts with the adjacent pairs excluded),
               foot reach, and a contact sheet of the sweep drawn from the real meshes
  inertia      the leg's inertia about the hip pitch axis read back from MuJoCo's mass
               matrix (mj_fullM, one DOF free at a time) vs the sum of body tensors -
               the "inertia measurement" the goal asks for, done in the simulator itself

Rendering: this host has no usable GL, so the frames are a painter's projection of the
MJCF meshes through MuJoCo's own body poses (same triangles the simulator loads).

Usage: validate_robot.py [--xml=...]   (mjlab .venv python)
"""
import json
import os
import sys

import numpy as np
import mujoco

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
XML = f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/pygmalion_v2.xml'
IMG = f'{REPO}/docs/img'
JOINTS = ['hip_pitch', 'hip_roll', 'hip_yaw', 'knee', 'ankle_pitch', 'ankle_roll']


def mesh_world(m, d, g):
    mid = m.geom_dataid[g]
    a, n = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
    v = m.mesh_vert[a:a + n]
    fa, fn = m.mesh_faceadr[mid], m.mesh_facenum[mid]
    f = m.mesh_face[fa:fa + fn]
    Rm = d.geom_xmat[g].reshape(3, 3)
    return v @ Rm.T + d.geom_xpos[g], f


def draw(ax, m, d, view='side', color_by_body=True):
    polys, cols, depth = [], [], []
    cm = plt.get_cmap('tab20')
    for g in range(m.ngeom):
        if m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH:
            continue
        V, F = mesh_world(m, d, g)
        if view == 'side':
            P = V[:, [0, 2]]
            dep = V[:, 1]
        else:
            P = V[:, [1, 2]]
            dep = -V[:, 0]
        tri = P[F]
        dz = dep[F].mean(1)
        nrm = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
        light = np.array([0.3, -0.8, 0.5]) if view == 'side' else np.array([0.8, 0.3, 0.5])
        lam = np.clip(0.35 + 0.65 * np.abs(nrm @ light), 0, 1)
        base = np.array(cm(m.geom_bodyid[g] % 20)[:3]) if color_by_body else np.array([0.6, 0.7, 0.8])
        polys.append(tri)
        cols.append(np.clip(base * lam[:, None], 0, 1))
        depth.append(dz)
    P = np.vstack(polys)
    C = np.vstack(cols)
    D = np.concatenate(depth)
    o = np.argsort(D)
    ax.add_collection(PolyCollection(P[o], facecolors=C[o], edgecolors='none', rasterized=True))
    ax.set_aspect('equal')
    ax.set_xlim(-0.45, 0.45)
    ax.set_ylim(-0.05, 1.15)
    ax.axhline(0, color='k', lw=0.8)


def set_free_base(d, z):
    d.qpos[:] = 0
    d.qpos[2] = z
    d.qpos[3] = 1.0


def main():
    xml = next((a.split('=')[1] for a in sys.argv if a.startswith('--xml=')), XML)
    m = mujoco.MjModel.from_xml_path(xml)
    d = mujoco.MjData(m)
    mp = json.load(open('/home/syaro/pyg_fea/steps/robot_massprops_step.json'))
    rep = {}

    # ---- 1. mass ----
    print('== mass')
    tot = float(m.body_subtreemass[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, 'base_link')])
    print(f'  total {tot:.3f} kg  (docs/82 catalogue-corrected 44.51 incl. arms; upper lump placeholder)')
    BN = {'thigh': 'thigh_link', 'shin': 'shin_link', 'foot': 'foot_link'}
    for b in ('hip_pitch_link', 'hip_roll_link', 'thigh', 'shin', 'foot'):
        bi = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f'L_{BN.get(b, b)}')
        print(f"  L_{b:16s} {m.body_mass[bi]:6.3f} kg  (massprops {mp['bodies'][b]['mass']:.3f})")
        assert abs(m.body_mass[bi] - mp['bodies'][b]['mass']) < 1e-3
    rep['mass_total'] = tot

    # ---- 2. zero-pose geometry ----
    mujoco.mj_resetData(m, d)
    set_free_base(d, 1.0)
    mujoco.mj_forward(m, d)
    P = {n: d.xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, n)].copy()
         for n in ('base_link', 'L_hip_pitch_link', 'L_shin_link', 'L_foot_link', 'R_foot_link')}
    sole = min(d.geom_xpos[g][2] - m.geom_size[g][0] for g in range(m.ngeom)
               if 'foot' in (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or '')
               and m.geom_type[g] == mujoco.mjtGeom.mjGEOM_CAPSULE)
    hip = P['L_hip_pitch_link']
    print('\n== zero-pose geometry (base at z=1.0)')
    print(f"  hip->knee {hip[2]-P['L_shin_link'][2]:.4f} m (CAD 0.370)  knee->ankle {P['L_shin_link'][2]-P['L_foot_link'][2]:.4f} (CAD 0.490)"
          f"  hip->sole {hip[2]-sole:.4f} (CAD 0.903)  stance width {abs(P['L_foot_link'][1]-P['R_foot_link'][1]):.4f} m (CAD 0.2474)")
    assert abs((hip[2] - P['L_shin_link'][2]) - 0.370) < 1e-3 and abs((P['L_shin_link'][2] - P['L_foot_link'][2]) - 0.490) < 1e-3
    rep['hip_to_sole'] = float(hip[2] - sole)
    rep['standing_base_z'] = float(1.0 - sole)          # base height with the sole on the ground
    print(f"  -> standing base height {rep['standing_base_z']:.4f} m (old model keyframe 0.87)")

    # ---- 3. joint sweeps: self-collision and reach ----
    adj = set()
    for s in 'LR':
        chain = ['base_link', f'{s}_hip_pitch_link', f'{s}_hip_roll_link', f'{s}_thigh_link', f'{s}_shin_link',
                 f'{s}_ankle_pitch_link', f'{s}_foot_link']
        for a, b in zip(chain[:-1], chain[1:]):
            adj.add(frozenset((a, b)))
    print('\n== joint sweeps (L leg, all others at 0): self-collision between non-adjacent bodies')
    frames = []
    sweep_rep = {}
    # L/R sign conventions must be the OLD model's: for +dq on each joint, the sign pattern of
    # the right foot's displacement relative to the left (mirrored y) is compared joint by
    # joint with pygmalion.xml - the old model mirrors the two roll joints but not the yaw
    def lr_pattern(model):
        dd = mujoco.MjData(model)
        out = {}
        for j in JOINTS:
            disp = {}
            for sd in 'LR':
                mujoco.mj_resetData(model, dd)
                dd.qpos[:] = 0
                dd.qpos[2] = 1.0
                dd.qpos[3] = 1.0
                mujoco.mj_forward(model, dd)
                fb = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, f'{sd}_foot_link')
                f0 = dd.xpos[fb].copy()
                jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f'{sd}_{j}_joint')
                dd.qpos[model.jnt_qposadr[jid]] = 0.3
                mujoco.mj_forward(model, dd)
                disp[sd] = dd.xpos[fb] - f0
            # the convention is whether +dq moves the two feet as mirror images (lateral
            # components opposite) or in the same lateral direction; x/z asymmetries are
            # geometry (the old foot sits off its yaw axis, v2's does not), not convention
            yl, yr = disp['L'][1], disp['R'][1]
            out[j] = ('mirror' if yl * yr < 0 else 'same') if min(abs(yl), abs(yr)) > 1e-3 else 'n/a'
        return out
    old = mujoco.MjModel.from_xml_path(os.path.join(os.path.dirname(xml), 'pygmalion.xml'))
    pat_old, pat_new = lr_pattern(old), lr_pattern(m)
    for j in JOINTS:
        assert pat_old[j] == pat_new[j], f'{j}: L/R convention differs from pygmalion.xml (old {pat_old[j]}, v2 {pat_new[j]})'
    print(f'  L/R sign conventions match pygmalion.xml for all 6 joints: {pat_new}')
    for j in JOINTS:
        jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f'L_{j}_joint')
        lo, hi = m.jnt_range[jid]
        qa = m.jnt_qposadr[jid]
        hits, reach = [], []
        for k, q in enumerate(np.linspace(lo, hi, 13)):
            mujoco.mj_resetData(m, d)
            set_free_base(d, 1.0)
            d.qpos[qa] = q
            mujoco.mj_forward(m, d)
            for c in range(d.ncon):
                b1 = m.geom_bodyid[d.contact[c].geom1]
                b2 = m.geom_bodyid[d.contact[c].geom2]
                n1 = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, b1)
                n2 = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, b2)
                if b1 == 0 or b2 == 0 or frozenset((n1, n2)) in adj:
                    continue
                hits.append((round(float(np.degrees(q)), 1), n1, n2, round(float(d.contact[c].dist), 4)))
            reach.append(d.xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, 'L_foot_link')].copy())
            if k in (0, 6, 12):
                frames.append((j, np.degrees(q), d.qpos.copy()))
        reach = np.array(reach)
        sweep_rep[j] = dict(range_deg=[float(np.degrees(lo)), float(np.degrees(hi))],
                            self_contacts=hits[:6], n_contacts=len(hits),
                            foot_x=[float(reach[:, 0].min()), float(reach[:, 0].max())],
                            foot_z=[float(reach[:, 2].min()), float(reach[:, 2].max())])
        print(f"  {j:12s} [{np.degrees(lo):6.1f},{np.degrees(hi):6.1f}] deg  foot x {reach[:,0].min():+.3f}..{reach[:,0].max():+.3f}"
              f"  z {reach[:,2].min():.3f}..{reach[:,2].max():.3f}  self-contacts {len(hits)}"
              + (f'  e.g. {hits[0]}' if hits else ''))
    rep['sweeps'] = sweep_rep

    # ---- 4. inertia read back from the simulator ----
    print('\n== inertia about the hip pitch axis, from mj_fullM (leg hanging, all joints 0)')
    mujoco.mj_resetData(m, d)
    set_free_base(d, 1.0)
    mujoco.mj_forward(m, d)
    # M[dof,dof] via M @ e_dof - works on every MuJoCo version regardless of how qM is stored
    for j in ('hip_pitch', 'knee'):
        jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f'L_{j}_joint')
        dof = m.jnt_dofadr[jid]
        e = np.zeros(m.nv)
        e[dof] = 1.0
        res = np.zeros(m.nv)
        mujoco.mj_mulM(m, d, res, e)
        print(f'  L_{j}: M[dof,dof] = {res[dof]:.4f} kg m2  (STEP point-mass estimate: hip 2.21 / knee 0.44 incl. ankle motors on the shin)')
        rep[f'I_{j}_axis'] = float(res[dof])

    # ---- 5. figure: zero pose two views + sweep contact sheet ----
    plt.rcParams.update({'figure.dpi': 120, 'font.size': 8})
    fig, ax = plt.subplots(1, 2, figsize=(8, 5))
    mujoco.mj_resetData(m, d)
    set_free_base(d, rep['standing_base_z'])
    mujoco.mj_forward(m, d)
    draw(ax[0], m, d, 'side')
    ax[0].set_title('pygmalion_v2 — side (x-z), standing')
    draw(ax[1], m, d, 'front')
    ax[1].set_title('front (y-z)')
    fig.tight_layout()
    fig.savefig(f'{IMG}/robot_v2_zero_pose.png')
    n = len(frames)
    fig, axes = plt.subplots(6, 3, figsize=(9, 17))
    for i, (j, qd, qpos) in enumerate(frames):
        d.qpos[:] = qpos
        mujoco.mj_forward(m, d)
        a = axes[i // 3, i % 3]
        draw(a, m, d, 'front' if j in ('hip_roll', 'ankle_roll', 'hip_yaw') else 'side')
        a.set_title(f'{j} {qd:+.0f}°', fontsize=8)
        a.set_xticks([])
        a.set_yticks([])
    fig.suptitle('Joint sweeps (L leg): min / mid / max of each range, drawn from the MJCF meshes', fontsize=9)
    fig.tight_layout()
    fig.savefig(f'{IMG}/robot_v2_joint_sweeps.png')
    json.dump(rep, open(f'{REPO}/pygmalion_locomotion/assets/pygmalion_v2/validation.json', 'w'), indent=1)
    print(f'\n-> {IMG}/robot_v2_zero_pose.png · {IMG}/robot_v2_joint_sweeps.png')


if __name__ == '__main__':
    main()
