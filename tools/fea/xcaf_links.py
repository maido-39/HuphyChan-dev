"""Decompose Huphy1.0_FullBody.step into per-link STEP compounds via XCAF.

Plain STEP parsing loses instance names (the file is heavily instanced); the
XCAF reader keeps the assembly tree, so every solid arrives with its component
path AND its placement. Output: ~/pyg_fea/steps/link_<L>.step + inventory JSON.

Run: .venv/bin/python3 tools/fea/xcaf_links.py
"""
import json
import re

from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString, TCollection_AsciiString
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDF import TDF_LabelSequence, TDF_Label
from OCP.TDataStd import TDataStd_Name
from OCP.TopoDS import TopoDS_Compound
from OCP.BRep import BRep_Builder
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopLoc import TopLoc_Location
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

STEP = '/home/syaro/MikuchanRemote/Human-Pygmalion/refs/Huphy_1.0_STEP/Huphy1.0_FullBody.step'
OUT = '/home/syaro/pyg_fea/steps'


def label_name(lab):
    nm = TDataStd_Name()
    if lab.FindAttribute(TDataStd_Name.GetID_s(), nm):
        return TCollection_AsciiString(nm.Get()).ToCString()
    return ''


def assign(path, com_z, vol):
    """Link bucket from component path keywords, falling back to a z-band."""
    p = path.lower()
    if re.search(r'feet|anklefeet|universaljointcore|20deg_flange', p):
        return 'L1_foot'
    if re.search(r'kneeb2ankle|anklebrace|knee2ankle|crank_|arm_[ab]|body17|body19', p):
        return 'L2_shin'
    if re.search(r'yaw2kneeplate|hipyaw2knee|support', p):
        return 'L3_thigh'
    if re.search(r'hippitch|hiproll|piproll', p):
        return 'L4_hip'
    if re.search(r'outer shell|inner ball|brass bushing', p):
        return 'L2_shin' if com_z > -800 else 'L1_foot'
    if re.search(r'6810zz|6814zz|crbs', p):
        return 'skip_bearing'
    if re.search(r'screw|bolt|nut|washer', p) or vol < 0.5:
        return 'skip_fastener'
    if com_z <= -790:
        return 'L1_foot'
    if com_z <= -560:
        return 'L2_shin'
    if com_z <= -420:
        return 'L2_shin_motor' if vol > 90 else 'L3_thigh'
    if com_z <= -240:
        return 'L3_thigh'
    if com_z <= -20:
        return 'L4_hip'
    return 'L5_pelvis'


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
            gp = GProp_GProps()
            BRepGProp.VolumeProperties_s(s, gp)
            c = gp.CentreOfMass()
            rows.append(dict(path=path, sub=k, vol=round(gp.Mass() / 1000., 2),
                             com=[round(c.X(), 1), round(c.Y(), 1), round(c.Z(), 1)],
                             shape=s))
            k += 1
            ex.Next()
    print(f'{len(rows)} located solids', flush=True)

    groups = {}
    for r in rows:
        groups.setdefault(assign(r['path'], r['com'][2], r['vol']), []).append(r)
    for g in sorted(groups):
        print(f'{g:16s} n {len(groups[g]):3d}  {sum(r["vol"] for r in groups[g]):8.1f} cm3')

    for g, rs in sorted(groups.items()):
        if g.startswith('skip'):
            continue
        bld = BRep_Builder()
        comp = TopoDS_Compound()
        bld.MakeCompound(comp)
        for r in rs:
            bld.Add(comp, r['shape'])
        w = STEPControl_Writer()
        w.Transfer(comp, STEPControl_AsIs)
        w.Write(f'{OUT}/link_{g}.step')
        print(f'wrote link_{g}.step ({len(rs)} solids)', flush=True)

    json.dump([{k: r[k] for k in ('path', 'sub', 'vol', 'com')}
               | {'grp': assign(r['path'], r['com'][2], r['vol'])} for r in rows],
              open(f'{OUT}/fullbody_links.json', 'w'), indent=0)
    print('done')


if __name__ == '__main__':
    main()
