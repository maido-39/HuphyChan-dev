"""Cross-check the exported URDF against the MJCF it was emitted with.

The URDF is read by an INDEPENDENT parser (MuJoCo's own URDF loader, not our emitter), the
MJCF by the normal path. Then, with the base fixed at the origin in both:
  1. every joint: name, world axis, anchor point and range must agree;
  2. every joint swept through its range (others at zero), then 200 random poses inside
     all ranges: every common body's world position and orientation must agree;
  3. mass / COM / inertia per body must agree (the URDF root link is merged into the world
     by the loader - that is the one expected difference, reported not flagged);
  4. a video: MJCF meshes solid, URDF meshes as red wireframe, overlaid, joint by joint.
A divergence here means the two files describe different robots.

Usage: urdf_crosscheck.py [--tag=pygmalion_v3_printed] [--fast]   (mjlab .venv python)
"""
import json, os, subprocess, sys
import numpy as np
import mujoco

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
ASSETS = f'{REPO}/pygmalion_locomotion/assets/pygmalion_v2'
XMLS = f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls'
VID = f'{REPO}/docs/video'
IMG = f'{REPO}/docs/img'
sys.path.insert(0, os.path.dirname(__file__))
from loop_ankle_verify import frame as draw_solid  # noqa: E402


def load_urdf(tag):
    """MuJoCo's URDF parser, asked to keep the visual meshes (discarded by default)."""
    txt = open(f'{ASSETS}/{tag}.urdf').read()
    i = txt.index('>', txt.index('<robot')) + 1
    txt = txt[:i] + f'\n  <mujoco><compiler discardvisual="false" meshdir="{ASSETS}"/></mujoco>' + txt[i:]
    return mujoco.MjModel.from_xml_string(txt)


def names(m, kind):
    return [mujoco.mj_id2name(m, kind, i) for i in range(getattr(m, {mujoco.mjtObj.mjOBJ_BODY: 'nbody', mujoco.mjtObj.mjOBJ_JOINT: 'njnt'}[kind]))]


def set_pose(m, d, q, jmap):
    d.qpos[:] = 0
    if m.nq >= 7 and m.jnt_type[0] == mujoco.mjtJoint.mjJNT_FREE:
        d.qpos[3] = 1.0                       # base at the origin, identity orientation
    for n, v in q.items():
        d.qpos[m.jnt_qposadr[jmap[n]]] = v
    mujoco.mj_kinematics(m, d)


def compare_bodies(mu, du, mx, dx, bu, bx):
    dp, da = 0.0, 0.0
    for n in bu:
        if n not in bx:
            continue
        dp = max(dp, np.linalg.norm(du.xpos[bu[n]] - dx.xpos[bx[n]]) * 1000)
        qa, qb = du.xquat[bu[n]], dx.xquat[bx[n]]
        da = max(da, np.degrees(2 * np.arccos(min(1.0, abs(float(np.dot(qa, qb)))))))
    return dp, da


def draw_wire(m, d, ax, view, every=12):
    from matplotlib.collections import LineCollection
    segs = []
    for g in range(m.ngeom):
        if m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH:
            continue
        mid = m.geom_dataid[g]
        if 'hull' in (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_MESH, mid) or ''):
            continue
        V = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]]
        F = m.mesh_face[m.mesh_faceadr[mid]:m.mesh_faceadr[mid] + m.mesh_facenum[mid]][::every]
        W = V @ d.geom_xmat[g].reshape(3, 3).T + d.geom_xpos[g]
        P = W[:, [0, 2]] if view == 'side' else W[:, [1, 2]]
        segs.append(np.stack([P[F[:, 0]], P[F[:, 1]]], 1))
    ax.add_collection(LineCollection(np.vstack(segs), colors='red', linewidths=0.25, alpha=0.7))


