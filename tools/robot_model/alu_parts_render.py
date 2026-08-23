"""Render each aluminium part on its own, filling the frame, for the 3D-print mass survey.

One PNG per part: nothing else in the picture, no axes, no caption - the name and the mass
live in their own spreadsheet columns. The camera is not fixed: six candidate directions are
projected and the one that shows the most of the part wins, so a flat plate is not handed
back edge-on. Shading is a simple Lambert term over the triangle normals with a painter's
depth sort, which is enough to read a machined shape.

Usage: alu_parts_render.py [--px=460]   (mjlab .venv python)
"""
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt                       # noqa: E402
from matplotlib.collections import PolyCollection     # noqa: E402

OUT = '/home/syaro/pyg_fea/fusion/alu_parts'
IMG = f'{OUT}/img'
# candidate camera directions (azimuth deg, elevation deg)
VIEWS = [(35, 22), (-35, 22), (125, 22), (35, -22), (0, 70), (90, 15)]


def basis(az, el):
    a, e = np.radians(az), np.radians(el)
    fwd = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(up, fwd)
    right /= np.linalg.norm(right)
    up = np.cross(fwd, right)
    return right, up, fwd


def render(V, F, path, px=460):
    best = None
    for az, el in VIEWS:
        r, u, f = basis(az, el)
        P = np.column_stack([V @ r, V @ u])
        tri = P[F]
        # signed area of every projected triangle, summed as visible area
        e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
        a = 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum()
        if best is None or a > best[0]:
            best = (a, r, u, f, P)
    _, r, u, fwd, P = best
    tri = P[F]
    D = (V @ fwd)[F].mean(1)
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    light = (r * 0.35 + u * 0.55 - fwd * 0.75)
    light /= np.linalg.norm(light)
    lam = np.clip(0.30 + 0.70 * np.abs(n @ light), 0, 1)
    base = np.array([0.72, 0.745, 0.78])              # anodised-aluminium grey
    cols = np.clip(base * lam[:, None], 0, 1)
    o = np.argsort(D)[::-1]

    lo, hi = P.min(0), P.max(0)
    span = float(max(hi - lo))
    pad = span * 0.06
    cx, cy = (lo + hi) / 2
    fig = plt.figure(figsize=(px / 100, px * 0.75 / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    # no wireframe: a visible mesh reads as a mesh, not as the part. Shading alone carries
    # the shape, with a hairline of the face colour itself to close the seams between
    # triangles that antialiasing would otherwise leave.
    ax.add_collection(PolyCollection(tri[o], facecolors=cols[o], edgecolors=cols[o],
                                     linewidths=0.3))
    ax.set_aspect('equal')
    half_w = max(span * 0.5 + pad, (hi[0] - lo[0]) * 0.5 + pad)
    half_h = half_w * 0.75
    if (hi[1] - lo[1]) * 0.5 + pad > half_h:
        half_h = (hi[1] - lo[1]) * 0.5 + pad
        half_w = half_h / 0.75
    ax.set_xlim(cx - half_w, cx + half_w)
    ax.set_ylim(cy - half_h, cy + half_h)
    ax.axis('off')
    fig.patch.set_facecolor('white')
    fig.savefig(path, dpi=100, facecolor='white')
    plt.close(fig)


def main():
    px = int(next((a.split('=')[1] for a in sys.argv if a.startswith('--px=')), 460))
    os.makedirs(IMG, exist_ok=True)
    meta = json.load(open(f'{OUT}/index.json'))
    z = np.load(f'{OUT}/all_meshes.npz')       # one key space, built by alu_parts_merge.py
    Z = {k: z[k] for k in z.files}
    done, missing = 0, []
    for r in meta:
        k = r['key']
        if f'{k}|v' not in Z:
            missing.append(r)
            continue
        V, F = np.asarray(Z[f'{k}|v'], float), np.asarray(Z[f'{k}|f'], int)
        V = V - V.mean(0)
        out = f'{IMG}/{k}.png'
        render(V, F, out, px)
        r['img'] = out
        done += 1
    json.dump(meta, open(f'{OUT}/index.json', 'w'), indent=1, ensure_ascii=False)
    print(f'rendered {done}/{len(meta)} parts -> {IMG}')
    if missing:
        print(f'{len(missing)} without a mesh yet:')
        for r in missing:
            print(f'   {r["link"][:20]:20s} {r["occ"][:26]:26s} {r["body"][:20]:20s}')


if __name__ == '__main__':
    main()
