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
try:                                    # loop-body frames: crank on its motor axis, rod at its pin
    _lp = json.load(open('/home/syaro/pyg_fea/fusion/ankle_loop_points_v3_printed.json'))
    for _t in 'AB':
        ORIGIN_CAD[f'crank_{_t}'] = np.array(_lp[_t]['motor'])
        ORIGIN_CAD[f'rod_{_t}'] = np.array(_lp[_t]['pin'])
except FileNotFoundError:
    pass
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
CRANK_RANGE = (-1.2, 1.2)      # rad, wider than the ankle needs; verified by the sweep
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


MOTOR_PROXIES = os.environ.get('PYG_MOTOR_PROXIES', '/home/syaro/pyg_fea/fusion/motor_proxies_fusion.json')

# --- IMU site -----------------------------------------------------------------------------
# Where the E2Box IMU actually is, measured off the live Fusion document on 2026-08-26
# (docs/105_imu_and_shoulder_cad_update.md s1). The old value 0.004 0 0.241 was inherited from
# the pre-v2 model ("old model geometry re-expressed at the hip-level base origin") and had
# never been measured - it sits 310.6 mm away from the real sensor, above the pelvis entirely.
#
# The user gave the position as "-Z 187 mm from the yaw motor surface". Enumerating every
# +-Z face pair 187 +- 1 mm apart found 43 matches and ALL of them are the RS04 Waist_Yaw
# motor - none is the RS03 Hip_Y - with the best pair exact to 0.00 mm:
#   Waist_Yaw face  CAD z = +177.50 mm   ->   IMU face  CAD z = -9.50 mm
# CAD root -> base_link is  (x,y,z) -> (70.0 - y, x, z - 60.0) mm, verified to 0.00 mm against
# both the hip centre and the knee axis.
#   spec face      CAD (7.078, 70.001,  -9.500) -> ( 0.000000, 0.007078, -0.069500) m   <- used
#   EBIMU board CoM CAD (7.078, 70.001, -16.086) -> ( 0.000000, 0.007078, -0.076086) m   (6.6 mm lower)
# The board's occurrence transform is identity and its faces are axis-aligned, so the site
# needs no rotation relative to base_link.
#
# Safe to change: base_lin_vel (the velocimeter on this site, the only position-dependent
# consumer) is a CRITIC-ONLY observation here. The actor sees base_ang_vel - a gyro, uniform
# over a rigid body - and projected_gravity, which is orientation-only. Measured on
# bundleD1_AB/32798, moving the site shifts base_lin_vel by |omega x dr| = 0.021 m/s median /
# 0.047 p95, i.e. 1.3 % of the tracked speed and 9 % of the +-0.5 m/s noise already injected
# into that term (tools/robot_model/loop_tests/imu_site_delta.py).
# NOTE the parse: `bool(os.environ.get(FLAG))` is true for the string "0", so PYG_X=0 turns
# such a flag ON. 21 PYG_* flags in this project read that way (docs/99 s"PYG flag parsing");
# no run has ever tripped it, but this one is written so PYG_IMU_LEGACY=0 means off.
IMU_LEGACY = os.environ.get('PYG_IMU_LEGACY', '').strip().lower() not in ('', '0', 'false', 'no')
IMU_POS = (0.004, 0.0, 0.241) if IMU_LEGACY else (-0.000001, 0.007078, -0.069500)
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


