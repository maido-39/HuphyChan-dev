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
# Upper body, articulated on the three joints the CAD actually has. The waist-yaw axis is
# the z line through the pelvis centre; the shoulder pitch (CAD x) and roll (CAD y) axes are
# concurrent at the shoulder point, so both links hang off the same origin.
TORSO_CAD = np.array([0.0, 70.0, 177.5])
SHOULDER_CAD = np.array([-200.0, 85.0, 540.0])
ARM = ['shoulder_pitch_link', 'arm']            # per side, children of the torso
ORIGIN_CAD['torso'] = TORSO_CAD
ORIGIN_CAD['shoulder_pitch_link'] = SHOULDER_CAD
ORIGIN_CAD['arm'] = SHOULDER_CAD
# simulator body names: the task configs bind to the old names (L_foot_link etc.)
BNAME = {'hip_pitch_link': 'hip_pitch_link', 'hip_roll_link': 'hip_roll_link', 'thigh': 'thigh_link',
         'shin': 'shin_link', 'ankle_pitch_link': 'ankle_pitch_link', 'foot': 'foot_link',
         'torso': 'torso_link', 'shoulder_pitch_link': 'shoulder_pitch_link', 'arm': 'arm_link'}
JOINT = {   # child body -> (joint name suffix, axis in sim frame, range rad, inherits old model)
    'hip_pitch_link': ('hip_pitch', (0, 1, 0), (-2.18166, 0.523599)),
    'hip_roll_link': ('hip_roll', (1, 0, 0), (-0.785398, 0.436332)),
    'thigh': ('hip_yaw', (0, 0, -1), (-0.872665, 0.872665)),
    # knee: the shin knee plates meet the thigh clevis plates at about -120 deg (mesh
    # interference check, red team 2026-08-20) - the old -140 is not reachable on this CAD
    'shin': ('knee', (0, -1, 0), (-2.094395, 0.0)),
    # ankle pitch: the DESIGN cap is -50/+30 (docs/71 s8g, docs/76 s12), not the old +40
    'ankle_pitch_link': ('ankle_pitch', (0, -1, 0), (-0.872665, 0.523599)),
    'foot': ('ankle_roll', (-1, 0, 0), (-0.349066, 0.349066)),
    # Upper body. Signs follow the legs so the two halves read the same way: pitch +q =
    # extension (limb back), roll +q = adduction (limb toward the centreline, axis flipped
    # on the right), yaw +q = turn left. Ranges are the CAD collision sweep (rom_check.py).
    'torso': ('waist_yaw', (0, 0, 1), (-1.047198, 1.047198)),
    'shoulder_pitch_link': ('shoulder_pitch', (0, 1, 0), (-3.141593, 1.047198)),
    'arm': ('shoulder_roll', (1, 0, 0), (-1.570796, 0.261799)),
}
# Joint ranges are MEASURED, not inherited: rom_check.py turns each joint in the assembled
# CAD until two solids that were not already touching push into each other, and writes
# rom_measured.json. The table above is only the fallback for when that file is missing.
# A design cap is applied on top ONLY where something other than part-on-part contact sets
# the limit, and each one carries its reason - a cap must never be a guess dressed as data.
ROM_FILE = '/home/syaro/pyg_fea/fusion/rom_measured.json'
DESIGN_CAP = {
    # the 2-RSU ankle is a CLOSED chain; a serial sweep drives the foot into push rods that
    # would really have followed it, so its range comes from the mechanism studies
    'ankle_pitch': (-50.0, 30.0),      # docs/71 s8g, docs/76 s12
    'ankle_roll': (-20.0, 20.0),       # JS6 clevis swing cone, docs/74 (PYG_ANKLE_ROLL15 -> 15)
    # Geometry allows more than the design wants. Set by the user 2026-08-23; each sits
    # inside the measured stop, which the assert below enforces.
    'hip_pitch': (-120.0, 25.0),       # extension 25 (metal at +26)
    'hip_roll': (-85.0, 25.0),         # abduction 85 (metal at -86); the inherited -45 had
                                       # no basis at all - it was the old MJCF's number, kept
                                       # by mistake after a sweep that stopped searching at
                                       # -70 and so never found the stop. Adduction 25 is the
                                       # gen21 verdict (2026-07-13)
    'hip_yaw': (-45.0, 45.0),          # metal at -48 / +52
    'knee': (-120.0, 0.0),             # no hyperextension (the sweep finds metal only at +2)
    'waist_yaw': (-60.0, 60.0),        # cable routing; the geometry is clear past +-120
    'shoulder_pitch': (-180.0, 60.0),  # nothing collides anywhere in +-200/90 - the arm is a
                                       # dummy rod - so a human-plausible range is declared
                                       # rather than advertising a full turn
}
CLOSED_CHAIN = {'ankle_pitch', 'ankle_roll'}
EFFORT = {'hip_pitch': 120, 'hip_roll': 120, 'hip_yaw': 60, 'knee': 120,
          'ankle_pitch': 90, 'ankle_roll': 50,
          'waist_yaw': 120, 'shoulder_pitch': 60, 'shoulder_roll': 60}   # RS04 / RS03 / RS03
