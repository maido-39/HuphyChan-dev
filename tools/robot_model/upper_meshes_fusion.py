"""Pull the upper-body meshes out of Fusion 360 - the STEP the campaign has covers the legs only.

The torso, the shoulder link and the arm exist only in the live Fusion document, so their
triangles are fetched over the MCP connector (`meshManager` per BRep body, low-quality
tessellation, assembly coordinates in cm) and written as STL in each rigid body's link frame,
matching the convention the leg meshes already use: origin on the joint, simulator axes
(x forward, y left, z up), metres.

Suppressed geometry is skipped: the light bulb of `ArmR_fullDoF` is off, and its 6.497 kg
alternative arm must not appear in either the mass properties or the picture.

One MCP round trip per rigid body keeps each payload to a few hundred kB.

Usage: upper_meshes_fusion.py   (mjlab venv, Fusion MCP reachable)
"""
import json
import os
import sys

import numpy as np
import trimesh

sys.path.insert(0, '/home/syaro/MikuchanRemote/Human-Pygmalion/tools/fusion')
import mcp_client as M  # noqa: E402

OUT = ('/home/syaro/MikuchanRemote/Human-Pygmalion/pygmalion_locomotion/assets/'
       'pygmalion_v2/meshes')
R_SIM = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])   # cad -> sim
# rigid body -> (origin in CAD mm, occurrence filters that belong to it)
GROUPS = {
    'torso': (np.array([0.0, 70.0, 177.5]), ['Torso:1', 'Neck:1']),
    # the CAD has ONE arm, so the shoulder-pitch motor is fetched on its own and drawn
    # twice - once as measured, once y-mirrored - to match the two-armed mass properties
    'torso_shpitch': (np.array([0.0, 70.0, 177.5]),
                      ['Actuator:1/Robstride RS03 - Shoulder_Pitch']),
    'shoulder_pitch_link': (np.array([-200.0, 85.0, 540.0]),
                            ['Arm_R:1/Shoulder-Pitch2Roll',
                             'Actuator:1/Robstride RS03 - Shoulder_Roll']),
    'arm': (np.array([-200.0, 85.0, 540.0]), ['Arm_R:1/ArmR_Dummy']),
}

LIST_SCRIPT = r'''
import adsk.core, adsk.fusion

def collect(o, path, live, want, out):
    live = live and o.isLightBulbOn
    p = path + "/" + o.name
    if live and any(w in p for w in want):
        for i in range(o.bRepBodies.count):
            b = o.bRepBodies.item(i)
            if b.isLightBulbOn:
                out.append([p, i, b.name])
    for i in range(o.childOccurrences.count):
        collect(o.childOccurrences.item(i), p, live, want, out)

def run(_context: str):
    app = adsk.core.Application.get()
    root = adsk.fusion.Design.cast(app.activeProduct).rootComponent
    out = []
    collect(root.occurrences.itemByName("Joints_UpperBody:1"), "", True, WANT, out)
    emit(out)
'''

MESH_SCRIPT = r'''
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
    occ = find(root.occurrences.itemByName("Joints_UpperBody:1"), "", TARGET)
    b = occ.bRepBodies.item(IDX)
    calc = b.meshManager.createMeshCalculator()
    calc.setQuality(adsk.fusion.TriangleMeshQualityOptions.LowQualityTriangleMesh)
    m = calc.calculate()
    v = m.nodeCoordinatesAsDouble
    f = m.nodeIndices
    # Payloads come back through the exception channel (mcp_client.script) because this
    # Fusion build returns an empty message for anything printed. That channel carries
    # hundreds of kB, so a body goes out in a couple of packed-binary slices.
    if __WHAT__ == "meta":
        emit({"nv": len(v), "nf": len(f)})
    src = v if __WHAT__ == "v" else f
    part = src[__START__:__START__ + __COUNT__]
    fmt = "<%df" % len(part) if __WHAT__ == "v" else "<%dI" % len(part)
    emit({"b": base64.b64encode(struct.pack(fmt, *part)).decode()})
'''


def _run(src, tries=5):
    """One MCP script call that hands its payload back through the exception channel."""
    return M.script(src, tries=tries)


def fetch(want):
    """Body by body - one group in one payload overflows the connector."""
    import base64
    import struct
    lst = _run(LIST_SCRIPT.replace('WANT', json.dumps(want)))
    out, failed = [], []
    for path, idx, name in lst:
        def call(what, start=0, count=0):
            src = (MESH_SCRIPT.replace('TARGET', json.dumps(path)).replace('IDX', str(idx))
                   .replace('__WHAT__', json.dumps(what)).replace('__START__', str(start))
                   .replace('__COUNT__', str(count)))
            return _run(src)

        def stream(what, n, fmt, chunk=40000):
            buf = []
            for st in range(0, n, chunk):
                cnt = min(chunk, n - st)
                d = call(what, st, cnt)
                buf.append(np.array(struct.unpack(fmt % cnt, base64.b64decode(d['b']))))
            return np.concatenate(buf) if buf else np.zeros(0)

        try:
            meta = call('meta')
            v = stream('v', meta['nv'], '<%df').astype(float)
            f = stream('f', meta['nf'], '<%dI').astype(int)
        except Exception as e:
            failed.append((name, str(e)[:60]))
            print(f'    {name[:40]:40s}  SKIPPED ({str(e)[:40]})', flush=True)
            continue
        out.append(dict(n=name, v=v, f=f))
        print(f'    {name[:40]:40s} {len(f) // 3:6d} tris', flush=True)
    if failed:
        print(f'    !! {len(failed)} bodies could not be fetched', flush=True)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    M.connect()
    stats = {}
    for body, (origin, want) in GROUPS.items():
        parts = fetch(want)
        meshes = []
        for p in parts:
            v = p['v'].reshape(-1, 3) * 10.0                            # cm -> mm, CAD frame
            f = p['f'].reshape(-1, 3)
            assert f.max() < len(v), f"{p['n']}: index {f.max()} vs {len(v)} verts"
            meshes.append(trimesh.Trimesh((v - origin) @ R_SIM.T / 1000.0, f, process=False))
        assert meshes, f'{body}: nothing fetched for {want}'
        mesh = trimesh.util.concatenate(meshes)
        mesh.export(f'{OUT}/{body}.stl')
        hull = mesh.convex_hull
        hull.export(f'{OUT}/{body}_hull.stl')
        mm = mesh.copy()
        mm.vertices[:, 1] *= -1
        mm.faces = mm.faces[:, [0, 2, 1]]
        mm.export(f'{OUT}/R_{body}.stl')
        hh = hull.copy()
        hh.vertices[:, 1] *= -1
        hh.faces = hh.faces[:, [0, 2, 1]]
        hh.export(f'{OUT}/R_{body}_hull.stl')
        b = mesh.bounds
        stats[body] = dict(parts=len(parts), faces=int(len(mesh.faces)),
                           bbox=np.round(b[1] - b[0], 3).tolist())
        print(f'{body:22s} {len(parts):3d} parts · {len(mesh.faces):7d} tris · '
              f'bbox {np.round(b[1] - b[0], 3)} m', flush=True)
    json.dump(stats, open(f'{OUT}/upper_meshes.json', 'w'), indent=1)
    print(f'-> {OUT}')


if __name__ == '__main__':
    main()
