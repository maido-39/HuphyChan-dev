"""Pull every aluminium part out of Fusion - metadata and its own mesh - for the 3D-print
mass survey.

Some parts were actually printed rather than machined, so the CAD's aluminium mass is only
a reference and the real ones have to be weighed. This produces the raw material for that
sheet: one row per aluminium body with the link it belongs to, its CAD mass at 6061 density,
and a picture of that part ALONE.

Meshes come over the MCP connector through the exception channel (mcp_client.script), body
by body, straight into the key space `index.json` already uses - keyed by the body's PATH,
not by the order Fusion happened to walk in, so a partial run and a later top-up land in the
same place. Anything already fetched is skipped, so re-running only costs the missing parts.

Usage: alu_parts_fetch.py [--limit=N]     (mjlab venv, Fusion MCP reachable)
"""
import base64
import json
import os
import struct
import sys

import numpy as np

sys.path.insert(0, '/home/syaro/MikuchanRemote/Human-Pygmalion/tools/fusion')
import mcp_client as M  # noqa: E402

OUT = os.environ.get('ALU_PARTS_DIR', '/home/syaro/pyg_fea/fusion/alu_parts')
MESHES = f'{OUT}/meshes.npz'
INDEX = f'{OUT}/index.json'

LIST_SRC = r'''
import adsk.core, adsk.fusion

def walk(o, path, live, out):
    live = live and o.isLightBulbOn
    p = path + "/" + o.name
    for i in range(o.bRepBodies.count):
        b = o.bRepBodies.item(i)
        mat = b.material.name if b.material else "?"
        if "Alumin" not in mat:
            continue
        pr = b.physicalProperties
        bb = b.boundingBox
        out.append({
            "path": p, "idx": i, "body": b.name, "occ": o.name,
            "hidden": not (live and b.isLightBulbOn),
            "comp": o.component.name if o.component else o.name,
            "mass_g": round(pr.mass * 1000.0, 3),
            "vol_cm3": round(pr.volume, 4),
            "com_mm": [round(pr.centerOfMass.x * 10, 3), round(pr.centerOfMass.y * 10, 3),
                       round(pr.centerOfMass.z * 10, 3)],
            "bbox_mm": [round((bb.maxPoint.x - bb.minPoint.x) * 10, 2),
                        round((bb.maxPoint.y - bb.minPoint.y) * 10, 2),
                        round((bb.maxPoint.z - bb.minPoint.z) * 10, 2)],
            "mat": mat})
    for i in range(o.childOccurrences.count):
        walk(o.childOccurrences.item(i), p, live, out)

def run(_context: str):
    app = adsk.core.Application.get()
    root = adsk.fusion.Design.cast(app.activeProduct).rootComponent
    out = []
    for i in range(root.occurrences.count):
        walk(root.occurrences.item(i), "", True, out)
    emit(out)
'''

MESH_SRC = r'''
import adsk.core, adsk.fusion, struct, base64

def find(o, path, target):
    p = path + "/" + o.name
    if p == target:
        return o
    for i in range(o.childOccurrences.count):
        r = find(o.childOccurrences.item(i), p, target)
        if r:
            return r
    return None

def run(_context: str):
    app = adsk.core.Application.get()
    root = adsk.fusion.Design.cast(app.activeProduct).rootComponent
    occ = None
    for i in range(root.occurrences.count):
        occ = find(root.occurrences.item(i), "", TARGET)
        if occ:
            break
    b = occ.bRepBodies.item(IDX)
    calc = b.meshManager.createMeshCalculator()
    calc.setQuality(adsk.fusion.TriangleMeshQualityOptions.LowQualityTriangleMesh)
    m = calc.calculate()
    v = m.nodeCoordinatesAsDouble
    f = m.nodeIndices
    if __WHAT__ == "meta":
        emit({"nv": len(v), "nf": len(f)})
    src = v if __WHAT__ == "v" else f
    part = src[__START__:__START__ + __COUNT__]
    fmt = "<%df" % len(part) if __WHAT__ == "v" else "<%dI" % len(part)
    emit({"b": base64.b64encode(struct.pack(fmt, *part)).decode()})
'''


def fetch_mesh(path, idx, chunk=40000):
    def call(what, start=0, count=0):
        src = (MESH_SRC.replace('TARGET', json.dumps(path)).replace('IDX', str(idx))
               .replace('__WHAT__', json.dumps(what)).replace('__START__', str(start))
               .replace('__COUNT__', str(count)))
        return M.script(src)

    def stream(what, n, fmt):
        buf = []
        for st in range(0, n, chunk):
            cnt = min(chunk, n - st)
            d = call(what, st, cnt)
            buf.append(np.array(struct.unpack(fmt % cnt, base64.b64decode(d['b']))))
        return np.concatenate(buf) if buf else np.zeros(0)

    meta = call('meta')
    v = stream('v', meta['nv'], '<%df').astype(float).reshape(-1, 3) * 10.0   # cm -> mm
    f = stream('f', meta['nf'], '<%dI').astype(int).reshape(-1, 3)
    return v, f


