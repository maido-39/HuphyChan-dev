"""Reusable assembly-FEA helpers for the Pygmalion structural campaign.

Pipeline: STEP compound -> gmsh (occ.fragment = conformal bonded assembly)
-> C3D10 mesh -> CalculiX deck (bearing/couple loads on measured bores)
-> ccx solve -> frd post -> viewer-case JSON.

Lives in the repo (NOT the scratchpad) because the scratchpad is wiped between
sessions -- a full pipeline rebuild cost us one campaign round on 2026-08-15.

Conventions: mm-N-MPa. CAD frame x lateral, y fore-aft (+y rear), z up.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from collections import Counter

import numpy as np

CCX = '/home/syaro/pyg_fea/ccxenv/bin/ccx'
LOCK_MESH = '/tmp/pyg_mesh.lock'
LOCK_SOLVE = '/tmp/pyg_ccx.lock'
AL = dict(name='ALU', E=68900.0, nu=0.33, yield_=276.0)   # 6061-T6
STEEL = dict(name='STEEL', E=210000.0, nu=0.30, yield_=640.0)

# C3D10 face -> corner-node local indices, CalculiX convention
C3D10_FACES = [(0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0)]


# --------------------------------------------------------------- geometry
def load_solids(step_path, min_vol_cm3=0.05, exclude=None):
    """Return [{name, shape, vol_cm3, com, bmin, bmax}] from a STEP file.

    `exclude` is a regex matched against the solid name (XCAF name when the
    file carries one, else `solid<i>`); volume filter drops fastener crumbs.
    """
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopoDS import TopoDS
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    names = re.findall(r"MANIFOLD_SOLID_BREP\('([^']*)'",
                       open(step_path, errors='ignore').read())
    rd = STEPControl_Reader()
    rd.ReadFile(step_path)
    rd.TransferRoots()
    ex = TopExp_Explorer(rd.OneShape(), TopAbs_SOLID)
    out, i = [], 0
    rx = re.compile(exclude, re.I) if exclude else None
    while ex.More():
        s = TopoDS.Solid_s(ex.Current())
        ex.Next()
        nm = names[i] if i < len(names) else f'solid{i}'
        i += 1
        gp = GProp_GProps()
        BRepGProp.VolumeProperties_s(s, gp)
        v = gp.Mass() / 1000.
        if v < min_vol_cm3 or (rx and rx.search(nm)):
            continue
        c = gp.CentreOfMass()
        bb = Bnd_Box()
        BRepBndLib.Add_s(s, bb)
        mn, mx = bb.CornerMin(), bb.CornerMax()
        out.append(dict(name=nm, shape=s, vol_cm3=round(v, 2),
                        com=[c.X(), c.Y(), c.Z()],
                        bmin=[mn.X(), mn.Y(), mn.Z()], bmax=[mx.X(), mx.Y(), mx.Z()]))
    return out


def write_step(shapes, path):
    """Write selected solids (from load_solids) to one STEP compound."""
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    bld = BRep_Builder()
    comp = TopoDS_Compound()
    bld.MakeCompound(comp)
    for s in shapes:
        bld.Add(comp, s['shape'] if isinstance(s, dict) else s)
    w = STEPControl_Writer()
    w.Transfer(comp, STEPControl_AsIs)
    w.Write(path)
    return path


def probe_features(step_path, kind='cyl', axis=None, near=None, tol=25.,
                   min_vol_cm3=0.05, exclude=None):
    """List cylinder/plane faces for BC discovery.

    kind: 'cyl' | 'plane'; axis: 'x'|'y'|'z' filter on face axis/normal;
    near: (x,y,z) with `tol` radius filter on the face location.
    Returns rows [{solid, name, r|d, loc, span, area}] sorted by radius/area.
    """
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    AX = {'x': 0, 'y': 1, 'z': 2}
    rows = []
    for sol in load_solids(step_path, min_vol_cm3, exclude):
        fx = TopExp_Explorer(sol['shape'], TopAbs_FACE)
        while fx.More():
            f = TopoDS.Face_s(fx.Current())
            fx.Next()
            ad = BRepAdaptor_Surface(f)
            t = ad.GetType()
            if kind == 'cyl' and t != GeomAbs_Cylinder:
                continue
            if kind == 'plane' and t != GeomAbs_Plane:
                continue
            if t == GeomAbs_Cylinder:
                g = ad.Cylinder()
                d = g.Axis().Direction()
                L = g.Axis().Location()
                key = g.Radius()
            else:
                g = ad.Plane()
                d = g.Axis().Direction()
                L = g.Location()
                key = None
            dv = np.array([d.X(), d.Y(), d.Z()])
            if axis and abs(dv[AX[axis]]) < 0.99:
                continue
            lv = np.array([L.X(), L.Y(), L.Z()])
            if near is not None and np.linalg.norm(lv - np.asarray(near, float)) > tol:
                continue
            gp = GProp_GProps()
            BRepGProp.SurfaceProperties_s(f, gp)
            bb = Bnd_Box()
            BRepBndLib.Add_s(f, bb)
            mn, mx = bb.CornerMin(), bb.CornerMax()
            rows.append(dict(solid=sol['name'], r=None if key is None else round(key, 2),
                             loc=[round(v, 2) for v in lv],
                             axis=[round(v, 3) for v in dv],
                             area=round(gp.Mass(), 1),
                             bmin=[round(mn.X(), 1), round(mn.Y(), 1), round(mn.Z(), 1)],
                             bmax=[round(mx.X(), 1), round(mx.Y(), 1), round(mx.Z(), 1)]))
    rows.sort(key=lambda r: (-(r['r'] or 0), -r['area']))
    return rows


def resolve_overlaps(step_path, out_path, min_overlap_cm3=0.005, verbose=True):
    """Cut interpenetrating solids apart so the mesher can work.

    Some CAD parts overlap (a hub inside a housing, a pin inside a boss). gmsh
    then emits "PLC Error: a segment and a facet intersect" with or without
    occ.fragment, and no mesh size helps. Here the smaller solid is subtracted
    from the larger one, which keeps every feature and removes the ambiguity.
    Returns (path, n_cuts).
    """
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    sols = load_solids(step_path, min_vol_cm3=0.0)
    shapes = [s['shape'] for s in sols]
    vols = [s['vol_cm3'] for s in sols]
    order = sorted(range(len(sols)), key=lambda i: -vols[i])
    cuts = 0
    for a_i in order:
        for b_i in order:
            if a_i == b_i or vols[b_i] > vols[a_i]:
                continue
            ba, bb = sols[a_i], sols[b_i]
            if any(ba['bmin'][k] > bb['bmax'][k] or bb['bmin'][k] > ba['bmax'][k]
                   for k in range(3)):
                continue
            com = BRepAlgoAPI_Common(shapes[a_i], shapes[b_i])
            com.Build()
            if not com.IsDone():
                continue
            gp = GProp_GProps()
            BRepGProp.VolumeProperties_s(com.Shape(), gp)
            ov = gp.Mass() / 1000.
            if ov < min_overlap_cm3:
                continue
            cut = BRepAlgoAPI_Cut(shapes[a_i], shapes[b_i])
            cut.Build()
            if cut.IsDone():
                shapes[a_i] = cut.Shape()
                cuts += 1
                if verbose:
                    print(f'   overlap {ov:.2f} cm3: cut solid {b_i} '
                          f'({vols[b_i]:.1f} cm3) out of {a_i} ({vols[a_i]:.1f} cm3)',
                          flush=True)
    write_step(shapes, out_path)
    return out_path, cuts


# ------------------------------------------------------------------ mesh
def _mesh_once(step_paths, out_inp, size_far, refine, fragment, order2, verbose,
               algo3d, heal, tol, curv=0, size_min=0.0, cylinders=None):
    """One meshing attempt (see mesh_assembly for the retry ladder)."""
    import gmsh
    gmsh.initialize()
    gmsh.option.setNumber('General.Terminal', 1 if verbose else 0)
    # OCC healing: imported assemblies carry slivers/seams that otherwise abort
    # the 3-D algorithm ("Embedded edge node ... on the seam edge").
    gmsh.option.setNumber('Geometry.Tolerance', tol)
    if heal:
        # NEVER enable OCCSewFaces/OCCMakeSolids on an already-valid assembly:
        # they turn the solids into shells and the "3-D" mesh comes out as bare
        # surface elements (silent, caught 2026-08-15 by an element-type check).
        for opt in ('Geometry.OCCFixDegenerated', 'Geometry.OCCFixSmallEdges',
                    'Geometry.OCCFixSmallFaces'):
            gmsh.option.setNumber(opt, 1)
    gmsh.model.add('asm')
    vols = []
    for p in ([step_paths] if isinstance(step_paths, str) else step_paths):
        tags = gmsh.model.occ.importShapes(p)
        vols += [t[1] for t in tags if t[0] == 3]
    if fragment and len(vols) > 1:
        frag, _ = gmsh.model.occ.fragment([(3, vols[0])], [(3, v) for v in vols[1:]])
        vols = [t[1] for t in frag if t[0] == 3]
    # proxies are added AFTER the fragment: intersecting them with the real
    # geometry produced sliver elements (ccx: "nonpositive jacobian"). They stay
    # separate bodies and are joined by the flange proximity tie instead.
    for c in (cylinders or []):
        ax = {'x': (1, 0, 0), 'y': (0, 1, 0), 'z': (0, 0, 1)}[c['axis']]
        base = [c['ctr'][i] - ax[i] * c['len'] / 2 for i in range(3)]
        vols.append(gmsh.model.occ.addCylinder(*base, *[a * c['len'] for a in ax], c['r']))
    gmsh.model.occ.synchronize()
    if heal:
        gmsh.model.mesh.removeDuplicateNodes()
    for k, v in enumerate(vols):
        gmsh.model.addPhysicalGroup(3, [v], k + 1, name=f'V{v}')
    fields = []
    for (x, y, z, rad, sz) in (refine or []):
        fid = gmsh.model.mesh.field.add('Ball')
        for k, val in [('Radius', rad), ('VIn', sz), ('VOut', size_far),
                       ('XCenter', x), ('YCenter', y), ('ZCenter', z)]:
            gmsh.model.mesh.field.setNumber(fid, k, val)
        fields.append(fid)
    if fields:
        fmin = gmsh.model.mesh.field.add('Min')
        gmsh.model.mesh.field.setNumbers(fmin, 'FieldsList', fields)
        gmsh.model.mesh.field.setAsBackgroundMesh(fmin)
    else:
        gmsh.option.setNumber('Mesh.MeshSizeMax', size_far)
    gmsh.option.setNumber('Mesh.MeshSizeFromPoints', 0)
    # curvature-driven sizing: without it a small bore/sphere gets one element
    # and gmsh dies with "Impossible to mesh periodic surface"
    gmsh.option.setNumber('Mesh.MeshSizeFromCurvature', curv)
    if size_min:
        gmsh.option.setNumber('Mesh.MeshSizeMin', size_min)
    gmsh.option.setNumber('Mesh.Algorithm3D', algo3d)
    gmsh.option.setNumber('Mesh.OptimizeNetgen', 1)
    gmsh.option.setNumber('Mesh.SecondOrderLinear', 1)
    try:
        gmsh.model.mesh.generate(3)
        if order2:
            gmsh.model.mesh.setOrder(2)
        gmsh.write(out_inp)
        nn = len(gmsh.model.mesh.getNodes()[0])
        etags, enodes = gmsh.model.mesh.getElementsByType(11)   # 11 = 10-node tet
        ne = len(etags)
        if ne == 0:
            raise RuntimeError('no C3D10 volume elements were generated '
                               '(surface-only mesh -- check healing options)')
        # CalculiX evaluates the C3D10 jacobian AT THE NODES (stress
        # extrapolation), where a badly distorted tet can be negative even
        # though every Gauss point is positive -- that is the "nonpositive
        # jacobian" abort, after which ccx writes displacements but no stress.
        # Gate on the nodal jacobian so the ladder can try another algorithm.
        nt, nc, _ = gmsh.model.mesh.getNodes()
        pos = {int(v): nc[3 * i:3 * i + 3] for i, v in enumerate(nt)}
        # gmsh tet10 order is n0..n3, e01,e12,e02,e03,e23,e13 -- the last two are
        # swapped versus Abaqus/CalculiX C3D10 (e13,e23), which the .inp writer
        # fixes on export. Permute here so the jacobian is evaluated in the same
        # convention the solver will use.
        conn = np.array(enodes, dtype=np.int64).reshape(ne, 10)[:, [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]]
        P = np.array([[pos[n] for n in row] for row in conn])

        def dN(r, s, u_t):
            u = 1 - r - s - u_t
            d = np.zeros((10, 3))
            d[0] = [-(4 * u - 1)] * 3
            d[1] = [4 * r - 1, 0, 0]
            d[2] = [0, 4 * s - 1, 0]
            d[3] = [0, 0, 4 * u_t - 1]
            d[4] = [4 * (u - r), -4 * r, -4 * r]
            d[5] = [4 * s, 4 * r, 0]
            d[6] = [-4 * s, 4 * (u - s), -4 * s]
            d[7] = [-4 * u_t, -4 * u_t, 4 * (u - u_t)]
            d[8] = [4 * u_t, 0, 4 * r]
            d[9] = [0, 4 * u_t, 4 * s]
            return d
        worst = np.full(ne, np.inf)
        for (r, s, u_t) in [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1),
                            (.5, 0, 0), (0, .5, 0), (0, 0, .5)]:
            J = np.einsum('nki,kj->nij', P, dN(r, s, u_t))
            worst = np.minimum(worst, np.linalg.det(J))
        bad = int((worst <= 0).sum())
        if bad:
            raise RuntimeError(f'{bad}/{ne} elements have a non-positive NODAL jacobian '
                               f'(min {worst.min():.3g})')
    finally:
        gmsh.finalize()
    return dict(inp=out_inp, nodes=nn, volumes=vols)


def mesh_assembly(step_paths, out_inp, size_far=4.0, refine=None, fragment=True,
                  curv=None,
                  order2=True, verbose=False, ladder=True, cylinders=None):
    """Mesh with a retry ladder over the usual imported-assembly failures.

    Attempts: Delaunay+healing -> HXT+healing -> HXT, coarser, healing+bigger
    OCC tolerance. Raises the last error if all fail.
    """
    attempts = [
        dict(algo3d=1, heal=False, tol=1e-6, curv=10, size_min=0.8,
             size_far=size_far, refine=refine),
        dict(algo3d=10, heal=False, tol=1e-6, curv=14, size_min=0.6,
             size_far=size_far, refine=refine),
        dict(algo3d=10, heal=True, tol=1e-3, curv=8, size_min=1.0,
             size_far=size_far * 1.5,
             refine=[(x, y, z, r, s * 1.4) for (x, y, z, r, s) in (refine or [])]),
        dict(algo3d=1, heal=True, tol=1e-3, curv=0, size_min=0.0,
             size_far=size_far * 2.0, refine=None),
    ]
    # last resort: skip occ.fragment. Overlapping/interfering CAD solids make
    # fragment emit self-intersecting facets ("PLC Error: a segment and a facet
    # intersect"), and bolted parts should not be bonded anyway - the campaign
    # ties them with node-pair MPCs / rigid motor housings instead.
    attempts.append(dict(algo3d=1, heal=False, tol=1e-6, curv=10, size_min=0.8,
                         size_far=size_far, refine=refine, no_fragment=True))
    if not ladder:
        attempts = attempts[:1]
    last = None
    if curv is not None:
        # a link may cap curvature refinement: on L3 the round features drove the
        # count to 630k nodes at the only size that meshes, far past what the
        # solver can hold
        for a in attempts:
            a['curv'] = min(a.get('curv', 0), curv) if curv else 0
    for i, a in enumerate(attempts):
        try:
            m = _mesh_once(step_paths, out_inp, a['size_far'], a['refine'],
                           False if a.get('no_fragment') else fragment,
                           order2, verbose, a['algo3d'], a['heal'], a['tol'],
                           a.get('curv', 0), a.get('size_min', 0.0), cylinders)
            if i:
                print(f'  (mesh succeeded on attempt {i + 1}: algo3d={a["algo3d"]}, '
                      f'size_far={a["size_far"]}, curv={a.get("curv")}, tol={a["tol"]}'
                      f'{", NO fragment - parts tied instead of bonded" if a.get("no_fragment") else ""})')
            # Report what was ACTUALLY used. The ladder can fall back to a coarser,
            # unrefined attempt while the caller writes the size it asked for into the
            # spec, so the recorded mesh no longer describes the solved model.
            m['used'] = dict(attempt=i + 1, size_far=a['size_far'], curv=a.get('curv'),
                             algo3d=a['algo3d'], no_fragment=bool(a.get('no_fragment')),
                             refined=bool(refine) and not a.get('no_refine'))
            return m
        except Exception as e:                      # noqa: BLE001
            last = e
            print(f'  mesh attempt {i + 1} failed: {str(e)[:120]}')
    raise last


def _mesh_assembly_single(step_paths, out_inp, size_far=4.0, refine=None, fragment=True,
                          order2=True, verbose=False):
    """Mesh one or more STEP files as ONE bonded assembly.

    `refine`: list of (x, y, z, radius, size) balls for local refinement.
    `fragment=True` runs occ.fragment over all volumes -> shared conformal
    faces -> parts are bonded without ties (screening-level joint model).
    Returns {'volumes': {tag: bbox}, 'inp': path}.
    """
    import gmsh
    gmsh.initialize()
    gmsh.option.setNumber('General.Terminal', 1 if verbose else 0)
    gmsh.model.add('asm')
    vols = []
    for p in ([step_paths] if isinstance(step_paths, str) else step_paths):
        tags = gmsh.model.occ.importShapes(p)
        vols += [t[1] for t in tags if t[0] == 3]
    if fragment and len(vols) > 1:
        frag, _ = gmsh.model.occ.fragment([(3, vols[0])], [(3, v) for v in vols[1:]])
        vols = [t[1] for t in frag if t[0] == 3]
    gmsh.model.occ.synchronize()
    for k, v in enumerate(vols):
        gmsh.model.addPhysicalGroup(3, [v], k + 1, name=f'V{v}')
    fields = []
    for (x, y, z, rad, sz) in (refine or []):
        fid = gmsh.model.mesh.field.add('Ball')
        for k, val in [('Radius', rad), ('VIn', sz), ('VOut', size_far),
                       ('XCenter', x), ('YCenter', y), ('ZCenter', z)]:
            gmsh.model.mesh.field.setNumber(fid, k, val)
        fields.append(fid)
    if fields:
        fmin = gmsh.model.mesh.field.add('Min')
        gmsh.model.mesh.field.setNumbers(fmin, 'FieldsList', fields)
        gmsh.model.mesh.field.setAsBackgroundMesh(fmin)
    else:
        gmsh.option.setNumber('Mesh.MeshSizeMax', size_far)
    gmsh.option.setNumber('Mesh.MeshSizeFromPoints', 0)
    gmsh.option.setNumber('Mesh.MeshSizeFromCurvature', 0)
    gmsh.option.setNumber('Mesh.OptimizeNetgen', 1)
    gmsh.option.setNumber('Mesh.SecondOrderLinear', 1)  # avoids nonpositive jacobians
    gmsh.model.mesh.generate(3)
    if order2:
        gmsh.model.mesh.setOrder(2)
    gmsh.write(out_inp)
    nn = len(gmsh.model.mesh.getNodes()[0])
    gmsh.finalize()
    return dict(inp=out_inp, nodes=nn, volumes=vols)


def parse_inp(path):
    """Parse a gmsh-written .inp -> (nodes{nid:xyz}, elems{eid:[10 nids]}, elsets)."""
    nodes, elems, elsets = {}, {}, {}
    mode = cur = None
    buf = []
    for line in open(path):
        ls = line.strip()
        if ls.startswith('*'):
            u = ls.upper()
            if u.startswith('*NODE') and 'FILE' not in u and 'PRINT' not in u:
                mode = 'n'
            elif u.startswith('*ELEMENT') and 'C3D10' in u:
                mode = 'e'
                m = re.search(r'ELSET=(\S+)', u)
                cur = (m.group(1).rstrip(',') if m else 'EALL')
                elsets.setdefault(cur, [])
            else:
                mode = None
            buf = []
            continue
        p = [v for v in ls.rstrip(',').split(',') if v.strip()]
        if mode == 'n' and len(p) >= 4:
            nodes[int(p[0])] = np.array([float(p[1]), float(p[2]), float(p[3])])
        elif mode == 'e':
            buf += [int(v) for v in p]
            if len(buf) >= 11:
                elems[buf[0]] = buf[1:11]
                elsets[cur].append(buf[0])
                buf = []
    return nodes, elems, elsets


def boundary_faces(elems, eids=None):
    """Outer boundary faces of an element subset -> {sorted_tri: (eid, face_no)}."""
    seen, first = Counter(), {}
    for e in (eids if eids is not None else elems):
        c = elems[e][:4]
        for fi, f in enumerate(C3D10_FACES):
            tri = (c[f[0]], c[f[1]], c[f[2]])
            key = tuple(sorted(tri))
            seen[key] += 1
            first.setdefault(key, (e, fi + 1, tri))
    return {k: first[k] for k, n in seen.items() if n == 1}


def sel_faces(bfaces, nodes, pred):
    """[(eid, face_no)] for boundary faces whose 3 corner nodes all satisfy pred(xyz)."""
    return [(e, f) for key, (e, f, tri) in bfaces.items() if all(pred(nodes[n]) for n in tri)]


def sel_nodes(nodes, ids, pred):
    return sorted(n for n in ids if pred(nodes[n]))


def cyl_pred(axis, ctr, radius, rtol=0.25, span=None):
    """Predicate for nodes/faces on a cylindrical bore.

    axis: 'x'|'y'|'z'; ctr: point on the axis; span: (lo, hi) along the axis.
    """
    ai = {'x': 0, 'y': 1, 'z': 2}[axis]
    oi = [i for i in range(3) if i != ai]
    c = np.asarray(ctr, float)

    def p(v):
        r = np.hypot(v[oi[0]] - c[oi[0]], v[oi[1]] - c[oi[1]])
        if abs(r - radius) > rtol:
            return False
        return True if span is None else (span[0] <= v[ai] <= span[1])
    return p


def plane_pred(axis, value, tol=0.1, box=None):
    ai = {'x': 0, 'y': 1, 'z': 2}[axis]

    def p(v):
        if abs(v[ai] - value) > tol:
            return False
        if box:
            for i, (lo, hi) in box.items():
                j = {'x': 0, 'y': 1, 'z': 2}[i]
                if not (lo <= v[j] <= hi):
                    return False
        return True
    return p


# ------------------------------------------------------------------ loads
def bearing_load(nodes, nids, axis, ctr, F):
    """Cosine-weighted pin-bearing traction on the loaded half of a bore.

    Returns {nid: (fx,fy,fz)} summing exactly to F -- the red-team-validated
    model (uniform full-bore smearing under-predicts bore stress ~2.5x).
    """
    ai = {'x': 0, 'y': 1, 'z': 2}[axis]
    oi = [i for i in range(3) if i != ai]
    F = np.asarray(F, float)
    Fp = F.copy()
    Fp[ai] = 0.
    n = np.linalg.norm(Fp)
    if n < 1e-9:                      # pure axial: spread uniformly
        w = {i: 1.0 for i in nids}
    else:
        u = Fp / n
        w = {}
        c = np.asarray(ctr, float)
        for i in nids:
            d = nodes[i] - c
            d[ai] = 0.
            dn = np.linalg.norm(d)
            if dn < 1e-9:
                continue
            proj = float(d @ u) / dn
            if proj > 0:              # loaded half only
                w[i] = proj
    tot = sum(w.values())
    if tot <= 0:
        raise ValueError('bearing_load: no loaded nodes selected')
    return {i: F * (v / tot) for i, v in w.items()}


def distribute_wrench(points, centre, Fv, Mv):
    """Split a joint wrench over the link's REAL attachment points (RBE3-like).

    points: [(x,y,z)] of each attachment (bearing seat centre, rod anchor, bolt
    pattern centroid). Returns [(fx,fy,fz)] per point such that
        sum f_i = Fv          and      sum (p_i - centre) x f_i = Mv
    with minimum norm (pseudo-inverse) -- i.e. the moment is reacted by the
    whole attachment pattern, not by one seat.

    Why this exists (2026-08-15): applying a joint moment locally at a single
    small bearing seat, or as a couple across only the closest pair, produced
    physically impossible loads (239 N*m on a 22 mm 6900 seat -> 8 kN couple,
    and a bogus 475-634 MPa). The foot, for instance, hangs on two 6900 seats
    AND two pushrod anchors; the real lever arm of the pattern is ~90 mm.
    """
    P = np.asarray(points, float)
    c = np.asarray(centre, float)
    R = P - c
    n = len(P)
    A = np.zeros((6, 3 * n))
    for i in range(n):
        A[0:3, 3 * i:3 * i + 3] = np.eye(3)
        rx, ry, rz = R[i]
        A[3:6, 3 * i:3 * i + 3] = np.array([[0, -rz, ry], [rz, 0, -rx], [-ry, rx, 0]])
    b = np.concatenate([np.asarray(Fv, float), np.asarray(Mv, float)])
    f, *_ = np.linalg.lstsq(A, b, rcond=None)
    res = A @ f - b
    if np.linalg.norm(res) > 1e-6 * max(1.0, np.linalg.norm(b)):
        raise ValueError(f'wrench not representable by this pattern (residual {res})')
    return f.reshape(n, 3)


def moment_load(nodes, nids, ctr, M):
    """Distribute a pure moment M about `ctr` as a tangential nodal force field.

    f_i = w_i * (M x r_i)/|r_i|^2 scaled so sum(r_i x f_i) == M (least-squares
    exact for the axis components present); zero net force.
    """
    c = np.asarray(ctr, float)
    M = np.asarray(M, float)
    R = np.array([nodes[i] - c for i in nids])
    F = np.cross(np.broadcast_to(M, R.shape), R)
    nrm = (R ** 2).sum(1, keepdims=True)
    nrm[nrm < 1e-9] = 1e-9
    F = F / nrm
    tot = np.cross(R, F).sum(0)
    scale = np.array([M[k] / tot[k] if abs(tot[k]) > 1e-9 else 0. for k in range(3)])
    # apply per-axis scaling through the moment decomposition
    out = np.zeros_like(F)
    for k in range(3):
        if abs(M[k]) < 1e-12:
            continue
        Mk = np.zeros(3)
        Mk[k] = M[k]
        Fk = np.cross(np.broadcast_to(Mk, R.shape), R) / nrm
        tk = np.cross(R, Fk).sum(0)[k]
        if abs(tk) > 1e-9:
            out += Fk * (M[k] / tk)
    F = out
    F -= F.mean(0)     # kill residual net force
    return {i: F[k] for k, i in enumerate(nids)}


def rigid_motor(nodes, flange_nids, ref_id, name):
    """Model an actuator as a RIGID BODY on its mounting flange.

    Meshing the real housings (3600 faces) or even envelope-cylinder proxies
    blew the model up (527k nodes, 1031 MPCs, failed solve). A motor housing is
    far stiffer than the aluminium bracket it bolts to, so the standard
    treatment is a rigid body over the flange nodes with the motor mass carried
    at a reference node -- cheap, and it puts the motor's weight and its torque
    reaction into the structure where they really act.
    """
    txt = [f'*NSET, NSET=NMOT{name}']
    ids = sorted(flange_nids)
    for i in range(0, len(ids), 8):
        txt.append(','.join(str(v) for v in ids[i:i + 8]) + ',')
    txt.append(f'*RIGID BODY, NSET=NMOT{name}, REF NODE={ref_id}')
    return '\n'.join(txt) + '\n'


# --------------------------------------------------------- joint modelling
# How screws and bearings must enter a model (QA finding 2026-08-15: bonding
# CAD screws/bearing balls into a fragment mesh makes rigid threads and rigid
# ball lumps -- stiffer than reality and terrible mesh quality).
#
#   screening (whole link)  screws  -> washer_footprints() as the bonded/fixed
#                                      patch, rest of the mating face free
#                           bearing -> bearing_load()/support on the real SEAT
#                                      over the loaded arc (never a rigid bore)
#   joint submodel          screws  -> solid bolt + *TIE at thread + contact +
#                                      thermal pretension (tools/fea/bolted_pilot.py)
#                           bearing -> keep rings, replace rolling elements
#                                      with smeared_raceway_modulus()

# catalog-order radial stiffness [N/mm]; ALWAYS report a x3 sensitivity band
BEARING_KR = {'6900ZZ': 3.0e4, '6810ZZ': 1.0e5, '6814ZZ': 1.5e5, 'CRBS808AUUU': 5.0e5}


def washer_footprints(nodes, node_ids, screws, r_head=4.0, axis_tol=0.2, face_tol=0.6):
    """Node sets under the screw heads/threads on a mating face.

    `screws`: [{com, axis, d}] from link_<L>_joints.json. Returns
    {screw_index: [nid, ...]} for nodes within r_head of each screw axis, i.e.
    the patch that actually carries clamp load -- use it instead of bonding or
    fixing a whole face (which is arbitrarily stiff and hides the bolt-hole
    stress concentration).
    """
    out = {}
    for k, s in enumerate(screws):
        if not s.get('axis'):
            continue
        a = np.asarray(s['axis'], float)
        a /= np.linalg.norm(a)
        c = np.asarray(s['com'], float)
        sel = []
        for n in node_ids:
            d = nodes[n] - c
            radial = np.linalg.norm(d - (d @ a) * a)
            if radial <= r_head:
                sel.append(n)
        if sel:
            out[k] = sel
    return out


def smeared_raceway_modulus(k_r, r_mean, width, thickness):
    """E [MPa] of an annulus that reproduces a bearing's radial stiffness.

    First-order: the loaded half of the raceway acts as a compression layer of
    area pi*r_mean*width and thickness `thickness`, so k = E*A/t.
    Use for the ring-to-ring gap after deleting the rolling elements; report a
    x3 sensitivity because catalog k_r itself is load-dependent.
    """
    A = np.pi * r_mean * width
    return float(k_r * thickness / A)


def annulus_between_rings(gmsh_mod, axis, ctr, r_in, r_out, width):
    """Create the smeared-raceway annulus solid (call before occ.synchronize)."""
    ax = {'x': (1, 0, 0), 'y': (0, 1, 0), 'z': (0, 0, 1)}[axis]
    base = [ctr[i] - ax[i] * width / 2 for i in range(3)]
    outer = gmsh_mod.occ.addCylinder(*base, *[a * width for a in ax], r_out)
    inner = gmsh_mod.occ.addCylinder(*base, *[a * width for a in ax], r_in)
    cut, _ = gmsh_mod.occ.cut([(3, outer)], [(3, inner)])
    return [t[1] for t in cut if t[0] == 3]


def components(elems):
    """Connected components of the element graph -> [set(eid), ...] (largest first)."""
    adj = {}
    for e, c in elems.items():
        for n in c[:4]:
            adj.setdefault(n, []).append(e)
    seen, out = set(), []
    for e0 in elems:
        if e0 in seen:
            continue
        stack, comp = [e0], set()
        seen.add(e0)
        while stack:
            e = stack.pop()
            comp.add(e)
            for n in elems[e][:4]:
                for e2 in adj[n]:
                    if e2 not in seen:
                        seen.add(e2)
                        stack.append(e2)
        out.append(comp)
    return sorted(out, key=len, reverse=True)


def proximity_tie(nodes, elems, comp_a, comp_b, gap=2.5, name='T_ASM'):
    """*TIE surfaces joining two mesh components that are bolted in reality.

    A bolted flange leaves the parts as separate mesh components (they only
    touch through the screws), and a floating body makes the solve singular.
    Tie the boundary faces sitting within `gap` of the other body -- that is
    the clamped flange contact. Returns (deck_text, n_slave_faces).
    """
    ba, bb = boundary_faces(elems, comp_a), boundary_faces(elems, comp_b)

    def cen(bf):
        return [(sum(nodes[n] for n in tri) / 3.0, e, f) for (e, f, tri) in bf.values()]
    ca, cb = cen(ba), cen(bb)
    if not ca or not cb:
        return '', 0
    PA = np.array([c for c, _, _ in ca])
    PB = np.array([c for c, _, _ in cb])
    keep_a, keep_b = [], []
    for k in range(0, len(PA), 1500):
        d = np.linalg.norm(PA[k:k + 1500, None, :] - PB[None, :, :], axis=2).min(1)
        keep_a += [ca[k + i] for i in np.where(d <= gap)[0]]
    for k in range(0, len(PB), 1500):
        d = np.linalg.norm(PB[k:k + 1500, None, :] - PA[None, :, :], axis=2).min(1)
        keep_b += [cb[k + i] for i in np.where(d <= gap)[0]]
    if not keep_a or not keep_b:
        return '', 0
    txt = [f'*SURFACE, NAME={name}_S, TYPE=ELEMENT']
    txt += [f'{e}, S{f}' for _, e, f in keep_a]
    txt += [f'*SURFACE, NAME={name}_M, TYPE=ELEMENT']
    txt += [f'{e}, S{f}' for _, e, f in keep_b]
    txt += [f'*TIE, NAME={name}, POSITION TOLERANCE={gap * 1.5:.2f}', f'{name}_S, {name}_M', '']
    return '\n'.join(txt), len(keep_a)


def node_pair_equations(nodes, elems, comp_a, comp_b, gap=3.0, max_pairs=400,
                        exclude=()):
    """*EQUATION MPCs joining two bolted mesh components.

    Preferred over *TIE for this campaign: the flange surfaces of a proxy body
    and a machined housing are curved and offset, and CalculiX's tie machinery
    then generates ill-shaped contact elements ("nonpositive jacobian" on
    perfectly healthy tets). Direct node-to-node equations are unconditionally
    stable and represent the clamped bolted joint well enough for screening.
    Returns (deck_text, n_pairs).
    """
    # a node that already carries a *BOUNDARY cannot also appear in an MPC
    # (CalculiX: "*ERROR in cascade: the DOF corresponding to ...")
    ex = set(exclude)
    sa = sorted({n for tri in boundary_faces(elems, comp_a) for n in tri} - ex)
    sb = sorted({n for tri in boundary_faces(elems, comp_b) for n in tri} - ex)
    PA = np.array([nodes[n] for n in sa])
    PB = np.array([nodes[n] for n in sb])
    pairs = []
    for k in range(0, len(PB), 1000):
        d = np.linalg.norm(PB[k:k + 1000, None, :] - PA[None, :, :], axis=2)
        j = d.argmin(1)
        dmin = d.min(1)
        for i in np.where(dmin <= gap)[0]:
            pairs.append((sb[k + i], sa[j[i]], float(dmin[i])))
    if not pairs:
        return '', 0
    if not pairs:
        return '', 0
    pairs.sort(key=lambda p: p[2])
    # spread the constraints over the interface instead of clustering
    step = max(1, len(pairs) // max_pairs)
    pairs = pairs[::step][:max_pairs]
    used = set()
    txt = []
    for nb, na, _ in pairs:
        if nb in used:
            continue
        used.add(nb)
        for dof in (1, 2, 3):
            txt.append('*EQUATION\n2')
            txt.append(f'{nb}, {dof}, 1.0, {na}, {dof}, -1.0')
    return '\n'.join(txt) + '\n', len(used)


# ------------------------------------------------------------------ deck
def write_deck(path, nodes, elems, elsets, mat_of_elset, fixed, cloads,
               out_fields=('U', 'S'), extra='', gravity=None, extra_nodes=None,
               density_t_mm3=2.70e-9, extra_cload=''):
    """Write a linear-static CalculiX deck. cloads: {nid: (fx,fy,fz)}.

    gravity: (gx,gy,gz) in mm/s^2 -> *DLOAD GRAV on every element set, so the
    link's own weight (and any inertial factor folded into the vector) is a real
    body load rather than something we hope the joint wrench already covered.
    extra_nodes: {nid: (x,y,z)} appended to the node block -- used for the motor
    reference nodes of the rigid-body motor model.
    """
    with open(path, 'w') as f:
        f.write('*NODE, NSET=NALL\n')
        for nid in sorted(nodes):
            x, y, z = nodes[nid]
            f.write(f'{nid}, {x:.6f}, {y:.6f}, {z:.6f}\n')
        for nid, (x, y, z) in sorted((extra_nodes or {}).items()):
            f.write(f'{nid}, {x:.6f}, {y:.6f}, {z:.6f}\n')
        for es, eids in elsets.items():
            if not eids:
                continue
            f.write(f'*ELEMENT, TYPE=C3D10, ELSET={es}\n')
            for e in eids:
                c = elems[e]
                f.write(f'{e}, ' + ', '.join(map(str, c[:6])) + ',\n  '
                        + ', '.join(map(str, c[6:])) + '\n')
        mats = {}
        for es, m in mat_of_elset.items():
            mats[m['name']] = m
        for m in mats.values():
            f.write(f"*MATERIAL, NAME={m['name']}\n*ELASTIC\n{m['E']}, {m['nu']}\n")
            if gravity is not None:
                f.write(f"*DENSITY\n{density_t_mm3}\n")
        for es, m in mat_of_elset.items():
            if elsets.get(es):
                f.write(f"*SOLID SECTION, ELSET={es}, MATERIAL={m['name']}\n")
        f.write('*NSET, NSET=FIX\n')
        for i in range(0, len(fixed), 8):
            f.write(','.join(str(v) for v in fixed[i:i + 8]) + ',\n')
        f.write(extra)
        f.write('*BOUNDARY\nFIX, 1, 3\n*STEP\n*STATIC\n')
        if gravity is not None:
            g = np.asarray(gravity, float)
            mag = float(np.linalg.norm(g))
            if mag > 0:
                u = g / mag
                f.write('*DLOAD\n')
                for es in elsets:
                    if elsets[es]:
                        f.write(f'{es}, GRAV, {mag:.4f}, {u[0]:.6f}, {u[1]:.6f}, {u[2]:.6f}\n')
        f.write('*CLOAD\n')
        for nid, v in sorted(cloads.items()):
            for k in range(3):
                if abs(v[k]) > 1e-12:
                    f.write(f'{nid}, {k + 1}, {v[k]:.6f}\n')
        f.write(extra_cload)          # rotational dofs of rigid-body reference nodes
        f.write('*NODE FILE\n' + ', '.join(x for x in out_fields if x == 'U')
                + '\n*EL FILE\n' + ', '.join(x for x in out_fields if x != 'U') + '\n*END STEP\n')
    return path


def run_ccx(job_dir, job, threads=None, lock=LOCK_SOLVE, timeout=None):
    """Solve with a global lock so parallel agents don't thrash 8 cores/15 GB."""
    threads = threads or int(os.environ.get('PYG_CCX_THREADS', 6))
    cmd = (f'cd {job_dir} && flock {lock} env OMP_NUM_THREADS={threads} '
           f'CCX_NPROC_EQUATION_SOLVER={threads} nice -n 10 {CCX} -i {job}')
    r = subprocess.run(['bash', '-lc', cmd], capture_output=True, text=True, timeout=timeout)
    tail = (r.stdout or '')[-3000:]
    ok = os.path.exists(f'{job_dir}/{job}.frd') and os.path.getsize(f'{job_dir}/{job}.frd') > 1000
    errs = [l for l in (r.stdout or '').splitlines() if 'ERROR' in l.upper()]
    return dict(ok=ok, errors=errs[:10], tail=tail)


