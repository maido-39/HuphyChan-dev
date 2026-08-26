"""Where each material sits in the robot: a translucent 3D render plus a mass breakdown.

The CAD carries 135 distinct material names, most of them per-body calibration copies
("PYG <occurrence path>" for motors and bearings, "PLA <body> <density>" for printed parts).
They collapse to six classes that actually mean something for a load study:

  printed    PLA*                         the 3D-printed structure
  aluminium  Aluminum*                    milled parts
  fastener   "Steel 4.6/8.8, Plain"       screws
  bearing    PYG ... 68xx/69xx/CRBS/JS06  bearings and rod ends
  motor      PYG ... Robstride            actuators, at their measured masses
  other      generic "Steel" etc.         CAD default, i.e. not yet assigned a real material

The 3D panel colours each LINK by the class holding the most mass in it and draws it
translucent so the interior reads; the bars carry the real per-class split, because a link is
almost never one material and a single colour would lie about that.

  MUJOCO_GL=egl .venv/bin/python3 tools/robot_model/material_diagram.py [--tag=pygmalion_v4_printed]
"""
import json
import os
import sys

os.environ.setdefault('MUJOCO_GL', 'egl')
os.environ.setdefault('MUJOCO_EGL_DEVICE_ID', '0')
import numpy as np                                     # noqa: E402
import mujoco                                          # noqa: E402
import matplotlib                                      # noqa: E402
matplotlib.use('Agg')
import matplotlib.pyplot as plt                        # noqa: E402
from matplotlib.patches import Patch                   # noqa: E402

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
XMLS = f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls'

CLASSES = ['printed', 'aluminium', 'fastener', 'bearing', 'motor', 'other']
COLOUR = {
    'printed':   (0.36, 0.72, 0.52),
    'aluminium': (0.55, 0.62, 0.72),
    'fastener':  (0.90, 0.76, 0.36),
    'bearing':   (0.42, 0.60, 0.86),
    'motor':     (0.87, 0.44, 0.38),
    'other':     (0.55, 0.55, 0.58),
}


def classify_material(mat, path):
    m = (mat or '').strip()
    if m.startswith('PLA'):
        return 'printed'
    if m.startswith('Alumin'):
        return 'aluminium'
    if m.startswith('Steel ') and 'Plain' in m:
        return 'fastener'
    if m.startswith('PYG'):
        blob = f'{m} {path}'
        if 'Robstride' in blob:
            return 'motor'
        if any(t in blob for t in ('ZZ-', 'CRBS', 'JS06', '6810', '6814', '6900', 'Bearing')):
            return 'bearing'
        return 'other'
    return 'other'