def main():
    tag = next((a.split('=')[1] for a in sys.argv if a.startswith('--tag=')), 'pygmalion_v3_printed')
    fast = '--fast' in sys.argv
    mu = load_urdf(tag); du = mujoco.MjData(mu)
    mx = mujoco.MjModel.from_xml_path(f'{XMLS}/{tag}.xml'); dx = mujoco.MjData(mx)
    bu = {n: i for i, n in enumerate(names(mu, mujoco.mjtObj.mjOBJ_BODY))}
    bx = {n: i for i, n in enumerate(names(mx, mujoco.mjtObj.mjOBJ_BODY))}
    ju = {n: i for i, n in enumerate(names(mu, mujoco.mjtObj.mjOBJ_JOINT))}
    jx = {n: i for i, n in enumerate(names(mx, mujoco.mjtObj.mjOBJ_JOINT)) if mx.jnt_type[i] != mujoco.mjtJoint.mjJNT_FREE}
    rep = {'tag': tag, 'joints': {}, 'bodies': {}}
    print(f'{tag}: URDF {mu.nbody} bodies / {mu.njnt} joints  MJCF {mx.nbody} bodies / {len(jx)} joints (+free)')
    missing = sorted(set(jx) - set(ju)) + sorted(set(ju) - set(jx))
    assert not missing, f'joint sets differ: {missing}'
    extra = sorted(set(bu) - set(bx))
    if extra:
        print('URDF-only bodies (expected: the 1 g universal-joint dummies of the loop rods):', extra)
        rep['urdf_only_bodies'] = extra
    # 1. joints at the zero pose
    set_pose(mu, du, {}, ju); set_pose(mx, dx, {}, jx)
    print('\njoints (zero pose): axis angle / anchor / range')
    worst_axis = worst_anchor = worst_range = 0.0
    for n in jx:
        a1, a2 = du.xaxis[ju[n]], dx.xaxis[jx[n]]
        ang = np.degrees(np.arccos(np.clip(abs(float(np.dot(a1, a2))), -1, 1)))
        same_sign = float(np.dot(a1, a2)) > 0
        anc = np.linalg.norm(du.xanchor[ju[n]] - dx.xanchor[jx[n]]) * 1000
        # an unlimited MJCF hinge (the rod universal joints) has jnt_range 0 0; the URDF
        # writes +-pi there because URDF revolute joints must carry a limit - not a difference
        rng = np.abs(mu.jnt_range[ju[n]] - mx.jnt_range[jx[n]]).max() if mx.jnt_limited[jx[n]] else 0.0
        worst_axis, worst_anchor, worst_range = max(worst_axis, ang), max(worst_anchor, anc), max(worst_range, rng)
        rep['joints'][n] = dict(axis_deg=round(float(ang), 4), same_sign=bool(same_sign), anchor_mm=round(float(anc), 4),
                                range_diff_rad=round(float(rng), 6), range=[round(float(x), 4) for x in mx.jnt_range[jx[n]]])
        flag = '' if ang < 0.01 and same_sign and anc < 0.05 and rng < 1e-5 else '   <-- DIFF'
        print(f'  {n:24s} axis {ang:7.4f} deg {"" if same_sign else "(FLIPPED)"} anchor {anc:7.4f} mm  range diff {rng:.1e}{flag}')
    # 2. sweeps
    print('\nsweeps (body position / orientation, URDF vs MJCF):')
    rng_ = np.random.default_rng(0)
    sweep_frames = []
    worst = {}
    for n in jx:
        lo, hi = mx.jnt_range[jx[n]]
        if hi <= lo:
            lo, hi = -1.0, 1.0
        dp = da = 0.0
        for v in np.linspace(lo, hi, 8 if fast else 16):
            set_pose(mu, du, {n: v}, ju); set_pose(mx, dx, {n: v}, jx)
            p, a = compare_bodies(mu, du, mx, dx, bu, bx)
            dp, da = max(dp, p), max(da, a)
            sweep_frames.append((n, float(v), p))
        worst[n] = (dp, da)
        rep['joints'][n].update(sweep_pos_mm=round(float(dp), 4), sweep_ang_deg=round(float(da), 4))
        print(f'  {n:24s} max body pos diff {dp:8.4f} mm  orientation {da:8.4f} deg')
    dp = da = 0.0
    for _ in range(50 if fast else 200):
        q = {n: rng_.uniform(*mx.jnt_range[jx[n]]) if mx.jnt_range[jx[n]][1] > mx.jnt_range[jx[n]][0] else rng_.uniform(-1, 1) for n in jx}
        set_pose(mu, du, q, ju); set_pose(mx, dx, q, jx)
        p, a = compare_bodies(mu, du, mx, dx, bu, bx)
        dp, da = max(dp, p), max(da, a)
    rep['random_poses'] = dict(n=50 if fast else 200, pos_mm=round(float(dp), 4), ang_deg=round(float(da), 4))
    print(f'  random poses (all joints)  max body pos diff {dp:8.4f} mm  orientation {da:8.4f} deg')
    # 3. mass properties
    print('\nmass properties per body:')
    for n in bx:
        if n == 'world':
            continue
        if n not in bu:
            rep['bodies'][n] = dict(note='URDF root merged into world by the loader', mass=round(float(mx.body_mass[bx[n]]), 4))
            print(f'  {n:24s} mass {mx.body_mass[bx[n]]:7.3f}  (URDF root link: merged into the world by the loader, expected)')
            continue
        dm = abs(mu.body_mass[bu[n]] - mx.body_mass[bx[n]])
        dc = np.linalg.norm(mu.body_ipos[bu[n]] - mx.body_ipos[bx[n]]) * 1000
        dI = np.abs(mu.body_inertia[bu[n]] - mx.body_inertia[bx[n]]).max()
        rep['bodies'][n] = dict(mass=round(float(mx.body_mass[bx[n]]), 4), mass_diff=float(dm), com_diff_mm=float(dc), inertia_diff=float(dI))
        flag = '' if dm < 1e-4 and dc < 0.05 and dI < 1e-5 else '   <-- DIFF'
        print(f'  {n:24s} mass {mx.body_mass[bx[n]]:7.3f} dm {dm:.1e}  com {dc:.4f} mm  dI {dI:.1e}{flag}')
    rep['worst'] = dict(axis_deg=float(worst_axis), anchor_mm=float(worst_anchor), range_rad=float(worst_range),
                        sweep_pos_mm=float(max(v[0] for v in worst.values())), sweep_ang_deg=float(max(v[1] for v in worst.values())))
    ok = worst_axis < 0.01 and worst_anchor < 0.05 and worst_range < 1e-5 and rep['worst']['sweep_pos_mm'] < 0.05 and rep['worst']['sweep_ang_deg'] < 0.01
    rep['verdict'] = 'MATCH' if ok else 'DIVERGENT'
    print(f"\nVERDICT {rep['verdict']}: worst axis {worst_axis:.4f} deg, anchor {worst_anchor:.4f} mm, sweep pos {rep['worst']['sweep_pos_mm']:.4f} mm / {rep['worst']['sweep_ang_deg']:.4f} deg")
    json.dump(rep, open(f'{ASSETS}/{tag}_urdf_crosscheck.json', 'w'), indent=1)
    # 4. video: joint by joint, MJCF solid + URDF red wireframe
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    bodies = [n for n in bx if n != 'world']
    step = 2 if fast else 1
    frames = sweep_frames[::step]
    os.makedirs(f'{VID}/_frames_xc', exist_ok=True)
    for k, (n, v, p) in enumerate(frames):
        set_pose(mu, du, {n: v}, ju); set_pose(mx, dx, {n: v}, jx)
        fig, axes = plt.subplots(1, 2, figsize=(9, 5), dpi=90)
        for ax, view in zip(axes, ('side', 'front')):
            draw_solid(mx, dx, ax, bodies, view=view, contacts=False, every=10)
            draw_wire(mu, du, ax, view)
            ax.set_xlim(-0.7, 0.7); ax.set_ylim(-1.15, 0.55); ax.set_xticks([]); ax.set_yticks([])
            ax.set_title(f'{view}: MJCF solid / URDF red wire', fontsize=9)
        fig.suptitle(f'{tag}  {n} = {np.degrees(v):+.1f} deg   body pos diff {p:.4f} mm', fontsize=10)
        fig.tight_layout()
        fig.savefig(f'{VID}/_frames_xc/{k:04d}.png'); plt.close(fig)
    out = f'{VID}/urdf_crosscheck_{tag}.mp4'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '8', '-i', f'{VID}/_frames_xc/%04d.png',
                    '-pix_fmt', 'yuv420p', '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', out], check=True)
    subprocess.run(['rm', '-r', f'{VID}/_frames_xc'])
    print(f'-> {out}')
    # still: per-joint worst deviation
    fig, ax = plt.subplots(figsize=(9, 3.2), dpi=110)
    ks = list(worst); ax.bar(range(len(ks)), [worst[k][0] for k in ks], color='steelblue')
    ax.set_xticks(range(len(ks))); ax.set_xticklabels([k.replace('_joint', '') for k in ks], rotation=60, ha='right', fontsize=7)
    ax.set_ylabel('max body position diff [mm]'); ax.set_title(f'{tag}: URDF (MuJoCo URDF loader) vs MJCF over each joint sweep - verdict {rep["verdict"]}', fontsize=9)
    ax.axhline(0.05, color='red', lw=0.8, ls='--'); fig.tight_layout(); fig.savefig(f'{IMG}/urdf_crosscheck_{tag}.png'); print(f'-> {IMG}/urdf_crosscheck_{tag}.png')


if __name__ == '__main__':
    main()
