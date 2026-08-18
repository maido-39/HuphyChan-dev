"""6061-T6 vs PLA on a SYMMETRIC basis - the same knockdowns applied to both.

Raised by the user, and correctly: the raw strengths differ by 276/51 = 5.4x, but the
first pass compared PLA's fully-derated allowable (2 MPa) against aluminium's plain
static one (276/2 = 138 MPa) and so reported a 69x gap. That is apples to oranges. Every
derate applied to PLA - anisotropy, fatigue, creep, temperature - has an aluminium
counterpart, and some of them are not small.

This builds the ladder for both materials side by side, so the gap can be attributed:

  step            6061-T6                          PLA (FDM)
  raw             276 MPa yield                    51 MPa printed XY yield
  anisotropy      x1.00  isotropic                 x0.33  interlayer 17 MPa measured
  fatigue @2e6    x0.34  S_N 95 (Goodman, R-0.3)   x0.10  Ezeh & Susmel design curve
  creep @RT       x1.00  none                      x0.80  judgement, weakest link
  temperature     x0.95  at 60 C                   x0.70  (disqualified above HDT 55 C)

and then judges the measured volume-weighted field against BOTH, at each rung, so it is
visible which rung actually decides the answer.

The aluminium fatigue side reuses the campaign's own screen (fatigue.py): S_N(2.2e6)
= 124 x K_surface x K_size = 95 MPa, S_u = 310, R = -0.3 for forces, Goodman.

Usage: material_compare.py [--out docs/img]
"""
import json
import os
import re
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

W = '/home/syaro/pyg_fea/work'

AL = dict(name='6061-T6', raw=276.0, aniso=1.00, fat=95.0 / 276.0, creep=1.00, temp=0.95)
PLA = dict(name='PLA (FDM)', raw=51.0, aniso=17.0 / 51.0, fat=0.10, creep=0.80, temp=0.70)
S_N_AL, S_U_AL, R_LOAD = 95.0, 310.0, -0.3
STATIC_FACTOR = 1.25       # the design tier already carries it; fatigue must not double it
SF = 1.3


def goodman_allow(S_N, S_u, R):
    """The sigma_max a Goodman line permits at SF 1, for this load ratio."""
    a = (1 - R) / 2
    m = (1 + R) / 2
    return 1.0 / (a / S_N + max(0.0, m) / S_u)


def ladder(M):
    """Cumulative allowable after each rung [MPa]."""
    out = [('raw', M['raw'])]
    v = M['raw'] * M['aniso']
    out.append(('anisotropy', v))
    v *= M['fat']
    out.append(('fatigue 2e6', v))
    v *= M['creep']
    out.append(('creep', v))
    v *= M['temp']
    out.append(('temperature', v))
    out.append((f'/ SF {SF}', v / SF))
    return out


