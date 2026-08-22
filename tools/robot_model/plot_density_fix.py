"""Figure: what the placeholder density correction changed, part by part.

Left panel - the motors and bearings that were still at the CAD default (Steel 7850, and
one bearing at Aluminium 2700) against their manufacturer mass. Right panel - the density
each placeholder now carries, with the 7850 default marked, which is also the evidence that
the two big motors are hollow shells at the right envelope rather than shrunken solids.

Usage: plot_density_fix.py   (mjlab .venv python; writes docs/img/placeholder_density_fix.png)
"""
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
BEFORE = '/home/syaro/pyg_fea/fusion/bodies_predensity.json'
AFTER = '/home/syaro/pyg_fea/fusion/bodies.json'
FIX = '/home/syaro/pyg_fea/fusion/density_fix.json'
OUT = f'{REPO}/docs/img/placeholder_density_fix.png'
# placeholder envelope (mm) measured in Fusion vs the catalogue outline
ENVELOPE = {'RS04': ((120.0, 120.0, 55.7), (120, 120, 56)),
            'RS03': ((99.5, 98.5, 56.6), (106, 106, 56)),
            'RS02': ((83.5, 83.5, 45.4), (78.5, 78.5, 41.5)),
            'RS00': ((57.0, 57.0, 51.4), (57, 57, 51))}


def main():
    old, new = json.load(open(BEFORE)), json.load(open(AFTER))
    rep = json.load(open(FIX))['report']
    rows = []
    for e in rep:
        occ = e['path'].split('/')[-1].split(':')[0].replace('Robstride ', '')
        before = sum(v['m'] for k, v in old.items()
                     if k.startswith(e['path'] + '::') and v.get('live', True)) * 1000.0
        after = sum(v['m'] for k, v in new.items()
                    if k.startswith(e['path'] + '::') and v['live']) * 1000.0
        rows.append((occ, before, after, e['want_g'], e['bodies'][0][3]))
    rows.sort(key=lambda r: -r[2])

    fig, ax = plt.subplots(1, 2, figsize=(13.0, 6.6), gridspec_kw={'width_ratios': [1.3, 1]})
    y = np.arange(len(rows))
    ax[0].barh(y + 0.20, [r[1] for r in rows], 0.38, label='CAD placeholder before',
               color='#c94c4c')
    ax[0].barh(y - 0.20, [r[2] for r in rows], 0.38, label='after density fix',
               color='#3d7ea6')
    ax[0].plot([r[3] for r in rows], y - 0.20, 'k|', ms=13, mew=1.6,
               label='manufacturer catalogue')
    for i, r in enumerate(rows):
        d = r[1] - r[2]
        if abs(d) >= 1.0:
            ax[0].text(max(r[1], r[2]) * 1.12, i, f'{-d:+.0f} g', va='center', fontsize=7.5)
    ax[0].set_yticks(y)
    ax[0].set_yticklabels([r[0] for r in rows], fontsize=8)
    ax[0].set_xlabel('mass per occurrence [g], log scale')
    ax[0].set_title('Placeholder mass: CAD default vs catalogue', fontsize=10)
    ax[0].legend(fontsize=8, loc='upper center', bbox_to_anchor=(0.5, -0.10), ncol=3,
                 frameon=False)
    ax[0].grid(axis='x', alpha=0.3)
    ax[0].set_xscale('log')                  # bearings are 9 g, motors 1420 g
    ax[0].set_xlim(5, max(r[1] for r in rows) * 3.2)

    dens = [(r[0], r[4]) for r in rows]
    ax[1].barh(np.arange(len(dens)), [d[1] for d in dens], 0.62, color='#6a9c78')
    ax[1].axvline(7850, color='k', ls='--', lw=1.1, label='CAD default: Steel 7850')
    ax[1].axvline(2700, color='gray', ls=':', lw=1.1, label='Aluminium 2700')
    ax[1].set_yticks(np.arange(len(dens)))
    ax[1].set_yticklabels([d[0] for d in dens], fontsize=8)
    ax[1].set_xlabel(r'density now assigned [kg/m$^3$]')
    ax[1].set_title('Density assigned to hit the catalogue mass', fontsize=10)
    ax[1].legend(fontsize=8, loc='upper center', bbox_to_anchor=(0.5, -0.10), ncol=2,
                 frameon=False)
    ax[1].grid(axis='x', alpha=0.3)
    txt = ('Envelope check (measured bbox vs catalogue outline, mm)\n' + '\n'.join(
        f'  {k}: {p[0]:.0f}x{p[1]:.0f}x{p[2]:.1f}  vs  {c[0]}x{c[1]}x{c[2]}'
        for k, (p, c) in ENVELOPE.items()))
    ax[1].set_xlim(0, 10200)
    fig.suptitle('Pygmalion CAD placeholders brought to manufacturer mass by density '
                 '(2026-08-22)', fontsize=11)
    fig.tight_layout(rect=(0, 0.20, 1, 1))
    fig.text(0.56, 0.015, txt, fontsize=7.4, family='monospace', va='bottom',
             bbox=dict(fc='white', ec='0.7', alpha=0.95))
    fig.savefig(OUT, dpi=130)
    print(f'-> {OUT}')
    print(f'total placeholder mass {sum(r[1] for r in rows) / 1000:.3f} -> '
          f'{sum(r[2] for r in rows) / 1000:.3f} kg')


if __name__ == '__main__':
    main()
