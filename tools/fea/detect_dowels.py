"""Find the dowel pins the bolt detector could not see.

detect_bolts.py identifies a fastener as a clearance hole coaxial with a smaller tapped
hole. A DOWEL is neither: it is a plain reamed hole at nominal diameter, no thread, no
oversize. So every dowel in this design was invisible to the analysis - which is why the
fastener check recommended adding pins to flanges that already have three.

A dowel hole here is a cylindrical face whose diameter is within an H7-ish band of a
nominal pin size (6 and 4 mm are the sizes used), that has no tapped hole on its axis.

Usage: detect_dowels.py [LINK ...]
"""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from detect_bolts import cyl_faces, group_axes  # noqa: E402

STEPS = '/home/syaro/pyg_fea/steps'
W = '/home/syaro/pyg_fea/work'
PINS = {6.0: 0.10, 4.0: 0.10, 5.0: 0.10, 3.0: 0.08}    # nominal -> tolerance band [mm]
TAP_D = {2.5, 3.3, 4.2, 5.0, 6.8}                      # tap drills that mean "threaded"


def dowels_of(step):
    faces = cyl_faces([step])
    groups = group_axes(faces)
    out = []
    for grp in groups:
        g = grp['faces']
        ds = sorted({round(2 * f['r'], 2) for f in g})
        # a threaded hole on the same axis means this is a screw, not a pin
        if any(any(abs(d - t) < 0.15 for t in TAP_D) for d in ds):
            continue
        for f in g:
            d = 2 * f['r']
            for nom, tol in PINS.items():
                if -0.02 <= d - nom <= tol:
                    ctr = f.get('ctr')
                    if ctr is None:
                        ctr = f['p0'] + 0.5 * (f['s0'] + f['s1']) * f['axis']
                    out.append(dict(dia=round(d, 3), nominal=nom,
                                    ctr=[round(float(v), 1) for v in np.asarray(ctr)],
                                    axis=[round(float(v), 3) for v in np.asarray(f['axis'])],
                                    depth=round(float(f['s1'] - f['s0']), 1)))
                    break
    # one entry per physical hole: merge faces that share a centre
    uniq = []
    for h in out:
        if not any(np.linalg.norm(np.array(h['ctr']) - np.array(u['ctr'])) < 2.0
                   and h['nominal'] == u['nominal'] for u in uniq):
            uniq.append(h)
    return uniq


def main():
    links = sys.argv[1:] or [os.path.basename(f)[5:-5] for f in
                             sorted(glob.glob(f'{STEPS}/link_L*.step'))]
    allout = {}
    for link in links:
        step = f'{STEPS}/link_{link}.step'
        if not os.path.exists(step):
            continue
        dw = dowels_of(step)
        allout[link] = dw
        by = {}
        for h in dw:
            by[h['nominal']] = by.get(h['nominal'], 0) + 1
        print(f"{link:20s} {len(dw):3d} dowel holes  " +
              (', '.join(f'Ø{int(k)}×{v}' for k, v in sorted(by.items())) or '-'), flush=True)
        for h in dw[:12]:
            print(f"    Ø{h['dia']:.2f} depth {h['depth']:5.1f} at {h['ctr']}")
    json.dump(allout, open(f'{W}/dowels_detected.json', 'w'), indent=1)
    print(f'\n-> {W}/dowels_detected.json')


if __name__ == '__main__':
    main()
