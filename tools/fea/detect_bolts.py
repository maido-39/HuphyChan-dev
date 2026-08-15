"""Infer bolted joints from hole geometry (user heuristic, 2026-08-15).

Design rule in this CAD: a through/clearance hole is nominal + 0.15 mm
(M4 -> 4.15, M5 -> 5.15). The mating part carries a COAXIAL, smaller and
deeper hole (the tapped hole) offset along the same axis. A head recess
(counterbore) may sit on the head side; its depth tells socket-head from
low-head ("소두") screws -- the hip-pitch group mixes both.

So a bolted joint = a coaxial chain of cylinder faces along one axis:

      [ counterbore ]  [ clearance dia+0.15 ]  ...  [ tapped (smaller, deeper) ]
      head side ------------------------- grip ------------------ engagement

This module finds those chains and returns bolt records:
    size, axis, head_point, grip_len, engagement_len, clearance_r, tap_r,
    counterbore (r, depth), head_type, parts (which solids each segment is in)

Used for (a) drawing the real fastening in the setup viewer, (b) placing
washer-footprint constraints / pretensioned bolt submodels in the FEA.

Run: detect_bolts.py <link_step_or_LINK> [--json out.json]
"""
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import femlib as F  # noqa: E402

STEPS = '/home/syaro/pyg_fea/steps'

# nominal -> (clearance dia, tap-drill dia, ISO 4762 head dia/height,
#             low-head DIN 7984 head dia/height)
SCREWS = {
    3: dict(clear=3.15, tap=2.5, head=5.5, hh=3.0, lh_head=5.5, lh_hh=2.0),
    4: dict(clear=4.15, tap=3.3, head=7.0, hh=4.0, lh_head=7.0, lh_hh=2.8),
    5: dict(clear=5.15, tap=4.2, head=8.5, hh=5.0, lh_head=8.5, lh_hh=3.5),
    6: dict(clear=6.15, tap=5.0, head=10.0, hh=6.0, lh_head=10.0, lh_hh=4.0),
}
# Tight: the design rule is exact (nominal+0.15), and a loose window makes
# M3-clearance 3.15 collide with the M4 tap drill 3.30 (misread 18 real M4 taps
# as M3 clearance holes on the first run).
RTOL = 0.07          # diameter match tolerance [mm]
AX_TOL = 0.25        # coaxiality tolerance [mm]
DIR_TOL = 0.02       # axis direction tolerance (1 - |dot|)


def cyl_faces(step_paths, min_vol_cm3=0.05):
    """All cylindrical faces with axis, radius and axial extent.

    Accepts several STEP files: a bolt very often has its clearance hole in one
    link and its tapped hole in the mating link, so detection must see both.
    """
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    out = []
    if isinstance(step_paths, str):
        step_paths = [step_paths]
    sols = []
    for sp in step_paths:
        tag = os.path.basename(sp).replace('link_', '').replace('.step', '')
        for k, so in enumerate(F.load_solids(sp, min_vol_cm3)):
            so['src'] = tag
            so['sid'] = f'{tag}#{k}'
            sols.append(so)
    for si, sol in enumerate(sols):
        fx = TopExp_Explorer(sol['shape'], TopAbs_FACE)
        while fx.More():
            f = TopoDS.Face_s(fx.Current())
            fx.Next()
            ad = BRepAdaptor_Surface(f)
            if ad.GetType() != GeomAbs_Cylinder:
                continue
            cy = ad.Cylinder()
            d = cy.Axis().Direction()
            L = cy.Axis().Location()
            ax = np.array([d.X(), d.Y(), d.Z()], float)
            if ax[np.argmax(np.abs(ax))] < 0:      # canonical direction
                ax = -ax
            p0 = np.array([L.X(), L.Y(), L.Z()], float)
            bb = Bnd_Box()
            BRepBndLib.Add_s(f, bb)
            mn, mx = bb.CornerMin(), bb.CornerMax()
            c0 = np.array([mn.X(), mn.Y(), mn.Z()])
            c1 = np.array([mx.X(), mx.Y(), mx.Z()])
            s0, s1 = float(c0 @ ax), float(c1 @ ax)
            gp = GProp_GProps()
            BRepGProp.SurfaceProperties_s(f, gp)
            r = cy.Radius()
            wrap = gp.Mass() / max(1e-9, 2 * np.pi * r * max(1e-6, s1 - s0))
            out.append(dict(solid=si, sid=sol['sid'], src=sol['src'],
                            name=sol['name'], r=r, axis=ax, p0=p0,
                            s0=min(s0, s1), s1=max(s0, s1), wrap=wrap))
        # keep solid bbox for reporting
    return out


