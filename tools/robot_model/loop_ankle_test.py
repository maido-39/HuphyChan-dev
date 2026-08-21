"""Can MuJoCo carry the 2-RSU ankle as a CLOSED LOOP on top of the v2 model? (v2.1 feasibility)

The goal note says the AB motor links can be modelled in mjlab - MuJoCo does closed
chains through `equality/connect`. This builds, from the v2 MJCF, the real mechanism on the
left leg at the CAD pose:

  crank A / B   hinge on the shin at the two RS03 axes (measured axis points), radius to the
                measured ball-joint pin
  rod A / B     ball joint at the crank pin, a site at the far end where the foot ball is
  connect       rod far-end site  <->  foot ball point, a 3-DOF constraint each

DOF accounting: each loop adds 1 (crank hinge) + 3 (rod ball) and removes 3 (connect),
so the two loops add 2 DOF - the same two the serial pitch/roll joints already have. With
the cranks driven, the serial joints become passive and follow the linkage. The test:
  1. closure residual at the CAD pose must be ~0 (the rod lengths ARE the CAD distances)
  2. with the base welded, torque on crank A must move ankle pitch and the rods must stay
     at their lengths - the loop transmits

Usage: loop_ankle_test.py   (mjlab .venv python). Writes xmls/pygmalion_v21_loop.xml.
"""
import numpy as np
import mujoco

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
XML = f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/pygmalion_v2.xml'
OUT = f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/pygmalion_v21_loop.xml'
R = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
SHIN = np.array([-123.7, 115.0, -310.0])
FOOT = np.array([-123.7, 145.0, -800.0])
# CAD mm: motor axis points (measured cylinder axes), crank pins = upper ball joints, foot balls
MOTOR = {'A': np.array([-138.9, 145.0, -500.0]), 'B': np.array([-108.4, 145.0, -600.0])}
PIN = {'A': np.array([-83.7, 205.7, -523.2]), 'B': np.array([-163.7, 208.0, -616.0])}
BALL = {'A': np.array([-86.2, 195.0, -810.0]), 'B': np.array([-161.2, 195.0, -810.0])}
ROD_KG = {'A': 0.0543, 'B': 0.0414}
CRANK_KG = 0.115


def sim(v, origin):
    return R @ ((v - origin) / 1000.0)


