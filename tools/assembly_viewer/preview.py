"""Static preview of the assembly viewer's data - a sanity check that does not need a browser.

It draws THE VIEWER'S OWN mesh list, loaded from `tools/assembly_viewer/meshes` at the exact
positions `screws.json` gives, rather than re-deriving the geometry from the MJCF. That
distinction matters: the viewer once silently dropped the whole hip cluster because its
body-name-to-STL mapping missed `hip_pitch_link.stl`, and a preview drawn from the MJCF would
have looked perfectly fine.

Usage: preview.py   (mjlab .venv python; writes docs/img/assembly_fasteners.png)
"""
import json
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402
import trimesh                           # noqa: E402
from matplotlib.collections import PolyCollection   # noqa: E402

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
DATA = f'{REPO}/tools/assembly_viewer/screws.json'
MESHES = f'{REPO}/tools/assembly_viewer/meshes'
OUT = f'{REPO}/docs/img/assembly_fasteners.png'


def draw_links(ax, links, ix, iy, depth_axis):
    """Project exactly the STLs the viewer loads, in the order it places them."""
    polys, cols, dep = [], [], []
    for i, l in enumerate(links):
        me = trimesh.load(f'{MESHES}/{l["stl"]}', process=False)
        V = np.asarray(me.vertices) + np.array(l['pos'])
        F = np.asarray(me.faces)
        n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        lam = np.clip(0.4 + 0.6 * np.abs(n @ np.array([0.4, -0.7, 0.6])), 0, 1)
        base = np.array([0.62, 0.66, 0.72])   # one neutral grey so the coloured screws read
        polys.append(V[F][:, :, [ix, iy]])
        cols.append(np.clip(base * lam[:, None], 0, 1))
        dep.append(V[F][:, :, depth_axis].mean(1))
    P, C, D = np.vstack(polys), np.vstack(cols), np.concatenate(dep)
    o = np.argsort(D)
    ax.add_collection(PolyCollection(P[o], facecolors=C[o], edgecolors='none',
                                     alpha=0.45, rasterized=True))
    ax.set_aspect('equal')


def main():
    d = json.load(open(DATA))

    kinds = {}
    for s in d['screws']:
        kinds.setdefault(f"{s['size']} {s['head']}", []).append(s)
    order = sorted(kinds, key=lambda k: -len(kinds[k]))
    cmap = plt.get_cmap('tab20')
    col = {k: cmap(i % 20) for i, k in enumerate(order)}

    fig, ax = plt.subplots(1, 2, figsize=(11.5, 7.0))
    for a, view in zip(ax, ('side', 'front')):
        ix, iy = (0, 2) if view == 'side' else (1, 2)
        draw_links(a, d['links'], ix, iy, 1 if view == 'side' else 0)
        for k in order:
            P = np.array([s['pos'] for s in kinds[k]])
            M_ = P[:, [ix, iy]]
            a.scatter(M_[:, 0], M_[:, 1], s=16, color=col[k], edgecolors='k',
                      linewidths=0.25, zorder=5, label=k if view == 'side' else None)
            # a tick down the screw axis, scaled to the real length, so the direction the
            # bolt goes in is visible and not just where it sits
            A = np.array([s['axis'] for s in kinds[k]])
            L = np.array([float(s['size'].split('x')[1]) if 'x' in s['size'] else 10.0
                          for s in kinds[k]]) / 1000.0
            a.quiver(M_[:, 0], M_[:, 1], A[:, ix] * L, A[:, iy] * L, color=col[k],
                     angles='xy', scale_units='xy', scale=1, width=0.0035,
                     headwidth=3.5, headlength=4, zorder=6)
            if view == 'front':          # the CAD has one side; the viewer mirrors it
                mir = np.array([[-p[1], p[2]] for p in P])
                a.scatter(mir[:, 0], mir[:, 1], s=16, color=col[k], alpha=0.35,
                          edgecolors='none', zorder=4)
        a.set_title(f'{view} — {len(d["screws"])} fasteners, {len(d["links"])} link meshes'
                    + ('  (faint = mirrored side)' if view == 'front' else ''), fontsize=10)
        a.autoscale_view()
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
