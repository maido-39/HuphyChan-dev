"""A load basis for SIMPLE WALKING, in the same frame and with the same statistics as the
campaign's design basis - so the two can be compared link by link.

The structural campaign judged every part against loads.json: link-local bracket wrench
P99 (|component|, L+R pooled with the R leg mirrored), worst of the flat and rough anchors,
over the policy's ENTIRE command box - including 2.5 m/s running, 1 m/s side-stepping and
1 rad/s turning. A robot that is only going to walk slowly on the flat for its first tests
does not see those loads, and the question "which parts must be machined FIRST" needs the
loads it will actually see.

This rebuilds the same statistics on a SUBSET of the flat anchor's measurement: the command
blocks inside a "simple walking" box. Two tiers are reported:

  T1  |vx| <= 0.5 m/s (and >= -0.5), |vy| <= 0.25, |wz| <= 0.25    slow walk + standing
  T2  vx in [-0.5, 1.0], |vy| <= 0.5, |wz| <= 0.5                   ordinary walking

A block whose predecessor was NOT in the tier starts with a transient from a fast command
(decelerating from 2.5 m/s is not simple walking), so its first 3 s are dropped.

Everything is reused from the campaign's own pipeline, and the reuse is verified:
the link-local wrench comes from wrench_studio's cached `sweep` (cfrc_int transported to the
joint anchor - the docs/64 s8i correction - rotated into the child link frame, negated), and
this script's mirror/pool/P99 on the FULL box must reproduce the server's cached load-case
statistics to 0.1 before any subset is reported.

Usage: walk_basis.py [--tag=gen21p2_fc]   ->  tools/fea/loads_walk.json
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MJLAB = '/home/syaro/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab'
OUT = f'{MJLAB}/analysis/out'
CACHE = '/home/syaro/MikuchanRemote/Human-Pygmalion/tools/wrench_studio/cache'
MIR_F = np.array([-1.0, 1.0, 1.0])
MIR_M = np.array([1.0, -1.0, -1.0])
JOINTS = ['hip_pitch', 'hip_roll', 'hip_yaw', 'knee', 'ankle_pitch', 'ankle_roll']
# joint axis in the CHILD link frame (mujoco jnt_axis of gen21p2_fc_model.mjb)
AXIS = {'hip_pitch': [1, 0, 0], 'hip_roll': [0, -0.966, 0.259], 'hip_yaw': [0, 0, -1],
        'knee': [-1, 0, 0], 'ankle_pitch': [-1, 0, 0], 'ankle_roll': [0, 1, 0]}
TIERS = {'T1_slow': dict(vx=(-0.5, 0.5), vy=0.25, wz=0.25),
         'T2_walk': dict(vx=(-0.5, 1.0), vy=0.5, wz=0.5),
         'FULL': None}
BLOCK, DROP, DS = 750, 150, 2


def block_mask(z, tier):
    """Full-rate boolean mask of the steps that belong to the tier."""
    vx, vy, wz = z['cmd_vx'], z['cmd_vy'], z['cmd_wz']
    n = len(vx)
    nb = n // BLOCK
    bvx, bvy, bwz = vx[::BLOCK][:nb], vy[::BLOCK][:nb], wz[::BLOCK][:nb]
    assert np.all(vx.reshape(nb, BLOCK) == bvx[:, None]), 'command blocks are not aligned'
    if tier is None:
        return np.ones(n, bool), nb, nb
    ok = ((bvx >= tier['vx'][0]) & (bvx <= tier['vx'][1])
          & (np.abs(bvy) <= tier['vy']) & (np.abs(bwz) <= tier['wz']))
    m = np.zeros(n, bool)
    for i in range(nb):
        if ok[i]:
            s = i * BLOCK + (DROP if (i > 0 and not ok[i - 1]) else 0)
            m[s:(i + 1) * BLOCK] = True
    return m, int(ok.sum()), nb


def pooled(sw, j):
    A = []
    for sd in 'LR':
        V = sw[f'W6_{sd}_{j}'].astype(float).copy()
        if sd == 'R':
            V[:, 0:3] *= MIR_F
            V[:, 3:6] *= MIR_M
        A.append(V)
    return np.vstack(A)


def transverse_basis(u):
    u = np.asarray(u, float)
    u = u / np.linalg.norm(u)
    ref = np.array([0, 0, 1.0]) if abs(u[2]) < 0.9 else np.array([1.0, 0, 0])
    e1 = np.cross(u, ref)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(u, e1)
    return u, e1, e2


def stats(A, m2, j):
    """|component| P99 and the axial / transverse moment split, on the masked rows."""
    mm = np.concatenate([m2, m2])
    B = A[mm]
    out = {c: float(np.percentile(np.abs(B[:, i]), 99))
           for i, c in enumerate(['Fx', 'Fy', 'Fz', 'Mx', 'My', 'Mz'])}
    u, e1, e2 = transverse_basis(AXIS[j])
    M = B[:, 3:6]
    out['M_axial'] = float(np.percentile(np.abs(M @ u), 99))
    t1, t2 = M @ e1, M @ e2
    out['Mt1'] = float(np.percentile(np.abs(t1), 99))
    out['Mt2'] = float(np.percentile(np.abs(t2), 99))
    out['Mt_norm'] = float(np.percentile(np.hypot(t1, t2), 99))
    out['F_norm'] = float(np.percentile(np.linalg.norm(B[:, 0:3], axis=1), 99))
    return out


def main():
    tag = next((a.split('=')[1] for a in sys.argv if a.startswith('--tag=')), 'gen21p2_fc')
    z = np.load(f'{OUT}/{tag}.npz')
    swf = f'{CACHE}/v3_sweep_{tag}_{DS}.npz'
    assert os.path.exists(swf), (
        f'{swf} missing - start wrench_studio once for this tag so it builds the sweep')
    sw = np.load(swf)
    n2 = sw['W6_L_knee'].shape[0]
    assert n2 == (len(z['cmd_vx']) + DS - 1) // DS, 'sweep cache and npz lengths differ'

    # ---- regression: FULL box must reproduce the server's own cached stats ----
    ref_f = f'{CACHE}/v3_lc_{tag}_hip_yaw_{DS}.json'
    if os.path.exists(ref_f):
        ref = json.load(open(ref_f))['stats']
        mine = stats(pooled(sw, 'hip_yaw'), np.ones(n2, bool), 'hip_yaw')
        for c in ('Fx', 'Fy', 'Fz', 'Mx', 'My', 'Mz'):
            assert abs(mine[c] - ref[c]['p99']) < 0.15, (
                f'hip_yaw {c}: {mine[c]:.1f} vs server {ref[c]["p99"]:.1f} - the mirror or '
                'pooling differs from the campaign pipeline')
        print('regression vs server cache (hip_yaw, full box): identical')

    loads = json.load(open(f'{HERE}/loads.json'))
    res = {'_provenance': (
        f'{tag} flat anchor, link-local bracket wrench at the joint anchor (wrench_studio '
        'sweep: cfrc_int transported to xanchor - docs/64 s8i - rotated into the child '
        'link frame, negated), L+R pooled with R mirrored (F x-1, M y,z x-1), |component| '
        'P99. Subset = command blocks inside the tier box; first 3 s dropped when the '
        'previous block was outside it. Units N, N.m. tau = |joint torque| P99 on the same '
        'steps. Compare with loads.json, which is worst-of(flat, rough) over the full box.'),
        '_tiers': {k: v for k, v in TIERS.items() if v},
        '_block_s': BLOCK * 0.02, '_drop_s': DROP * 0.02}
    for tier, box in TIERS.items():
        m, nblk, nb = block_mask(z, box)
        m2 = m[::DS]
        T = {'_blocks': f'{nblk}/{nb}', '_steps': int(m.sum())}
        for j in JOINTS:
            A = pooled(sw, j)
            s = stats(A, m2, j)
            tau = np.concatenate([np.abs(z[f'tau_L_{j}_joint'][m]),
                                  np.abs(z[f'tau_R_{j}_joint'][m])])
            s['tau'] = float(np.percentile(tau, 99))
            s['tau_peak'] = float(tau.max())
            T[j] = {k: round(v, 1) for k, v in s.items()}
        g = np.concatenate([z['GRF_L_foot_link_z'][m], z['GRF_R_foot_link_z'][m]])
        T['GRF_z'] = {'P99': round(float(np.percentile(g, 99)), 1),
                      'peak': round(float(g.max()), 1)}
        res[tier] = T
    json.dump(res, open(f'{HERE}/loads_walk.json', 'w'), indent=1, ensure_ascii=False)

    # ---- report ----
    print(f"\n{'joint':12s} {'comp':6s} {'campaign':>9s} {'flat FULL':>10s} "
          f"{'T2 walk':>8s} {'%':>5s} {'T1 slow':>8s} {'%':>5s}")
    for j in JOINTS:
        for c in ('Fx', 'Fy', 'Fz', 'Mt1', 'Mt2', 'tau'):
            cam = loads[j]['P99'].get(c, float('nan')) if c in ('Fx', 'Fy', 'Fz') else float('nan')
            f, t2, t1 = (res['FULL'][j][c], res['T2_walk'][j][c], res['T1_slow'][j][c])
            camtxt = f'{cam:9.0f}' if cam == cam else f'{"-":>9s}'
            print(f'{j:12s} {c:6s} {camtxt} {f:10.1f} {t2:8.1f} {100*t2/f:5.0f} '
                  f'{t1:8.1f} {100*t1/f:5.0f}')
    for tier in ('FULL', 'T2_walk', 'T1_slow'):
        print(f"{tier:8s} blocks {res[tier]['_blocks']:8s} steps {res[tier]['_steps']:6d} "
              f"GRF_z P99 {res[tier]['GRF_z']['P99']:.0f} N")
    print(f'\n-> {HERE}/loads_walk.json')


if __name__ == '__main__':
    main()
