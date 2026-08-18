"""The PLA answer on a sourced basis, per part and per link, with stiffness as well as strength.

Replaces the placeholder material numbers in pla_screen.py with datasheet and literature
values, and adds the criterion the strength screen cannot see.

MATERIAL (sourced, not recalled):
  Prusament PLA TDS v1.1 (ISO 527-1, PRINTED specimens, 100 % rectilinear infill)
    tensile yield 51 +- 3 MPa horizontal · INTERLAYER ADHESION 17 +- 3 MPa
    tensile modulus 2.3 GPa · HDT 55 C at both 0.45 and 1.80 MPa · density 1.24 g/cm3
  Ezeh & Susmel, AM-PLA fatigue re-analysis (Procedia Struct. Integrity 2018 /
  Int. J. Fatigue 2019): reference design curve, negative inverse slope k = 5.5,
    ENDURANCE LIMIT AT 2e6 CYCLES = 10 % OF UTS at >95 % survival, and mean stress is
    captured by the MAXIMUM stress in the cycle - so for a pulsating gait load it is the
    peak, not the amplitude, that must stay under it.

Why fatigue and not creep governs (this corrects the first pass, which reached a similar
number by the wrong route): the ankle sees ~2.2e6 cycles per 100 h of walking, so the
2e6-cycle endurance limit is not an asymptote the robot approaches - it is reached in about
90 hours. A part sized on static strength would fail by fatigue first.

STIFFNESS. Deflection scales exactly as 1/E under linear elasticity, so the ratio needs no
new solve: it is 69.0 / 2.3 = 30x for identical geometry. The absolute numbers come from the
campaign's own unit-load solves, whose .frd files carry the DISP block.

Usage: pla_verdict.py [--out docs/img]
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import femlib as FL  # noqa: E402

W = '/home/syaro/pyg_fea/work'

AL_YIELD, E_AL, RHO_AL = 276.0, 69000.0, 2.70
PLA_UTS_XY, PLA_INTERLAYER = 51.0, 17.0
E_PLA, RHO_PLA = 2300.0, 1.24
FATIGUE_FRAC = 0.10        # endurance limit / UTS at 2e6 cycles, PS>95 % (Ezeh & Susmel)
SF = 1.5                   # on top of a curve already at 95 % survival
HDT_C = 55.0

UNIT_F = 1000.0            # N, the campaign's unit force case


def allowables():
    """(name, MPa, basis) - the ladder, most to least permissive."""
    return [
        ('정적·면내 (프로토타입)', PLA_UTS_XY / 2.0, 'Prusament 51 MPa / SF2, 단기·면내'),
        ('정적·층간', PLA_INTERLAYER / SF, f'실측 층간 {PLA_INTERLAYER:.0f} MPa / SF{SF}'),
        ('★피로·면내 (2e6 cyc)', PLA_UTS_XY * FATIGUE_FRAC / SF,
         f'Ezeh&Susmel 0.10x{PLA_UTS_XY:.0f} / SF{SF}'),
        ('★피로·층간', PLA_INTERLAYER * FATIGUE_FRAC / SF,
         f'0.10x{PLA_INTERLAYER:.0f} / SF{SF}'),
        ('모터 체결부 (HDT 55 C)', 0.0, 'RS03/RS04 하우징 온도가 HDT를 넘음 — 불허'),
    ]


def deflection(link):
    """Max nodal displacement under the campaign's unit force cases [mm], Al."""
    env = f'{W}/{link}/envelope_P99.json'
    if not os.path.exists(env):
        return None
    d = json.load(open(env))
    comps, mags = d.get('comps'), d.get('magnitudes')
    if not comps or not mags:
        return None
    best = None
    for c in comps:
        if not c.startswith('F'):
            continue
        f = f'{W}/{link}/{link}_u{c}.frd'
        if not os.path.exists(f):
            continue
        _, blocks = FL.parse_frd(f)
        disp = next((v for k, v in blocks if 'DISP' in k.upper()), None)
        if not disp:
            continue
        U = np.array(list(disp.values()), float)[:, :3]
        umax = float(np.linalg.norm(U, axis=1).max())
        scaled = umax * mags[c] / UNIT_F        # to the design load magnitude
        if best is None or scaled > best[1]:
            best = (c, scaled, umax)
    return best


def main():
    P = json.load(open(f'{W}/part_screen.json'))
    lad = allowables()
    a_fat_xy = lad[2][1]
    a_fat_z = lad[3][1]

    print('PLA 허용응력 — 출처 기반')
    for n, v, b in lad:
        print(f'   {n:26s} {v:6.2f} MPa   ({b})')
    print(f'   (참고) 6061-T6 SF2      {AL_YIELD/2:6.1f} MPa')

    for r in P:
        r['sf_al'] = (AL_YIELD / 2) / max(r['p99'], 1e-9)
        r['sf_pla_xy'] = a_fat_xy / max(r['p99'], 1e-9)
        r['sf_pla_z'] = a_fat_z / max(r['p99'], 1e-9)
    P.sort(key=lambda r: -r['p99'])

    n = len(P)
    vt = sum(r['vol_cm3'] for r in P)
    for nm, key, allow in (('정적·면내 25.5', None, PLA_UTS_XY / 2),
                           ('정적·층간 11.3', None, PLA_INTERLAYER / SF),
                           ('★피로·면내 3.40', 'sf_pla_xy', a_fat_xy),
                           ('★피로·층간 1.13', 'sf_pla_z', a_fat_z)):
        ok = [r for r in P if r['p99'] <= allow]
        print(f'\nPLA {nm} MPa 기준 통과: {len(ok):3d}/{n} 부품 '
              f'({100*len(ok)/n:.0f} %) · 체적 {sum(r["vol_cm3"] for r in ok):.0f}/{vt:.0f} cm³')
        for r in sorted(ok, key=lambda r: -r['vol_cm3'])[:6]:
            print(f'    {r["link"]:22s} {r["part"]:9s} {r["label"]:13s} '
                  f'{r["vol_cm3"]:6.1f}cm³  p99 {r["p99"]:5.2f} MPa')

    print(f'\n6061-T6 SF2 통과: {sum(1 for r in P if r["sf_al"] >= 1)}/{n} 부품')
    print(f'최악 부품(알루미늄): {P[0]["link"]} {P[0]["part"]} {P[0]["label"]} '
          f'{P[0]["p99"]:.1f} MPa, SF {P[0]["sf_al"]:.2f}')

    print(f'\n강성 — 처짐은 1/E로 정확히 스케일. E_Al {E_AL/1000:.0f} / '
          f'E_PLA {E_PLA/1000:.1f} GPa = **{E_AL/E_PLA:.0f}배**')
    print(f"{'링크':22s} {'지배':6s} {'알루미늄':>9s} {'PLA':>9s}")
    for link in sorted({r['link'] for r in P}):
        dd = deflection(link)
        if not dd:
            continue
        c, u, _ = dd
        print(f'{link:22s} {c:6s} {u:8.2f}mm {u*E_AL/E_PLA:8.1f}mm')

    json.dump(P, open(f'{W}/pla_verdict.json', 'w'), indent=1, ensure_ascii=False)
    print(f'\n-> {W}/pla_verdict.json')


if __name__ == '__main__':
    main()
