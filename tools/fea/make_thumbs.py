"""Thumbnail per link (and per part) so the viewer tells you what you are about to open.

Picking a link from a dropdown of names like `L5cf_hip_nomotor_fine` tells you nothing
about which lump of metal that is. This renders each case from its own viewer payload -
same surface triangles the 3D view uses - so the selector can show the part before it
loads 30 MB, and the parts table can show each solid highlighted inside the whole link.

Two products per link:
  thumb_<link>.png        the whole link, shaded, 3/4 view
  thumbpart_<link>.png    a contact sheet: the link ghosted with each solid lit in turn,
                          captioned with its stress, so "VOLUME7" becomes a picture

Rendering is a depth-sorted painter's fill of the payload triangles with a simple lambert
shade - no GL, no extra dependency, and it matches what the viewer draws because it is the
same triangle list.

Usage: make_thumbs.py [LINK ...] [--size=260] [--parts]
"""
import glob
import json
import os
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402

STATIC = '/home/syaro/MikuchanRemote/Human-Pygmalion/tools/wrench_studio/static'
# matplotlib has no Hangul face here, so the Korean positional labels would render as tofu
KO2EN = {'하단': 'low', '중단': 'mid', '상단': 'up', '앞': 'front', '중앙': 'ctr',
         '뒤': 'rear', '좌': 'L', '중': 'C', '우': 'R'}


def en(label):
    return '·'.join(KO2EN.get(t, t) for t in (label or '').split('·'))
VIEW_AZ, VIEW_EL = 35.0, 22.0          # 3/4 view, degrees


def rot(az, el):
    a, e = np.radians(az), np.radians(el)
    Rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, np.cos(e), -np.sin(e)], [0, np.sin(e), np.cos(e)]])
    return Rx @ Rz


def render(ax, P, T, face_rgb, edge=None, lw=0.0):
    """Depth-sorted lambert fill. face_rgb: (n_tri, 3) or a single colour."""
    R = rot(VIEW_AZ, VIEW_EL)
    Q = P @ R.T
    tri = Q[T]                                   # (n,3,3)
    depth = tri[:, :, 1].mean(1)                 # +y is into the screen after the rotation
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = n / np.maximum(ln, 1e-9)
    lamb = np.clip(0.35 + 0.65 * np.abs(n @ np.array([0.3, -0.8, 0.5])), 0, 1)
    o = np.argsort(-depth)                       # far first
    C = np.asarray(face_rgb, float)
    if C.ndim == 1:
        C = np.tile(C, (len(T), 1))
    C = np.clip(C * lamb[:, None], 0, 1)
    polys = tri[o][:, :, [0, 2]]
    ax.add_collection(PolyCollection(polys, facecolors=C[o], edgecolors=edge or 'none',
                                     linewidths=lw))
    ax.set_xlim(Q[:, 0].min(), Q[:, 0].max())
    ax.set_ylim(Q[:, 2].min(), Q[:, 2].max())
    ax.set_aspect('equal')
    ax.axis('off')


def load(link):
    f = f'{STATIC}/link_setup_{link}.json'
    if not os.path.exists(f):
        return None
    D = json.load(open(f))
    S = D.get('peak') or next(iter(D.values()))
    P = np.asarray(S['nodes'], float)
    T = np.asarray(S['tris'], int)
    assert T.max() < len(P), f'{link}: triangle index {T.max()} exceeds {len(P)} nodes'
    return S, P, T


def main():
    size = int(next((a.split('=')[1] for a in sys.argv if a.startswith('--size=')), 260))
    do_parts = '--parts' in sys.argv
    links = [a for a in sys.argv[1:] if not a.startswith('--')] or \
        sorted(os.path.basename(f)[11:-5] for f in glob.glob(f'{STATIC}/link_setup_L*.json'))

    made = 0
    for link in links:
        got = load(link)
        if not got:
            continue
        S, P, T = got
        pid = S.get('part_id')
        parts = S.get('parts') or []

        # ---- whole-link thumbnail ----
        fig = plt.figure(figsize=(size / 100, size / 100), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        fig.patch.set_facecolor('#0d1117')
        if pid:
            # colour by part so the shape reads as an assembly, not a blob
            ids = np.asarray(pid)
            tid = ids[T[:, 0]]
            cm = plt.get_cmap('tab20')
            C = cm(tid % 20)[:, :3]
        else:
            C = np.array([0.62, 0.70, 0.80])
        render(ax, P, T, C)
        fig.savefig(f'{STATIC}/thumb_{link}.png', facecolor='#0d1117')
        plt.close(fig)
        made += 1

        # ---- per-part contact sheet ----
        if do_parts and pid and parts:
            ids = np.asarray(pid)
            tid = ids[T[:, 0]]
            keep = [p for p in parts if p.get('vol_cm3', 0) >= 0.05]
            keep.sort(key=lambda p: -p.get('p99', 0))
            keep = keep[:12]
            if not keep:
                continue
            ncol = min(4, len(keep))
            nrow = int(np.ceil(len(keep) / ncol))
            fig = plt.figure(figsize=(2.4 * ncol, 2.7 * nrow), dpi=110)
            fig.patch.set_facecolor('#0d1117')
            names = S.get('part_names') or []
            for i, p in enumerate(keep):
                ax = fig.add_subplot(nrow, ncol, i + 1)
                ax.set_facecolor('#0d1117')
                k = names.index(p['name']) if p['name'] in names else -1
                m = tid == k
                C = np.tile(np.array([0.20, 0.23, 0.28]), (len(T), 1))
                C[m] = [0.95, 0.45, 0.30]
                render(ax, P, T, C)
                ax.set_title(f"{p['name'].replace('VOLUME', 'V')}  {en(p.get('label'))}\n"
                             f"{p.get('vol_cm3', 0):.1f} cm3 · p99 {p.get('p99', 0):.1f} MPa",
                             fontsize=7.5, color='#c9d1d9', pad=3)
            fig.suptitle(f'{link} — which solid is which (orange = this part)',
                         color='#c9d1d9', fontsize=10)
            fig.tight_layout()
            fig.savefig(f'{STATIC}/thumbpart_{link}.png', facecolor='#0d1117')
            plt.close(fig)
        print(f'{link:30s} {len(P):6d} nodes / {len(T):6d} tris'
              f'{" · parts sheet" if do_parts and pid and parts else ""}', flush=True)

    print(f'\n-> {made} thumbnails in {STATIC}/thumb_*.png')


if __name__ == '__main__':
    main()
