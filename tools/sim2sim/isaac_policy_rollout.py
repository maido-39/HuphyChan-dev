"""Roll the trained RP walking policy in IsaacSim - the dynamic half of the cross-engine check.

Reproduces the mjlab control stack exactly, from the dumped contract (not from memory):
  50 Hz loop (decimation 4 over 1/200 s physics), obs = [ang_vel_b(3), gravity_b(3),
  q-q0(12), dq(12), last_action(12), cmd(3)], q_target = q0 + 0.25*action, per-joint PD
  (hip 150/6, knee 220/6, ankle 28.5/1.81), efforts applied as torques.

The policy's joint ORDER is mjlab's (L leg then R leg); Isaac's articulation is breadth-first.
The remap is built from names - this file is therefore also the reference implementation of
the deployment transfer layer's index mapping.

Waist/shoulders exist in the USD but were welded in training: driven to 0 with a stiff PD.

Results (tracking, falls, contact) go to JSON BEFORE app.close().
"""
import json
import os

os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
USD = '/home/syaro/pyg_fea/usd/pygmalion_v4_printed.usd'
ONNX = (f'{REPO}/mujoco-sim/mjlab/logs/rsl_rl/pygmalion_velocity/'
        '2026-08-26_15-45-16_bundleD1_RP/2026-08-26_15-45-16_bundleD1_RP.onnx')
CONTRACT = '/home/syaro/pyg_fea/work/rp_policy_contract.json'
RES = '/home/syaro/pyg_fea/work/isaac_rollout.json'
TRAJ = '/home/syaro/pyg_fea/work/isaac_rollout_traj.npz'
CMD = [1.6, 0.0, 0.0]
SECONDS = 14.0
res = {'ok': False}

