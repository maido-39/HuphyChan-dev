"""Decompose Huphy1.0_FullBody.step into per-link STEP compounds via XCAF,
with fasteners and bearings classified OUT of the structure and catalogued
as joint metadata.

Why the split matters (found 2026-08-15 QA): the first version matched link
keywords before fastener keywords, so 42 screws + a 6810 bearing landed inside
L3_thigh and 78 screws inside L4_hip. Meshed with occ.fragment those become
BONDED rigid threads and a rigid ball-bearing lump -- stiffer than reality and
a mesh-quality disaster (that is what stalled the first campaign round).
Screws and bearings must enter the model deliberately:
  screws   -> washer-footprint constraints (screening) or pretensioned solid
              bolts with contact (joint submodel, tools/fea/bolted_pilot.py)
  bearings -> load/support on the real SEAT over a realistic arc, rolling
              elements replaced by a smeared raceway (never bonded balls)

Outputs (into ~/pyg_fea/steps/):
  link_<L>.step          structural solids only
  link_<L>_joints.json   screws (size, position, axis, length) + bearings
                         (type, seat axis/centre, bore/OD, width) of that link
  fullbody_links.json    full inventory with the classification

Run: mujoco-sim/mjlab/.venv/bin/python3 tools/fea/xcaf_links.py
"""
import json
import re
from collections import defaultdict

import numpy as np
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString, TCollection_AsciiString
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDF import TDF_LabelSequence, TDF_Label
from OCP.TDataStd import TDataStd_Name
from OCP.TopoDS import TopoDS_Compound, TopoDS
from OCP.BRep import BRep_Builder
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE
from OCP.TopLoc import TopLoc_Location
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

STEP = '/home/syaro/MikuchanRemote/Human-Pygmalion/refs/Huphy_1.0_STEP/Huphy1.0_FullBody.step'
OUT = '/home/syaro/pyg_fea/steps'

FASTENER = re.compile(r'screw|bolt|nut|washer|iso ?4762|iso ?10642|jis ?b ?1176', re.I)
BEARING = re.compile(r'6810|6814|6900|6812|crbs|bearing', re.I)


def label_name(lab):
    nm = TDataStd_Name()
    if lab.FindAttribute(TDataStd_Name.GetID_s(), nm):
        return TCollection_AsciiString(nm.Get()).ToCString()
    return ''


# The CAD's own sub-assembly names ARE the link definition -- use them instead
# of z-bands/keywords. (2026-08-15: keyword matching on the full path let an
# ancestor name like "Ankle2Feet" swallow every descendant, so the shin plates
# and cranks landed in the foot link.)
LINK_NAME = {
    'joints/ankle2feet': 'L1_ankle_foot',
    'joints/knee2ankle': 'L2_shin',
    'joints/hipyaw2knee': 'L3_thigh',
    'joints/piproll2yaw': 'L4_hip_yaw',
    'joints/hippitch2roll': 'L5_hip_pitchroll',
    'joints/centerparts': 'L6_pelvis',
    'profile sketch/2020-20-standard': 'L6_pelvis',
}


def link_of(path, z=None, vol=None):
    """Link = the CAD sub-assembly the solid belongs to."""
    parts = [p.split(':')[0].strip().lower() for p in path.split('/') if p.strip()]
    if not parts:
        return 'unassigned'
    key = '/'.join(parts[:2])
    if key in LINK_NAME:
        return LINK_NAME[key]
    if parts[0] == 'actuators':
        return 'ACT_' + re.sub(r'[^a-z0-9]+', '_', parts[1])[:24]
    for k, v in LINK_NAME.items():
        if parts[0] == k.split('/')[1]:
            return v
    return 'unassigned_' + parts[0][:20]


def cyl_axis(shape):
    """Dominant cylindrical axis of a solid (screw shank / bearing bore)."""
    best = None
    fx = TopExp_Explorer(shape, TopAbs_FACE)
    while fx.More():
        f = TopoDS.Face_s(fx.Current())
        fx.Next()
        ad = BRepAdaptor_Surface(f)
        if ad.GetType() != GeomAbs_Cylinder:
            continue
        gp = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, gp)
        cy = ad.Cylinder()
        d, L = cy.Axis().Direction(), cy.Axis().Location()
        if best is None or gp.Mass() > best[0]:
            best = (gp.Mass(), [d.X(), d.Y(), d.Z()], [L.X(), L.Y(), L.Z()], cy.Radius())
    if best is None:
        return None
    return dict(axis=[round(v, 3) for v in best[1]], on_axis=[round(v, 2) for v in best[2]],
                r=round(best[3], 2))


def cyl_radii(shape):
    """(min, max) cylinder radius of a solid -- bearing ring bore/OD."""
    rs = []
    fx = TopExp_Explorer(shape, TopAbs_FACE)
    while fx.More():
        f = TopoDS.Face_s(fx.Current())
        fx.Next()
        ad = BRepAdaptor_Surface(f)
        if ad.GetType() == GeomAbs_Cylinder:
            rs.append(ad.Cylinder().Radius())
    return (round(min(rs), 2), round(max(rs), 2)) if rs else (None, None)