# ------------------------------------------------------------------- post
def parse_frd(path):
    """-> (coords{nid:xyz}, blocks[(name, {nid: [vals]})]) for DISP/STRESS."""
    coords, blocks = {}, []
    lines = open(path).readlines()
    i, n = 0, len(lines)
    while i < n:
        L = lines[i]
        if L.startswith('    2C'):
            i += 1
            while i < n and lines[i].startswith(' -1'):
                nid = int(lines[i][3:13])
                coords[nid] = (float(lines[i][13:25]), float(lines[i][25:37]), float(lines[i][37:49]))
                i += 1
            continue
        if L.startswith('  100C'):
            j, name = i + 1, None
            while j < n and lines[j].startswith(' -'):
                if lines[j].startswith(' -4'):
                    name = lines[j].split()[1]
                if lines[j].startswith(' -1'):
                    break
                j += 1
            if name in ('DISP', 'STRESS'):
                nv = 3 if name == 'DISP' else 6
                d = {}
                i = j
                while i < n and lines[i].startswith(' -1'):
                    nid = int(lines[i][3:13])
                    d[nid] = [float(lines[i][13 + 12 * k:25 + 12 * k]) for k in range(nv)]
                    i += 1
                blocks.append((name, d))
                continue
        i += 1
    return coords, blocks


