"""Data for the assembly viewer: every fastener, what it is called, and where it goes.

Two sources, and the second is optional so the viewer works even while Fusion is busy:
  * `bodies.json` (tools/fusion/dump_bodies.py) always has each fastener's centre of mass
    and its Fusion component name, and the name carries the standard designation -
    "Hexagon Socket Countersunk Head Screw ISO 10642 - M4 x 16 Steel 8.8 Plain v1".
  * `fasteners.json` (tools/fusion/dump_fasteners.py) adds the occurrence TRANSFORM, so the
    viewer can draw a screw pointing the way it actually goes in rather than a bare marker.
    Fusion rejects scripts while a command dialog is open, so this file may not exist yet;
    the viewer degrades to spheres and says so.

Everything is emitted in the SIMULATOR frame (x forward, y left, z up, metres) at the zero
pose, where every link frame coincides with its CAD placement, so the fasteners and the link
meshes line up with one shared transform: sim = (cad_mm - pelvis_origin) turned +90 deg
about z, in metres.

The CAD models one leg and one arm; the other side is emitted as a flagged mirror.

Usage: build_data.py   (mjlab .venv python)
"""
import json
import os
import re
import shutil
import sys

import numpy as np

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
sys.path.insert(0, f'{REPO}/tools/robot_model')
sys.path.insert(0, f'{REPO}/tools/fusion')
from massprops_fusion import classify                       # noqa: E402
from dump_fasteners import designation                      # noqa: E402

BODIES = '/home/syaro/pyg_fea/fusion/bodies.json'
FAST = '/home/syaro/pyg_fea/fusion/fasteners.json'
OUT = f'{REPO}/tools/assembly_viewer'
MESHDIR = f'{REPO}/pygmalion_locomotion/assets/pygmalion_v2/meshes'
XML = f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/pygmalion_v2.xml'
PELVIS = np.array([0.0, 70.0, 60.0])                        # CAD mm, the base link origin
R = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
KEY = ('Screw', 'Bolt', 'Nut', 'Washer', 'Pin')
# body stem -> mesh stem, only where the two genuinely differ
BODY_ALIAS = {'base_link': 'pelvis', 'thigh_link': 'thigh', 'shin_link': 'shin',
              'foot_link': 'foot', 'torso_link': 'torso', 'arm_link': 'arm'}
# meshes that ride a body without being named after it: the CAD has ONE shoulder-pitch
# motor, drawn on the torso for both arms
EXTRA_MESH = {'torso_link': ('torso_shpitch', 'R_torso_shpitch')}
# bodies that are deliberately not meshed - the ankle universal-joint cross
NO_MESH = {'ankle_pitch_link'}


def to_sim(cad_mm):
    return R @ (np.asarray(cad_mm, float) - PELVIS) / 1000.0