try:
    import numpy as np
    import onnxruntime as rt
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})
    import omni.usd
    from isaacsim.core.api import World
    from isaacsim.core.prims import Articulation

    C = json.load(open(CONTRACT))
    pol_names = C['joint_names']                       # mjlab order = policy order
    q0 = np.array([C['default_q'][n] for n in pol_names])
    kp = np.array([C['gains_sw'][n]['kp'] for n in pol_names])
    kd = np.array([C['gains_sw'][n]['kd'] for n in pol_names])
    frc = np.array([abs(C['gains'][n]['forcerange'][1]) for n in pol_names])
    # T-N clamp tables, exactly mjlab's semantics: motoring quadrant follows the measured curve
    # (flat at peak below the corner speed, tapering to zero at no-load), braking quadrant gets
    # the full peak. Training ran WITH this clamp; without it Isaac has extra torque at speed
    # and walked 17 % over the command.
    tn_w, tn_t = {}, {}
    for fam, pts in C['tn_curves'].items():
        tn_w[fam] = np.array([w for w, _ in pts])
        tn_t[fam] = np.array([t for _, t in pts])
    fam_of = [C['joint_family'][n] for n in pol_names]

    def tn_avail(speed_abs, fam):
        return np.interp(speed_abs, tn_w[fam], tn_t[fam])

    def tn_clamp_vec(tau, omega):
        out = np.empty_like(tau)
        for i, fam in enumerate(fam_of):
            peak = tn_t[fam][0]
            hi = tn_avail(omega[i], fam) if omega[i] >= 0 else peak
            lo = -(tn_avail(-omega[i], fam) if omega[i] < 0 else peak)
            out[i] = min(max(tau[i], lo), hi)
        return out
    scale = 0.25
    decim = C['decimation']

    sess = rt.InferenceSession(ONNX)

    ctx = omni.usd.get_context()
    ctx.open_stage(USD)
    world = World(stage_units_in_meters=1.0, physics_dt=C['physics_dt'], rendering_dt=1/25)
    # NOT the default ground plane: its material is friction 0.5/0.5 with RESTITUTION 0.8 -
    # a bouncy floor. MuJoCo trains on friction 1.0 and no restitution, so the mismatch alone
    # produces a fast, springy over-speed gait (observed +34 % over command before this).
    world.scene.add_default_ground_plane(static_friction=1.0, dynamic_friction=1.0,
                                         restitution=0.0)
    art = Articulation('/pygmalion_v4_printed', name='robot')
    world.reset()
    art.initialize()

    isaac_names = list(art.dof_names)
    n_all = len(isaac_names)
    pol2isaac = np.array([isaac_names.index(n) for n in pol_names])
    upper = [i for i, n in enumerate(isaac_names) if n not in pol_names]

    # torque control everywhere: zero the engine PD, we compute efforts ourselves so the loop
    # matches mjlab (whose PD lives in software, with the same kp/kd, then a force clamp)
    art.set_gains(kps=np.zeros((1, n_all)), kds=np.zeros((1, n_all)))

    # ARMATURE - the fix for the instant blow-up. URDF cannot express reflected rotor inertia,
    # so the imported model's ankle sees ~7e-4 kg*m^2 where training saw ~0.021 (armature
    # included). Software damping kd*dt/I then sits far past the explicit stability limit and
    # the leg explodes within three control ticks (observed: q jumped 0.117 rad in 20 ms).
    # Same physics as the PYG_MOTOR_MEAS=0 incident (docs/99). Joint viscous damping goes in
    # engine-side too; Coulomb friction is applied in the torque loop below.
    arma = np.zeros(n_all)
    visc = np.zeros(n_all)
    fric = np.zeros(n_all)
    for jn, prop in C['dof_props'].items():
        i = isaac_names.index(jn)
        arma[i] = prop['armature']
        visc[i] = prop['damping']
        fric[i] = prop['frictionloss']
    art.set_armatures(arma.reshape(1, -1))

    # initial pose: default_q, base 5 mm above sole contact height, zero velocity
    q_init = np.zeros(n_all)
    q_init[pol2isaac] = q0
    art.set_joint_positions(q_init.reshape(1, -1))
    art.set_joint_velocities(np.zeros((1, n_all)))
    # spawn height computed in MuJoCo for THIS pose (sole exactly at the floor + 2 mm):
    # guessing it dropped the robot ~25 mm and it fell inside half a second.
    art.set_world_poses(positions=[[0.0, 0.0, C.get('spawn_base_z', 0.9085)]])

    last_act = np.zeros(12, dtype=np.float32)
    g_w = np.array([0.0, 0.0, -1.0])
    steps = int(SECONDS / C['step_dt'])
    log = {'t': [], 'base_xy': [], 'base_z': [], 'vx_b': [], 'quat': [], 'fell': False}

    def quat_rot_inv(q, v):
        w, x, y, z = q
        # rotate v by the inverse of quaternion q (w,x,y,z)
        u = np.array([x, y, z])
        return v + 2.0 * np.cross(u, np.cross(u, v) - w * v)

    for k in range(steps):
        pos, quat = art.get_world_poses()
        quat = np.asarray(quat).flatten()              # w,x,y,z
        lin_w = np.asarray(art.get_velocities()).flatten()[:3]
        ang_w = np.asarray(art.get_velocities()).flatten()[3:6]
        q_all = np.asarray(art.get_joint_positions()).flatten()
        dq_all = np.asarray(art.get_joint_velocities()).flatten()

        ang_b = quat_rot_inv(quat, ang_w)
        grav_b = quat_rot_inv(quat, g_w)
        q = q_all[pol2isaac]
        dq = dq_all[pol2isaac]

        cmd_now = [CMD[0] * min(1.0, k * C['step_dt'] / 2.0), CMD[1], CMD[2]]
        obs = np.concatenate([ang_b, grav_b, q - q0, dq, last_act, cmd_now]).astype(np.float32)
        act = sess.run(None, {'obs': obs.reshape(1, -1)})[0].flatten()
        if k < 3:                                      # diagnostic: the first ticks tell the story
            res.setdefault('diag', []).append(dict(
                k=k, quat=[round(float(v), 4) for v in quat],
                grav_b=[round(float(v), 4) for v in grav_b],
                ang_b=[round(float(v), 4) for v in ang_b],
                q_minus_q0=[round(float(v), 4) for v in (q - q0)],
                act=[round(float(v), 3) for v in act]))
        last_act = act.copy()
        q_t = q0 + scale * act

        for _ in range(decim):
            q_all = np.asarray(art.get_joint_positions()).flatten()
            dq_all = np.asarray(art.get_joint_velocities()).flatten()
            tau = np.zeros(n_all)
            raw = np.clip(kp * (q_t - q_all[pol2isaac]) - kd * dq_all[pol2isaac], -frc, frc)
            tau[pol2isaac] = tn_clamp_vec(raw, dq_all[pol2isaac])
            tau -= visc * dq_all + fric * np.tanh(dq_all / 0.05)   # viscous + smoothed Coulomb
            for i in upper:                            # weld the unused upper joints
                tau[i] = 400.0 * (0.0 - q_all[i]) - 20.0 * dq_all[i]
            art.set_joint_efforts(tau.reshape(1, -1))
            world.step(render=False)

        pos_q = art.get_world_poses()
        pos = np.asarray(pos_q[0]).flatten()
        vb = quat_rot_inv(np.asarray(pos_q[1]).flatten(),
                          np.asarray(art.get_velocities()).flatten()[:3])
        log['t'].append(round(k * C['step_dt'], 3))
        log['base_xy'].append([round(float(pos[0]), 4), round(float(pos[1]), 4)])
        log['base_z'].append(round(float(pos[2]), 4))
        log['vx_b'].append(round(float(vb[0]), 4))
        if pos[2] < 0.45:
            log['fell'] = True
            break

    vx = np.array(log['vx_b'][int(2.0 / C['step_dt']):])   # skip 2 s warmup
    res.update(ok=True, fell=log['fell'], sim_seconds=log['t'][-1] if log['t'] else 0,
               vx_mean=float(vx.mean()) if len(vx) else None,
               vx_err=float(np.mean(np.abs(vx - CMD[0]))) if len(vx) else None,
               base_z_mean=float(np.mean(log['base_z'])),
               final_x=log['base_xy'][-1][0] if log['base_xy'] else None)
    np.savez_compressed(TRAJ, **{k: np.array(v) for k, v in log.items() if k != 'fell'})
    json.dump(res, open(RES, 'w'), indent=1)
    app.close()
except Exception as e:
    import traceback
    res.update(error=f'{type(e).__name__}: {e}', tb=traceback.format_exc()[-1800:])
    json.dump(res, open(RES, 'w'), indent=1)