def von_mises(s):
    sxx, syy, szz, sxy, syz, szx = np.asarray(s).T
    return np.sqrt(0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
                   + 3 * (sxy ** 2 + syz ** 2 + szx ** 2))


def summarize(frd, nodes=None, load_nids=(), filter_mm=1.5, yield_=276.0, sf_load=1.25):
    """Max/P99 von Mises, with an artifact-filtered value away from load nodes."""
    coords, blocks = parse_frd(frd)
    S = [d for nm, d in blocks if nm == 'STRESS'][-1]
    U = [d for nm, d in blocks if nm == 'DISP'][-1]
    ids = np.array(sorted(S))
    vm = von_mises([S[i] for i in ids])
    P = np.array([coords[i] for i in ids])
    out = dict(max_vM=float(vm.max()), p99_vM=float(np.percentile(vm, 99)),
               argmax_xyz=[round(float(v), 1) for v in P[int(np.argmax(vm))]],
               max_disp_um=float(max(np.linalg.norm(U[i]) for i in U) * 1000),
               SF=float(yield_ / (vm.max() * sf_load)))
    if len(load_nids):
        LP = np.array([coords[i] for i in load_nids if i in coords])
        if len(LP):
            keep = np.ones(len(ids), bool)
            for k in range(0, len(LP), 400):
                d = np.linalg.norm(P[:, None, :] - LP[None, k:k + 400, :], axis=2).min(1)
                keep &= d > filter_mm
            if keep.any():
                out['max_vM_filtered'] = float(vm[keep].max())
                out['SF_filtered'] = float(yield_ / (vm[keep].max() * sf_load))
                out['argmax_filtered_xyz'] = [round(float(v), 1) for v in P[keep][int(np.argmax(vm[keep]))]]
    return out