# Upper body. When the mass-property file carries an `upper` block (the Fusion export does -
# the current CAD is "wUpper" and models Torso, Neck and the arm), it is used verbatim,
# mirrored to two arms. Otherwise the old placeholder lump is used: the docs/82
# catalogue-corrected table (Torso+Neck+2 arms + WaistYaw2Pitch 0.775, no battery), with the
# old base_link COM re-expressed at the HIP (old base origin = hip + (+0.104, 0, -0.059)).
UPPER_MASS = 15.335 + 0.775
UPPER_COM_SIM = np.array([0.012, 0.0, 0.366])
UPPER_DIAG = np.array([1.62441, 1.27435, 0.55027]) * (UPPER_MASS / 28.0892)
# sole from the CAD: plate bottom 43 mm under the ankle axis, 180 ahead / 80 behind, 100 wide
SOLE_Z, SOLE_X = -0.043, (-0.080, 0.180)


def to_sim_vec(v):
    return R @ np.asarray(v, float)


MOTOR_PROXIES = '/home/syaro/pyg_fea/fusion/motor_proxies_fusion.json'
CENTRELINE_MM = 5.0        # |x_cad| under this = on the centreline, drawn once, not mirrored


def motor_geoms(mp, body, side, collision=False):
    """MJCF cylinder visuals for the actuators riding on `body`, in its link frame.

    Placement comes from the LIVE Fusion document (motor_proxies_fusion.py), not from the
    STEP export: the two agree within 4 mm everywhere except the hip-pitch RS04, which moved
    75 mm between revisions, and the STEP has no upper body at all.

    The placeholders are not meshed - gmsh takes minutes on their fine features - and the
    measured centre, axis, radius and length reproduce their envelope exactly.
    """
    out = []
    for key, mo in mp.get('motors', {}).items():
        if mo['link'] != body:
            continue
        centre = np.array(mo['com'], float)
        if abs(centre[0]) < CENTRELINE_MM and side == 'R':
            continue                       # centreline actuator: drawn once, on the L pass
        c = to_sim_vec((centre - ORIGIN_CAD[body]) / 1000.0)
        ax = to_sim_vec(mo['axis'])
        if side == 'R':
            c = c * np.array([1, -1, 1])
            ax = ax * np.array([1, -1, 1])
        r = mo['r'] / 1000.0
        h = mo['len'] / 2000.0
        nm = mo['joint'] if abs(centre[0]) < CENTRELINE_MM else f'{side}_{mo["joint"]}'
        cls, suffix = ('collision', '_motor_collision') if collision else ('visual', '_motor')
        mat = '' if collision else ' material="black"'
        out.append(f'<geom name="{nm}{suffix}" type="cylinder" size="{r:.4f} {h:.4f}" '
                   f'pos="{c[0]:.5f} {c[1]:.5f} {c[2]:.5f}" '
                   f'zaxis="{ax[0]:.4f} {ax[1]:.4f} {ax[2]:.4f}" class="{cls}"{mat}/>')
    return out


def mesh_bounds(name):
    """(min, max) of a link-frame STL, metres - collision primitives are sized from the
    real geometry rather than from numbers copied out of the old model."""
    import trimesh
    m = trimesh.load(f'{MESHDIR}/{name}.stl', process=False)
    return np.asarray(m.bounds[0]), np.asarray(m.bounds[1])


