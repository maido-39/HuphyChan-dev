"""Aluminium-tapped-thread check for every detected bolt (no nuts in this design).

Every fastener threads straight into 6061-T6, so the weak link is the INTERNAL
(aluminium) thread, not the steel screw:

  * engagement rule: steel-into-aluminium wants L_e >= 2 x D (1.5 x D marginal);
    the 1 x D rule only applies to a steel nut / steel tapping.
  * stripping load  F_strip = A_s * tau_y ,  A_s ~ 0.6 * pi * D * L_e
    (coarse-thread engineering approximation of the internal shear area),
    tau_y = 0.577 * sigma_y = 159 MPa for 6061-T6.
  * usable preload is therefore capped by the ALUMINIUM, not by the bolt grade:
    F_pre_max = F_strip / SF_thread.
  * head seating: preload / head bearing area must stay below the aluminium
    bearing limit, which is what makes LOW-HEAD (소두) screws worth checking --
    their seating area is what carries the clamp force into soft material.

Run: thread_check.py [--json out.json]
"""
import json
import sys
from collections import Counter, defaultdict

import numpy as np

BOLTS = '/home/syaro/pyg_fea/steps/bolts_all.json'
AL_YIELD = 276.0          # 6061-T6 [MPa]
AL_TAU = 0.577 * AL_YIELD
AL_BEARING = 0.9 * AL_YIELD   # embedment limit under a bolt head (conservative)
SF_THREAD = 2.0
# tensile stress area [mm^2] and head bearing dia [mm], coarse pitch
BOLT = {3: dict(As=5.03, head=5.5, p=0.5), 4: dict(As=8.78, head=7.0, p=0.7),
        5: dict(As=14.2, head=8.5, p=0.8), 6: dict(As=20.1, head=10.0, p=1.0)}
GRADE = {'4.6': 240.0, '8.8': 640.0, '12.9': 1100.0}      # proof-ish yield [MPa]
PRELOAD_FRAC = 0.65       # of yield, common assembly target


def strip_force(d, Le):
    """Internal-thread stripping load in aluminium [N]."""
    A_s = 0.6 * np.pi * d * Le
    return A_s * AL_TAU


def main():
    bolts = json.load(open(BOLTS))
    paired = [b for b in bolts if b.get('engagement_mm')]
    rows = []
    for b in paired:
        d = b['nominal']
        Le = b['engagement_mm']
        spec = BOLT[d]
        F_strip = strip_force(d, Le)
        F_allow = F_strip / SF_THREAD
        pre = {g: PRELOAD_FRAC * s * spec['As'] for g, s in GRADE.items()}
        cb = b.get('counterbore')
        head_d = cb['d'] if cb else spec['head']
        A_head = np.pi / 4 * (head_d ** 2 - b['clearance_d'] ** 2)
        rows.append(dict(size=b['size'], d=d, Le=Le, LeD=Le / d, F_strip=F_strip,
                         F_allow=F_allow, pre46=pre['4.6'], pre88=pre['8.8'],
                         A_head=A_head, head_d=head_d,
                         low='LOW-HEAD' in b['head_type'],
                         head_point=b['head_point'], links=b.get('links')))
    print(f'{len(rows)} bolts with a tapped counterpart (all into aluminium, no nuts)\n')
    print('engagement L_e / D distribution:')
    hist = Counter()
    for r in rows:
        k = ('>=2.0D' if r['LeD'] >= 2 else '1.5-2.0D' if r['LeD'] >= 1.5 else
             '1.0-1.5D' if r['LeD'] >= 1.0 else '<1.0D')
        hist[k] += 1
    for k in ('>=2.0D', '1.5-2.0D', '1.0-1.5D', '<1.0D'):
        print(f'   {k:9s} {hist[k]:4d}')
    short = [r for r in rows if r['LeD'] < 1.5]
    print(f'\n{len(short)} bolts below the 1.5xD aluminium guideline')
    for r in sorted(short, key=lambda r: r['LeD'])[:12]:
        print(f"   {r['size']} L_e {r['Le']:5.1f} = {r['LeD']:.2f}D  strip {r['F_strip']/1000:5.1f} kN "
              f"allow {r['F_allow']/1000:5.1f} kN  @ {r['head_point']} {r['links']}")

    print('\nper size: aluminium thread capacity vs assembly preload')
    by = defaultdict(list)
    for r in rows:
        by[r['size']].append(r)
    for s, rs in sorted(by.items()):
        Le = np.array([r['Le'] for r in rs])
        F_allow = np.array([r['F_allow'] for r in rs])
        r0 = rs[0]
        print(f"   {s}: n={len(rs):3d}  L_e {Le.min():4.1f}-{Le.max():4.1f} mm "
              f"({Le.min()/r0['d']:.1f}-{Le.max()/r0['d']:.1f} D)")
        print(f"       allowable preload from the ALU thread (SF {SF_THREAD:.0f}): "
              f"{F_allow.min()/1000:.1f}-{F_allow.max()/1000:.1f} kN")
        print(f"       assembly preload if screws are  4.6: {r0['pre46']/1000:.1f} kN"
              f"   |  8.8: {r0['pre88']/1000:.1f} kN")
        bad46 = sum(r['pre46'] > r['F_allow'] for r in rs)
        bad88 = sum(r['pre88'] > r['F_allow'] for r in rs)
        print(f"       bolts where preload exceeds the alu-thread allowable: "
              f"4.6 -> {bad46},  8.8 -> {bad88}")
        # head seating pressure at the 8.8 preload
        p = np.array([r['pre88'] / r['A_head'] for r in rs])
        print(f"       head seating pressure @8.8 preload: {p.min():.0f}-{p.max():.0f} MPa "
              f"(alu embedment limit ~{AL_BEARING:.0f})"
              f"{'  <-- EXCEEDS' if p.max() > AL_BEARING else ''}")
    low = [r for r in rows if r['low']]
    if low:
        print(f'\nlow-head (소두) bolts: {len(low)}')
        for r in low:
            print(f"   {r['size']} head d{r['head_d']} seating area {r['A_head']:.1f} mm2 "
                  f"-> {r['pre88']/r['A_head']:.0f} MPa @8.8 preload  @ {r['head_point']}")
    if '--json' in sys.argv:
        out = sys.argv[sys.argv.index('--json') + 1]
        json.dump(rows, open(out, 'w'), indent=1, default=float)
        print('wrote', out)


if __name__ == '__main__':
    main()
