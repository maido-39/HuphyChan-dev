"""Bolt-group check at every analysed interface, under the measured joint wrench.

The continuum runs model a bolted interface as clamped pads or MPC ties, which is
right for the metal but says nothing about the screws themselves. This closes that
gap with the classical bolt-pattern analysis, using the same P99 x 1.25 wrench the
FEA uses:

  tension per bolt   T_i = F_n/N + M_bend * d_i / sum(d_j^2)
  shear per bolt     V_i = |F_t|/N + |M_n| * r_i / sum(r_j^2)      (torsion about n)

and compares each against the three limits that actually govern here:

  1. ALUMINIUM THREAD  - every tapped hole is in 6061-T6, no nuts anywhere, so the
     usable preload is F_strip/SF, not the bolt grade (see thread_check.py).
  2. JOINT SEPARATION  - T_i must stay under the clamp load, or the joint gaps and
     the screws start seeing the alternating load directly (fatigue).
  3. SLIP             - the shear should be carried by friction, V_i <= mu*(F_pre - T_i);
     if it is not, the screws work in shear through clearance holes, which for a
     walking robot is a fretting/loosening problem, not a strength one.

Interfaces come from the link specs: every 'bolt_pads' fix or load selector, plus
any detected bolt group that sits on one. Usage: bolt_group.py [LINK ...]
"""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import thread_check as TC  # noqa: E402

W = '/home/syaro/pyg_fea/work'
STEPS = '/home/syaro/pyg_fea/steps'
MU = 0.35              # aluminium-aluminium, machined dry
SF_THREAD = 2.0        # thread stripping reserve on the preload
GRADE = '4.6'          # what the CAD calls out today (ISO 4762 class 4.6)
STRESS_AREA = {3: 5.03, 4: 8.78, 5: 14.2, 6: 20.1, 8: 36.6}     # mm^2, ISO metric coarse


def bolt_capacity(nominal, Le_mm):
    """(allowable preload, bolt proof load, thread strip load) for one screw [N]."""
    F_strip = TC.strip_force(nominal, Le_mm)
    F_pre = F_strip / SF_THREAD
    As = STRESS_AREA.get(int(nominal), 8.78)
    F_proof = As * TC.GRADE[GRADE]
    return min(F_pre, 0.7 * F_proof), F_proof, F_strip


def group_check(P, n, F, M, sizes, Le):
    """Classical bolt-pattern distribution. P: bolt points, n: interface normal."""
    P = np.asarray(P, float)
    n = np.asarray(n, float) / np.linalg.norm(n)
    c = P.mean(0)
    R = P - c
    r_n = R - np.outer(R @ n, n)                 # in-plane arms
    r = np.linalg.norm(r_n, axis=1)
    N = len(P)

    Fn = float(F @ n)                            # axial (separating) component
    Ft = F - Fn * n                               # in-plane (shear) component
    Mn = float(M @ n)                             # torsion about the normal
    Mb = M - Mn * n                               # bending

    # tension: uniform part + bending about the pattern's own axes
    T = np.full(N, Fn / N)
    if np.linalg.norm(Mb) > 1e-9:
        e = Mb / np.linalg.norm(Mb)              # bending axis
        d = r_n - np.outer(r_n @ e, e)           # lever arm perpendicular to it
        dd = np.linalg.norm(d, axis=1) * np.sign(d @ np.cross(n, e))
        s = float((dd ** 2).sum())
        if s > 1e-9:
            T = T + np.linalg.norm(Mb) * dd / s

    # shear: uniform part + torsion about the normal
    V = np.full(N, np.linalg.norm(Ft) / N)
    s2 = float((r ** 2).sum())
    if s2 > 1e-9 and abs(Mn) > 1e-9:
        V = np.hypot(V, abs(Mn) * r / s2)

    rows = []
    for i in range(N):
        F_pre, F_proof, F_strip = bolt_capacity(sizes[i], Le[i])
        slip = MU * max(0.0, F_pre - max(0.0, T[i]))
        rows.append(dict(
            i=i, size=f'M{int(sizes[i])}', T_N=round(float(T[i]), 1), V_N=round(float(V[i]), 1),
            preload_N=round(F_pre, 1), strip_N=round(F_strip, 1), proof_N=round(F_proof, 1),
            sep_margin=round(float(F_pre / max(1e-9, T[i])), 2) if T[i] > 0 else None,
            slip_margin=round(float(slip / max(1e-9, V[i])), 2),
            shear_margin=round(float(0.6 * F_proof / max(1e-9, V[i])), 2)))
    return rows, c