def fitted_capsule(name, stl, cls='collision', q=0.90, exclude=None):
    """A capsule that hugs the mesh: axis = the mesh's longest bounding-box direction, ends
    = the extreme projections pulled in by the radius, radius = the q-quantile of the
    vertices' distance from the axis (q < 1 so bolt heads and a flange rim do not fatten the
    whole link). Never degenerates to a sphere - a pill is what was asked for. `exclude` is
    an optional vertex mask to drop first (e.g. the fat shoulder end of the arm rod).
    Non-adjacent overlaps left at the zero pose are trimmed afterwards by
    resolve_zero_pose_overlaps(), which reports every radius it shrinks."""
    import trimesh
    V = np.asarray(trimesh.load(f'{MESHDIR}/{stl}.stl', process=False).vertices)
    if exclude is not None:
        V = V[~exclude(V)]
    c = V.mean(0)
    a = np.zeros(3)
    a[int(np.argmax(V.max(0) - V.min(0)))] = 1.0
    t = (V - c) @ a
    perp = np.linalg.norm((V - c) - np.outer(t, a), axis=1)
    r = float(np.quantile(perp, q))
    half = max((t.max() - t.min()) / 2 - r, 0.005)
    mid = c + a * (t.max() + t.min()) / 2
    p0, p1 = mid - a * half, mid + a * half
    return (f'<geom name="{name}" class="{cls}" type="capsule" fromto="{p0[0]:.4f} {p0[1]:.4f} {p0[2]:.4f}  '
            f'{p1[0]:.4f} {p1[1]:.4f} {p1[2]:.4f}" size="{r:.4f}"/>')


def resolve_zero_pose_overlaps(xml_path, margin=0.002, max_iter=40):
    """Shrink collision radii until no NON-ADJACENT pair touches at the zero pose.

    The capsules are fitted to the meshes and only adjacent links are excluded, so wherever
    the CAD nests one link inside another (the roll housing inside the pelvis frame, the
    dummy arm 5 mm into the hip) the fitted shapes overlap. Rather than hide that behind an
    exclusion, both shapes give up half the penetration plus a margin, and every change is
    printed - a radius that had to shrink a lot is a shape the CAD really does overlap.
    """
    import mujoco
    spec = mujoco.MjSpec.from_file(xml_path)
    log = {}
    for _ in range(max_iter):
        m = spec.compile()
        d = mujoco.MjData(m)
        d.qpos[:] = m.qpos0
        d.qpos[2] = 1.5
        mujoco.mj_forward(m, d)
        hits = [(d.contact[i].geom1, d.contact[i].geom2, d.contact[i].dist) for i in range(d.ncon)
                if m.geom_bodyid[d.contact[i].geom1] and m.geom_bodyid[d.contact[i].geom2]]
        if not hits:
            break
        for g1, g2, dist in hits:
            for g in (g1, g2):
                name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g)
                sg = next(x for x in spec.geoms if x.name == name)
                if sg.type == mujoco.mjtGeom.mjGEOM_BOX:
                    continue                         # the foot box keeps its footprint
                cut = -dist / 2 + margin
                sg.size[0] = max(sg.size[0] - cut, 0.01)
                log[name] = log.get(name, 0.0) + cut
    spec.to_file(xml_path)
    return log


LOOP_PTS = '/home/syaro/pyg_fea/fusion/ankle_loop_points_v3_printed.json'