def box_geom(name, lo, hi, cls='collision', shrink=0.0):
    c = (lo + hi) / 2
    h = np.maximum((hi - lo) / 2 - shrink, 0.005)
    return (f'<geom name="{name}" class="{cls}" type="box" '
            f'pos="{c[0]:.4f} {c[1]:.4f} {c[2]:.4f}" size="{h[0]:.4f} {h[1]:.4f} {h[2]:.4f}"/>')


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
    # output name: a different mass model must not overwrite pygmalion_v2 - the aluminium
    # build the tasks and keyframes were tuned on
    tag = next((a.split('=')[1] for a in sys.argv if a.startswith('--tag=')), 'pygmalion_v2')
    mp = json.load(open(mpf))
    # ---- resolve joint ranges from the CAD sweep ----
    rom = json.load(open(ROM_FILE)) if os.path.exists(ROM_FILE) else {}
    rom_log = []
    for b, (jn, ax, rg) in list(JOINT.items()):
        lo_d, hi_d = np.degrees(rg)
        src = 'inherited'
        if jn in rom:
            m_lo, m_hi = rom[jn]['free_deg']
            if jn in CLOSED_CHAIN:
                lo_d, hi_d = DESIGN_CAP[jn]
                src = 'mechanism (closed chain)'
            else:
                lo_d, hi_d, src = m_lo, m_hi, 'CAD sweep'
                if jn in DESIGN_CAP:
                    c_lo, c_hi = DESIGN_CAP[jn]
                    assert c_lo >= m_lo - 1e-6 and c_hi <= m_hi + 1e-6, (
                        f'{jn}: design cap {(c_lo, c_hi)} is WIDER than the geometry '
                        f'allows {(m_lo, m_hi)}')
                    lo_d, hi_d = c_lo, c_hi
                    src = 'CAD sweep, design-capped'
        JOINT[b] = (jn, ax, (float(np.radians(lo_d)), float(np.radians(hi_d))))
        rom_log.append((jn, lo_d, hi_d, src,
                        rom.get(jn, {}).get('blocker_lo'), rom.get(jn, {}).get('blocker_hi')))

    # actuator cylinders are geometry, not mass, and come from the live Fusion document
    assert os.path.exists(MOTOR_PROXIES), (
        f'{MOTOR_PROXIES} missing - run tools/robot_model/motor_proxies_fusion.py')
    mp['motors'] = json.load(open(MOTOR_PROXIES))
    os.makedirs(OUT_URDF, exist_ok=True)

    # ---- joint offsets (sim, m) and the leg-length anchor ----
    off = {}
    prev = 'pelvis'
    for b in CHAIN:
        off[b] = to_sim_vec((ORIGIN_CAD[b] - ORIGIN_CAD[prev]) / 1000.0)
        prev = b
    leg = (ORIGIN_CAD['hip_pitch_link'] - ORIGIN_CAD['foot'])[2]
    assert abs(leg - 860.0) < 0.1, f'hip-to-ankle {leg} mm, CAD says 860'

    # ---- base_link: the pelvis. The upper body is ARTICULATED when the mass-property
    # file carries the three CAD upper bodies; only an older file still needs the lump. ----
    def shift(I, m, c, about):
        d = c - about
        return I + m * (np.dot(d, d) * np.eye(3) - np.outer(d, d))

    m_p, c_p, I_p = body_inertial('pelvis', mp)
    articulated = all(b in mp['bodies'] for b in ('torso',) + tuple(ARM))
    if articulated:
        m_b, c_b, I_b = m_p, c_p, I_p
        upper = {}
        for b in ('torso',) + tuple(ARM):
            m, c, I = body_inertial(b, mp)
            upper[b] = dict(L=(m, c, I), R=(m,) + mirror(c, I))
        m_u = upper['torso']['L'][0] + 2 * sum(upper[b]['L'][0] for b in ARM)
    else:                                   # placeholder lump on the pelvis
        upper = None
        m_u, c_u, I_u = UPPER_MASS, UPPER_COM_SIM, np.diag(UPPER_DIAG)
        m_b = m_p + m_u
        c_b = (m_p * c_p + m_u * c_u) / m_b
        I_b = shift(I_p, m_p, c_p, c_b) + shift(I_u, m_u, c_u, c_b)
    # joint offsets for the upper chain (sim, m)
    off['torso'] = to_sim_vec((ORIGIN_CAD['torso'] - ORIGIN_CAD['pelvis']) / 1000.0)
    off['shoulder_pitch_link'] = to_sim_vec(
        (ORIGIN_CAD['shoulder_pitch_link'] - ORIGIN_CAD['torso']) / 1000.0)
    off['arm'] = np.zeros(3)                # pitch and roll axes are concurrent
    legs = {}
    for b in CHAIN:
        m, c, I = body_inertial(b, mp)
        legs[b] = dict(L=(m, c, I), R=(m,) + mirror(c, I))
    total = m_b + m_u + 2 * sum(legs[b]['L'][0] for b in CHAIN)
    UPPER_MASS_USED = m_u
    for b in CHAIN:
        w = np.linalg.eigvalsh(legs[b]['L'][2])
        assert w.min() > 0, f'{b}: non-physical inertia'

    # ---- MJCF ----
    X = []
    X.append(f'<mujoco model="{tag}">\n  <compiler angle="radian" meshdir="assets_v2" autolimits="true"/>\n')
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
      <default class="hull">
        <geom group="4" type="mesh" density="0" material="hull" contype="0" conaffinity="0"/>
      </default>
      <site group="5" rgba="1 0 0 1"/>
    </default>
  </default>
  <asset>
    <material name="silver" rgba="0.7 0.7 0.7 1"/>
    <material name="hull" rgba="0.2 0.4 0.9 0.25"/>
    <material name="black" rgba="0.2 0.2 0.2 1"/>
    <material name="red" rgba="1.0 0.0 0.0 1.0"/>