def main():
    spec = mujoco.MjSpec.from_file(XML)
    shin = next(b for b in spec.bodies if b.name == 'L_shin_link')
    for tag in 'AB':
        # crank: hinge about the motor axis (x in CAD -> y in sim) at the motor axis point
        c = shin.add_body(name=f'L_crank_{tag}', pos=sim(MOTOR[tag], SHIN), mass=CRANK_KG,
                          ipos=[0, 0, 0], fullinertia=[4e-5, 4e-5, 4e-5, 0, 0, 0])
        c.add_joint(name=f'L_crank_{tag}_joint', type=mujoco.mjtJoint.mjJNT_HINGE, axis=[0, 1, 0],
                    damping=0.2, armature=0.005)
        pin_rel = sim(PIN[tag], MOTOR[tag])
        c.add_geom(type=mujoco.mjtGeom.mjGEOM_CAPSULE, fromto=[0, 0, 0, *pin_rel], size=[0.006, 0, 0],
                   contype=0, conaffinity=0, rgba=[0.9, 0.5, 0.2, 1], group=2)
        # rod: ball joint at the pin, body axis along the rod at the CAD pose
        vec = sim(BALL[tag], PIN[tag])
        L = np.linalg.norm(vec)
        r = c.add_body(name=f'L_rod_{tag}', pos=pin_rel, mass=ROD_KG[tag], ipos=vec / 2,
                       fullinertia=[ROD_KG[tag] * L * L / 12] * 2 + [1e-6, 0, 0, 0])
        r.add_joint(name=f'L_rod_{tag}_ball', type=mujoco.mjtJoint.mjJNT_BALL, damping=0.02, armature=0.0005)
        r.add_geom(type=mujoco.mjtGeom.mjGEOM_CAPSULE, fromto=[0, 0, 0, *vec], size=[0.005, 0, 0],
                   contype=0, conaffinity=0, rgba=[0.2, 0.6, 0.9, 1], group=2)
        r.add_site(name=f'L_rod_{tag}_end', pos=vec, size=[0.004, 0, 0])
        foot = next(b for b in spec.bodies if b.name == 'L_foot_link')
        foot.add_site(name=f'L_ball_{tag}', pos=sim(BALL[tag], FOOT), size=[0.004, 0, 0])
        eq = spec.add_equality()
        eq.type = mujoco.mjtEq.mjEQ_CONNECT
        eq.objtype = mujoco.mjtObj.mjOBJ_SITE       # site-site connect: no anchor data needed
        eq.name = f'L_loop_{tag}'
        eq.name1 = f'L_rod_{tag}_end'
        eq.name2 = f'L_ball_{tag}'
        eq.solref[:] = [0.002, 1.0]            # stiff ball joint, not a spring
        r_perp = np.linalg.norm(np.delete(pin_rel, 1))   # radius perpendicular to the hinge (sim y)
        print(f'loop {tag}: rod length {L*1000:.1f} mm (CAD A_L 289 / B_L 195), '
              f'crank radius {r_perp*1000:.1f} mm (CAD A_r 65 / B_r 62)')
    # actuators on the cranks for the test
    for tag in 'AB':
        # position servo on the crank (what the RS03 does), gains in the RS03 class
        a = spec.add_actuator()
        a.name = f'L_crank_{tag}_motor'
        a.trntype = mujoco.mjtTrn.mjTRN_JOINT
        a.target = f'L_crank_{tag}_joint'
        a.gear[0] = 1.0
        a.gaintype = mujoco.mjtGain.mjGAIN_FIXED
        a.biastype = mujoco.mjtBias.mjBIAS_AFFINE   # without this the bias is IGNORED and the
        a.gainprm[0] = 100.0                        # "servo" is a pure torque motor (runaway)
        a.biasprm[1] = -100.0
        a.biasprm[2] = -5.0
        a.ctrlrange[:] = [-1.5, 1.5]
        a.ctrllimited = True
        a.forcerange[:] = [-60, 60]
        a.forcelimited = True
    for j in spec.joints:
        if j.name in ('L_ankle_pitch_joint', 'L_ankle_roll_joint'):
            j.armature = 0.005
            j.damping = np.full(3, 0.5)
    spec.option.timestep = 0.001
    m = spec.compile()
    spec.to_file(OUT)
    d = mujoco.MjData(m)
    d.qpos[:] = 0
    d.qpos[2] = 1.0
    d.qpos[3] = 1.0
    # quaternion parts of the ball joints must be unit
    for j in range(m.njnt):
        if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_BALL:
            d.qpos[m.jnt_qposadr[j]:m.jnt_qposadr[j] + 4] = [1, 0, 0, 0]
    mujoco.mj_forward(m, d)
    # 1. closure residual at the CAD pose
    for tag in 'AB':
        sid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, f'L_rod_{tag}_end')
        ball_w = d.xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, 'L_foot_link')] + \
            d.xmat[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, 'L_foot_link')].reshape(3, 3) @ sim(BALL[tag], FOOT)
        print(f'closure {tag}: |rod end - foot ball| = {np.linalg.norm(d.site_xpos[sid]-ball_w)*1000:.3f} mm at the CAD pose')
    # 2. weld the base, drive crank A, watch the ankle follow
    spec2 = mujoco.MjSpec.from_file(OUT)
    w = spec2.add_equality()
    w.type = mujoco.mjtEq.mjEQ_WELD
    w.objtype = mujoco.mjtObj.mjOBJ_BODY
    w.name1 = 'L_shin_link'                     # hold the SHIN: hip/knee have no actuators here
    m2 = spec2.compile()
    d2 = mujoco.MjData(m2)
    d2.qpos[:] = 0
    d2.qpos[2] = 1.0
    d2.qpos[3] = 1.0
    for j in range(m2.njnt):
        if m2.jnt_type[j] == mujoco.mjtJoint.mjJNT_BALL:
            d2.qpos[m2.jnt_qposadr[j]:m2.jnt_qposadr[j] + 4] = [1, 0, 0, 0]
    ap = mujoco.mj_name2id(m2, mujoco.mjtObj.mjOBJ_JOINT, 'L_ankle_pitch_joint')
    ar = mujoco.mj_name2id(m2, mujoco.mjtObj.mjOBJ_JOINT, 'L_ankle_roll_joint')
    aA = mujoco.mj_name2id(m2, mujoco.mjtObj.mjOBJ_ACTUATOR, 'L_crank_A_motor')
    aB = mujoco.mj_name2id(m2, mujoco.mjtObj.mjOBJ_ACTUATOR, 'L_crank_B_motor')
    print('\ncrank position targets -> ankle response (shin welded, 1 s each):')
    eqA = [i for i in range(m2.neq) if m2.eq_type[i] == mujoco.mjtEq.mjEQ_CONNECT]
    for tA, tB, lab in ((0.2, 0.2, 'both +11.5 deg (pitch)'), (-0.2, -0.2, 'both -11.5'), (0.2, -0.2, 'A+ B- (roll)'), (0.0, 0.0, 'back to 0')):
        c0A, c0B = float(d2.ctrl[aA]), float(d2.ctrl[aB])
        for k in range(1000):                      # 1 s: ramp the target over the first half
            f = min(1.0, k / 500.0)
            d2.ctrl[aA], d2.ctrl[aB] = c0A + f * (tA - c0A), c0B + f * (tB - c0B)
            mujoco.mj_step(m2, d2)
        # closure error measured directly: rod end site vs foot ball site
        err = max(np.linalg.norm(d2.site_xpos[mujoco.mj_name2id(m2, mujoco.mjtObj.mjOBJ_SITE, f'L_rod_{t}_end')]
                                 - d2.site_xpos[mujoco.mj_name2id(m2, mujoco.mjtObj.mjOBJ_SITE, f'L_ball_{t}')]) for t in 'AB')
        cA = np.degrees(d2.qpos[m2.jnt_qposadr[mujoco.mj_name2id(m2, mujoco.mjtObj.mjOBJ_JOINT, 'L_crank_A_joint')]])
        print(f'  {lab:24s} crank A {cA:+6.1f}  pitch {np.degrees(d2.qpos[m2.jnt_qposadr[ap]]):+6.1f} deg  roll {np.degrees(d2.qpos[m2.jnt_qposadr[ar]]):+6.1f} deg'
              f'  closure error {err*1000:.3f} mm')
    print(f'-> {OUT}')


if __name__ == '__main__':
    main()
