"""Cross-engine static gravity check for the CLOSED-LOOP (AB) ankle - IsaacSim side.

The serial twin of this script held all 17 joints with a stiff servo and read the settled efforts.
That cannot be copied verbatim onto a loop: four of the joints it used to hold (the ankles) have no
motor any more, and four joints it never had (the cranks) now carry the foot through two rods and a
pair of ball-jointed loop closures that PhysX solves OUTSIDE the articulation. So two phases run:

  motors    the honest machine - servo on the 17 real motors only; ankles, rod U-joints and the
            loop closures are left to find their own equilibrium. If the USD anchors are right the
            ankles must land on the MuJoCo pose without ever being told to, which is the single
            strongest check that the loop geometry survived the port.
  all_held  every joint servoed, including the passive ones. This is what a naive port of the
            serial script would do, and it is reported so the two can be told apart rather than
            silently conflated.

Both phases also report the loop drift: the world-space distance between the two points each
spherical joint is supposed to hold together. A maximal-coordinate joint is solved at lower
priority than the articulation, so this is where error shows up first.

Results are written after EVERY phase, and always before close() - Kit's close() hard-exits.

  OMNI_KIT_ACCEPT_EULA=YES ~/isaacsim_venv/bin/python3 tools/sim2sim/xengine_loop_isaac_side.py
"""
import json
import os

os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
USD = '/home/syaro/pyg_fea/usd/pygmalion_v4_printed_loop.usd'
REF = '/home/syaro/pyg_fea/work/xengine_loop_mujoco.json'
LOOPJ = '/home/syaro/pyg_fea/work/author_loop_usd.json'
RES = '/home/syaro/pyg_fea/work/xengine_loop_isaac.json'

DT = 1 / 500
SETTLE = 2500                      # 5 s: the free ankle has to be driven there through the rods
ARMATURE = {'crank': 0.005, 'rod': 0.0005}      # mirrors the MJCF; URDF cannot carry armature
res = {'ok': False, 'usd': USD, 'physics_dt': DT, 'settle_steps': SETTLE}


def dump():
    json.dump(res, open(RES, 'w'), indent=1)


