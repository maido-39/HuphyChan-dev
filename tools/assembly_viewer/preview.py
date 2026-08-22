"""Static preview of the assembly viewer's data - a sanity check that does not need a browser.

Draws the robot's collision hulls behind every fastener the viewer will show, coloured by
designation, so the screw positions can be checked against the geometry at a glance.

Usage: preview.py   (mjlab .venv python; writes docs/img/assembly_fasteners.png)
"""
import json
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402
import mujoco                            # noqa: E402

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
sys.path.insert(0, f'{REPO}/tools/robot_model')
from validate_robot import draw          # noqa: E402

DATA = f'{REPO}/tools/assembly_viewer/screws.json'
XML = f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/pygmalion_v2.xml'
OUT = f'{REPO}/docs/img/assembly_fasteners.png'


def main():
    d = json.load(open(DATA))
    m = mujoco.MjModel.from_xml_path(XML)
    dd = mujoco.MjData(m)
    dd.qpos[:] = 0
    dd.qpos[3] = 1.0
    mujoco.mj_forward(m, dd)

    kinds = {}
    for s in d['screws']:
        kinds.setdefault(f"{s['size']} {s['head']}", []).append(s)
    order = sorted(kinds, key=lambda k: -len(kinds[k]))
    cmap = plt.get_cmap('tab20')
    col = {k: cmap(i % 20) for i, k in enumerate(order)}

    fig, ax = plt.subplots(1, 2, figsize=(11.5, 7.0))
    for a, view in zip(ax, ('side', 'front')):
        draw(a, m, dd, view, group=4)
        for k in order:
            P = np.array([s['pos'] for s in kinds[k]])
            M_ = np.array([[p[0], p[2]] if view == 'side' else [p[1], p[2]] for p in P])
            a.scatter(M_[:, 0], M_[:, 1], s=16, color=col[k], edgecolors='k',
                      linewidths=0.25, zorder=5, label=k if view == 'side' else None)
            if view == 'front':          # the CAD has one side; the viewer mirrors it
                mir = np.array([[-p[1], p[2]] for p in P])
                a.scatter(mir[:, 0], mir[:, 1], s=16, color=col[k], alpha=0.35,
                          edgecolors='none', zorder=4)
        a.set_title(f'{view} — {len(d["screws"])} fasteners in the CAD'
                    + ('  (faint = mirrored side)' if view == 'front' else ''), fontsize=10)
    ax[0].legend(fontsize=7, loc='upper left', bbox_to_anchor=(1.02, 1.0),
                 frameon=False, ncol=1)
    fig.suptitle('Assembly viewer data: every fastener, coloured by designation '
                 f'({"oriented" if d["oriented"] else "position only"})', fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT, dpi=130)
    print(f'-> {OUT}')
    for k in order:
        print(f'  {len(kinds[k]):4d}  {k}')


if __name__ == '__main__':
    main()