def export_viewer_case(frd, inp, out_json, desc, nu=0.33, E=68900.0, case_key=None,
                       merge_into=None):
    """Write the WebGL-viewer case schema (surface nodes + fields)."""
    nodes, elems, _ = parse_inp(inp)
    bf = boundary_faces(elems)
    tris = [tri for (_, _, tri) in bf.values()]
    coords, blocks = parse_frd(frd)
    S = [d for nm, d in blocks if nm == 'STRESS'][-1]
    U = [d for nm, d in blocks if nm == 'DISP'][-1]
    used = sorted({t for tri in tris for t in tri})
    idx = {nid: k for k, nid in enumerate(used)}
    xyz = [[round(float(v), 2) for v in nodes[n]] for n in used]
    dsp = [[round(float(v), 6) for v in U.get(n, (0, 0, 0))] for n in used]
    Sm = np.array([S.get(n, [0] * 6) for n in used])
    sxx, syy, szz, sxy, syz, szx = Sm.T
    vm = von_mises(Sm)
    P1 = np.zeros(len(used)); P2 = np.zeros(len(used)); P3 = np.zeros(len(used))
    for k in range(len(used)):
        T = np.array([[sxx[k], sxy[k], szx[k]], [sxy[k], syy[k], syz[k]], [szx[k], syz[k], szz[k]]])
        ev = np.linalg.eigvalsh(T)
        P1[k], P2[k], P3[k] = ev[2], ev[1], ev[0]
    Uv = np.array(dsp)
    rl = lambda a, d=2: [round(float(v), d) for v in a]
    case = dict(nodes=xyz, disp=dsp, tris=[[idx[a], idx[b], idx[c]] for a, b, c in tris],
                fields=dict(vM=rl(vm), S1=rl(P1), S2=rl(P2), S3=rl(P3),
                            Sxx=rl(sxx), Syy=rl(syy), Szz=rl(szz),
                            Sxy=rl(sxy), Syz=rl(syz), Szx=rl(szx),
                            eps_vM=rl(vm * (2 * (1 + nu) / (3 * E)) * 1e6, 1),
                            U_mag=rl(np.linalg.norm(Uv, axis=1) * 1000),
                            Ux=rl(Uv[:, 0] * 1000), Uy=rl(Uv[:, 1] * 1000), Uz=rl(Uv[:, 2] * 1000)),
                desc=desc)
    if merge_into and os.path.exists(merge_into):
        data = json.load(open(merge_into))
        data[case_key] = case
        json.dump(data, open(merge_into, 'w'), separators=(',', ':'))
    json.dump({case_key or 'case': case} if case_key else case,
              open(out_json, 'w'), separators=(',', ':'))
    return dict(surf_nodes=len(used), tris=len(tris), path=out_json)
