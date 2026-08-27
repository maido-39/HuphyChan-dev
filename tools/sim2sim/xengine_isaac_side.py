"""Cross-engine static gravity check - IsaacSim side.

Same pose as the MuJoCo half, base fixed, qdot=0. PhysX has no direct qfrc_bias equivalent, so
the gravity load is read the operational way: hold the pose with strong PD, wait for the servo
to settle, and record the applied joint efforts - at rest they equal the gravity torque.
Results to disk BEFORE close().
"""
import json
import os

os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
USD = '/home/syaro/pyg_fea/usd/pygmalion_v4_printed.usd'
RES = '/home/syaro/pyg_fea/work/xengine_isaac.json'
POSE = json.load(open('/home/syaro/pyg_fea/work/xengine_mujoco.json'))['pose']
res = {'ok': False}

try:
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})
    import numpy as np
    import omni.usd
    from isaacsim.core.api import World
    from isaacsim.core.prims import Articulation
    from pxr import UsdPhysics

    ctx = omni.usd.get_context()
    ctx.open_stage(USD)
    # Weld the base with a FixedJoint world->base_link. Setting the base kinematic instead
    # DISSOLVES the articulation (dof_names comes back None): PhysX drops an articulation whose
    # root is kinematic. A fixed joint keeps the articulated chain and just pins its root.
    stage = ctx.get_stage()
    fj = UsdPhysics.FixedJoint.Define(stage, '/pygmalion_v4_printed/base_weld')
    fj.CreateBody1Rel().SetTargets(['/pygmalion_v4_printed/base_link'])

    world = World(stage_units_in_meters=1.0, physics_dt=1/200, rendering_dt=1/25)
    art = Articulation('/pygmalion_v4_printed', name='robot')
    world.reset()
    art.initialize()

    names = list(art.dof_names)
    idx = {n: i for i, n in enumerate(names)}
    q_t = np.zeros(len(names))
    for jn, q in POSE.items():
        q_t[idx[jn]] = q

    # stiff position hold so the settled effort equals the gravity load
    n = len(names)
    art.set_gains(kps=np.full((1, n), 2000.0), kds=np.full((1, n), 100.0))
    art.set_joint_positions(q_t.reshape(1, -1))
    art.set_joint_velocities(np.zeros((1, n)))
    art.set_joint_position_targets(q_t.reshape(1, -1))
    for _ in range(600):                       # 3 s at 200 Hz to settle
        world.step(render=False)

    q = np.asarray(art.get_joint_positions()).flatten()
    tau = np.asarray(art.get_measured_joint_efforts()).flatten()
    res.update(ok=True,
               q_err_max=float(np.max(np.abs(q - q_t))),
               torque_Nm={jn: round(float(tau[idx[jn]]), 4) for jn in POSE},
               q_reached={jn: round(float(q[idx[jn]]), 4) for jn in POSE})
    json.dump(res, open(RES, 'w'), indent=1)
    app.close()
except Exception as e:
    import traceback
    res.update(error=f'{type(e).__name__}: {e}', tb=traceback.format_exc()[-1800:])
    json.dump(res, open(RES, 'w'), indent=1)
