"""Printed-part density ratio: measured PLA mass over the CAD mass at aluminium 6061.

Reads tools/robot_model/alu_parts_measured.json, prints mean / median / min / max / std for
the confident set and for everything, and draws one figure: each part's ratio as a bar, the
physical ceiling (PLA 1.24 / Al 2.70 = 0.459) as a line, and the mean with +-1 sd as a band.
The number that matters downstream is 2.70 x mean - the density to give printed parts in
the CAD so the URDF comes out at the real mass.

Usage: alu_parts_ratio.py   (mjlab .venv python; writes docs/img/alu_parts_density_ratio.png)
"""
import json
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
IDX = os.environ.get('ALU_PARTS_DIR', '/home/syaro/pyg_fea/fusion/alu_parts') + '/index.json'
MEAS = f'{REPO}/tools/robot_model/alu_parts_measured.json'
OUT = f'{REPO}/docs/img/alu_parts_density_ratio.png'
CEIL = 1.24 / 2.70
COL = {'high': '#3a9d5d', 'med': '#d9a400', 'low': '#e07b2a'}


def find_part(meta, occ, body):
    """The index row for a measured part: by body name when that is unique, else (occ, body).

    Occurrence names drift between CAD revisions (HipRoll2Yaw is spelled PipRoll2Yaw in the
    8/16 file) while body names do not, so the body name is the stable key.
    """
    hits = [r for r in meta if r['body'] == body]
    if len(hits) == 1:
        return hits[0]
    hits = [r for r in hits if r['occ'].split(':')[0] == occ]
    return hits[0] if len(hits) == 1 else None


def main():
    meta = json.load(open(IDX))
    rows, absent = [], []
    for e in json.load(open(MEAS))['entries']:
        if e['g'] is None:
            continue
        row = find_part(meta, e['occ'], e['body'])
        if row is None:
            absent.append(e['body'])
            continue
        al = row['mass_g']
        rows.append(dict(part=e['body'], conf=e['conf'], al=al, g=e['g'], q=e['g'] / al))
    rows.sort(key=lambda r: r['q'])
    if absent:
        print(f'no denominator in this CAD revision, skipped: {absent}')
    q_all = np.array([r['q'] for r in rows])
    q_med = np.array([r['q'] for r in rows if r['conf'] in ('high', 'med')])

    def st(q):
        return dict(n=len(q), mean=q.mean(), median=np.median(q), min=q.min(), max=q.max(),
                    std=q.std(ddof=1))
    S = {'confident': st(q_med), 'all': st(q_all)}
    for k, s in S.items():
        print(f"{k:10s} n={s['n']:2d}  mean {s['mean']:.3f}  median {s['median']:.3f}  "
              f"min {s['min']:.3f}  max {s['max']:.3f}  sd {s['std']:.3f}  "
              f"-> density {2.70 * s['mean']:.3f} g/cm3")

    fig, ax = plt.subplots(figsize=(11, 6))
    y = np.arange(len(rows))
    ax.barh(y, [r['q'] for r in rows], color=[COL[r['conf']] for r in rows], height=0.7)
    m, sd = S['confident']['mean'], S['confident']['std']
    ax.axvspan(m - sd, m + sd, color='#d9a400', alpha=0.12, label=f'confident mean ± 1 sd  ({m:.3f} ± {sd:.3f})')
    ax.axvline(m, color='#8a6d00', lw=1.4)
    ax.axvline(CEIL, color='#c00000', ls='--', lw=1.3,
               label=f'physical ceiling: PLA 1.24 / Al 2.70 = {CEIL:.3f} (100 % infill)')
    for i, r in enumerate(rows):
        ax.text(r['q'] + 0.006, i, f"{r['g']:.1f} / {r['al']:.0f} g", va='center', fontsize=8,
                color='#333')
    ax.set_yticks(y)
    ax.set_yticklabels([r['part'] for r in rows], fontsize=9)
    ax.set_xlabel('measured printed mass / CAD mass at aluminium 6061')
    ax.set_xlim(0, 0.55)
    ax.set_title(f'Printed-part density ratio — {len(rows)} parts read off the photos '
                 f'(yellow = confident match, orange = verify)', fontsize=11)
    ax.grid(axis='x', alpha=0.3)
    ax.legend(fontsize=8.5, loc='lower right')
    fig.tight_layout()
    fig.savefig(OUT, dpi=130)
    print(f'-> {OUT}')
    json.dump({k: {kk: float(vv) for kk, vv in v.items()} for k, v in S.items()},
              open(f'{REPO}/tools/robot_model/alu_parts_ratio_stats.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