def loop_xml(s, ind, mp, sign):
    """The 2-RSU ankle as the real mechanism, on one leg (children of the shin; the foot's
    ball sites are emitted by the caller).

    crank_{A,B}   hinge on the shin about the RS03 axis (CAD x -> sim y), origin on that axis
    rod_{A,B}     child of the crank at the crank pin, a UNIVERSAL joint there (two hinges:
                  the crank axis, then the axis perpendicular to it and to the rod) - not a
                  ball joint, so the rod cannot spin about itself and mjlab's joint indexing
                  sees hinges only
    connect       rod far-end site <-> foot ball site, 3 constraints
    DOF: 2 passive ankle hinges + 2 cranks + 2x2 rod hinges - 2x3 connects = 2, exactly the
    two cranks - the ankle pitch/roll hinges are passive and follow the linkage.
    Masses and inertias are the real ones (massprops_fusion with PYG_ANKLE_LOOP=1).
    """
    pts = json.load(open(LOOP_PTS))
    out = []
    for tag in 'AB':
        P = pts[tag]
        motor, pin, ball = (np.array(P[k]) for k in ('motor', 'pin', 'ball'))
        o_c = to_sim_vec((motor - ORIGIN_CAD['shin']) / 1000.0)      # crank origin, shin frame
        pin_rel = to_sim_vec((pin - motor) / 1000.0)                  # pin, crank frame
        vec = to_sim_vec((ball - pin) / 1000.0)                       # rod vector, rod frame
        if sign > 0:                                                  # right leg: mirror y
            o_c, pin_rel, vec = (v * np.array([1, -1, 1]) for v in (o_c, pin_rel, vec))
        axis1 = np.array([0.0, 1.0, 0.0])                             # crank axis (CAD x -> sim y)
        axis2 = np.cross(axis1, vec / np.linalg.norm(vec))
        axis2 /= np.linalg.norm(axis2)
        mc, cc, Ic = body_inertial(f'crank_{tag}', mp)
        mr, cr, Ir = body_inertial(f'rod_{tag}', mp)
        if sign > 0:
            cc, Ic = mirror(cc, Ic)
            cr, Ir = mirror(cr, Ir)
        pre = 'R_' if sign > 0 else ''
        out.append(f'{ind}<body name="{s}_crank_{tag}" pos="{o_c[0]:.6g} {o_c[1]:.6g} {o_c[2]:.6g}">')
        out.append(f'{ind}  <inertial pos="{cc[0]:.6g} {cc[1]:.6g} {cc[2]:.6g}" mass="{mc:.5g}" fullinertia="{fullinertia(Ic)}"/>')
        out.append(f'{ind}  <joint name="{s}_crank_{tag}_joint" axis="0 1 0" range="{CRANK_RANGE[0]} {CRANK_RANGE[1]}" armature="0.005" damping="0.2"/>')
        out.append(f'{ind}  <geom mesh="{s}_crank_{tag}" class="visual" material="black"/>')
        out.append(f'{ind}  <body name="{s}_rod_{tag}" pos="{pin_rel[0]:.6g} {pin_rel[1]:.6g} {pin_rel[2]:.6g}">')
        out.append(f'{ind}    <inertial pos="{cr[0]:.6g} {cr[1]:.6g} {cr[2]:.6g}" mass="{mr:.5g}" fullinertia="{fullinertia(Ir)}"/>')
        out.append(f'{ind}    <joint name="{s}_rod_{tag}_u1" axis="{axis1[0]:.4f} {axis1[1]:.4f} {axis1[2]:.4f}" armature="0.0005" damping="0.02"/>')
        out.append(f'{ind}    <joint name="{s}_rod_{tag}_u2" axis="{axis2[0]:.4f} {axis2[1]:.4f} {axis2[2]:.4f}" armature="0.0005" damping="0.02"/>')
        out.append(f'{ind}    <geom mesh="{s}_rod_{tag}" class="visual"/>')
        out.append(f'{ind}    <site name="{s}_rod_{tag}_end" pos="{vec[0]:.6g} {vec[1]:.6g} {vec[2]:.6g}" size="0.004"/>')
        out.append(f'{ind}  </body>')
        out.append(f'{ind}</body>')
    return out


