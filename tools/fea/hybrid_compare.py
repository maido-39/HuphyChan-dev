"""Hybrid builds: what actually happens when one solid is printed instead of milled.

A PLA solid inside an aluminium assembly is 30x more compliant, so it does not simply
"carry its old stress in a weaker material" - it SHEDS load to whatever is stiff next to
it. Two things therefore have to be checked together, and neither is visible in a screen
that only compares stress against an allowable:

  the substituted part   its stress DROPS. The question is whether it drops far enough to
                         clear the PLA fatigue allowable (~3.9 MPa in-plane best case).
  its neighbours         their stress RISES by whatever the soft part shed. The question
                         is whether the link still clears in aluminium afterwards.

and a third, at link level: the assembly gets more compliant, so deflection grows.

The hybrid twins are solved on the SAME mesh as their aluminium baseline (copied in
deliberately), so the only difference between the two runs is the material of the named
solids - any change in the field is attributable to the substitution and nothing else.

Usage: hybrid_compare.py [HYBRID ...] [--out docs/img]
"""
import json
import os
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from part_screen import analyse as part_analyse  # noqa: E402

W = '/home/syaro/pyg_fea/work'
AL_ALLOW = 138.0            # 6061-T6, SF 2
PLA_ALLOW = 3.9             # in-plane fatigue best case (docs/79 §10d)
PLA_ALLOW_Z = 0.73          # interlayer, the conservative end


def specs():
    return json.load(open(f'{HERE}/link_specs.json'))


def main():
    out = next((a.split('=')[1] for a in sys.argv if a.startswith('--out=')),
               '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img')
    S = specs()
    names = [a for a in sys.argv[1:] if not a.startswith('--')] or \
        [k for k, v in S.items() if isinstance(v, dict) and v.get('_hybrid_of')]
    assert names, 'no hybrid specs found (they carry _hybrid_of)'

    cards = []
    for h in names:
        base = S[h]['_hybrid_of']
        sub = {x.upper() for x in S[h]['pla_parts']}
        if not os.path.exists(f'{W}/{h}/envelope_P99.json'):
            print(f'{h:24s} not solved yet - skipped')
            continue
        A = {r['part'].upper(): r for r in (part_analyse(base) or [])}
        B = {r['part'].upper(): r for r in (part_analyse(h) or [])}
        assert A and B, f'{h}: part analysis failed'
        assert set(A) == set(B), (
            f'{h}: the hybrid has different element sets than {base} - '
            'the meshes are not the same, so the comparison is not controlled')
        eA = json.load(open(f'{W}/{base}/envelope_P99.json'))
        eB = json.load(open(f'{W}/{h}/envelope_P99.json'))
        rows = []
        for k in sorted(A, key=lambda k: -A[k]['p99']):
            rows.append(dict(part=k, pla=k in sub, label=A[k]['label'],
                             vol=A[k]['vol_cm3'], before=A[k]['p99'], after=B[k]['p99'],
                             delta=100 * (B[k]['p99'] - A[k]['p99']) / max(A[k]['p99'], 1e-9)))
        cards.append(dict(name=h, base=base, sub=sub, rows=rows,
                          link_before=eA.get('p99_vM'), link_after=eB.get('p99_vM'),
                          pt_before=eA.get('max_vM_design'), pt_after=eB.get('max_vM_design')))

        print(f'\n=== {h}   (기준 {base}, PLA: {", ".join(sorted(sub))})')
        print(f"{'부품':10s} {'위치':13s} {'cm3':>6s} {'전':>7s} {'후':>7s} {'변화':>8s}  판정")
        for r in rows:
            if r['pla']:
                ok = r['after'] <= PLA_ALLOW
                v = f"PLA {'✅' if ok else '❌'} (허용 {PLA_ALLOW})"
            else:
                v = 'Al ✅' if r['after'] <= AL_ALLOW else 'Al ❌'
            mark = '★' if r['pla'] else ' '
            print(f"{mark}{r['part']:9s} {r['label']:13s} {r['vol']:6.1f} {r['before']:7.2f} "
                  f"{r['after']:7.2f} {r['delta']:+7.1f}%  {v}")
        nb = [r for r in rows if not r['pla']]
        worst = max(nb, key=lambda r: r['delta']) if nb else None
        print(f"  링크 필드 p99 {eA.get('p99_vM', 0):.1f} -> {eB.get('p99_vM', 0):.1f} MPa "
              f"({100*(eB.get('p99_vM', 0)-eA.get('p99_vM', 1))/max(eA.get('p99_vM', 1), 1e-9):+.1f} %)"
              f" · SF {AL_ALLOW/max(eB.get('p99_vM', 1e-9), 1e-9):.2f}")
        if worst:
            print(f"  이웃 최대 상승: {worst['part']} {worst['before']:.1f} -> "
                  f"{worst['after']:.1f} MPa ({worst['delta']:+.1f} %)")

    assert cards, 'nothing solved yet'
    # ---- figure ----
    plt.rcParams.update({'figure.dpi': 135, 'font.size': 9})
    n = len(cards)
    fig, ax = plt.subplots(1, n, figsize=(5.0 * n, 5.0), squeeze=False)
    for j, c in enumerate(cards):
        a = ax[0, j]
        rows = c['rows'][:14]
        y = np.arange(len(rows))
        a.barh(y - 0.2, [r['before'] for r in rows], 0.38, color='#7fb3ff', label='all-Al')
        a.barh(y + 0.2, [r['after'] for r in rows], 0.38,
               color=['#c0392b' if r['pla'] else '#2e86c1' for r in rows], label='hybrid')
        a.axvline(PLA_ALLOW, color='#c0392b', ls='--', lw=1.2)
        a.text(PLA_ALLOW * 1.1, len(rows) - 0.5, f'PLA {PLA_ALLOW}', fontsize=7,
               color='#c0392b')
        a.axvline(AL_ALLOW, color='k', ls=':', lw=1.1)
        a.set_yticks(y)
        a.set_yticklabels([('★ ' if r['pla'] else '') + r['part'].replace('VOLUME', 'V')
                           for r in rows], fontsize=7)
        a.invert_yaxis()
        a.set_xscale('log')
        a.set_xlabel('volume-weighted p99 [MPa]')
        a.set_title(f"{c['name']}\nPLA: {', '.join(sorted(c['sub']))}\n"
                    f"link p99 {c['link_before']:.1f} → {c['link_after']:.1f} MPa",
                    fontsize=8.5)
        a.legend(fontsize=7)
        a.grid(alpha=0.3, axis='x')
    fig.suptitle('Hybrid substitution, same mesh: the printed solid sheds load, its '
                 'neighbours take it', fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'hybrid_compare.png'))
    json.dump(cards, open(f'{W}/hybrid_compare.json', 'w'), indent=1, ensure_ascii=False,
              default=lambda o: sorted(o) if isinstance(o, set) else str(o))
    print('\n-> docs/img/hybrid_compare.png')


if __name__ == '__main__':
    main()