try:
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})

    import numpy as np
    import omni.usd
    from isaacsim.core.api import World
    from isaacsim.core.prims import Articulation, RigidPrim
    from pxr import UsdPhysics

    ref = json.load(open(REF))
    loops = json.load(open(LOOPJ))['joints']
    POSE = ref['pose']                       # all 29 joints, loop-consistent (residual < 1e-9 mm)
    ACT = ref['actuated']

    ctx = omni.usd.get_context()
    ctx.open_stage(USD)
    stage = ctx.get_stage()
    root = stage.GetDefaultPrim().GetPath().pathString

    # Weld the base: a kinematic root dissolves the articulation, a fixed joint pins it.
    fj = UsdPhysics.FixedJoint.Define(stage, f'{root}/base_weld')
    fj.CreateBody1Rel().SetTargets([f'{root}/base_link'])

    world = World(stage_units_in_meters=1.0, physics_dt=DT, rendering_dt=1 / 25)
    art = Articulation(root, name='robot')

    # the two bodies of every loop closure, so their anchor points can be compared in world space
    body_paths = sorted({j['body0_prim'] for j in loops} | {j['body1_prim'] for j in loops})
    probe = RigidPrim(prim_paths_expr=body_paths, name='loop_bodies')

    world.reset()
    art.initialize()
    probe.initialize()

    names = list(art.dof_names)
    idx = {n: i for i, n in enumerate(names)}
    n = len(names)
    res.update(n_dof=n, dof_names=names,
               total_mass_kg=round(float(np.asarray(art.get_body_masses()).sum()), 4),
               n_bodies=len(list(art.body_names)),
               missing_from_usd=[j for j in POSE if j not in idx],
               extra_in_usd=[j for j in names if j not in POSE])
    try:
        res['solver_iters'] = [int(np.asarray(art.get_solver_position_iteration_counts()).flatten()[0]),
                               int(np.asarray(art.get_solver_velocity_iteration_counts()).flatten()[0])]
    except Exception as e:
        res['solver_iters_err'] = f'{type(e).__name__}: {e}'
    dump()
    if res['missing_from_usd']:
        raise RuntimeError(f"USD is missing joints the MuJoCo loop model has: {res['missing_from_usd']}")

    q_t = np.zeros(n)
    for jn, q in POSE.items():
        q_t[idx[jn]] = q

    arma = np.zeros(n)
    for jn in names:
        if 'crank' in jn:
            arma[idx[jn]] = ARMATURE['crank']
        elif '_rod_' in jn:
            arma[idx[jn]] = ARMATURE['rod']
    art.set_armatures(arma.reshape(1, -1))

    def quat_rot(q, v):
        w, x, y, z = q
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        return R @ np.asarray(v)

    def drift():
        """world separation of each closure's two anchor points, in millimetres."""
        pos, quat = probe.get_world_poses()
        pos = np.asarray(pos); quat = np.asarray(quat)
        where = {p: i for i, p in enumerate(list(probe.prim_paths))}
        out = {}
        for j in loops:
            a = pos[where[j['body0_prim']]] + quat_rot(quat[where[j['body0_prim']]], j['localPos0'])
            b = pos[where[j['body1_prim']]] + quat_rot(quat[where[j['body1_prim']]], j['localPos1'])
            out[j['name']] = round(float(np.linalg.norm(a - b) * 1e3), 6)
        return out

    def phase(tag, kp, kd):
        art.set_gains(kps=kp.reshape(1, -1), kds=kd.reshape(1, -1))
        # ALL joint positions at once, passive ones included. Setting only the driven subset is
        # the documented way to make a closed-loop articulation explode (IsaacLab #1250): the
        # untouched passive joints leave the closure violated and the solver launches the robot.
        art.set_joint_positions(q_t.reshape(1, -1))
        art.set_joint_velocities(np.zeros((1, n)))
        art.set_joint_position_targets(q_t.reshape(1, -1))
        for _ in range(SETTLE):
            world.step(render=False)
        q = np.asarray(art.get_joint_positions()).flatten()
        qd = np.asarray(art.get_joint_velocities()).flatten()
        tau = np.asarray(art.get_measured_joint_efforts()).flatten()
        r = {
            'gains': {'kp': {jn: float(kp[idx[jn]]) for jn in names},
                      'kd': {jn: float(kd[idx[jn]]) for jn in names}},
            'q_reached': {jn: round(float(q[idx[jn]]), 6) for jn in names},
            'qd_max': float(np.max(np.abs(qd))),
            'torque_Nm': {jn: round(float(tau[idx[jn]]), 4) for jn in names},
            'q_err_max_driven': float(np.max(np.abs((q - q_t)[[idx[j] for j in ACT]]))),
            'loop_drift_mm': drift(),
            'ankle_err_rad': {jn: round(float(q[idx[jn]] - q_t[idx[jn]]), 6)
                              for jn in names if 'ankle' in jn},
        }
        res[tag] = r
        dump()
        return r

    PASSIVE = [jn for jn in names if jn not in ACT]

    # phase 1: only the real motors are held
    kp = np.zeros(n); kd = np.zeros(n)
    for jn in ACT:
        kp[idx[jn]], kd[idx[jn]] = (400.0, 20.0) if 'crank' in jn else (2000.0, 100.0)
    for jn in PASSIVE:
        kd[idx[jn]] = 0.02 if '_rod_' in jn else 0.05      # MJCF rod damping; ankles get a whisker
    p1 = phase('motors', kp, kd)
    print('motors  q_err', round(p1['q_err_max_driven'], 5), 'drift(mm)', p1['loop_drift_mm'])

    # phase 2: everything held, the naive serial-script port
    kp2 = np.full(n, 2000.0); kd2 = np.full(n, 100.0)
    for jn in names:
        if 'crank' in jn:
            kp2[idx[jn]], kd2[idx[jn]] = 400.0, 20.0
        elif '_rod_' in jn:
            kp2[idx[jn]], kd2[idx[jn]] = 40.0, 2.0         # 0.08 kg rods; 2000 would ring
    p2 = phase('all_held', kp2, kd2)
    print('all_held q_err', round(p2['q_err_max_driven'], 5), 'drift(mm)', p2['loop_drift_mm'])

    res['ok'] = True
    dump()
    app.close()
except Exception as e:
    import traceback
    res.update(ok=False, error=f'{type(e).__name__}: {e}', tb=traceback.format_exc()[-2500:])
    dump()