def loop_urdf(s, mp, sign):
    """The same mechanism for the URDF - as a TREE. URDF has no loop closure and no universal
    joint, so: crank (revolute) -> rod_u (1 g dummy link) -> rod (revolute x2 = the universal
    joint); the rod's far end is left open and the closure is stated in a comment. Link masses
    and inertias equal the MJCF's (the dummy links add 2 x 1 g per leg, URDF-only bodies)."""
    pts = json.load(open(LOOP_PTS))
    links, joints = [], []
    for tag in 'AB':
        P = pts[tag]
        motor, pin, ball = (np.array(P[k]) for k in ('motor', 'pin', 'ball'))
        o_c = to_sim_vec((motor - ORIGIN_CAD['shin']) / 1000.0)
        pin_rel = to_sim_vec((pin - motor) / 1000.0)
        vec = to_sim_vec((ball - pin) / 1000.0)
        if sign > 0:
            o_c, pin_rel, vec = (v * np.array([1, -1, 1]) for v in (o_c, pin_rel, vec))
        axis1 = np.array([0.0, 1.0, 0.0])
        axis2 = np.cross(axis1, vec / np.linalg.norm(vec)); axis2 /= np.linalg.norm(axis2)
        mc, cc, Ic = body_inertial(f'crank_{tag}', mp)
        mr, cr, Ir = body_inertial(f'rod_{tag}', mp)
        if sign > 0:
            cc, Ic = mirror(cc, Ic)
            cr, Ir = mirror(cr, Ir)
        pre = 'R_' if sign > 0 else ''
        def link(name, m, c, I, mesh=None):
            t = (f'  <link name="{name}">\n    <inertial>\n      <origin xyz="{c[0]:.6g} {c[1]:.6g} {c[2]:.6g}" rpy="0 0 0"/>\n'
                 f'      <mass value="{m:.5g}"/>\n      {urdf_inertia(I)}\n    </inertial>\n')
            if mesh:
                t += f'    <visual>\n      <geometry><mesh filename="meshes/{mesh}"/></geometry>\n    </visual>\n'
            return t + '  </link>\n'
        def joint(name, parent, child, o, ax, rg=None, effort=0.0):
            lim = (f'    <limit lower="{rg[0]}" upper="{rg[1]}" effort="{effort}" velocity="20"/>\n' if rg
                   else f'    <limit lower="-3.1416" upper="3.1416" effort="0" velocity="50"/>\n')
            return (f'  <joint name="{name}" type="revolute">\n    <origin xyz="{o[0]:.6g} {o[1]:.6g} {o[2]:.6g}" rpy="0 0 0"/>\n'
                    f'    <parent link="{parent}"/>\n    <child link="{child}"/>\n    <axis xyz="{ax[0]:.4f} {ax[1]:.4f} {ax[2]:.4f}"/>\n{lim}  </joint>\n')
        links.append(link(f'{s}_crank_{tag}', mc, cc, Ic, f'{pre}crank_{tag}.stl'))
        links.append(link(f'{s}_rod_{tag}_u', 1e-3, np.zeros(3), np.eye(3) * 1e-7))
        links.append(link(f'{s}_rod_{tag}', mr, cr, Ir, f'{pre}rod_{tag}.stl'))
        joints.append(joint(f'{s}_crank_{tag}_joint', f'{s}_shin_link', f'{s}_crank_{tag}', o_c, (0, 1, 0), CRANK_RANGE, 60.0))
        joints.append(joint(f'{s}_rod_{tag}_u1', f'{s}_crank_{tag}', f'{s}_rod_{tag}_u', pin_rel, axis1))
        joints.append(joint(f'{s}_rod_{tag}_u2', f'{s}_rod_{tag}_u', f'{s}_rod_{tag}', np.zeros(3), axis2))
        joints.append(f'  <!-- loop closure, not expressible in URDF: the far end of {s}_rod_{tag} at xyz="{vec[0]:.6g} {vec[1]:.6g} {vec[2]:.6g}" '
                      f'(rod frame) is a ball joint on {s}_foot_link - see the <equality><connect> in {s and ""}the MJCF -->\n')
    return links, joints


