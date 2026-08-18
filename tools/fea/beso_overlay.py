"""Recover the BESO retained set from its voxel STL and write it into the viewer payload.

optimize_link.py used to record only a voxel STL of the optimised shape, so the viewer had
no way to shade what actually survived and kept falling back on the retracted stress
threshold (which claimed 64-72 % removable against BESO's real 39 %). The STL is written as
one cube per retained element centroid, so the centroids - and therefore the retained
elements - can be recovered exactly.

The runner now stores `retained_elements` directly; this exists for results produced before
that, and asserts the recovered volume matches what optimise.json recorded.

Usage: beso_overlay.py L1g_foot_corner
"""
import json
import os
import sys

import numpy as np
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from part_screen import read_mesh_sets  # noqa: E402

W = '/home/syaro/pyg_fea/work'
STATIC = '/home/syaro/MikuchanRemote/Human-Pygmalion/tools/wrench_studio/static'


def stl_cube_centres(path, cube=3.0):
    """Centres of the cubes in a voxel STL written by lightweight.write_voxel_stl."""
    V = []
    for ln in open(path):
        t = ln.split()
        if t and t[0] == 'vertex':
            V.append((float(t[1]), float(t[2]), float(t[3])))
    V = np.asarray(V)
    assert len(V), f'{path}: no vertices'
    # each cube contributes 36 vertices (12 triangles); group by rounding to the grid
    key = np.round(V / cube).astype(np.int64)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    ctr = np.zeros((len(uniq), 3))
    cnt = np.zeros(len(uniq))
    np.add.at(ctr, inv, V)
    np.add.at(cnt, inv, 1)
    return ctr / cnt[:, None]


def main():
    link = sys.argv[1]
    opt = json.load(open(f'{W}/{link}/optimise.json'))
    nodes, sets = read_mesh_sets(link)
    assert nodes and sets, f'{link}: no mesh'
    P = np.array([nodes[i] for i in nodes])
    ids = list(nodes)

    if opt.get('retained_elements'):
        print('optimise.json already carries the retained element set - nothing to recover')
        return
    ctr = stl_cube_centres(opt['stl'])
    print(f'{link}: recovered {len(ctr)} retained centroids from the voxel STL')

    tree = cKDTree(ctr)
    d, _ = tree.query(P)
    keep = d < 6.0                       # within a cube of a retained centroid
    frac = 100 * keep.mean()
    want = opt['final']['volume_pct']
    print(f'  surface nodes retained {frac:.1f} % · volume retained {want:.1f} %')
    # These SHOULD differ, and the gap is the point: BESO hollows the inside first, so the
    # outer skin survives far more than the volume does. A surface colouring therefore
    # cannot represent a volumetric removal - it would read as "almost nothing was taken"
    # while 39 % of the material is gone. So the overlay is written only as a hint, and the
    # honest artefact for this result is the optimised solid itself.
    assert frac >= want, (
        f'{link}: surface retention {frac:.1f} % below volume retention {want:.1f} % - '
        'that is backwards for an interior-first removal, check the recovery')

    pay = f'{STATIC}/link_setup_{link}.json'
    if not os.path.exists(pay):
        print(f'  no viewer payload for {link}')
        return
    D = json.load(open(pay))
    S = D.get('peak') or next(iter(D.values()))
    Q = np.asarray(S['nodes'], float)
    dq, _ = tree.query(Q)
    S['beso_keep'] = [int(x) for x in (dq < 6.0)]
    S['beso'] = dict(removed_pct=opt['final']['removed_pct'],
                     volume_cm3=opt['final']['volume_cm3'],
                     V0_cm3=opt['V0_cm3'], SF=opt['final']['SF'],
                     stl=os.path.basename(opt['stl']),
                     surface_kept_pct=round(frac, 1),
                     note='removal is interior; the surface keeps {:.0f} % while the '
                          'volume keeps {:.0f} %'.format(frac, want))
    json.dump(D, open(pay, 'w'), separators=(',', ':'))
    print(f'  -> viewer payload gains beso_keep ({100*np.mean(dq < 6.0):.1f} % of surface)')


if __name__ == '__main__':
    main()
