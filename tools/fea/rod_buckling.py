"""The ankle push-rods: the parts the campaign never analysed, and the one failure
mode the campaign never checked.

Arm_A and Arm_B connect the crank to the foot's spherical bearings. They belong to no
link, so the link-by-link campaign skipped them entirely - and they are exactly the
parts where von Mises against yield is the wrong question: a pin-ended strut at L/r =
164 fails by BUCKLING long before it yields.

This runs both checks on the real geometry with the measured rod force:
  * linear buckling (CalculiX *BUCKLE) with spherical bearings modelled as pins
  * the static stress at the same load

Loads come from tools/fea/loads.json `_rod_lc3_worst_frame` - the measured simultaneous
forces at the two foot ball joints.

Usage: rod_buckling.py [--factor 1.25]
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import femlib as F  # noqa: E402

STEP = '/home/syaro/MikuchanRemote/Human-Pygmalion/refs/Huphy_1.0_STEP/Ankle2Feet.step'
W = '/home/syaro/pyg_fea/work/rods'
YIELD = 276.0
RODS = {'Arm_A': 29, 'Arm_B': 30}      # solid indices in Ankle2Feet.step


def end_nodes(nodes, surf, axis, lo_hi, span=12.0):
    """Surface nodes within `span` mm of each end along the rod axis."""
    a = 'xyz'.index(axis)
    lo = [n for n in surf if nodes[n][a] <= lo_hi[0] + span]
    hi = [n for n in surf if nodes[n][a] >= lo_hi[1] - span]
    return sorted(lo), sorted(hi)


def main():
    factor = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--factor=')), 1.25))
    os.makedirs(W, exist_ok=True)
    loads = json.load(open(f'{HERE}/loads.json'))['_rod_lc3_worst_frame']
    ball = {'Arm_A': np.array(loads['ballA_N'], float),
            'Arm_B': np.array(loads['ballB_N'], float)}
    sol = F.load_solids(STEP)
    out = {}

    for name, idx in RODS.items():
        s = sol[idx]
        step_one = f'{W}/{name}.step'
        F.write_step([s], step_one)
        m = F.mesh_assembly(step_one, f'{W}/{name}.inp', size_far=3.0, refine=[], fragment=False)
        nodes, elems, elsets = F.parse_inp(f'{W}/{name}.inp')
        bf = F.boundary_faces(elems)
        surf = sorted({n for (_, _, t) in bf.values() for n in t})
        b0, b1 = np.array(s['bmin']), np.array(s['bmax'])
        ax = 'xyz'[int(np.argmax(b1 - b0))]
        a = 'xyz'.index(ax)
        loN, hiN = end_nodes(nodes, surf, ax, (b0[a], b1[a]))

        # the rod axis and how much of the measured ball force acts along it
        Fv = ball[name] * factor
        e = np.zeros(3)
        e[a] = 1.0
        P_axial = float(Fv @ e)
        compressive = P_axial > 0        # ball pushes the rod towards the crank
        P = abs(P_axial)

        # SPHERICAL BEARINGS ARE PINS. Clamping a band of end nodes (the first attempt)
        # restrains end rotation and turns the strut into a fixed-fixed column, which is
        # 4x stiffer against buckling - it reported SF 4.99 where the pinned value is ~1.
        # Each end is therefore rigid-coupled to a reference node at the ball centre and
        # only its TRANSLATIONS are held; the rod is free to rotate about both ends.
        refA, refB = max(nodes) + 1, max(nodes) + 2
        cA = np.mean([nodes[n] for n in loN], axis=0)
        cB = np.mean([nodes[n] for n in hiN], axis=0)
        extra = ['*NSET, NSET=ENDA']
        extra += [','.join(str(v) for v in loN[i:i + 8]) + ',' for i in range(0, len(loN), 8)]
        extra += [f'*RIGID BODY, NSET=ENDA, REF NODE={refA}', '*NSET, NSET=ENDB']
        extra += [','.join(str(v) for v in hiN[i:i + 8]) + ',' for i in range(0, len(hiN), 8)]
        extra += [f'*RIGID BODY, NSET=ENDB, REF NODE={refB}', '*BOUNDARY']
        extra += [f'{refB}, {d}, {d}' for d in (1, 2, 3) if d != a + 1]
        extra_txt = '\n'.join(extra) + '\n'
        cl = {}
        axial_cload = f'{refB}, {a + 1}, {-P:.6f}\n'

        # --- static stress
        job = f'{name}_static'
        F.write_deck(f'{W}/{job}.inp', nodes, elems, elsets, {k: F.AL for k in elsets},
                     [refA], cl, extra=extra_txt,
                     extra_nodes={refA: tuple(cA), refB: tuple(cB)},
                     extra_cload=axial_cload)
        F.run_ccx(W, job, timeout=3600)
        coords, blocks = F.parse_frd(f'{W}/{job}.frd')
        S = [x for nm, x in blocks if nm == 'STRESS'][-1]
        ids = sorted(S)
        vm = F.von_mises(np.array([S[i] for i in ids]))
        # ignore the loaded/clamped ends, they are load-introduction artefacts
        Pn = np.array([coords[i] for i in ids])
        body = (Pn[:, a] > b0[a] + 25) & (Pn[:, a] < b1[a] - 25)
        vm_body = float(vm[body].max()) if body.any() else float(vm.max())

        # --- linear buckling on the same load
        bjob = f'{name}_buckle'
        deck = open(f'{W}/{job}.inp').read()
        deck = deck.replace('*STATIC\n', '*BUCKLE\n3\n')
        # keep the mode shapes: a buckling factor is meaningless until you know whether
        # the mode is a global bow or a local web/plate collapse near the end fitting
        deck = re.sub(r'\*NODE FILE.*?\*END STEP', '*NODE FILE\n U\n*END STEP', deck, flags=re.S)
        open(f'{W}/{bjob}.inp', 'w').write(deck)
        F.run_ccx(W, bjob, timeout=3600)
        lam = []
        if os.path.exists(f'{W}/{bjob}.dat'):
            for ln in open(f'{W}/{bjob}.dat'):
                mm = re.match(r'\s*(\d+)\s+(-?[\d.eE+-]+)\s*$', ln)
                if mm:
                    lam.append(float(mm.group(2)))
        lam = [x for x in lam if x > 0]
        # Cross-check against the classical column, because CalculiX can return spurious
        # low eigenvalues when a rigid body is attached: on a prismatic bar with Arm_B's
        # section the first FE factor was 0.12 of the exact Euler value, while the same
        # recipe reproduced Arm_A's bar to 0.99. Never accept an FE buckling factor that
        # the closed-form solution does not corroborate.
        cen_e = np.array([np.mean([nodes[k] for k in elems[q][:4]], axis=0) for q in elems])
        vol_e = np.array([abs(np.linalg.det(np.array([nodes[k] for k in elems[q][1:4]])
                                            - np.array(nodes[elems[q][0]]))) / 6.0 for q in elems])
        zc = cen_e[:, a]
        Imins = []
        for z0 in np.arange(zc.min() + 4, zc.max() - 4, 4.0):
            mm2 = (zc >= z0 - 2) & (zc < z0 + 2)
            if mm2.sum() < 8:
                continue
            C2 = cen_e[mm2][:, [k for k in range(3) if k != a]]
            w2 = vol_e[mm2]
            c2 = (C2 * w2[:, None]).sum(0) / w2.sum()
            Q2 = C2 - c2
            Ixx = (w2 * Q2[:, 1] ** 2).sum() / 4.0
            Iyy = (w2 * Q2[:, 0] ** 2).sum() / 4.0
            Ixy = (w2 * Q2[:, 0] * Q2[:, 1]).sum() / 4.0
            Imins.append(0.5 * (Ixx + Iyy) - np.hypot(0.5 * (Ixx - Iyy), Ixy))
        I_use = float(np.median(Imins)) if Imins else float('nan')
        span = float(np.linalg.norm(cB - cA))
        P_euler = np.pi ** 2 * 68900.0 * I_use / span ** 2
        sf_euler = P_euler / max(P, 1e-9)
        fe_ok = [x for x in lam if 0.5 * sf_euler <= x <= 2.0 * sf_euler]
        out[name] = dict(
            length_mm=round(float(b1[a] - b0[a]), 1), axis=ax,
            mesh_nodes=m['nodes'], volume_cm3=round(s['vol_cm3'], 2),
            ball_force_N=[round(float(v), 1) for v in ball[name]],
            factor=factor, axial_N=round(P, 1),
            state='compression' if compressive else 'tension',
            static_vM_body_MPa=round(vm_body, 1),
            SF_yield=round(YIELD / max(vm_body, 1e-9), 2),
            buckling_factors=[round(x, 3) for x in lam[:3]],
            I_min_median_mm4=round(I_use, 1), pin_span_mm=round(span, 1),
            P_euler_N=round(float(P_euler), 0), SF_buckling_classical=round(float(sf_euler), 2),
            SF_buckling_FE=(round(fe_ok[0], 2) if fe_ok else None),
            SF_buckling=round(float(min([sf_euler] + fe_ok[:1])), 2),
            fe_modes_rejected=[round(x, 3) for x in lam[:3] if x not in fe_ok])
        print(f"{name}: {out[name]['length_mm']} mm, {P:.0f} N "
              f"{out[name]['state']} (x{factor}) · static {vm_body:.1f} MPa "
              f"(SF {out[name]['SF_yield']}) · Euler I={I_use:.0f} mm4 over {span:.0f} mm "
              f"-> P_cr {P_euler:.0f} N (SF {sf_euler:.2f}) · FE corroborating mode "
              f"{out[name]['SF_buckling_FE']} (rejected {out[name]['fe_modes_rejected']}) "
              f"=> SF_buckling {out[name]['SF_buckling']}", flush=True)

    json.dump(out, open(f'{W}/rods.json', 'w'), indent=1)
    print(f'\n-> {W}/rods.json')


if __name__ == '__main__':
    main()