''')
    X.append('    <mesh name="pelvis" file="pelvis.stl"/>\n    <mesh name="pelvis_hull" file="pelvis_hull.stl"/>\n')
    for s in 'LR':
        for b in CHAIN:
            if b == 'ankle_pitch_link':
                continue
            f = f'{"R_" if s == "R" else ""}{b}.stl'
            X.append(f'    <mesh name="{s}_{b}" file="{f}"/>\n')
            X.append(f'    <mesh name="{s}_{b}_hull" file="{f.replace(".stl", "_hull.stl")}"/>\n')
    if articulated:
        X.append('    <mesh name="torso" file="torso.stl"/>\n'
                 '    <mesh name="torso_hull" file="torso_hull.stl"/>\n')
        for s_ in 'LR':
            pre = 'R_' if s_ == 'R' else ''
            X.append(f'    <mesh name="{s_}_torso_shpitch" file="{pre}torso_shpitch.stl"/>\n')
            for b in ARM:
                X.append(f'    <mesh name="{s_}_{b}" file="{pre}{b}.stl"/>\n')
                X.append(f'    <mesh name="{s_}_{b}_hull" file="{pre}{b}_hull.stl"/>\n')
    X.append('  </asset>\n  <worldbody>\n    <body name="base_link" childclass="pygmalion">\n      <freejoint name="root"/>\n')
    X.append(f'      <inertial pos="{c_b[0]:.6g} {c_b[1]:.6g} {c_b[2]:.6g}" mass="{m_b:.5g}" fullinertia="{fullinertia(I_b)}"/>\n')
    X.append('      <geom mesh="pelvis" class="visual"/>\n      <geom name="pelvis_hull" mesh="pelvis_hull" class="hull"/>\n')
    for g in motor_geoms(mp, 'pelvis', 'L'):
        X.append('      ' + g + '\n')
    for g in motor_geoms(mp, 'pelvis', 'R'):
        X.append('      ' + g + '\n')

    if not articulated:
        # old model geometry re-expressed at the hip-level base origin (+0.104 x, -0.059 z)
        X.append('      <geom name="base_torso_collision" class="collision" type="capsule" fromto="0.004 0 0.061  0.004 0 0.521" size="0.11"/>\n')
        X.append('      <geom name="base_head_collision" class="collision" type="sphere" pos="0.004 0 0.731" size="0.09"/>\n')
    X.append('      <geom name="base_pelvis_collision" class="collision" type="box" pos="0 0 0.008" size="0.069 0.045 0.075"/>\n')
    X.append('      <site name="imu_in_base" size="0.03" pos="0.004 0 0.241"/>\n')
    for s in 'LR':
        sign = -1.0 if s == 'L' else 1.0
        depth = 3
        for b in CHAIN:
            jn, ax, rg = JOINT[b]
            if s == 'R' and jn in ('hip_roll', 'ankle_roll'):
                ax = tuple(-v for v in ax)          # +q = adduction / inversion on BOTH legs
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
                X.append(f'{ind}  <geom name="{s}_{BNAME[b]}_hull" mesh="{s}_{b}_hull" class="hull"/>\n')
            for g in motor_geoms(mp, b, s):
                X.append(f'{ind}  ' + g + '\n')
            if b == 'hip_pitch_link':
                X.append(f'{ind}  <geom name="{s}_hip_pitch_collision" class="collision" type="sphere" pos="0.0 {0.012*sign:.3f} 0.0" size="0.068"/>\n')
            if b == 'hip_roll_link':
                X.append(f'{ind}  <geom name="{s}_hip_roll_collision" class="collision" type="capsule" fromto="0 0 0.03  0 0 -0.085" size="0.05"/>\n')
            if b in ('thigh', 'shin'):
                # radius from the CAD, not from the old model: the inherited thigh capsule
                # was 58 mm against a real 34.9 mm half-width, which put the thigh inside
                # the arm at the zero pose. The axis stays where it was - only the girth
                # becomes a measurement.
                lo_m, hi_m = mesh_bounds(('R_' if s == 'R' else '') + b)
                r_m = round(float(hi_m[1] - lo_m[1]) / 2, 4)
                ft = ('-0.005 0 -0.13  -0.045 0 -0.37' if b == 'thigh'
                      else '0 0 0.0  -0.03 0 -0.44')
                X.append(f'{ind}  <geom name="{s}_{b}_collision" class="collision" '
                         f'type="capsule" fromto="{ft}" size="{r_m:.4f}"/>\n')
            if b == 'shin':
                # the two RS03 on the back of the shin (CAD z -500/-600 -> -0.19/-0.29 below the knee)
                X.append(f'{ind}  <geom name="{s}_shin_motors_collision" class="collision" type="capsule" fromto="-0.03 0 -0.16  -0.03 0 -0.32" size="0.055"/>\n')
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
    # ---- upper body: torso on the waist yaw, then an arm on each shoulder ----
    if articulated:
        m, c, I = upper['torso']['L']
        o = off['torso']
        jn, ax, rg = JOINT['torso']
        X.append(f'      <body name="torso_link" pos="{o[0]:.6g} {o[1]:.6g} {o[2]:.6g}">\n')
        X.append(f'        <inertial pos="{c[0]:.6g} {c[1]:.6g} {c[2]:.6g}" mass="{m:.5g}" fullinertia="{fullinertia(I)}"/>\n')
        X.append(f'        <joint name="waist_yaw_joint" pos="0 0 0" axis="{ax[0]} {ax[1]} {ax[2]}" range="{rg[0]} {rg[1]}"/>\n')
        X.append('        <geom mesh="torso" class="visual"/>\n')
        X.append('        <geom name="torso_hull" mesh="torso_hull" class="hull"/>\n')
        for s_ in 'LR':
            X.append(f'        <geom mesh="{s_}_torso_shpitch" class="visual" material="black"/>\n')
        for s_ in 'LR':
            for g in motor_geoms(mp, 'torso', s_):
                X.append('        ' + g + '\n')
        lo, hi = mesh_bounds('torso')
        X.append('        ' + box_geom('torso_collision', lo, hi) + '\n')
        for s_ in 'LR':
            sgn = -1.0 if s_ == 'L' else 1.0
            oa = off['shoulder_pitch_link'].copy()
            oa[1] = sgn * abs(oa[1])
            ind = '        '
            for k, b in enumerate(ARM):
                jn, ax, rg = JOINT[b]
                if s_ == 'R' and jn == 'shoulder_roll':
                    ax = tuple(-v for v in ax)
                oo = oa if k == 0 else off['arm']
                m, c, I = upper[b][s_]
                ind += '  '
                X.append(f'{ind}<body name="{s_}_{BNAME[b]}" pos="{oo[0]:.6g} {oo[1]:.6g} {oo[2]:.6g}">\n')
                X.append(f'{ind}  <inertial pos="{c[0]:.6g} {c[1]:.6g} {c[2]:.6g}" mass="{m:.5g}" fullinertia="{fullinertia(I)}"/>\n')
                X.append(f'{ind}  <joint name="{s_}_{jn}_joint" pos="0 0 0" axis="{ax[0]} {ax[1]} {ax[2]}" range="{rg[0]} {rg[1]}"/>\n')
                X.append(f'{ind}  <geom mesh="{s_}_{b}" class="visual"/>\n')
                X.append(f'{ind}  <geom name="{s_}_{BNAME[b]}_hull" mesh="{s_}_{b}_hull" class="hull"/>\n')
                for g in motor_geoms(mp, b, s_):
                    X.append(f'{ind}  ' + g + '\n')
                lo, hi = mesh_bounds(('R_' if s_ == 'R' else '') + b)
                # a box, not a capsule: a capsule sized to the widest section (the shoulder
                # end) is 44 mm fat all the way down and would sit permanently inside the hip
                X.append(f'{ind}  ' + box_geom(f'{s_}_{BNAME[b]}_collision', lo, hi) + '\n')
            for _ in ARM:
                X.append(ind + '</body>\n')
                ind = ind[:-2]
        X.append('      </body>\n')
    X.append('    </body>\n  </worldbody>\n  <contact>\n')
    for s in 'LR':
        pairs = ['base_link'] + [f'{s}_{BNAME[b]}' for b in CHAIN]
        for a, b in zip(pairs[:-1], pairs[1:]):
            X.append(f'    <exclude body1="{a}" body2="{b}"/>\n')
        # the hip is a nested cluster: pelvis, hip_pitch_link and hip_roll_link interpenetrate by
        # construction (motor housings inside each other's envelopes), so the 2-apart pairs in
        # that cluster are excluded too; leg-vs-leg and torso-vs-thigh stay live
        X.append(f'    <exclude body1="base_link" body2="{s}_hip_roll_link"/>\n')
        X.append(f'    <exclude body1="{s}_hip_pitch_link" body2="{s}_thigh_link"/>\n')
    if articulated:
        X.append('    <exclude body1="base_link" body2="torso_link"/>\n')
        for s in 'LR':
            X.append(f'    <exclude body1="torso_link" body2="{s}_shoulder_pitch_link"/>\n')
            X.append(f'    <exclude body1="{s}_shoulder_pitch_link" body2="{s}_arm_link"/>\n')
            X.append(f'    <exclude body1="torso_link" body2="{s}_arm_link"/>\n')
            # ArmR_Dummy is a straight rod hanging from a shoulder 76 mm outboard of the hip
            # axis, and in the CAD's own zero pose it already interferes with the hip roll
            # link by 5.1 mm (rom_check.py, measured on the triangle meshes - docs/88 s3c).
            # The simulator would otherwise carry a permanent contact there. This is masked
            # in the model and REPORTED as a CAD issue, not silently absorbed.
            for h in ('hip_pitch_link', 'hip_roll_link'):
                X.append(f'    <exclude body1="{s}_arm_link" body2="{s}_{h}"/>\n')
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
    open(f'{OUT_MJCF}/{tag}.xml', 'w').write(mjcf)
    link = f'{OUT_MJCF}/assets_v2'
    if not os.path.islink(link) and not os.path.exists(link):
        os.symlink(MESHDIR, link)
    open(f'{OUT_URDF}/{tag}.xml', 'w').write(mjcf.replace('meshdir="assets_v2"', 'meshdir="meshes"'))

    # ---- URDF ----
    U = [f'<?xml version="1.0"?>\n<robot name="{tag}">\n']
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
            if s == 'R' and jn in ('hip_roll', 'ankle_roll'):
                ax = tuple(-v for v in ax)
            o = off[b].copy()
            if b == 'hip_pitch_link':
                o[1] = sign * abs(o[1])
            U.append(f'  <joint name="{s}_{jn}_joint" type="revolute">\n    <origin xyz="{o[0]:.6g} {o[1]:.6g} {o[2]:.6g}" rpy="0 0 0"/>\n'
                     f'    <parent link="{parent}"/>\n    <child link="{s}_{BNAME[b]}"/>\n    <axis xyz="{ax[0]} {ax[1]} {ax[2]}"/>\n'
                     f'    <limit lower="{rg[0]}" upper="{rg[1]}" effort="{EFFORT[jn]}" velocity="20"/>\n  </joint>\n')
            parent = f'{s}_{BNAME[b]}'
    if articulated:
        m, c, I = upper['torso']['L']
        U.append(link_xml('torso_link', m, c, I, 'torso.stl'))
        for s_ in 'LR':
            for b in ARM:
                m, c, I = upper[b][s_]
                U.append(link_xml(f'{s_}_{BNAME[b]}', m, c, I,
                                  f'{"R_" if s_ == "R" else ""}{b}.stl'))
        jn, ax, rg = JOINT['torso']
        o = off['torso']
        U.append(f'  <joint name="waist_yaw_joint" type="revolute">\n    <origin xyz="{o[0]:.6g} {o[1]:.6g} {o[2]:.6g}" rpy="0 0 0"/>\n'
                 f'    <parent link="base_link"/>\n    <child link="torso_link"/>\n    <axis xyz="{ax[0]} {ax[1]} {ax[2]}"/>\n'
                 f'    <limit lower="{rg[0]}" upper="{rg[1]}" effort="{EFFORT[jn]}" velocity="20"/>\n  </joint>\n')
        for s_ in 'LR':
            sgn = -1.0 if s_ == 'L' else 1.0
            parent = 'torso_link'
            for k, b in enumerate(ARM):
                jn, ax, rg = JOINT[b]
                if s_ == 'R' and jn == 'shoulder_roll':
                    ax = tuple(-v for v in ax)
                o = off['shoulder_pitch_link'].copy() if k == 0 else off['arm'].copy()
                if k == 0:
                    o[1] = sgn * abs(o[1])
                U.append(f'  <joint name="{s_}_{jn}_joint" type="revolute">\n    <origin xyz="{o[0]:.6g} {o[1]:.6g} {o[2]:.6g}" rpy="0 0 0"/>\n'
                         f'    <parent link="{parent}"/>\n    <child link="{s_}_{BNAME[b]}"/>\n    <axis xyz="{ax[0]} {ax[1]} {ax[2]}"/>\n'
                         f'    <limit lower="{rg[0]}" upper="{rg[1]}" effort="{EFFORT[jn]}" velocity="20"/>\n  </joint>\n')
                parent = f'{s_}_{BNAME[b]}'
    U.append('</robot>\n')
    open(f'{OUT_URDF}/{tag}.urdf', 'w').write(''.join(U))

    # ---- compile check ----
    import mujoco
    model = mujoco.MjModel.from_xml_path(f'{OUT_MJCF}/{tag}.xml')
    print(f'MJCF compiled: {model.nbody} bodies, {model.njnt} joints, {model.ngeom} geoms, '
          f'{model.nmesh} meshes; total mass {model.body_subtreemass[1]:.3f} kg')
    print(f'  base_link (pelvis) = {m_b:.3f} kg · upper body {m_u:.3f} kg '
          f'{"ARTICULATED (3 joints)" if articulated else "placeholder lump on the pelvis"}')
    for b in CHAIN:
        m, c, I = legs[b]['L']
        print(f'  {b:16s} {m:6.3f} kg  com {np.round(c, 4)}  I diag {np.round(np.diag(I), 5)}')
    if articulated:
        for b in ('torso',) + tuple(ARM):
            m, c, I = upper[b]['L']
            print(f'  {b:16s} {m:6.3f} kg  com {np.round(c, 4)}  I diag {np.round(np.diag(I), 5)}'
                  + ('' if b == 'torso' else '  (x2)'))
    print(f'  python total {total:.3f} kg')
    print(f"\n  {'joint':16s} {'range (deg)':>18s}   source / what stops it")
    for jn, lo_d, hi_d, src, bl, bh in rom_log:
        stop = f'{bl or "-"} | {bh or "-"}' if src.startswith('CAD') else ''
        print(f'  {jn:16s} [{lo_d:7.1f},{hi_d:7.1f}]   {src:26s} {stop}')
    print(f'-> {OUT_MJCF}/{tag}.xml · {OUT_URDF}/{tag}.urdf')


if __name__ == '__main__':
    main()
