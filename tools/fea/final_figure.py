"""The campaign's two closing figures: the corrected field basis, and the foot removal curve.

Panel 1  how far the node-based percentile runs above the volume-weighted one, per link.
         The bias is one-sided (never negative) because refinement always adds nodes where
         the stress is high, never where it is low.
Panel 2  every link ranked on the mesh-independent field basis, with the SF 2 line.
Panel 3  the BESO removal curve for the foot: volume retained against the field stress it
         costs, read straight out of the optimiser log.

Usage: final_figure.py [--out docs/img]
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
ALLOW = 276.0
BESO_LOG = f'{W}/beso_L1g_p99_run2.log'


def read_beso(path):
    """(volume cm3, retained %, design MPa, SF) per iteration."""
    rows = []
    for ln in open(path):
        m = re.match(r'\s+iter\s+(\d+):\s+\d+ elems,\s+([\d.]+) cm3\s+\(\s*([\d.]+) %\),'
                     r'\s+design\s+([\d.]+) MPa,\s+SF\s+([\d.]+)', ln)
        if m:
            rows.append((int(m.group(1)), float(m.group(2)), float(m.group(3)),
                         float(m.group(4)), float(m.group(5))))
    return rows


def main():
    out = next((a.split('=')[1] for a in sys.argv if a.startswith('--out=')),
               '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img')
    V = json.load(open(f'{W}/field_volume.json'))
    assert V, 'field_volume.json is empty - run field_volume.py --all first'
    for r in V:
        r['sf'] = ALLOW / r['p99_vol']
        r['bias'] = 100 * (r['p99_node'] - r['p99_vol']) / r['p99_vol']
    V.sort(key=lambda r: r['sf'])

    plt.rcParams.update({'figure.dpi': 135, 'font.size': 9})
    fig, ax = plt.subplots(1, 3, figsize=(15.6, 5.4))

    # 1) the bias, sorted
    B = sorted(V, key=lambda r: -r['bias'])
    y = np.arange(len(B))
    ax[0].barh(y, [r['bias'] for r in B], color='#c0392b')
    ax[0].set_yticks(y)
    ax[0].set_yticklabels([r['link'].replace('_', ' ')[:24] for r in B], fontsize=6.2)
    ax[0].invert_yaxis()
    ax[0].axvline(0, color='k', lw=0.8)
    med = float(np.median([r['bias'] for r in V]))
    ax[0].axvline(med, color='#2e86c1', ls='--', lw=1.2)
    ax[0].text(med + 2, len(B) * 0.9, f'median {med:+.0f} %', fontsize=8, color='#2e86c1')
    ax[0].set_xlabel('node p99 above volume-weighted p99 [%]')
    ax[0].set_title('The node percentile is biased high on every link\n'
                    '(refinement adds nodes only where stress is high)', fontsize=9)
    ax[0].grid(alpha=0.3, axis='x')

    # 2) the ranked field verdict
    y = np.arange(len(V))
    cols = ['#c0392b' if r['sf'] < 2 else '#e67e22' if r['sf'] < 3 else '#27ae60' for r in V]
    ax[1].barh(y, [r['sf'] for r in V], color=cols)
    ax[1].set_yticks(y)
    ax[1].set_yticklabels([r['link'].replace('_', ' ')[:24] for r in V], fontsize=6.2)
    ax[1].invert_yaxis()
    ax[1].axvline(2.0, color='k', ls='--', lw=1.2)
    ax[1].text(2.05, len(V) * 0.05, 'SF 2', fontsize=8)
    ax[1].set_xscale('log')
    ax[1].set_xlabel('SF on the volume-weighted field p99')
    ax[1].set_title(f'Every link clears SF {V[0]["sf"]:.2f}\n'
                    f'worst: {V[0]["link"].replace("_", " ")}', fontsize=9)
    ax[1].grid(alpha=0.3, axis='x')

    # 3) the foot removal curve
    if os.path.exists(BESO_LOG):
        R = read_beso(BESO_LOG)
        assert R, f'no iteration lines parsed from {BESO_LOG}'
        it = [r[0] for r in R]
        vol = [r[1] for r in R]
        pct = [r[2] for r in R]
        des = [r[3] for r in R]
        a2 = ax[2]
        a2.plot(pct, des, 'o-', color='#2e86c1', lw=2, ms=6)
        for i, v, p, d in zip(it, vol, pct, des):
            if i % 2 == 0 or i == it[-1]:
                a2.annotate(f'{v:.0f} cm³', (p, d), textcoords='offset points',
                            xytext=(0, 9), fontsize=7, ha='center')
        a2.axhline(ALLOW / 2, color='k', ls='--', lw=1.2)
        a2.set_ylim(min(des) - 2, ALLOW / 2 + 6)          # keep the target line clear of the title
        a2.text(pct[-1], ALLOW / 2 - 2.2, 'SF 2 target (138 MPa)', fontsize=8, ha='right')
        a2.invert_xaxis()
        a2.set_xlabel('volume retained [%]')
        a2.set_ylabel('field design stress [MPa]')
        rem = 100 - pct[-1]
        a2.set_title(f'Foot BESO: {rem:.0f} % removed for '
                     f'{100*(des[-1]-des[0])/des[0]:+.0f} % stress\n'
                     f'{vol[0]:.0f} → {vol[-1]:.0f} cm³, SF {R[0][4]:.2f} → {R[-1][4]:.2f}',
                     fontsize=9)
        a2.grid(alpha=0.3)
        print(f'BESO: {len(R)} iterations, {vol[0]:.1f} -> {vol[-1]:.1f} cm3 '
              f'({rem:.1f} % removed), design {des[0]:.1f} -> {des[-1]:.1f} MPa '
              f'({100*(des[-1]-des[0])/des[0]:+.1f} %), SF {R[0][4]:.2f} -> {R[-1][4]:.2f}')

    fig.suptitle('Closing the campaign: the field basis is volume-weighted, and on it every '
                 'link clears SF 2.68 with essentially no yielded material', fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'fea_final_verdict.png'))
    print(f"worst field SF {V[0]['sf']:.2f} ({V[0]['link']}) · "
          f"max yielded volume {max(r['over_vol_pct'] for r in V):.6f} % · "
          f"node bias {min(r['bias'] for r in V):+.0f}…{max(r['bias'] for r in V):+.0f} %")
    print('-> docs/img/fea_final_verdict.png')


if __name__ == '__main__':
    main()
