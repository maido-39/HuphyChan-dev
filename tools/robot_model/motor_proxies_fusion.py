"""Where the actuators actually sit, taken from the CURRENT Fusion document.

The motor cylinders in the model were being drawn from `actuator_proxies.json`, measured off
the STEP export - which is one revision behind. Most motors moved only a few mm between the
two, but the hip-pitch RS04 moved **75 mm**, and the four upper-body actuators do not exist
in the STEP at all, so nothing was drawn for them.

Everything here comes from the live document instead:
  centre  the body's centre of mass (a symmetric disc, so this IS its centre)
  axis    the direction the bounding box is THINNEST - a QDD motor is a flat disc, 56 mm
          across its axis against 120 mm in plane, so the thin direction cannot be mistaken
  r, len  by family, read off a motor whose box is axis-aligned. Taking the radius from each
          body's own box would be wrong for the ones mounted at 45 deg, where the box spans
          the diagonal (Hip_P reads 161.8 mm across a real 120 mm envelope).

The occurrence NAMES in the CAD are not a reliable guide to what a motor drives: `Hip_P` is
coaxial with the hip ROLL axis and `Hip_R` with the hip PITCH axis. The joint each one drives
is decided here by its axis and where it sits, and the stator is put on that joint's PARENT
link - which is what the geometry says regardless of the label.

Usage: motor_proxies_fusion.py   (writes ~/pyg_fea/fusion/motor_proxies_fusion.json)
"""
import json
import os

import numpy as np

BODIES = os.environ.get('PYG_BODIES', '/home/syaro/pyg_fea/fusion/bodies.json')
BBOX = '/home/syaro/pyg_fea/fusion/placeholder_bbox.json'
OUT = os.environ.get('PYG_MOTOR_PROXIES', '/home/syaro/pyg_fea/fusion/motor_proxies_fusion.json')
# family -> (radius mm, length mm), from the axis-aligned instance of each
FAMILY = {'RS04': (60.0, 55.7), 'RS03': (49.5, 56.6),
          'RS02': (41.8, 45.4), 'RS00': (28.5, 51.4)}
# Fusion occurrence -> (joint it drives, link its stator rides)
DRIVES = {
    'Hip_P': ('hip_roll', 'hip_pitch_link'),     # coaxial with the ROLL axis despite the name
    'Hip_R': ('hip_pitch', 'pelvis'),            # coaxial with the PITCH axis despite the name
    'Hip_Y': ('hip_yaw', 'hip_roll_link'),
    'Knee_P': ('knee', 'thigh'),                 # stator clamped by the thigh clevis plates
    'Ankle_A:3': ('ankle_a', 'shin'),
    'Ankle_A (1)': ('ankle_b', 'shin'),
    'Waist_Yaw': ('waist_yaw', 'pelvis'),
    'Shoulder_Pitch': ('shoulder_pitch', 'torso'),
    'Shoulder_Roll': ('shoulder_roll', 'shoulder_pitch_link'),
    'Neck_Yaw': ('neck_yaw', 'torso'),
    'Neck_Pitch': ('neck_pitch', 'torso'),
}


def main():
    B = json.load(open(BODIES))
    boxes = {}
    # the box comes from the SAME dump as the masses when it carries one ('bb', written by
    # dump_bodies.py since 2026-08-23) - the separate placeholder_bbox.json was a snapshot of
    # the 8/22 design original and put the hip-pitch cylinder 75.6 mm off the axis it drives
    if all('bb' in rec for rec in B.values()):
        # the dump stores min/max corners (6 values, mm); the proxy logic wants the three
        # SIZES (cm) - argmin over corners would pick the smallest coordinate, not the
        # thinnest direction, and call the waist-yaw motor x-axis
        bbox_rows = [(path.split('::')[0], path.split('::')[1], rec['m'], rec['v'], rec['mat'],
                      [(rec['bb'][i + 3] - rec['bb'][i]) / 10.0 for i in range(3)]) for path, rec in B.items()
                     if 'obstride' in path
                     and not any(t in path for t in ('NotUse', 'fullDoF', 'REF', 'NoSim'))]
        # no `live` test: a switched-off light bulb is a view state, and in the export copy
        # every group but the ankle is switched off
    else:
        bbox_rows = json.load(open(BBOX))
    for path, body, mass, vol, mat, bb in bbox_rows:
        boxes[f'{path}::{body}'] = np.array(bb) * 10.0        # cm -> mm

    out = {}
    for path, r in sorted(B.items()):
        if 'obstride' not in path or any(t in path for t in ('NotUse', 'fullDoF', 'REF', 'NoSim')):
            continue                    # alternatives out; the light bulb is only a view state
        occ = path.split('::')[0].split('/')[-1]
        key = next((k for k in DRIVES if k in occ), None)
        assert key, f'no joint mapping for {occ}'
        fam = next(f for f in FAMILY if f in occ)
        bb = boxes.get(path)
        assert bb is not None, f'no bounding box for {path}'
        axis = np.zeros(3)
        axis[int(np.argmin(bb))] = 1.0                        # thinnest box direction
        rad, ln = FAMILY[fam]
        joint, link = DRIVES[key]
        name = f'{joint}_{fam.lower()}'
        assert name not in out, f'duplicate proxy name {name}'
        out[name] = dict(occurrence=occ, family=fam, joint=joint, link=link,
                         com=[round(v * 10.0, 3) for v in r['c']],   # CAD mm
                         axis=[float(v) for v in axis], r=rad, len=ln,
                         mass_kg=round(r['m'], 4), box_mm=[round(v, 1) for v in bb])
    json.dump(out, open(OUT, 'w'), indent=1)
    print(f"{'proxy':22s} {'family':>6s} {'drives':>15s} {'rides on':>18s} "
          f"{'CAD centre (mm)':>26s} {'axis':>10s}")
    for k, v in out.items():
        ax = 'xyz'[int(np.argmax(v['axis']))]
        print(f"  {k:20s} {v['family']:>6s} {v['joint']:>15s} {v['link']:>18s} "
              f"{str(v['com']):>26s} {ax:>10s}")
    print(f'\n{len(out)} actuators -> {OUT}')


if __name__ == '__main__':
    main()
