"""Build the Pygmalion v2 robot description - URDF and MJCF - from one mass-property file.

Inputs
  massprops   ~/pyg_fea/steps/robot_massprops_step.json (massprops_step.py) today; the
              Fusion 360 export with the same schema once the connector is reachable.
              Frame: CAD global mm. Bodies: pelvis, hip_pitch_link, hip_roll_link, thigh,
              shin, foot (left leg).
  meshes      pygmalion_locomotion/assets/pygmalion_v2/meshes/*.stl (meshes_step.py),
              already in each body's link frame, simulator axes, metres.

Frames. CAD -> sim is a +90 deg turn about z: sim = (-y_cad, x_cad, z_cad), so the robot
walks along +x with the left leg at -y, exactly the convention of the existing
pygmalion.xml. Link origins sit on joint points: base at the pelvis centre (CAD 0,70,60);
hip_pitch/hip_roll/thigh at the hip point (-123.7,70,60) where the three hip axes are
concurrent (measured from the motor cylinders, massprops_step.py); shin at the knee
(-123.7,115,-310); ankle_pitch/foot at the ankle (-123.7,145,-800). Joint axes and signs
follow the existing model (hip_pitch +y, hip_roll +x, hip_yaw -z, knee -y, ankle_pitch -y,
ankle_roll -x) so policies, rewards and init keyframes keep their meaning.

The ankle is SERIAL (pitch then roll): the two RS03, the cranks and the clevis fork are on
the shin, the rods half/half, the ankle cross on the foot (massprops_step.py). The upper
body is a placeholder lump on base_link - mass from the catalogue-corrected final-design
table (docs/82), COM and inertia scaled from the old base_link - until the Fusion export
carries the arms.

Checks: joint points must reproduce the CAD leg length; every body inertia must be
positive definite; the MJCF must compile in MuJoCo; total mass is printed against the
final-design table.

Usage: build_robot.py [--massprops=path] [--out=...]   (mjlab .venv python)
"""
import json
import os
import sys

import numpy as np

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
MESHDIR = f'{REPO}/pygmalion_locomotion/assets/pygmalion_v2/meshes'
OUT_URDF = f'{REPO}/pygmalion_locomotion/assets/pygmalion_v2'
OUT_MJCF = f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls'
R = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])   # cad -> sim
HIP = np.array([-123.7, 70.0, 60.0])
ORIGIN_CAD = {'pelvis': np.array([0.0, 70.0, 60.0]), 'hip_pitch_link': HIP,
              'hip_roll_link': HIP, 'thigh': HIP, 'shin': np.array([-123.7, 115.0, -310.0]),
              'ankle_pitch_link': np.array([-123.7, 145.0, -800.0]),
              'foot': np.array([-123.7, 145.0, -800.0])}
CHAIN = ['hip_pitch_link', 'hip_roll_link', 'thigh', 'shin', 'ankle_pitch_link', 'foot']
# simulator body names: the task configs bind to the old names (L_foot_link etc.)
BNAME = {'hip_pitch_link': 'hip_pitch_link', 'hip_roll_link': 'hip_roll_link', 'thigh': 'thigh_link',
         'shin': 'shin_link', 'ankle_pitch_link': 'ankle_pitch_link', 'foot': 'foot_link'}
JOINT = {   # child body -> (joint name suffix, axis in sim frame, range rad, inherits old model)
    'hip_pitch_link': ('hip_pitch', (0, 1, 0), (-2.18166, 0.523599)),
    'hip_roll_link': ('hip_roll', (1, 0, 0), (-0.785398, 0.436332)),
    'thigh': ('hip_yaw', (0, 0, -1), (-0.872665, 0.872665)),
    'shin': ('knee', (0, -1, 0), (-2.44346, 0.0)),
    'ankle_pitch_link': ('ankle_pitch', (0, -1, 0), (-0.872665, 0.698132)),
    'foot': ('ankle_roll', (-1, 0, 0), (-0.349066, 0.349066)),
}
EFFORT = {'hip_pitch': 120, 'hip_roll': 120, 'hip_yaw': 60, 'knee': 120,
          'ankle_pitch': 90, 'ankle_roll': 50}
# upper-body placeholder (docs/82 catalogue-corrected table: Torso+Neck+2 arms, no battery)
UPPER_MASS = 15.335
UPPER_COM_SIM = np.array([-0.092, 0.0, 0.366])          # old base_link COM, hip-level origin
UPPER_DIAG = np.array([1.62441, 1.27435, 0.55027]) * (UPPER_MASS / 28.0892)
# sole from the CAD: plate bottom 43 mm under the ankle axis, 180 ahead / 80 behind, 100 wide
SOLE_Z, SOLE_X = -0.043, (-0.080, 0.180)