def group_axes(faces):
    """Bucket faces onto shared axis lines (same direction, same line)."""
    groups = []
    for f in faces:
        placed = False
        for g in groups:
            if abs(abs(float(f['axis'] @ g['axis'])) - 1.0) > DIR_TOL:
                continue
            d = f['p0'] - g['p0']
            perp = d - (d @ g['axis']) * g['axis']
            if np.linalg.norm(perp) <= AX_TOL:
                g['faces'].append(f)
                placed = True
                break
        if not placed:
            groups.append(dict(axis=f['axis'].copy(), p0=f['p0'].copy(), faces=[f]))
    return groups


def classify(r):
    """Return (nominal, role) for a hole radius, or (None, None)."""
    d = 2 * r
    for n, s in SCREWS.items():
        if abs(d - s['clear']) <= RTOL:
            return n, 'clearance'
        if abs(d - s['tap']) <= RTOL:
            return n, 'tap'
    return None, None


def detect(step_paths, min_vol_cm3=0.05, verbose=False):
    faces = cyl_faces(step_paths, min_vol_cm3)
    bolts = []
    for g in group_axes(faces):
        ax = g['axis']
        segs = sorted(g['faces'], key=lambda f: f['s0'])
        holes = []
        for f in segs:
            n, role = classify(f['r'])
            holes.append(dict(f, nominal=n, role=role, length=f['s1'] - f['s0']))
        clears = [h for h in holes if h['role'] == 'clearance']
        taps = [h for h in holes if h['role'] == 'tap']
        if not clears:
            continue
        for c in clears:
            # the tapped hole sits coaxially beyond the clearance bore, in the
            # mating part (usually another solid, often in another link file)
            cand = [t for t in taps
                    if t['sid'] != c['sid'] and t['nominal'] == c['nominal']]
            t = (min(cand, key=lambda t: min(abs(t['s0'] - c['s1']), abs(c['s0'] - t['s1'])))
                 if cand else None)
            def cbore_of(head_s, from_low):
                """Head recess: a larger coaxial hole abutting the head face."""
                best = None
                for h in holes:
                    if h['role'] or h['r'] <= c['r'] + 0.3 or h['r'] > c['r'] + 4.0:
                        continue
                    near = abs(h['s1'] - head_s) < 0.8 if from_low else abs(h['s0'] - head_s) < 0.8
                    if near:
                        best = h
                return best

            def head_kind(cb, nominal):
                if not cb:
                    return 'through (no recess)'
                spec = SCREWS[nominal]
                # socket head height vs low-head ("소두") height decides the class
                mid = (spec['hh'] + spec['lh_hh']) / 2
                return ('counterbored, socket head ISO 4762'
                        if cb['length'] >= mid else
                        'counterbored, LOW-HEAD 소두 (DIN 7984 class)')

            if t is None:
                # no tapped counterpart in this set: still a real bolt location
                cb_lo, cb_hi = cbore_of(c['s0'], True), cbore_of(c['s1'], False)
                cb0 = cb_lo or cb_hi
                head_lo = cb_lo is not None or cb_hi is None   # default: enter from -s
                head_s0 = c['s0'] if head_lo else c['s1']
                bolts.append(dict(
                    size=f"M{c['nominal']}", nominal=c['nominal'],
                    axis=[round(float(v), 4) for v in ax],
                    head_point=[round(float(v), 2) for v in
                                (c['p0'] - (c['p0'] @ ax) * ax + head_s0 * ax)],
                    clearance_d=round(2 * c['r'], 2), tap_d=None,
                    grip_mm=round(float(c['s1'] - c['s0']), 2), engagement_mm=None,
                    shank_dir=[round(float(v), 4) for v in (ax if head_lo else -ax)],
                    counterbore=None if not cb0 else dict(d=round(2 * cb0['r'], 2),
                                                          depth=round(float(cb0['length']), 2)),
                    head_type=head_kind(cb0, c['nominal']) + ' | tap not in set',
                    parts=dict(clearance=c['sid'], tapped=None),
                    links=[c['src']],
                    min_screw_len=None))
                continue
            gap_after = t['s0'] - c['s1']
            gap_before = c['s0'] - t['s1']
            if gap_after >= -0.6 and gap_after < 12:
                head_dir = -ax                       # head sits at the low-s end
                head_s = c['s0']
                grip = c['s1'] - c['s0']
                eng_s0, eng_s1 = t['s0'], t['s1']
            elif gap_before >= -0.6 and gap_before < 12:
                head_dir = ax
                head_s = c['s1']
                grip = c['s1'] - c['s0']
                eng_s0, eng_s1 = t['s0'], t['s1']
            else:
                continue
            # stacked clearance holes on the same axis add to the grip
            for c2 in clears:
                if c2 is c or c2['nominal'] != c['nominal']:
                    continue
                if abs(c2['s1'] - c['s0']) < 1.0 or abs(c['s1'] - c2['s0']) < 1.0:
                    grip += c2['length']
                    head_s = min(head_s, c2['s0']) if head_dir[0] == -ax[0] else max(head_s, c2['s1'])
            cb = cbore_of(head_s, head_dir @ ax < 0)
            # a counterbore is machined on the HEAD side: if it turned up on the
            # opposite end, the head/shank orientation was inferred backwards
            if cb is None:
                other_s = c['s1'] if head_dir @ ax < 0 else c['s0']
                cb_other = cbore_of(other_s, head_dir @ ax > 0)
                if cb_other is not None:
                    head_dir = -head_dir
                    head_s = other_s
                    cb = cb_other
            head_type = head_kind(cb, c['nominal'])
            bolts.append(dict(
                size=f"M{c['nominal']}",
                nominal=c['nominal'],
                axis=[round(float(v), 4) for v in ax],
                shank_dir=[round(float(v), 4) for v in (-head_dir)],
                head_point=[round(float(v), 2) for v in
                            (c['p0'] - (c['p0'] @ ax) * ax + head_s * ax)],
                clearance_d=round(2 * c['r'], 2),
                tap_d=round(2 * t['r'], 2),
                grip_mm=round(float(grip), 2),
                engagement_mm=round(float(eng_s1 - eng_s0), 2),
                counterbore=None if not cb else dict(d=round(2 * cb['r'], 2),
                                                     depth=round(float(cb['length']), 2)),
                head_type=head_type,
                parts=dict(clearance=c['sid'], tapped=t['sid']),
                links=sorted({c['src'], t['src']}),
                min_screw_len=round(float(grip + max(3.0, 1.5 * c['nominal'])), 1),
            ))
    # de-duplicate bolts that share an axis and head point
    uniq = {}
    for b in bolts:
        k = (b['size'], tuple(np.round(b['head_point'], 1)), tuple(np.round(b['axis'], 2)))
        if k not in uniq or b['grip_mm'] > uniq[k]['grip_mm']:
            uniq[k] = b
    return list(uniq.values())


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if args and args[0] == 'ALL':
        import glob
        steps = sorted(glob.glob(f'{STEPS}/link_L*.step'))
    else:
        steps = [a if a.endswith('.step') else f'{STEPS}/link_{a}.step' for a in args]
    step = ' + '.join(os.path.basename(s) for s in steps)
    bolts = detect(steps)
    by = defaultdict(int)
    for b in bolts:
        by[(b['size'], b['head_type'])] += 1
    print(f'{step}: {len(bolts)} bolt locations detected')
    for (s, h), n in sorted(by.items()):
        print(f'   {s:3s} x{n:3d}  {h}')
    for b in sorted(bolts, key=lambda b: (b['size'], b['head_point']))[:60]:
        cb = b['counterbore']
        print(f"   {b['size']} head@{b['head_point']} ax{b['axis']} "
              f"clear {b['clearance_d']} tap {b['tap_d']} grip {b['grip_mm']} "
              f"eng {b['engagement_mm']} "
              f"{'cbore d%.1f/%.1f' % (cb['d'], cb['depth']) if cb else 'no cbore'} "
              f"[{b['head_type']}] links {b.get('links', '-')}")
    if '--json' in sys.argv:
        out = sys.argv[sys.argv.index('--json') + 1]
        json.dump(bolts, open(out, 'w'), indent=1)
        print('wrote', out)


if __name__ == '__main__':
    main()