def main():
    doc = TDocStd_Document(TCollection_ExtendedString('doc'))
    rd = STEPCAFControl_Reader()
    rd.SetNameMode(True)
    assert rd.ReadFile(STEP) == IFSelect_RetDone
    print('transferring 230 MB STEP (~4 min)...', flush=True)
    rd.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    items = []

    def walk(lab, loc, path):
        name = label_name(lab)
        if st.IsAssembly_s(lab):
            comps = TDF_LabelSequence()
            st.GetComponents_s(lab, comps)
            for i in range(1, comps.Length() + 1):
                c = comps.Value(i)
                cloc = loc.Multiplied(st.GetLocation_s(c))
                ref = TDF_Label()
                if st.GetReferredShape_s(c, ref):
                    walk(ref, cloc, path + '/' + (label_name(c) or label_name(ref)))
                else:
                    walk(c, cloc, path + '/' + label_name(c))
        else:
            sh = st.GetShape_s(lab)
            if not sh.IsNull():
                items.append((path + '/' + name, sh.Located(loc)))

    roots = TDF_LabelSequence()
    st.GetFreeShapes(roots)
    for i in range(1, roots.Length() + 1):
        walk(roots.Value(i), TopLoc_Location(), '')
    print(f'{len(items)} leaf components', flush=True)

    rows = []
    for path, sh in items:
        ex = TopExp_Explorer(sh, TopAbs_SOLID)
        k = 0
        while ex.More():
            s = ex.Current()
            ex.Next()
            gp = GProp_GProps()
            BRepGProp.VolumeProperties_s(s, gp)
            c = gp.CentreOfMass()
            bb = Bnd_Box()
            BRepBndLib.Add_s(s, bb)
            mn, mx = bb.CornerMin(), bb.CornerMax()
            com = [round(c.X(), 2), round(c.Y(), 2), round(c.Z(), 2)]
            vol = round(gp.Mass() / 1000., 3)
            # classification: fastener / bearing BEFORE any link keyword
            if FASTENER.search(path):
                kind = 'fastener'
            elif BEARING.search(path):
                kind = 'bearing'
            else:
                kind = 'struct'
            rows.append(dict(path=path, sub=k, vol=vol, com=com, kind=kind,
                             bmin=[round(mn.X(), 1), round(mn.Y(), 1), round(mn.Z(), 1)],
                             bmax=[round(mx.X(), 1), round(mx.Y(), 1), round(mx.Z(), 1)],
                             link=link_of(path, com[2], vol), shape=s))
            k += 1
    print(f'{len(rows)} located solids', flush=True)

    # ---------------- structural STEP per link
    by_link = defaultdict(list)
    for r in rows:
        by_link[r['link']].append(r)
    for lk, rs in sorted(by_link.items()):
        sset = [r for r in rs if r['kind'] == 'struct']
        f = [r for r in rs if r['kind'] == 'fastener']
        b = [r for r in rs if r['kind'] == 'bearing']
        print(f'{lk:14s} struct {len(sset):3d} ({sum(r["vol"] for r in sset):7.1f} cm3)'
              f'  fasteners {len(f):3d}  bearing-parts {len(b):3d}')
        if not sset:
            continue
        bld = BRep_Builder()
        comp = TopoDS_Compound()
        bld.MakeCompound(comp)
        for r in sset:
            bld.Add(comp, r['shape'])
        w = STEPControl_Writer()
        w.Transfer(comp, STEPControl_AsIs)
        w.Write(f'{OUT}/link_{lk}.step')

        # ---------------- joint metadata
        screws = []
        for r in f:
            m = re.search(r'M(\d+)(?:\s*x\s*[\d.]+)?\s*x\s*(\d+)', r['path'])
            ax = cyl_axis(r['shape'])
            screws.append(dict(name=r['path'].split('/')[-1][:60],
                               size=f'M{m.group(1)}x{m.group(2)}' if m else '?',
                               d=float(m.group(1)) if m else None,
                               L=float(m.group(2)) if m else None,
                               com=r['com'], vol=r['vol'],
                               axis=ax['axis'] if ax else None,
                               r_shank=ax['r'] if ax else None))
        # group bearing solids by instance path (rings + rolling elements)
        binst = defaultdict(list)
        for r in b:
            binst[re.sub(r'/[^/]*$', '', r['path'])].append(r)
        bearings = []
        for inst, rs2 in binst.items():
            typ = re.search(r'(6810ZZ|6814ZZ|6900ZZ|6812|CRBS808AUUU)', inst)
            big = sorted(rs2, key=lambda r: -r['vol'])[:2]     # the two rings
            rings = []
            for r in big:
                lo, hi = cyl_radii(r['shape'])
                ax = cyl_axis(r['shape'])
                rings.append(dict(vol=r['vol'], r_in=lo, r_out=hi,
                                  axis=ax['axis'] if ax else None, com=r['com']))
            allp = np.array([r['com'] for r in rs2])
            bearings.append(dict(type=typ.group(1) if typ else inst.split('/')[-1][:40],
                                 n_solids=len(rs2), centre=[round(float(v), 2) for v in allp.mean(0)],
                                 rings=rings,
                                 note='rolling elements present in CAD - never bond them; '
                                      'use a smeared raceway or seat traction'))
        json.dump(dict(link=lk, screws=screws, bearings=bearings),
                  open(f'{OUT}/link_{lk}_joints.json', 'w'), indent=1)
        print(f'   -> link_{lk}.step + {len(screws)} screws / {len(bearings)} bearings metadata')

    json.dump([{k: r[k] for k in ('path', 'sub', 'vol', 'com', 'kind', 'link')} for r in rows],
              open(f'{OUT}/fullbody_links.json', 'w'), indent=0)
    print('done')


if __name__ == '__main__':
    main()