def main():
    out = next((a.split('=')[1] for a in sys.argv if a.startswith('--out=')),
               '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img')
    V = {r['link']: r for r in json.load(open(f'{W}/field_volume.json')) if r.get('p99_vol')}
    parts = {}
    for l, r in V.items():
        p = re.match(r'(L\d)', l).group(1)
        if p not in parts or r['p99_vol'] > parts[p]['s']:
            parts[p] = dict(link=l, s=r['p99_vol'])

    la, lp = ladder(AL), ladder(PLA)
    print(f"{'단계':16s} {'6061-T6':>10s} {'PLA':>9s} {'비':>7s}")
    for (na, va), (npl, vp) in zip(la, lp):
        print(f'{na:16s} {va:10.1f} {vp:9.2f} {va/vp:6.1f}x')
    a_allow, p_allow = la[-1][1], lp[-1][1]

    # the aluminium fatigue check the campaign actually uses, on the FIELD basis
    gm = goodman_allow(S_N_AL, S_U_AL, R_LOAD)
    print(f'\n알루미늄 Goodman 허용 sigma_max (R {R_LOAD}) = {gm:.1f} MPa '
          f'→ 필드 p99 환산 {gm*STATIC_FACTOR:.1f} MPa')
    print(f'PLA 피로 허용 (층간) = {p_allow:.2f} MPa · 면내면 '
          f'{PLA["raw"]*PLA["fat"]*PLA["creep"]*PLA["temp"]/SF:.2f} MPa')

    print(f"\n{'부품':6s} {'측정 p99':>9s} {'Al 정적SF':>10s} {'Al 피로SF':>10s} "
          f"{'PLA 피로SF':>11s}")
    rows = []
    for p in sorted(parts):
        s = parts[p]['s']
        sf_static = (AL['raw'] / 2) / s
        smax = s / STATIC_FACTOR
        sf_fat = gm / smax
        sf_pla = p_allow / s
        rows.append((p, s, sf_static, sf_fat, sf_pla))
        f = '✅' if sf_fat >= 1 else '❌'
        print(f'{p:6s} {s:8.1f}M {sf_static:10.2f} {sf_fat:9.2f}{f} {sf_pla:11.3f}')

    print(f'\n원자재 비 {AL["raw"]/PLA["raw"]:.1f}x → 설계허용 비 {a_allow/p_allow:.0f}x')
    print('  기여: 이방성 {:.1f}x · 피로 {:.1f}x · 크리프+온도 {:.1f}x'.format(
        1 / PLA['aniso'], (AL['fat'] / PLA['fat']),
        1 / (PLA['creep'] * PLA['temp']) * (AL['creep'] * AL['temp'])))

    # ---- figure ----
    plt.rcParams.update({'figure.dpi': 135, 'font.size': 9})
    fig, ax = plt.subplots(1, 2, figsize=(12.4, 4.8))
    x = np.arange(len(la))
    ax[0].step(x, [v for _, v in la], where='mid', lw=2.2, color='#2e86c1', label='6061-T6')
    ax[0].step(x, [v for _, v in lp], where='mid', lw=2.2, color='#c0392b', label='PLA (FDM)')
    for i, ((na, va), (_, vp)) in enumerate(zip(la, lp)):
        ax[0].annotate(f'{va:.0f}', (i, va), xytext=(0, 7), textcoords='offset points',
                       ha='center', fontsize=7.5, color='#2e86c1')
        ax[0].annotate(f'{vp:.1f}', (i, vp), xytext=(0, -13), textcoords='offset points',
                       ha='center', fontsize=7.5, color='#c0392b')
        ax[0].annotate(f'{va/vp:.0f}×', (i, np.sqrt(va * vp)), ha='center', fontsize=7,
                       color='#666')
    ax[0].set_xticks(x)
    ax[0].set_xticklabels([n for n, _ in la], rotation=25, ha='right', fontsize=8)
    ax[0].set_yscale('log')
    ax[0].set_ylabel('allowable [MPa]')
    ax[0].set_title(f'The gap opens rung by rung: {AL["raw"]/PLA["raw"]:.1f}× raw → '
                    f'{a_allow/p_allow:.0f}× at design', fontsize=9.5)
    ax[0].legend(fontsize=8)
    ax[0].grid(alpha=0.3)

    y = np.arange(len(rows))
    w = 0.27
    ax[1].barh(y - w, [r[2] for r in rows], w, color='#7fb3ff', label='Al static (SF2)')
    ax[1].barh(y, [r[3] for r in rows], w, color='#2e86c1', label='Al fatigue (Goodman)')
    ax[1].barh(y + w, [r[4] for r in rows], w, color='#c0392b', label='PLA fatigue')
    ax[1].axvline(1.0, color='k', ls='--', lw=1.2)
    ax[1].set_yticks(y)
    ax[1].set_yticklabels([r[0] for r in rows], fontsize=8)
    ax[1].invert_yaxis()
    ax[1].set_xscale('log')
    ax[1].set_xlabel('safety factor')
    ax[1].set_title('Same measured stress, three bases', fontsize=9.5)
    ax[1].legend(fontsize=7.5)
    ax[1].grid(alpha=0.3, axis='x')
    fig.suptitle('Symmetric comparison — every derate applied to PLA has an aluminium '
                 'counterpart', fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'material_compare.png'))
    print('\n-> docs/img/material_compare.png')


if __name__ == '__main__':
    main()
