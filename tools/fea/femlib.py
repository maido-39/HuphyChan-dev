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


# ------------------------------------------------------------------ mesh
def mesh_assembly(step_paths, out_inp, size_far=4.0, refine=None, fragment=True,
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


# ------------------------------------------------------------------ deck
def write_deck(path, nodes, elems, elsets, mat_of_elset, fixed, cloads,
               out_fields=('U', 'S'), extra=''):
    """Write a linear-static CalculiX deck. cloads: {nid: (fx,fy,fz)}."""
    with open(path, 'w') as f:
        f.write('*NODE, NSET=NALL\n')
        for nid in sorted(nodes):
            x, y, z = nodes[nid]
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
        for es, m in mat_of_elset.items():
            if elsets.get(es):
                f.write(f"*SOLID SECTION, ELSET={es}, MATERIAL={m['name']}\n")
        f.write('*NSET, NSET=FIX\n')
        for i in range(0, len(fixed), 8):
            f.write(','.join(str(v) for v in fixed[i:i + 8]) + ',\n')
        f.write(extra)
        f.write('*BOUNDARY\nFIX, 1, 3\n*STEP\n*STATIC\n*CLOAD\n')
        for nid, v in sorted(cloads.items()):
            for k in range(3):
                if abs(v[k]) > 1e-12:
                    f.write(f'{nid}, {k + 1}, {v[k]:.6f}\n')
        f.write('*NODE FILE\n' + ', '.join(x for x in out_fields if x == 'U')
                + '\n*EL FILE\n' + ', '.join(x for x in out_fields if x != 'U') + '\n*END STEP\n')
    return path


def run_ccx(job_dir, job, threads=6, lock=LOCK_SOLVE, timeout=None):
    """Solve with a global lock so parallel agents don't thrash 8 cores/15 GB."""
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
