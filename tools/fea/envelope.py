"""Directional load envelope by linear superposition.

The measured wrench table (docs/64) gives per-component magnitudes -- |Fx|,
|Fy|, ... -- so the SIGN of each component is not known and a single signed
load case is not a design case. Since a linear-static solve is linear in the
load, we solve six unit cases per load point (Fx, Fy, Fz, Mx, My, Mz) and then,
per node, take the worst of the 2^6 = 64 sign combinations:

    sigma(s) = sum_k s_k * (P_k / unit_k) * sigma_k ,  s_k in {-1, +1}

von Mises is evaluated after the summation, so this is the exact envelope over
sign combinations, not an approximation. With several load points the sign of
each point's wrench is shared per component (a joint reaction acts as one
vector), which is what `groups` expresses.

Output per node: worst von Mises, the governing sign vector, and the field
arrays needed by the viewer.
"""
import itertools

import numpy as np

UNIT_F = 1000.0   # N per unit force case
UNIT_M = 100.0    # N*m per unit moment case
COMPS = ('Fx', 'Fy', 'Fz', 'Mx', 'My', 'Mz')


def combine(unit_stress, magnitudes, chunk=200_000):
    """unit_stress: (6, N, 6) stress tensors of the unit cases.
    magnitudes: (6,) actual load magnitudes in N / N*m.
    Returns dict(vm_max (N,), sign_idx (N,), signs (64,6)).
    """
    U = np.asarray(unit_stress, float)
    scale = np.array([magnitudes[i] / (UNIT_F if i < 3 else UNIT_M) for i in range(6)])
    U = U * scale[:, None, None]
    signs = np.array(list(itertools.product([1., -1.], repeat=6)))   # (64,6)
    N = U.shape[1]
    vm_max = np.zeros(N)
    which = np.zeros(N, int)
    for a in range(0, N, chunk):
        b = min(N, a + chunk)
        blk = U[:, a:b, :]                       # (6, n, 6)
        # (64, n, 6) = sum_k signs[:,k] * blk[k]
        tot = np.tensordot(signs, blk, axes=(1, 0))
        sxx, syy, szz, sxy, syz, szx = (tot[..., i] for i in range(6))
        vm = np.sqrt(0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
                     + 3 * (sxy ** 2 + syz ** 2 + szx ** 2))
        which[a:b] = vm.argmax(0)
        vm_max[a:b] = vm.max(0)
    return dict(vm_max=vm_max, sign_idx=which, signs=signs)


def summarize(env, coords, ids, load_nids=(), filter_mm=1.5, yield_=276.0):
    vm = env['vm_max']
    P = np.asarray(coords)
    out = dict(max_vM=float(vm.max()), p99_vM=float(np.percentile(vm, 99)),
               argmax_xyz=[round(float(v), 1) for v in P[int(vm.argmax())]],
               governing_signs=dict(zip(COMPS, env['signs'][env['sign_idx'][int(vm.argmax())]].tolist())),
               SF=float(yield_ / vm.max()))
    if len(load_nids):
        idx = {n: k for k, n in enumerate(ids)}
        LP = np.array([P[idx[n]] for n in load_nids if n in idx])
        if len(LP):
            keep = np.ones(len(ids), bool)
            for k in range(0, len(LP), 400):
                d = np.linalg.norm(P[:, None, :] - LP[None, k:k + 400, :], axis=2).min(1)
                keep &= d > filter_mm
            if keep.any():
                out['max_vM_filtered'] = float(vm[keep].max())
                out['SF_filtered'] = float(yield_ / vm[keep].max())
                out['argmax_filtered_xyz'] = [round(float(v), 1)
                                              for v in P[keep][int(vm[keep].argmax())]]
    return out