def main():
    B = json.load(open(BODIES))
    axes = {}
    if os.path.exists(FAST):
        for f in json.load(open(FAST)):
            axes[f['path']] = f
    screws, seen = [], {}
    for path, rec in B.items():
        if not rec['live']:
            continue
        occ = path.split('::')[0]
        seg = next((s for s in occ.split('/') if any(k in s for k in KEY)), None)
        if seg is None:
            continue
        e = seen.get(occ)
        if e is None:
            d = designation(seg)
            body = classify(path) or '?'
            e = dict(occ=occ, name=re.sub(r':\d+$', '', seg), body=body, mass_g=0.0,
                     pos=[0.0, 0.0, 0.0], m_sum=0.0, **d)
            seen[occ] = e
            screws.append(e)
        # mass-weighted centre over the occurrence's bodies
        c = np.array(rec['c'], float) * 10.0                 # cm -> mm, CAD
        e['pos'] = list(np.array(e['pos']) * e['m_sum'] + c * rec['m'])
        e['m_sum'] += rec['m']
        e['pos'] = list(np.array(e['pos']) / max(e['m_sum'], 1e-12))
        e['mass_g'] += rec['m'] * 1000.0

    out = []
    out = []
    for i, e in enumerate(screws):
        ax, seat = None, None
        if e['occ'] in axes:
            f = axes[e['occ']]
            ax = [round(float(v), 4) for v in R @ np.array(f['axis'], float)]
            # The Fusion fastener components put their ORIGIN on the BEARING FACE - measured,
            # not assumed: the origin sits along +axis from the bounding-box centre by
            # exactly (length/2 - head height) for every size in the assembly (M4x12 +4.0 of
            # 16.0, M4x20 +7.4 of 22.8, M3x60 +28.5 of 63.0, 283/283 positive). So the head
            # always grows along +axis, the shank along -axis, and the origin is the point an
            # assembler cares about: where the head lands.
            seat = np.array(f['pos'], float)
        anchor = seat if seat is not None else np.array(e['pos'], float)
        p = to_sim(anchor)
        out.append(dict(id=i, name=e['name'], size=e['size'], head=e['head'], std=e['std'],
                        grade=e['grade'], body=e['body'], mass_g=round(e['mass_g'], 2),
                        anchor=('bearing face' if seat is not None else 'centre of mass'),
                        cad_mm=[round(float(v), 1) for v in anchor],
                        pos=[round(float(v), 5) for v in p],
                        axis=ax,
                        side='C' if abs(p[1]) < 0.02 else 'L'))

    # link meshes, placed by the simulator at the zero pose
    import mujoco
    m = mujoco.MjModel.from_xml_path(XML)
    d = mujoco.MjData(m)
    d.qpos[:] = 0
    d.qpos[3] = 1.0
    mujoco.mj_forward(m, d)
    links = []
    missing = []
    for bid in range(1, m.nbody):
        bn = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, bid)
        stem = bn[2:] if bn[:2] in ('L_', 'R_') else bn
        pre = 'R_' if bn.startswith('R_') else ''
        # Try the body name as-is first. Stripping "_link" before looking would miss
        # hip_pitch_link.stl and shoulder_pitch_link.stl, which is exactly how the whole hip
        # cluster went missing from the viewer once - so the candidates are explicit and an
        # unmatched body is an ERROR, never a silent skip.
        cands = [stem, stem.replace('_link', ''), BODY_ALIAS.get(stem, '')]
        found = next((c for c in cands if c and
                      os.path.exists(f'{MESHDIR}/{pre}{c}.stl')), None)
        if found is None:
            if stem not in NO_MESH:
                missing.append(bn)
            continue
        extra = [e for e in EXTRA_MESH.get(stem, ())
                 if os.path.exists(f'{MESHDIR}/{e}.stl')]
        for f in [pre + found + '.stl'] + [e + '.stl' for e in extra]:
            links.append(dict(body=bn, stl=f,
                              pos=[round(float(v), 5) for v in d.xpos[bid]]))
    assert not missing, f'these bodies have no mesh and are not on the NO_MESH list: {missing}'

    os.makedirs(f'{OUT}/meshes', exist_ok=True)
    for l in links:
        shutil.copy(f'{MESHDIR}/{l["stl"]}', f'{OUT}/meshes/{l["stl"]}')
    for f in ('three.min.js', 'OrbitControls.js', 'STLLoader.js'):
        os.makedirs(f'{OUT}/vendor', exist_ok=True)
        shutil.copy(f'{REPO}/tools/wrench_studio/static/vendor/{f}', f'{OUT}/vendor/{f}')

    data = dict(oriented=bool(axes), n=len(out), screws=out, links=links,
                note=('screw axes from the Fusion occurrence transforms' if axes else
                      'no orientation yet - Fusion was busy; markers are spheres'))
    json.dump(data, open(f'{OUT}/screws.json', 'w'), indent=1)
    import collections
    c = collections.Counter(f"{s['size']} {s['head']}" for s in out)
    print(f'{len(out)} fasteners, {len(c)} kinds, oriented={bool(axes)}')
    for k, v in c.most_common():
        print(f'  {v:4d}  {k}')
    print(f'{len(links)} link meshes copied')
    print(f'-> {OUT}/screws.json')


if __name__ == '__main__':
    main()
