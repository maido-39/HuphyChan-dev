"""Attach bearing instances to their link and locate the real housing SEAT.

Bearings sit as top-level instances in the CAD tree, so the link decomposition
leaves them unassigned. Here each instance is matched to the nearest link and
its seat is FOUND IN THE LINK GEOMETRY (a cylinder face whose radius equals the
bearing OD/2), so loads and supports can be applied where the outer ring really
presses instead of on a bare bore.

Writes/updates ~/pyg_fea/steps/link_<L>_joints.json ('bearings' list).
Run: mujoco-sim/mjlab/.venv/bin/python3 tools/fea/assign_bearings.py
"""
import json
import os
import re
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import femlib as F  # noqa: E402

STEPS = '/home/syaro/pyg_fea/steps'
# catalog geometry: bore d, OD D, width B [mm]
CATALOG = {'6900ZZ': (10, 22, 6), '6810ZZ': (50, 65, 7),
           '6814ZZ': (70, 90, 10), 'CRBS808AUUU': (80, 96, 8)}


def main():
    rows = json.load(open(f'{STEPS}/fullbody_links.json'))
    links = sorted({r['link'] for r in rows
                    if r['kind'] == 'struct' and r['link'].startswith('L')})
    cloud = {lk: np.array([r['com'] for r in rows
                           if r['link'] == lk and r['kind'] == 'struct']) for lk in links}

    inst = defaultdict(list)
    for r in rows:
        if r['kind'] == 'bearing':
            inst[re.sub(r'/[^/]*$', '', r['path'])].append(r)

    per_link = defaultdict(list)
    for path, rs in inst.items():
        m = re.search(r'(6900ZZ|6810ZZ|6814ZZ|CRBS808AUUU)', path)
        typ = m.group(1) if m else path.split('/')[-1][:30]
        P = np.array([r['com'] for r in rs])
        # a single instance path can hold several physical bearings (e.g. the
        # two 6900 pairs of one gimbal) -> split by gaps in the COM cloud
        groups = [P]
        for k in range(3):
            spread = P[:, k].max() - P[:, k].min()
            if spread > 25:
                med = (P[:, k].max() + P[:, k].min()) / 2
                groups = [P[P[:, k] <= med], P[P[:, k] > med]]
                break
        for G in groups:
            c = G.mean(0)
            best = min(links, key=lambda lk: np.linalg.norm(cloud[lk] - c, axis=1).min())
            d = float(np.linalg.norm(cloud[best] - c, axis=1).min())
            per_link[best].append(dict(type=typ, centre=[round(float(v), 2) for v in c],
                                       n_solids=len(G), dist_to_link_mm=round(d, 1)))

    for lk, bs in sorted(per_link.items()):
        step = f'{STEPS}/link_{lk}.step'
        if not os.path.exists(step):
            continue
        print(f'\n=== {lk}: {len(bs)} bearing instances')
        for b in bs:
            d, D, B = CATALOG.get(b['type'], (None, None, None))
            b['catalog'] = dict(bore=d, OD=D, width=B) if d else None
            b['kr_N_per_mm'] = F.BEARING_KR.get(b['type'])
            seats = []
            if D:
                # the outer ring can seat in EITHER link of the joint -> search all
                for lk2 in links:
                    s2 = f'{STEPS}/link_{lk2}.step'
                    if not os.path.exists(s2):
                        continue
                    for ax in ('x', 'y', 'z'):
                        for f in F.probe_features(s2, kind='cyl', axis=ax,
                                                  near=b['centre'], tol=30.):
                            if f['r'] and abs(f['r'] - D / 2) < 0.6:
                                seats.append(dict(link=lk2, axis=ax, r=f['r'], loc=f['loc'],
                                                  area=f['area'], span=[f['bmin'], f['bmax']]))
                b['joint_links'] = sorted({s['link'] for s in seats})
            b['seats'] = seats
            print(f"  {b['type']:12s} centre {b['centre']} n={b['n_solids']:2d} "
                  f"dist {b['dist_to_link_mm']:5.1f} mm  seats r~{D/2 if D else '?'}: {len(seats)}")
            for s in seats[:4]:
                print(f"      seat {s['axis']}-axis r{s['r']:.2f} at {s['loc']} area {s['area']:.0f}")
        jf = f'{STEPS}/link_{lk}_joints.json'
        data = json.load(open(jf)) if os.path.exists(jf) else dict(link=lk, screws=[])
        data['bearings'] = bs
        data['_note'] = ('bearings: apply joint load / support on the SEAT cylinder over the '
                         'loaded arc (femlib.bearing_load). Never bond CAD rolling elements; '
                         'for a joint submodel keep the rings and use '
                         'femlib.smeared_raceway_modulus(kr, ...) for the raceway.')
        json.dump(data, open(jf, 'w'), indent=1)
    print('\nupdated joint metadata')


if __name__ == '__main__':
    main()