def foot_ball_sites(s, sign):
    pts = json.load(open(LOOP_PTS))
    out = []
    for tag in 'AB':
        b = to_sim_vec((np.array(pts[tag]['ball']) - ORIGIN_CAD['foot']) / 1000.0)
        if sign > 0:
            b = b * np.array([1, -1, 1])
        out.append(f'<site name="{s}_ball_{tag}" pos="{b[0]:.6g} {b[1]:.6g} {b[2]:.6g}" size="0.004"/>')
    return out


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
    # --ankle=loop: the 2-RSU ankle as the closed mechanism (needs a massprops file made with
    # PYG_ANKLE_LOOP=1, and the crank/rod/shin_noloop meshes from meshes_step.py --loop)
    loop = next((a.split('=')[1] for a in sys.argv if a.startswith('--ankle=')), 'serial') == 'loop'
    if loop:
        tag = tag + '_loop' if not tag.endswith('_loop') else tag
    mp = json.load(open(mpf))
    # ---- resolve joint ranges from the CAD sweep ----
    # measured ranges are not optional: without the sweep file the old MJCF ranges would come
    # back silently, and the ankle design caps with them (red team 2026-08-23)
    assert os.path.exists(ROM_FILE), f'{ROM_FILE} missing - run tools/robot_model/rom_check.py'
    rom = json.load(open(ROM_FILE))
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
        <default class="foot_box">
          <geom type="box"/>
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
    if loop:
        for s_ in 'LR':
            pre = 'R_' if s_ == 'R' else ''
            for b in ('crank_A', 'crank_B', 'rod_A', 'rod_B'):
                X.append(f'    <mesh name="{s_}_{b}" file="{pre}{b}.stl"/>\n')
            X.append(f'    <mesh name="{s_}_shin_noloop" file="{pre}shin_noloop.stl"/>\n')
            X.append(f'    <mesh name="{s_}_foot_noloop" file="{pre}foot_noloop.stl"/>\n')
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
    X.append('      ' + fitted_capsule('base_pelvis_collision', 'pelvis') + '\n')
    X.append(f'      <site name="imu_in_base" size="0.03" pos="{IMU_POS[0]:.6g} {IMU_POS[1]:.6g} {IMU_POS[2]:.6g}"/>\n')
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
                vis = f'{s}_{b}'
                if loop and b in ('shin', 'foot'):
                    vis = f'{s}_{b}_noloop'          # the cranks and rods are their own bodies now
                X.append(f'{ind}  <geom mesh="{vis}" class="visual"/>\n')
                X.append(f'{ind}  <geom name="{s}_{BNAME[b]}_hull" mesh="{s}_{b}_hull" class="hull"/>\n')
            for g in motor_geoms(mp, b, s):
                X.append(f'{ind}  ' + g + '\n')
            # ---- collision: one capsule that hugs each link's mesh (the hip links and the
            # thigh/shin included), a box for the foot. No hand-typed radii or offsets. ----
            pre = 'R_' if s == 'R' else ''
            if b in ('hip_pitch_link', 'hip_roll_link', 'thigh', 'shin'):
                stl = pre + (f'{b}_noloop' if (loop and b == 'shin') else b)
                X.append(f'{ind}  ' + fitted_capsule(f'{s}_{BNAME[b]}_collision', stl) + '\n')
            if b == 'foot':
                lo_f, hi_f = mesh_bounds(pre + ('foot_noloop' if loop else 'foot'))
                # the sole box: full plate footprint, from the sole up to the ankle-cross
                # housing; name keeps the foot[1-7] pattern the task's contact config uses
                X.append(f'{ind}  ' + box_geom(f'{s}_foot1_collision', lo_f, hi_f, cls='foot_box') + '\n')
                X.append(f'{ind}  <site name="{"left" if s == "L" else "right"}_foot" pos="{(lo_f[0]+hi_f[0])/2:.3f} 0 {lo_f[2]:.3f}" size="0.01"/>\n')
                if loop:
                    for g in foot_ball_sites(s, sign):
                        X.append(f'{ind}  ' + g + '\n')
            if b == 'shin' and loop:
                X.extend(l + '\n' for l in loop_xml(s, ind + '  ', mp, sign))
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
        X.append('        ' + fitted_capsule('torso_collision', 'torso') + '\n')
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
                # the arm is a straight rod with a fat shoulder end: fit the capsule to the
                # rod only (drop the top 12 cm) so it does not read as 44 mm all the way down
                X.append(f'{ind}  ' + fitted_capsule(f'{s_}_{BNAME[b]}_collision', ('R_' if s_ == 'R' else '') + b,
                                                     exclude=(lambda V: V[:, 2] > -0.12) if b == 'arm' else None) + '\n')
            for _ in ARM:
                X.append(ind + '</body>\n')
                ind = ind[:-2]
        X.append('      </body>\n')
    X.append('    </body>\n  </worldbody>\n  <contact>\n')
    # Only ADJACENT bodies are excluded from collision (user, 2026-08-23). The capsules are
    # fitted to the meshes, so non-adjacent links must not overlap at the zero pose on their
    # own; validate_robot.py checks that, and the hip-cluster / arm-hip exclusions the
    # previous model carried are gone.
    for s in 'LR':
        pairs = ['base_link'] + [f'{s}_{BNAME[b]}' for b in CHAIN]
        for a, b in zip(pairs[:-1], pairs[1:]):
            X.append(f'    <exclude body1="{a}" body2="{b}"/>\n')
        # the ankle cross is a 40 g universal-joint body between shin and foot: physically
        # those two are adjacent, so they are excluded across it
        X.append(f'    <exclude body1="{s}_shin_link" body2="{s}_foot_link"/>\n')
        if loop:
            for t in 'AB':          # the loop bodies carry no collision geoms; listed for clarity
                X.append(f'    <exclude body1="{s}_shin_link" body2="{s}_crank_{t}"/>\n')
                X.append(f'    <exclude body1="{s}_crank_{t}" body2="{s}_rod_{t}"/>\n')
                X.append(f'    <exclude body1="{s}_rod_{t}" body2="{s}_foot_link"/>\n')
    if articulated:
        X.append('    <exclude body1="base_link" body2="torso_link"/>\n')
        for s in 'LR':
            X.append(f'    <exclude body1="torso_link" body2="{s}_shoulder_pitch_link"/>\n')
            X.append(f'    <exclude body1="{s}_shoulder_pitch_link" body2="{s}_arm_link"/>\n')
            # The ONE non-adjacent exclusion kept: ArmR_Dummy is a placeholder rod that the CAD
            # itself drives 5.1 mm into the hip roll link at the zero pose (docs/88 s3c). Left
            # to the overlap resolver, clearing it costs the hip roll capsule half its radius
            # and the arm capsule all of it - a real leg link degraded for a dummy. Excluded
            # and reported instead; drop these two lines once the arm CAD is fixed.
            for h in ('hip_pitch_link', 'hip_roll_link'):
                X.append(f'    <exclude body1="{s}_arm_link" body2="{s}_{h}"/>\n')
    X.append('  </contact>\n')
    if loop:
        X.append('  <equality>\n')
        for s in 'LR':
            for t in 'AB':
                X.append(f'    <connect name="{s}_loop_{t}" site1="{s}_rod_{t}_end" site2="{s}_ball_{t}" solref="0.002 1" solimp="0.999 0.9999 0.0001"/>\n')
        X.append('  </equality>\n')
    X.append('''
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
    trimmed = resolve_zero_pose_overlaps(f'{OUT_MJCF}/{tag}.xml')
    if trimmed:
        print('collision radii trimmed to clear non-adjacent overlaps at the zero pose:')
        for k, v in sorted(trimmed.items(), key=lambda kv: -kv[1]):
            print(f'   {k:32s} -{v * 1000:5.1f} mm')
    mjcf = open(f'{OUT_MJCF}/{tag}.xml').read()
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
    if loop:
        for s in 'LR':
            links_, joints_ = loop_urdf(s, mp, -1.0 if s == 'L' else 1.0)
            U.extend(links_); U.extend(joints_)
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
          f'{"ARTICULATED (5 joints: waist yaw + shoulder pitch/roll x2)" if articulated else "placeholder lump on the pelvis"}')
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