def main():
    specs = json.load(open(f'{HERE}/link_specs.json'))
    links = sys.argv[1:] or [os.path.basename(os.path.dirname(f))
                             for f in sorted(glob.glob(f'{W}/*/envelope_P99.json'))]
    out = {}
    for link in links:
        spec = specs.get(link)
        if not spec:
            continue
        geo = spec.get('geometry_of', link)
        jf = f'{STEPS}/link_{geo}_joints.json'
        if not os.path.exists(jf):
            continue
        bolts = json.load(open(jf)).get('detected_bolts', [])
        env = spec['envelope']
        mg = env.get('magnitudes_N', {})
        F = np.array([mg.get('Fx', 0.0), mg.get('Fy', 0.0), mg.get('Fz', 0.0)]) * 1.25
        tau = float(env.get('axial_torque_Nm', 0.0)) * 1000.0      # N.mm

        for blk in list(env.get('fix', [])) + list(env.get('points', [])):
            if blk.get('type') != 'bolt_pads':
                continue
            pads = np.asarray(blk['points'], float)
            # the bolts of this pad group: nearest detected bolt to each pad
            sizes, Le, P = [], [], []
            for q in pads:
                if not bolts:
                    break
                k = int(np.argmin([np.linalg.norm(np.asarray(b['head_point'], float) - q)
                                   for b in bolts]))
                b = bolts[k]
                if np.linalg.norm(np.asarray(b['head_point'], float) - q) > 12.0:
                    continue
                P.append(b['head_point'])
                sizes.append(b['nominal'])
                Le.append(b.get('engagement_mm') or 2.0 * b['nominal'])
            if len(P) < 3:
                continue
            n = np.asarray(blk.get('axis_vec') or [0, 0, 1], float)
            if isinstance(blk.get('axis'), str):
                n = {'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]}[blk['axis']]
                n = np.asarray(n, float)
            c = np.asarray(P, float).mean(0)
            jc = np.asarray(env.get('joint_ctr') or c, float)
            M = np.cross(jc - c, F) + tau * n / max(1e-9, np.linalg.norm(n))
            rows, ctr = group_check(P, n, F, M, sizes, Le)
            worst = min(rows, key=lambda r: min(r['slip_margin'],
                                                r['sep_margin'] if r['sep_margin'] else 9e9))
            key = f"{link}:{blk.get('name', blk.get('type'))}"
            out[key] = dict(bolts=len(rows), centre=[round(float(v), 1) for v in ctr],
                            normal=[round(float(v), 2) for v in n],
                            F_N=[round(float(v), 1) for v in F],
                            M_Nmm=[round(float(v), 1) for v in M], rows=rows)
            print(f"{key}\n   {len(rows)} x M{int(np.median(sizes))} · worst bolt: "
                  f"T {worst['T_N']:.0f} N, V {worst['V_N']:.0f} N vs preload "
                  f"{worst['preload_N']:.0f} N → separation margin "
                  f"{worst['sep_margin']}, slip margin {worst['slip_margin']}, "
                  f"shear margin {worst['shear_margin']}")
    json.dump(out, open(f'{W}/bolt_groups.json', 'w'), indent=1)
    print(f'\n{len(out)} bolted interfaces -> {W}/bolt_groups.json')


if __name__ == '__main__':
    main()
