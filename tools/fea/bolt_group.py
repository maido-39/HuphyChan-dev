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

LOADS = json.load(open(f'{HERE}/loads.json'))
W = '/home/syaro/pyg_fea/work'
STEPS = '/home/syaro/pyg_fea/steps'
MU = 0.35              # aluminium-aluminium, machined dry
SF_THREAD = 2.0        # thread stripping reserve on the preload
# ASSUMPTION, not a CAD readout: no property class is recorded in the STEP. 4.6 is the
# conservative reading of a plain ISO 4762 callout. Override with --grade=8.8 to see the
# sensitivity; note the aluminium thread, not the bolt, caps the preload either way.
GRADE = os.environ.get('PYG_BOLT_GRADE', '4.6')
STRESS_AREA = {3: 5.03, 4: 8.78, 5: 14.2, 6: 20.1, 8: 36.6}     # mm^2, ISO metric coarse


def load_centre(env):
    """Where the wrench is applied, from the spec alone (no mesh needed)."""
    pts = env.get('points') or []
    acc = []
    for p in pts:
        if p.get('type') == 'bolt_pads' and p.get('points'):
            acc.append(np.asarray(p['points'], float).mean(0))
        elif p.get('ctr'):
            acc.append(np.asarray(p['ctr'], float))
        elif p.get('type') == 'plane':
            ax = 'xyz'.index(p['axis'])
            box = p.get('box') or {}
            q = np.zeros(3)
            q[ax] = float(p['value'])
            for k, a in (('x', 0), ('y', 1), ('z', 2)):
                if a != ax and k in box:
                    q[a] = 0.5 * (box[k][0] + box[k][1])
            acc.append(q)
    return np.mean(acc, axis=0) if acc else None


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

    # shear: uniform part + torsion about the normal. These are worth keeping apart:
    # a centring register (a bearing seat or spigot, which most of these flanges have)
    # carries the in-plane FORCE as a form fit, but a smooth cylinder cannot carry
    # TORQUE about its own axis - that part has only friction or dowels behind it.
    Vf = np.full(N, np.linalg.norm(Ft) / N)
    Vt = np.zeros(N)
    s2 = float((r ** 2).sum())
    if s2 > 1e-9 and abs(Mn) > 1e-9:
        Vt = abs(Mn) * r / s2
    V = np.hypot(Vf, Vt)

    rows = []
    for i in range(N):
        F_pre, F_proof, F_strip = bolt_capacity(sizes[i], Le[i])
        slip = MU * max(0.0, F_pre - max(0.0, T[i]))
        rows.append(dict(
            i=i, size=f'M{int(sizes[i])}', T_N=round(float(T[i]), 1), V_N=round(float(V[i]), 1),
            V_force_N=round(float(Vf[i]), 1), V_torsion_N=round(float(Vt[i]), 1),
            preload_N=round(F_pre, 1), strip_N=round(F_strip, 1), proof_N=round(F_proof, 1),
            sep_margin=round(float(F_pre / max(1e-9, T[i])), 2) if T[i] > 0 else None,
            slip_margin=round(float(slip / max(1e-9, V[i])), 2),
            # mu = 0.35 and a nominal preload are both best-case. Torque-controlled
            # assembly scatters the preload about +-25 %, and machined aluminium runs
            # mu = 0.2-0.5, so the pessimistic corner is what a joint has to survive.
            slip_margin_worst=round(float(0.20 * max(0.0, 0.75 * F_pre - max(0.0, T[i]))
                                          / max(1e-9, V[i])), 2),
            slip_margin_with_register=round(float(slip / max(1e-9, Vt[i])), 2),
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
        # Same source and same factor the FEA uses: measured P99 from loads.json,
        # overridden per link where the spec says so (the foot uses measured GRF).
        base = LOADS.get(env['joint'], {}).get('P99', {})
        mg = {**base, **(env.get('magnitudes_N') or {})}
        F = np.array([mg.get('Fx', 0.0), mg.get('Fy', 0.0), mg.get('Fz', 0.0)]) * 1.25
        if not F.any():
            print(f'{link}: no measured wrench for joint {env["joint"]!r} - skipped')
            continue
        tau = float(env.get('axial_torque_Nm', 0.0)) * 1000.0      # N.mm

        for blk in list(env.get('fix', [])) + list(env.get('points', [])):
            if blk.get('type') != 'bolt_pads':
                continue
            pads = np.asarray(blk['points'], float)
            # the bolts of this pad group: nearest detected bolt to each pad
            sizes, Le, P = [], [], []
            assumed_Le = False
            claimed = set()          # one bolt cannot serve two pads
            for q in pads:
                if not bolts:
                    break
                k = int(np.argmin([np.linalg.norm(np.asarray(b['head_point'], float) - q)
                                   for b in bolts]))
                if k in claimed:
                    continue
                claimed.add(k)
                b = bolts[k]
                # A bolt head sits at the far end of its grip, so on a thick flange the
                # head is legitimately far from the pad. Match on the distance ACROSS the
                # pad normal, and allow the head to be anywhere along it.
                hp = np.asarray(b['head_point'], float)
                nrm = np.asarray(b.get('axis') or [0, 0, 1], float)
                nrm = nrm / max(np.linalg.norm(nrm), 1e-9)
                lateral = np.linalg.norm((hp - q) - np.dot(hp - q, nrm) * nrm)
                along = abs(float(np.dot(hp - q, nrm)))
                if lateral > 6.0 or along > 60.0:
                    continue
                P.append(b['head_point'])
                sizes.append(b['nominal'])
                # 2xD is an ASSUMPTION when the CAD gave no tapped depth. Flag it so a
                # margin computed on a guess is not read as a measurement.
                Le.append(b.get('engagement_mm') or 2.0 * b['nominal'])
                if not b.get('engagement_mm'):
                    assumed_Le = True
            if len(P) < 3:
                continue
            # The interface normal decides what is tension and what is shear, so taking
            # it from a global-axis STRING is only right when the flange happens to be
            # perpendicular to that axis. Fit it to the bolt pattern instead, and say so
            # when the pattern is not planar (then no single normal is correct).
            # Fit to the PAD points, not the bolt heads: heads sit at different depths
            # along their own axes, so they are never coplanar and fitting to them gave a
            # normal 90 deg off the truth (my own first version of this check).
            Pn = np.asarray(pads, float)
            c_fit = Pn.mean(0)
            _, sv, vt = np.linalg.svd(Pn - c_fit)
            n = vt[-1] / max(np.linalg.norm(vt[-1]), 1e-9)
            flat = sv[-1] / max(sv[0], 1e-9)
            hint = blk.get('axis')
            if isinstance(hint, str):
                nh = np.asarray({'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1]}[hint], float)
                if float(n @ nh) < 0:
                    n = -n
                ang = np.degrees(np.arccos(min(1.0, abs(float(n @ nh)))))
                if ang > 10.0:
                    print(f'   NOTE: {link} / {str(blk.get("name", blk.get("type")))[:38]} '
                          f'normal is {ang:.0f} deg off the '
                          f"declared '{hint}' axis - using the fitted normal "
                          f'{np.round(n, 2)}', flush=True)
            if flat > 0.15:
                print(f'   WARNING: {link} / {str(blk.get("name", blk.get("type")))[:38]} '
                      f'is NOT planar (out-of-plane / span = '
                      f'{flat:.2f}); a single interface normal cannot describe it, so its '
                      'tension/shear split is approximate', flush=True)
            c = np.asarray(P, float).mean(0)
            # The moment at a bolted interface is what the load does about it. Using
            # a non-existent 'joint_ctr' key made the arm zero, so every bolt came out
            # at zero tension - the one number a cantilevered flange is all about.
            lc = load_centre(env)
            arm = (lc - c) if lc is not None else np.zeros(3)
            M = np.cross(arm, F) + tau * n / max(1e-9, np.linalg.norm(n))
            if blk in env.get('points', []):
                M = tau * n / max(1e-9, np.linalg.norm(n))   # the load enters here
            rows, ctr = group_check(P, n, F, M, sizes, Le)
            worst = min(rows, key=lambda r: min(r['slip_margin'],
                                                r['sep_margin'] if r['sep_margin'] else 9e9))
            tmax = max(rows, key=lambda r: r['T_N'])
            key = f"{link}:{blk.get('name', blk.get('type'))}#{len(out)}"
            out[key] = dict(bolts=len(rows), engagement_assumed=assumed_Le,
                            centre=[round(float(v), 1) for v in ctr],
                            normal=[round(float(v), 2) for v in n],
                            F_N=[round(float(v), 1) for v in F],
                            M_Nmm=[round(float(v), 1) for v in M], rows=rows)
            print(f"{key}\n   {len(rows)} x M{int(np.median(sizes))} · most tensioned: "
                  f"T {tmax['T_N']:.0f} N vs preload {tmax['preload_N']:.0f} N "
                  f"(separation margin {tmax['sep_margin']}) · worst bolt: "
                  f"T {worst['T_N']:.0f} N, V {worst['V_N']:.0f} N vs preload "
                  f"{worst['preload_N']:.0f} N → separation margin "
                  f"{worst['sep_margin']}, slip margin {worst['slip_margin']} "
                  f"(V force {worst['V_force_N']:.0f} N + torsion {worst['V_torsion_N']:.0f} N; "
                  f"with a centring register only the torsion part needs friction -> "
                  f"{worst['slip_margin_with_register']}), shear margin {worst['shear_margin']}")
    json.dump(out, open(f'{W}/bolt_groups.json', 'w'), indent=1)
    print(f'\n{len(out)} bolted interfaces -> {W}/bolt_groups.json')


if __name__ == '__main__':
    main()