def to_sim_vec(v):
    return R @ np.asarray(v, float)


MOTOR_BODY = {'robstride_rs04_hip_r_1_': 'pelvis', 'robstride_rs04_hip_r': 'pelvis',
              'robstride_rs04_hip_p': 'hip_pitch_link', 'robstride_rs03_hip_y': 'hip_roll_link',
              'robstride_rs04_knee_p': 'shin', 'robstride_rs03_ankle_a': 'shin',
              'robstride_rs03_ankle_b': 'shin'}


def motor_geoms(mp, body, side):
    """MJCF cylinder visuals for the actuators riding on `body`, in its link frame.

    The placeholders are not meshed (gmsh takes minutes on their fine features); the
    measured axis, radius and length reproduce their envelope exactly.
    """
    prox = json.load(open('/home/syaro/pyg_fea/steps/actuator_proxies.json'))
    out = []
    for key, b in MOTOR_BODY.items():
        if b != body:
            continue
        mo = mp['motors'][key]
        c = to_sim_vec((np.array(mo['com']) - ORIGIN_CAD[body]) / 1000.0)
        ax = to_sim_vec(mo['axis'])
        if side == 'R':
            c = c * np.array([1, -1, 1])
            ax = ax * np.array([1, -1, 1])
        r = mo['r'] / 1000.0
        h = prox[key]['len'] / 2000.0
        # cylinder along `ax`: express as zaxis
        out.append(f'<geom name="{side}_{key[10:]}_motor" type="cylinder" size="{r:.4f} {h:.4f}" '
                   f'pos="{c[0]:.5f} {c[1]:.5f} {c[2]:.5f}" zaxis="{ax[0]:.4f} {ax[1]:.4f} {ax[2]:.4f}" '
                   f'class="visual" material="black"/>')
    return out


def body_inertial(b, mp):
    """(com_sim m, I_sim kg m2 about COM) of a massprops body, in its link frame."""
    d = mp['bodies'][b]
    com = to_sim_vec((np.array(d['com']) - ORIGIN_CAD[b]) / 1000.0)
    I = R @ np.array(d['I_com']) @ R.T * 1e-6
    return d['mass'], com, I


def mirror(com, I):
    M = np.diag([1.0, -1.0, 1.0])
    return M @ com, M @ I @ M


def fullinertia(I):
    return f'{I[0,0]:.6g} {I[1,1]:.6g} {I[2,2]:.6g} {I[0,1]:.6g} {I[0,2]:.6g} {I[1,2]:.6g}'


def urdf_inertia(I):
    return (f'<inertia ixx="{I[0,0]:.6g}" ixy="{I[0,1]:.6g}" ixz="{I[0,2]:.6g}" '
            f'iyy="{I[1,1]:.6g}" iyz="{I[1,2]:.6g}" izz="{I[2,2]:.6g}"/>')