def link_of(f):
    """Rigid body a Fusion aluminium body belongs to, by its group and name."""
    g = f['occ'].split(':')[0]
    n = f['body']
    if g == 'CenterParts':
        return 'base_link (골반)'
    if g == 'HipPitch2Roll':
        return 'hip_pitch_link'
    if g in ('HipRoll2Yaw', 'PipRoll2Yaw'):
        return 'hip_roll_link'
    if g in ('HipYaw2Knee', 'CenterPin_RS03'):
        return 'thigh_link (허벅지)'
    if g == 'Knee2Ankle':
        return 'shin_link (정강이)'
    if g == 'Ankle2Feet':
        if n.startswith('Arm_') or n.startswith('AnkleBrace'):
            return 'shin/foot (푸시로드)'
        if n == 'AnkleUniversalJointCore':
            return 'ankle_pitch_link'
        if n.startswith(('FEET', 'AnkleFeetPillow', 'Ankle_Stopper_Roll', 'Flange')):
            return 'foot_link (발)'
        return 'shin_link (정강이)'
    if g.startswith(('Torso', 'Neck', 'Waist', 'DR2020', 'DF2020')):
        return 'torso_link (몸통)'
    if g.startswith('Shoulder'):
        return 'shoulder_pitch_link'
    if 'Arm' in g:
        return 'arm_link (팔)'
    return '(미배정)'


def main():
    limit = int(next((a.split('=')[1] for a in sys.argv if a.startswith('--limit=')), 0))
    os.makedirs(OUT, exist_ok=True)
    ALL = f'{OUT}/all_meshes.npz'
    if os.path.exists(INDEX):
        meta = json.load(open(INDEX))
    else:
        # no index yet for this data directory: build it from what Fusion reports now, so a
        # NEW CAD revision is one `ALU_PARTS_DIR=... alu_parts_fetch.py` away
        M.connect()
        rows0 = M.script(LIST_SRC)
        meta = []
        for i, f in enumerate(rows0):
            meta.append(dict(link=link_of(f), occ=f['occ'], body=f['body'], mass_g=f['mass_g'],
                             vol=f['vol_cm3'], path=f'{f["path"]}::{f["body"]}', key=f'{i:03d}',
                             group=f['occ'].split(':')[0], com_mm=f['com_mm'],
                             bbox_mm=f['bbox_mm'], hidden=f['hidden'], mesh_src=None))
        json.dump(meta, open(INDEX, 'w'), indent=1, ensure_ascii=False)
        print(f'bootstrapped {INDEX} with {len(meta)} aluminium bodies '
              f'({sum(1 for r in meta if r["hidden"])} hidden, kept and flagged)', flush=True)
    by_path = {r['path']: r for r in meta}
    cache = dict(np.load(ALL)) if os.path.exists(ALL) else {}
    have = {k.split('|')[0] for k in cache}

    M.connect()
    rows = M.script(LIST_SRC)
    print(f'{len(rows)} live aluminium bodies in Fusion; '
          f'{len(have)}/{len(meta)} already have a mesh', flush=True)

    todo = []
    for f in rows:
        key = f'{f["path"]}::{f["body"]}'
        r = by_path.get(key)
        if r is None:
            print(f'  ! Fusion body not in the index: {key[:70]}', flush=True)
            continue
        if r['key'] in have:
            continue
        todo.append((r, f))
    if limit:
        todo = todo[:limit]
    print(f'{len(todo)} to fetch', flush=True)

    done, failed = 0, []
    for n, (r, f) in enumerate(todo):
        try:
            v, faces = fetch_mesh(f['path'], f['idx'])
        except Exception as e:
            failed.append((r, str(e).strip().splitlines()[-1][:90]))
            print(f'  [{n:3d}] {r["body"][:26]:26s} FAILED {failed[-1][1]}', flush=True)
            continue
        cache[f'{r["key"]}|v'] = v
        cache[f'{r["key"]}|f'] = faces
        r['mesh_src'] = 'Fusion'
        done += 1
        print(f'  [{n:3d}] {r["occ"].split(":")[0][:24]:24s} {r["body"][:22]:22s} '
              f'{r["mass_g"]:8.2f} g  {len(faces):6d} tris', flush=True)
        if done % 8 == 0:
            np.savez_compressed(ALL, **cache)
            json.dump(meta, open(INDEX, 'w'), indent=1, ensure_ascii=False)
    np.savez_compressed(ALL, **cache)
    json.dump(meta, open(INDEX, 'w'), indent=1, ensure_ascii=False)
    have = {k.split('|')[0] for k in cache}
    print(f'\n{len(have)}/{len(meta)} parts now have a mesh  (+{done} this run)')
    if failed:
        print(f'{len(failed)} failed:')
        for r, e in failed[:10]:
            print(f'   {r["body"][:26]:26s} {e}')
    print(f'-> {ALL}')


if __name__ == '__main__':
    main()