def main():
    args = sys.argv[1:]
    tag = next((a.split('=')[1] for a in args if a.startswith('--tag=')), 'pygmalion_v4_printed')
    sys.path.insert(0, f'{REPO}/tools/robot_model')
    os.environ['PYG_BODIES'] = f'/home/syaro/pyg_fea/fusion/bodies_{tag.replace("pygmalion_", "")}.json'
    import massprops_fusion as M

    B = json.load(open(os.environ['PYG_BODIES']))
    per_link = {}
    for path, rec in B.items():
        if not rec.get('live', True):
            continue
        link = M.classify(path)
        if link is None:
            continue
        cls = classify_material(rec.get('mat'), path)
        per_link.setdefault(link, dict.fromkeys(CLASSES, 0.0))
        per_link[link][cls] += rec['m']

    order = [k for k in ('pelvis', 'hip_pitch_link', 'hip_roll_link', 'thigh', 'shin',
                         'ankle_pitch_link', 'foot', 'torso', 'shoulder_pitch_link', 'arm')
             if k in per_link] + [k for k in per_link if k not in (
                 'pelvis', 'hip_pitch_link', 'hip_roll_link', 'thigh', 'shin',
                 'ankle_pitch_link', 'foot', 'torso', 'shoulder_pitch_link', 'arm')]

    # ---- render: motors drawn as themselves, structure translucent over them ----
    # The first version tinted each LINK by whichever class held the most mass in it. Every leg
    # link's biggest single class is "motor" (pelvis 2.840/3.414, thigh 1.420/2.070, shin
    # 1.760/2.225), so waist-to-ankle came out one flat colour that said nothing and openly
    # disagreed with the bars beside it. The model already separates the parts: each actuator is
    # its own cylinder geom named *_motor, the structure is the unnamed visual mesh, and *_hull /
    # *_collision are proxies. Colour those three groups for what they are, and tint the structure
    # by its dominant NON-motor class - which is what the structure is actually made of.
    BODY2LINK = {
        'base_link': 'pelvis', 'torso_link': 'torso',
        'L_hip_pitch_link': 'hip_pitch_link', 'R_hip_pitch_link': 'hip_pitch_link',
        'L_hip_roll_link': 'hip_roll_link', 'R_hip_roll_link': 'hip_roll_link',
        'L_thigh_link': 'thigh', 'R_thigh_link': 'thigh',
        'L_shin_link': 'shin', 'R_shin_link': 'shin',
        'L_foot_link': 'foot', 'R_foot_link': 'foot',
        'L_ankle_pitch_link': 'ankle_pitch_link', 'R_ankle_pitch_link': 'ankle_pitch_link',
        'L_shoulder_pitch_link': 'shoulder_pitch_link',
        'R_shoulder_pitch_link': 'shoulder_pitch_link',
        'L_arm_link': 'arm', 'R_arm_link': 'arm',
    }
    struct_cls = {}
    for lk, v in per_link.items():
        nm = {c: v[c] for c in CLASSES if c != 'motor'}
        struct_cls[lk] = max(nm, key=nm.get) if sum(nm.values()) > 0 else 'other'

    spec = mujoco.MjSpec.from_file(f'{XMLS}/{tag}.xml')
    spec.visual.global_.offwidth, spec.visual.global_.offheight = 1100, 1100
    n_motor = n_struct = n_hidden = 0
    for g in spec.geoms:
        gname = g.name or ''
        body = g.parent.name if g.parent else ''
        lk = BODY2LINK.get(body)
        if gname.endswith('_motor'):
            c = COLOUR['motor']
            g.rgba = [c[0], c[1], c[2], 1.0]               # solid: these are the point of the figure
            n_motor += 1
        elif gname.endswith('_hull') or gname.endswith('_collision') or gname.endswith('_box'):
            g.rgba = [0.0, 0.0, 0.0, 0.0]                  # proxies, not material - hide
            n_hidden += 1
        else:
            c = COLOUR[struct_cls.get(lk, 'other')]
            g.rgba = [c[0], c[1], c[2], 0.38]              # translucent so the motors read through
            n_struct += 1
    print(f'  render: {n_motor} motor cylinders solid, {n_struct} structural meshes translucent, '
          f'{n_hidden} collision/hull proxies hidden')
    for lk in sorted(struct_cls):
        print(f'    structure of {lk:20s} -> {struct_cls[lk]}')
    fl = spec.worldbody.add_geom()
    fl.name, fl.type = 'matmap_floor', mujoco.mjtGeom.mjGEOM_PLANE
    fl.size, fl.pos, fl.rgba = [4.0, 4.0, 0.05], [0, 0, 0], [0.90, 0.91, 0.93, 1.0]
    for pos, dirn in (((1.6, -1.3, 3.0), (-0.35, 0.4, -1.0)), ((-1.7, 1.5, 2.4), (0.4, -0.4, -1.0))):
        lt = spec.worldbody.add_light()
        lt.pos, lt.dir = list(pos), list(dirn)
        lt.diffuse, lt.specular = [0.72, 0.72, 0.74], [0.1, 0.1, 0.11]
    m = spec.compile()
    d = mujoco.MjData(m)
    d.qpos[0:3] = [0, 0, 1.0]
    d.qpos[3:7] = [1, 0, 0, 0]
    mujoco.mj_forward(m, d)
    r = mujoco.Renderer(m, height=1000, width=700)
    cam = mujoco.MjvCamera()
    cam.lookat[:] = [0, 0, 0.78]
    cam.distance, cam.elevation, cam.azimuth = 2.75, -4, 132
    r.update_scene(d, camera=cam, scene_option=mujoco.MjvOption())
    img = r.render()
    del r

    # ---- figure ----
    fig = plt.figure(figsize=(16.5, 9.0))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.32], wspace=0.16)
    ax0 = fig.add_subplot(gs[0])
    ax0.imshow(img)
    ax0.axis('off')
    ax0.set_title(f'{tag}\nmotors solid  -  structure translucent, tinted by its OWN material'
                  '  -  collision proxies hidden', fontsize=10)

    ax = fig.add_subplot(gs[1])
    y = np.arange(len(order))
    left = np.zeros(len(order))
    for cls in CLASSES:
        w = np.array([per_link[lk][cls] for lk in order])
        if w.sum() <= 0:
            continue
        ax.barh(y, w, left=left, color=COLOUR[cls], edgecolor='white', linewidth=0.6, label=cls)
        left += w
    for i, lk in enumerate(order):
        ax.text(left[i] + 0.02, i, f'{left[i]:.3f} kg', va='center', fontsize=8.5, color='#333')
    ax.set_yticks(y)
    ax.set_yticklabels(order, fontsize=9.5)
    ax.invert_yaxis()
    ax.set_xlabel('mass per link [kg]  (one side as modelled)')
    ax.set_xlim(0, left.max() * 1.16)
    ax.grid(axis='x', alpha=0.3)
    ax.set_title('mass by material class', fontsize=11)
    ax.legend(handles=[Patch(facecolor=COLOUR[c], label=c) for c in CLASSES
                       if any(per_link[lk][c] > 0 for lk in order)],
              loc='lower right', fontsize=9, framealpha=0.95)

    tot = {c: sum(per_link[lk][c] for lk in order) for c in CLASSES}
    tt = sum(tot.values())
    sub = '   '.join(f'{c} {tot[c]:.3f} kg ({100*tot[c]/tt:.0f} %)' for c in CLASSES if tot[c] > 0)
    fig.suptitle(f'Material map  -  {sub}', y=0.975, fontsize=11.5)
    out = f'{REPO}/docs/img/material_map_{tag.replace("pygmalion_", "")}.png'
    fig.savefig(out, dpi=125, bbox_inches='tight', facecolor='white')
    print('wrote', out)
    for lk in order:
        row = '  '.join(f'{c}={per_link[lk][c]:.3f}' for c in CLASSES if per_link[lk][c] > 0)
        print(f'  {lk:20s} {sum(per_link[lk].values()):7.3f} kg   {row}')


if __name__ == '__main__':
    main()
