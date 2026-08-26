"""Turn measured rotor-face normals into a per-joint PASS/FAIL against the user's sign convention.

Convention (user, 2026-08-26): look straight at the actuator ROTOR face - the one carrying 6 M4
threaded holes and 3 alignment pins - along the axis protruding from it. CLOCKWISE is POSITIVE.

The algebra, spelled out because getting it backwards inverts every joint. The viewpoint was
confirmed by the user on 2026-08-26: you look ALONG the normal, i.e. down the axis with the
rotor face receding from you, NOT face-on.
  n            = OUTWARD normal of the rotor face (points away from the motor body)
  viewer       = looks along +n, i.e. n points AWAY from the viewer, into the screen
  right-hand   = a rotation vector along +n appears CLOCKWISE to that viewer
  therefore    = CLOCKWISE (the user's +) is a rotation vector along +n

  required_plus_axis = +n

(The face-on reading gives -n and flips every verdict; that was the first implementation and it
was wrong.)

A joint MATCHES when the model's own axis, expressed in the same frame, is parallel to -n
(dot > 0) and is INVERTED when antiparallel (dot < 0).

Input : rotor_faces.json  {motor_key: {joint, n_root: [x,y,z], ...}}  (from the CAD measurement)
Output: motor_sign_convention.json  {joint_name: {matches, axis, n_base, dot, note}}
        consumed by rom_sweep_video.py to put the verdict on screen.

  .venv/bin/python3 tools/robot_model/motor_sign_check.py [rotor_faces.json]
"""
import json
import os
import sys

import numpy as np
import mujoco

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
XML = f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/pygmalion_v3_printed.xml'
OUT = f'{REPO}/tools/robot_model/motor_sign_convention.json'

# CAD root -> URDF/base_link is a +90 deg rotation about Z followed by a translation. A normal
# is a direction, so only the rotation applies: (x, y, z)_cad -> (-y, x, z)_base.
def cad_dir_to_base(v):
    x, y, z = v
    return np.array([-y, x, z], dtype=float)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else f'{REPO}/tools/robot_model/rotor_faces.json'
    if not os.path.exists(src):
        print(f'!! {src} missing - run the CAD rotor-face measurement first')
        return 2
    rotor = {k: v for k, v in json.load(open(src)).items() if not k.startswith('_')}
    m = mujoco.MjModel.from_xml_path(XML)

    out = {}
    print(f'{"joint":26s} {"n (base)":>20s} {"required +":>20s} {"model axis":>20s}  verdict')
    for key, r in rotor.items():
        joints = r['joint'] if isinstance(r.get('joint'), list) else [r.get('joint')]
        n_cad = np.array(r['n_root'], dtype=float)
        n_cad /= np.linalg.norm(n_cad)
        n_base = cad_dir_to_base(n_cad)
        need = n_base                                      # the user's + axis: CW looking ALONG n
        for jn in [j for j in joints if j]:
            try:
                jid = m.joint(jn).id
            except Exception:
                print(f'{jn:26s} -- not in the model, skipped')
                continue
            axis = np.array(m.jnt_axis[jid], dtype=float)
            axis /= np.linalg.norm(axis)
            dot = float(np.dot(axis, need))
            if abs(dot) < 0.9:
                verdict, matches = 'AXIS NOT PARALLEL - check frames', None
            else:
                matches = dot > 0
                verdict = 'match' if matches else 'INVERTED'
            out[jn] = dict(matches=matches, dot=round(dot, 4),
                           axis=[round(v, 3) for v in axis.tolist()],
                           n_base=[round(v, 3) for v in n_base.tolist()],
                           n_root=[round(v, 3) for v in n_cad.tolist()],
                           motor=key, note=r.get('evidence', ''))
            fmt = lambda v: '[' + ' '.join(f'{x:+.2f}' for x in v) + ']'
            print(f'{jn:26s} {fmt(n_base):>20s} {fmt(need):>20s} {fmt(axis):>20s}  {verdict}')
    json.dump(out, open(OUT, 'w'), indent=1)
    n_bad = sum(1 for v in out.values() if v['matches'] is False)
    n_ok = sum(1 for v in out.values() if v['matches'] is True)
    print(f'\n{n_ok} match, {n_bad} inverted, {len(out) - n_ok - n_bad} undetermined -> {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
