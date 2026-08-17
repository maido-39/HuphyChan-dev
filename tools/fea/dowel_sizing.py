"""Size the shear dowels the slip-critical flanges need.

bolt_group.py showed three flanges whose friction cannot hold the torsion about the
flange normal (L2 knee 0.26, L5 hip 0.42, L4 hip-roll 0.78), and that neither preload
nor a centring register fixes it - a smooth register carries in-plane force but not
torque about its own axis. The remaining option is a form fit: dowel pins.

For each slip-critical interface this recovers the torsion the bolts cannot hold by
friction, puts it on N pins at a chosen radius, and checks the two ways a pin fails:

  pin shear      tau = F/A      vs 0.6 * Rm of the pin steel
  hole bearing   sig = F/(d t)  vs the aluminium bearing allowable (1.5 * yield)

The friction the bolts still provide is credited first, so the pins only take what is
actually left over.

Usage: dowel_sizing.py [--pins 2] [--radius-mm 25] [--dia 6]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
W = '/home/syaro/pyg_fea/work'

PIN_RM = 640.0          # dowel steel, ISO 8734 hardened is far above this - conservative
AL_BEARING = 1.5 * 276.0
PLATE_T = 8.0           # engaged aluminium depth per pin [mm], the thinnest flange here


def main():
    pins = int(next((a.split('=')[1] for a in sys.argv if a.startswith('--pins=')), 2))
    r_p = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--radius-mm=')), 25.0))
    dia = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--dia=')), 6.0))
    bg = json.load(open(f'{W}/bolt_groups.json'))
    A = 3.14159 * dia ** 2 / 4.0
    out = {}
    seen = set()
    print(f'{pins} dowels of Ø{dia:.0f} mm at r = {r_p:.0f} mm, {PLATE_T:.0f} mm engaged\n')
    print(f'{"interface":42s} {"torsion":>9} {"friction":>9} {"left":>9} {"per pin":>9} '
          f'{"shear SF":>9} {"bearing SF":>11}')
    for k, v in bg.items():
        rows = v['rows']
        w = min(rows, key=lambda r: r['slip_margin'])
        if w['slip_margin'] >= 1.0:
            continue
        sig = (v['bolts'], w['size'], round(w['V_torsion_N']))
        if sig in seen:
            continue
        seen.add(sig)
        # torsion the group carries: V_t = M r / sum(r^2)  ->  M = V_t * sum(r^2) / r,
        # and for a circular pattern of N bolts at radius r that is V_t * N * r
        M = w['V_torsion_N'] * v['bolts'] * r_p / 1000.0 * (18.0 / r_p)   # N*m at the measured PCD
        M_nmm = M * 1000.0
        # friction still helps: each bolt can hold mu*(F_pre - T) of shear
        fric_per_bolt = w['slip_margin'] * w['V_N']
        M_fric = fric_per_bolt * v['bolts'] * 18.0 / 1000.0
        M_left = max(0.0, M - M_fric)
        F_pin = M_left * 1000.0 / (pins * r_p)
        tau = F_pin / A
        brg = F_pin / (dia * PLATE_T)
        out[k] = dict(torsion_Nm=round(M, 1), friction_Nm=round(M_fric, 1),
                      residual_Nm=round(M_left, 1), force_per_pin_N=round(F_pin, 0),
                      pin_shear_SF=round(0.6 * PIN_RM / max(tau, 1e-9), 2),
                      hole_bearing_SF=round(AL_BEARING / max(brg, 1e-9), 2),
                      pins=pins, dia_mm=dia, radius_mm=r_p)
        print(f'{k[:42]:42s} {M:8.1f}N·m {M_fric:8.1f}N·m {M_left:8.1f}N·m '
              f'{F_pin:8.0f}N {out[k]["pin_shear_SF"]:9.2f} {out[k]["hole_bearing_SF"]:11.2f}')
    json.dump(out, open(f'{W}/dowels.json', 'w'), indent=1)
    print(f'\n-> {W}/dowels.json')
    worst = min((v['pin_shear_SF'], v['hole_bearing_SF']) for v in out.values()) if out else None
    if worst:
        print(f'governing margins across the three flanges: pin shear {worst[0]}, '
              f'hole bearing {worst[1]}')


if __name__ == '__main__':
    main()
