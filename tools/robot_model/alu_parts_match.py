"""Match every aluminium body Fusion reports to its solid in the STEP export.

The part survey needs a picture of each aluminium part on its own. Fusion knows the part
NAMES; the STEP export holds the geometry the campaign already meshes. Neither carries the
other's key, so the two are joined on physics: a solid's VOLUME and its CENTRE OF MASS in
assembly coordinates identify it uniquely - two different parts do not share both to within
1 % and 2 mm.

Whatever fails to match is reported rather than guessed at; the STEP is one revision behind
Fusion (260814 v1 vs 260819 v4) and does not contain the upper body at all, so those parts
have to come from Fusion directly.

Usage: alu_parts_match.py [--size=5]   (mjlab .venv python)
"""
import json
import os
import sys

import numpy as np
import gmsh
import trimesh

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
STEPS = '/home/syaro/pyg_fea/steps'
META = '/home/syaro/pyg_fea/fusion/alu_meta.json'
OUT = '/home/syaro/pyg_fea/fusion/alu_parts'
# Fusion occurrence group -> the STEP file that was exported for it
GROUP_STEP = {'CenterParts': 'link_L6_pelvis', 'HipPitch2Roll': 'link_L5_hip_pitchroll',
              'HipRoll2Yaw': 'link_L4_hip_yaw', 'HipYaw2Knee': 'link_L3_thigh',
              'Knee2Ankle': 'link_L2_shin', 'Ankle2Feet': 'link_L1_ankle_foot',
              'Flange': 'link_L1_ankle_foot', 'CenterPin_RS03': 'link_L3_thigh'}
VOL_TOL = 0.01          # relative
COM_TOL = 2.0           # mm


def step_solids(path, size):
    """[(volume cm3, com mm, vertices mm, faces)] one per solid."""
    gmsh.model.add(os.path.basename(path))
    gmsh.model.occ.importShapes(path)
    gmsh.model.occ.synchronize()
    gmsh.option.setNumber('Mesh.MeshSizeMax', size)
    gmsh.option.setNumber('Mesh.MeshSizeFromCurvature', 16)
    gmsh.option.setNumber('Mesh.MeshSizeMin', size / 6)
    gmsh.model.mesh.generate(2)
    tags, coords, _ = gmsh.model.mesh.getNodes()
    xyz = np.asarray(coords).reshape(-1, 3)
    idx = {int(t): i for i, t in enumerate(tags)}
    out = []
    for _, vol in gmsh.model.getEntities(3):
        tris = []
        for fd, ft in gmsh.model.getBoundary([(3, vol)], oriented=False, recursive=False):
            et, _, nodes = gmsh.model.mesh.getElements(2, ft)
            for t, n in zip(et, nodes):
                if t == 2:
                    tris.append(np.asarray(n).reshape(-1, 3))
        if not tris:
            continue
        T = np.vectorize(idx.get)(np.vstack(tris))
        m = trimesh.Trimesh(xyz, T, process=True)
        m.remove_unreferenced_vertices()
        trimesh.repair.fix_normals(m)
        v = abs(m.volume) / 1000.0 if m.is_watertight else 0.0
        com = np.asarray(m.center_mass if m.is_watertight else m.centroid)
        out.append((v, com, m.vertices.copy(), m.faces.copy()))
    gmsh.model.remove()
    return out


def main():
    size = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--size=')), 5))
    os.makedirs(OUT, exist_ok=True)
    meta = json.load(open(META))
    for i, r in enumerate(meta):
        r['key'] = f'{i:03d}'
        r['group'] = r['occ'].split(':')[0]
        r['com_mm'] = None            # filled from bodies.json below

    B = json.load(open('/home/syaro/pyg_fea/fusion/bodies.json'))
    for r in meta:
        r['com_mm'] = (np.array(B[r['path']]['c']) * 10.0).tolist()

    gmsh.initialize()
    gmsh.option.setNumber('General.Terminal', 0)
    solids = {}
    for f in sorted(set(GROUP_STEP.values())):
        p = f'{STEPS}/{f}.step'
        if not os.path.exists(p):
            print(f'  {f}: MISSING', flush=True)
            continue
        solids[f] = step_solids(p, size)
        print(f'  {f}: {len(solids[f])} solids', flush=True)
    gmsh.finalize()

    cache, matched, unmatched = {}, [], []
    used = {k: set() for k in solids}
    for r in meta:
        f = GROUP_STEP.get(r['group'])
        best, bd = None, None
        if f in solids:
            for j, (v, com, V, F) in enumerate(solids[f]):
                if j in used[f] or v <= 0:
                    continue
                dv = abs(v - r['vol']) / max(r['vol'], 1e-9)
                dc = float(np.linalg.norm(com - np.array(r['com_mm'])))
                if dv < VOL_TOL and dc < COM_TOL and (bd is None or dc < bd):
                    best, bd = j, dc
        if best is None:
            unmatched.append(r)
            continue
        used[f].add(best)
        v, com, V, F = solids[f][best]
        cache[f'{r["key"]}|v'] = V
        cache[f'{r["key"]}|f'] = F
        r['match'] = dict(step=f, solid=best, com_err_mm=round(bd, 3),
                          vol_step_cm3=round(v, 3))
        matched.append(r)

    np.savez_compressed(f'{OUT}/step_meshes.npz', **cache)
    json.dump(meta, open(f'{OUT}/index.json', 'w'), indent=1, ensure_ascii=False)
    print(f'\nmatched {len(matched)}/{len(meta)} aluminium parts from the STEP')
    print(f'worst COM error {max((r["match"]["com_err_mm"] for r in matched), default=0):.2f} mm')
    if unmatched:
        print(f'\n{len(unmatched)} still need Fusion (upper body, or changed since the STEP):')
        for r in unmatched:
            print(f'   {r["link"][:20]:20s} {r["occ"][:26]:26s} {r["body"][:22]:22s} '
                  f'{r["mass_g"]:7.2f} g')
    print(f'-> {OUT}/step_meshes.npz')


if __name__ == '__main__':
    main()