def main():
    mpf = next((a.split('=')[1] for a in sys.argv if a.startswith('--massprops=')),
               '/home/syaro/pyg_fea/steps/robot_massprops_step.json')
    mp = json.load(open(mpf))
    os.makedirs(OUT_URDF, exist_ok=True)

    # ---- joint offsets (sim, m) and the leg-length anchor ----
    off = {}
    prev = 'pelvis'
    for b in CHAIN:
        off[b] = to_sim_vec((ORIGIN_CAD[b] - ORIGIN_CAD[prev]) / 1000.0)
        prev = b
    leg = (ORIGIN_CAD['hip_pitch_link'] - ORIGIN_CAD['foot'])[2]
    assert abs(leg - 860.0) < 0.1, f'hip-to-ankle {leg} mm, CAD says 860'

    # ---- base_link: pelvis (exact) + upper-body lump (placeholder) ----
    m_p, c_p, I_p = body_inertial('pelvis', mp)
    m_b = m_p + UPPER_MASS
    c_b = (m_p * c_p + UPPER_MASS * UPPER_COM_SIM) / m_b
    def shift(I, m, c, about):
        d = c - about
        return I + m * (np.dot(d, d) * np.eye(3) - np.outer(d, d))
    I_b = shift(I_p, m_p, c_p, c_b) + shift(np.diag(UPPER_DIAG), UPPER_MASS, UPPER_COM_SIM, c_b)
    legs = {}
    for b in CHAIN:
        m, c, I = body_inertial(b, mp)
        legs[b] = dict(L=(m, c, I), R=(m,) + mirror(c, I))
    total = m_b + 2 * sum(legs[b]['L'][0] for b in CHAIN)
    for b in CHAIN:
        w = np.linalg.eigvalsh(legs[b]['L'][2])
        assert w.min() > 0, f'{b}: non-physical inertia'

    # ---- MJCF ----
    X = []
    X.append('<mujoco model="pygmalion_v2">\n  <compiler angle="radian" meshdir="assets_v2" autolimits="true"/>\n')
    X.append('''  <default>
    <default class="pygmalion">
      <default class="visual">
        <geom group="2" type="mesh" density="0" material="silver" contype="0" conaffinity="0"/>
      </default>
      <default class="collision">
        <geom group="3" rgba=".2 .6 .2 .3" type="capsule" contype="1" conaffinity="1"/>
        <default class="foot_capsule">
          <geom type="capsule" size="0.01"/>
        </default>
      </default>
      <site group="5" rgba="1 0 0 1"/>
    </default>
  </default>
  <asset>
    <material name="silver" rgba="0.7 0.7 0.7 1"/>
    <material name="black" rgba="0.2 0.2 0.2 1"/>
    <material name="red" rgba="1.0 0.0 0.0 1.0"/>
''')
    X.append('    <mesh name="pelvis" file="pelvis.stl"/>\n')
    for s in 'LR':
        for b in CHAIN:
            if b == 'ankle_pitch_link':
                continue
            f = f'{"R_" if s == "R" else ""}{b}.stl'
            X.append(f'    <mesh name="{s}_{b}" file="{f}"/>\n')
    X.append('  </asset>\n  <worldbody>\n    <body name="base_link" childclass="pygmalion">\n      <freejoint name="root"/>\n')
    X.append(f'      <inertial pos="{c_b[0]:.6g} {c_b[1]:.6g} {c_b[2]:.6g}" mass="{m_b:.5g}" fullinertia="{fullinertia(I_b)}"/>\n')
    X.append('      <geom mesh="pelvis" class="visual"/>\n')
    for g in motor_geoms(mp, 'pelvis', 'L'):
        X.append('      ' + g + '\n')
    for g in motor_geoms(mp, 'pelvis', 'R'):
        if 'hip_r_1_' not in g:          # the waist motor sits on the centreline: once only
            X.append('      ' + g + '\n')
    X.append('      <geom name="base_torso_collision" class="collision" type="capsule" fromto="-0.09 0 0.10  -0.09 0 0.56" size="0.11"/>\n')
    X.append('      <geom name="base_head_collision" class="collision" type="sphere" pos="-0.09 0 0.77" size="0.09"/>\n')
    X.append('      <site name="imu_in_base" size="0.03" pos="-0.09 0 0.28"/>\n')
    for s in 'LR':
        sign = -1.0 if s == 'L' else 1.0
        depth = 3
        for b in CHAIN:
            jn, ax, rg = JOINT[b]
            o = off[b].copy()
            if b == 'hip_pitch_link':
                o[1] = sign * abs(o[1])
            ind = '  ' * depth
            m, c, I = legs[b][s]
            X.append(f'{ind}<body name="{s}_{BNAME[b]}" pos="{o[0]:.6g} {o[1]:.6g} {o[2]:.6g}">\n')
            X.append(f'{ind}  <inertial pos="{c[0]:.6g} {c[1]:.6g} {c[2]:.6g}" mass="{m:.5g}" fullinertia="{fullinertia(I)}"/>\n')
            X.append(f'{ind}  <joint name="{s}_{jn}_joint" pos="0 0 0" axis="{ax[0]} {ax[1]} {ax[2]}" range="{rg[0]} {rg[1]}"/>\n')
            if b != 'ankle_pitch_link':
                X.append(f'{ind}  <geom mesh="{s}_{b}" class="visual"/>\n')
            for g in motor_geoms(mp, b, s):
                X.append(f'{ind}  ' + g + '\n')
            if b == 'thigh':
                X.append(f'{ind}  <geom name="{s}_thigh_collision" class="collision" type="capsule" fromto="0 0 -0.03  -0.045 0 -0.34" size="0.062"/>\n')
            if b == 'shin':
                X.append(f'{ind}  <geom name="{s}_shin_collision" class="collision" type="capsule" fromto="0 0 -0.03  -0.03 0 -0.40" size="0.05"/>\n')
            if b == 'foot':
                X.append(f'{ind}  <site name="{"left" if s == "L" else "right"}_foot" pos="0.05 0 {SOLE_Z:.3f}" size="0.01"/>\n')
                for i, y in enumerate((-0.04, -0.02, 0.0, 0.02, 0.04), start=2):
                    x0, x1 = SOLE_X
                    if abs(y) > 0.03:
                        x0, x1 = x0 + 0.02, x1 - 0.02
                    X.append(f'{ind}  <geom name="{s}_foot{i}_collision" class="foot_capsule" fromto="{x0:.3f} {y:.3f} {SOLE_Z+0.01:.3f}  {x1:.3f} {y:.3f} {SOLE_Z+0.01:.3f}"/>\n')
            depth += 1
        for b in reversed(CHAIN):
            depth -= 1
            X.append('  ' * depth + '</body>\n')
    X.append('    </body>\n  </worldbody>\n  <contact>\n')
    for s in 'LR':
        pairs = ['base_link'] + [f'{s}_{BNAME[b]}' for b in CHAIN]
        for a, b in zip(pairs[:-1], pairs[1:]):
            X.append(f'    <exclude body1="{a}" body2="{b}"/>\n')
    X.append('''  </contact>
  <sensor>
    <gyro name="imu_ang_vel" site="imu_in_base"/>
    <velocimeter name="imu_lin_vel" site="imu_in_base"/>
    <accelerometer name="imu_lin_acc" site="imu_in_base"/>
    <framezaxis name="imu_upvector" objtype="body" objname="world" reftype="site" refname="imu_in_base"/>
    <subtreeangmom name="root_angmom" body="base_link"/>
  </sensor>
</mujoco>
''')
    mjcf = ''.join(X)
    open(f'{OUT_MJCF}/pygmalion_v2.xml', 'w').write(mjcf)
    link = f'{OUT_MJCF}/assets_v2'
    if not os.path.islink(link) and not os.path.exists(link):
        os.symlink(MESHDIR, link)
    open(f'{OUT_URDF}/pygmalion_v2.xml', 'w').write(mjcf.replace('meshdir="assets_v2"', 'meshdir="meshes"'))

    # ---- URDF ----
    U = ['<?xml version="1.0"?>\n<robot name="pygmalion_v2">\n']
    def link_xml(name, m, c, I, mesh, hull=None):
        s = f'  <link name="{name}">\n    <inertial>\n      <origin xyz="{c[0]:.6g} {c[1]:.6g} {c[2]:.6g}" rpy="0 0 0"/>\n      <mass value="{m:.5g}"/>\n      {urdf_inertia(I)}\n    </inertial>\n'
        if mesh:
            s += f'    <visual>\n      <geometry><mesh filename="meshes/{mesh}"/></geometry>\n    </visual>\n'
            s += f'    <collision>\n      <geometry><mesh filename="meshes/{hull or mesh.replace(".stl", "_hull.stl")}"/></geometry>\n    </collision>\n'
        return s + '  </link>\n'
    U.append(link_xml('base_link', m_b, c_b, I_b, 'pelvis.stl'))
    for s in 'LR':
        for b in CHAIN:
            m, c, I = legs[b][s]
            mesh = None if b == 'ankle_pitch_link' else f'{"R_" if s == "R" else ""}{b}.stl'
            U.append(link_xml(f'{s}_{BNAME[b]}', m, c, I, mesh))
    for s in 'LR':
        sign = -1.0 if s == 'L' else 1.0
        parent = 'base_link'
        for b in CHAIN:
            jn, ax, rg = JOINT[b]
            o = off[b].copy()
            if b == 'hip_pitch_link':
                o[1] = sign * abs(o[1])
            U.append(f'  <joint name="{s}_{jn}_joint" type="revolute">\n    <origin xyz="{o[0]:.6g} {o[1]:.6g} {o[2]:.6g}" rpy="0 0 0"/>\n'
                     f'    <parent link="{parent}"/>\n    <child link="{s}_{BNAME[b]}"/>\n    <axis xyz="{ax[0]} {ax[1]} {ax[2]}"/>\n'
                     f'    <limit lower="{rg[0]}" upper="{rg[1]}" effort="{EFFORT[jn]}" velocity="20"/>\n  </joint>\n')
            parent = f'{s}_{BNAME[b]}'
    U.append('</robot>\n')
    open(f'{OUT_URDF}/pygmalion_v2.urdf', 'w').write(''.join(U))

    # ---- compile check ----
    import mujoco
    model = mujoco.MjModel.from_xml_path(f'{OUT_MJCF}/pygmalion_v2.xml')
    print(f'MJCF compiled: {model.nbody} bodies, {model.njnt} joints, {model.ngeom} geoms, '
          f'{model.nmesh} meshes; total mass {model.body_subtreemass[1]:.3f} kg')
    print(f'  base_link (pelvis {m_p:.3f} + upper lump {UPPER_MASS}) = {m_b:.3f} kg')
    for b in CHAIN:
        m, c, I = legs[b]['L']
        print(f'  {b:16s} {m:6.3f} kg  com {np.round(c, 4)}  I diag {np.round(np.diag(I), 5)}')
    print(f'  python total {total:.3f} kg  (docs/82 catalogue-corrected full robot 44.51, no battery)')
    print(f'-> {OUT_MJCF}/pygmalion_v2.xml · {OUT_URDF}/pygmalion_v2.urdf')


if __name__ == '__main__':
    main()
