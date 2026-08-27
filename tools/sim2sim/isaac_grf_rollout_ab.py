"""AB (closed-loop 2-RSU ankle) policy rollout in IsaacSim, with GRF, joint torques and loop drift.

This is the AB twin of `isaac_grf_rollout.py`. The instrument is the same (RigidContactView on
the two feet, sampled every physics substep, run through the strike detector copied verbatim
from `impact_probe_multi.py`), so the Isaac and MuJoCo GRF numbers land in one table without an
asterisk on the detector. Three things are new, and all three are forced by the loop:

1. THE POLICY IS NOT THE RP POLICY, AND ITS INTERFACE IS NOT THE RP INTERFACE.
   Actions are 12 - hips, knees and the four CRANKS. The ankle pitch/roll hinges have no motor;
   they are dragged by the rods. But the OBSERVATION carries 16 joints (hips, knees, cranks AND
   the passive ankles - the hardware can reconstruct them from the crank encoders), so
   obs = 3 + 3 + 16 + 16 + 12 + 3 = 53, not 45. Everything here is read from
   `ab_policy_contract.json`, dumped from the training env by `dump_contract_ab.py`.

2. RESET MUST WRITE ALL 29 JOINTS AT ONCE.
   IsaacLab #1250: setting only the driven subset leaves the closure violated and the solver
   launches the robot across the map. The contract carries a loop-consistent pose for all 24
   mjlab DOFs; the 5 upper-body joints (welded away in mjlab) are written to the angles that
   reproduce the mjlab geometry, including the 15 deg arm abduction that mjlab bakes into the
   body quat before deleting the joint (`PYG_ARM_ABD_DEG`, default 15). Holding them at 0 - what
   the RP port did - hangs 5.7 kg of arm 5 cm further inboard than the trained model.

3. SOLVER ITERATIONS ARE MANDATORY, NOT OPTIONAL.
   The URDF importer silently writes 32/1, which the contact sweep showed is the worst setting
   in the study (peak x1.97, rate x2.92 vs MuJoCo). PYG_ITERS must be set explicitly or this
   script refuses to run, and the value it actually got back from the live articulation is
   echoed into the result JSON. Never quote a number from here without its iteration pair.

WHAT (B) ADDS: per-substep joint torque and loop drift
-----------------------------------------------------
The sweep's unresolved #1 was that lowering the position iteration count from 32 to 4 might buy
GRF fidelity at the cost of articulation constraint error - which would matter, because the load
study wants JOINT torques, not just the force under the sole. So every substep also records:
  * `tau_applied`   - the effort this script commands (its own PD + T-N clamp + friction)
  * `tau_measured`  - `Articulation.get_measured_joint_efforts()`, the DOF force PhysX actually
                      resolved. On the passive ankle and rod hinges this is pure loop transmission.
  * `loop_drift`    - world distance between the two anchor points of each of the four closure
                      joints, in mm. The static number was 0.0003 mm; landing impact is the test.
  * q, dq           - so the q/qtarget/error decomposition can be run offline.

  PYG_ITERS=4,8 OMNI_KIT_ACCEPT_EULA=YES ~/isaacsim_venv/bin/python3 \\
      tools/sim2sim/isaac_grf_rollout_ab.py [usd] [seconds]
"""
import json
import os
import sys

os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
sys.path.insert(0, f'{REPO}/tools/sim2sim')
USD = sys.argv[1] if len(sys.argv) > 1 else '/home/syaro/pyg_fea/usd/pygmalion_v3_printed_loop.usd'
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0
ONNX = (f'{REPO}/mujoco-sim/mjlab/logs/rsl_rl/pygmalion_velocity/'
        '2026-08-26_15-02-37_bundleD1_AB/2026-08-26_15-02-37_bundleD1_AB.onnx')
CONTRACT = '/home/syaro/pyg_fea/work/ab_policy_contract.json'
MJCF = (f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/'
        'pygmalion_v3_printed_loop.xml')
OUTDIR = '/home/syaro/pyg_fea/work/ab_rollout'
os.makedirs(OUTDIR, exist_ok=True)
TAG = os.environ.get('PYG_TAG', '').strip() or 'run'
STEM = f'{OUTDIR}/isaac_ab_{TAG}'
RES, TRACE = f'{STEM}.json', f'{STEM}_traces.npz'
MJ_NPZ = '/home/syaro/pyg_fea/work/impact_multi_nodr/bundleD1_AB_raw.npz'
MJ_JSON = '/home/syaro/pyg_fea/work/impact_multi_nodr/bundleD1_AB.json'
CMD = [1.6, 0.0, 0.0]
WARM = 3.0
FEET = ['L_foot_link', 'R_foot_link']
ARM_ABD = float(os.environ.get('PYG_ARM_ABD_DEG', '15'))
res = {'ok': False, 'usd': USD, 'seconds_requested': SECONDS, 'tag': TAG, 'onnx': ONNX}

ITERS = os.environ.get('PYG_ITERS', '').strip()
if not ITERS:
    res['error'] = ('PYG_ITERS is mandatory: the URDF importer writes 32/1, the worst setting '
                    'in the contact sweep. Set e.g. PYG_ITERS=4,8.')
    json.dump(res, open(RES, 'w'), indent=1)
    sys.exit(2)
ITERS = [int(x) for x in ITERS.split(',')]

HI, LO = 0.25, 0.05


def strike_stats(F, dt):
    off_min = int(0.08 / dt)
    win = int(0.06 / dt)
    peaks, rates, impulses, widths, n_td, t_td = [], [], [], [], 0, []
    for e in range(F.shape[1]):
        for k in range(F.shape[2]):
            f = F[:, e, k]
            armed, off_run = True, off_min
            for t in range(len(f)):
                if f[t] < LO:
                    off_run += 1
                    if off_run >= off_min:
                        armed = True
                else:
                    if armed and f[t] > HI:
                        armed, off_run = False, 0
                        t0 = t
                        while t0 > 0 and f[t0 - 1] >= LO:
                            t0 -= 1
                        w = f[t0:t0 + win]
                        if len(w) >= 4:
                            n_td += 1
                            peaks.append(float(w.max()))
                            rates.append(float(np.max(np.diff(w)) / dt))
                            impulses.append(float(w.sum() * dt))
                            widths.append(float((w >= 1.0).sum() * dt))
                            t_td.append(t0)
                    off_run = 0
    return peaks, rates, impulses, widths, n_td, t_td


def summarise(F, dt, label):
    peaks, rates, imps, widths, n_td, _ = strike_stats(F, dt)
    T, E, K = F.shape
    out = dict(label=label, hz=round(1 / dt), n_envs=E, n_feet=K,
               seconds_analysed=round(T * dt, 2), n_strikes=n_td,
               strikes_per_s_per_env=round(n_td / (E * T * dt), 3),
               duty=float((F >= LO).mean()))
    if n_td:
        out.update(peak_BW_med=float(np.median(peaks)),
                   peak_BW_p90=float(np.percentile(peaks, 90)),
                   peak_BW_max=float(np.max(peaks)),
                   rate_BWs_med=float(np.median(rates)),
                   rate_BWs_p90=float(np.percentile(rates, 90)),
                   rate_BWs_p25=float(np.percentile(rates, 25)),
                   impulse60ms_BWs_med=float(np.median(imps)),
                   width_above_1BW_ms_med=float(np.median(widths)) * 1000.0)
    out['mean_total_BW'] = float(F.sum(axis=2).mean())
    return out


try:
    import numpy as np
    import onnxruntime as rt
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})
    import omni.usd
    from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema
    from isaacsim.core.api import World
    from isaacsim.core.prims import Articulation, RigidPrim
    from author_loop_usd import read_connects

    C = json.load(open(CONTRACT))
    act_names = C['action_joint_names']            # 12, action order
    obs_names = C['obs_joint_names']               # 16, observation order
    mj_names = C['joint_names']                    # 24 mjlab DOFs
    q0_all = C['default_q']
    kp = np.array([C['gains_sw'][n]['kp'] for n in act_names])
    kd = np.array([C['gains_sw'][n]['kd'] for n in act_names])
    frc = np.array([abs(C['gains'][n]['forcerange'][1]) for n in act_names])
    tn_w = {f: np.array([w for w, _ in p]) for f, p in C['tn_curves'].items()}
    tn_t = {f: np.array([t for _, t in p]) for f, p in C['tn_curves'].items()}
    fam_of = [C['joint_family'][n] for n in act_names]

    def tn_clamp_vec(tau, omega):
        out = np.empty_like(tau)
        for i, fam in enumerate(fam_of):
            peak = tn_t[fam][0]
            hi = np.interp(omega[i], tn_w[fam], tn_t[fam]) if omega[i] >= 0 else peak
            lo = -(np.interp(-omega[i], tn_w[fam], tn_t[fam]) if omega[i] < 0 else peak)
            out[i] = min(max(tau[i], lo), hi)
        return out

    # the contract stores the scale as the cfg's {pattern: value} dict; mjlab resolves it per
    # joint, so a single value is only safe if every pattern carries the same one - assert it
    # rather than assume, because a per-joint scale would silently mis-drive the cranks.
    if isinstance(C['action_scale'], (int, float)):
        scale = float(C['action_scale'])
    else:
        vals = set(round(float(v), 9) for v in C['action_scale'].values())
        if len(vals) != 1:
            raise RuntimeError(f'per-joint action scale {C["action_scale"]} is not uniform')
        scale = vals.pop()
    decim = C['decimation']
    dt_phys, dt_ctrl = C['physics_dt'], C['step_dt']
    sess = rt.InferenceSession(ONNX)
    res['obs_dim_expected'] = C['obs_dim']
    res['onnx_io'] = [[i.name, list(i.shape)] for i in sess.get_inputs()] + \
                     [[o.name, list(o.shape)] for o in sess.get_outputs()]

    ctx = omni.usd.get_context()
    ctx.open_stage(USD)
    world = World(stage_units_in_meters=1.0, physics_dt=dt_phys, rendering_dt=1 / 25)
    world.scene.add_default_ground_plane(static_friction=1.0, dynamic_friction=1.0,
                                         restitution=0.0)
    stage = ctx.get_stage()
    root = str(stage.GetDefaultPrim().GetPath()) if stage.GetDefaultPrim() else '/robot'
    res['robot_root'] = root

    ground = None
    for p in stage.Traverse():
        s = p.GetPath().pathString
        if s.startswith('/World/defaultGroundPlane') and p.HasAPI(UsdPhysics.CollisionAPI):
            ground = s
            break
    if ground is None:
        raise RuntimeError('ground collider not found under /World/defaultGroundPlane')
    res['ground_collider'] = ground

    # --- solver iterations, authored before world.reset() (when omni.physx parses the stage) --
    K = {'sweep_tag': TAG}
    rows = []
    for p in stage.TraverseAll():
        if p.HasAPI(UsdPhysics.ArticulationRootAPI):
            a = PhysxSchema.PhysxArticulationAPI.Apply(p)
            pi = a.CreateSolverPositionIterationCountAttr()
            vi = a.CreateSolverVelocityIterationCountAttr()
            rows.append(dict(path=p.GetPath().pathString, was=[pi.Get(), vi.Get()]))
            pi.Set(ITERS[0]); vi.Set(ITERS[1])
    K['solver_iterations'] = dict(set_to=ITERS, prims=rows)
    res['knobs'] = K

    # --- the four loop closures: anchor pairs, so their world separation can be watched --------
    loops = read_connects(MJCF)
    bodies = {p.GetName(): p.GetPath().pathString for p in stage.Traverse()
              if p.HasAPI(UsdPhysics.RigidBodyAPI)}
    missing_b = sorted({c[k] for c in loops for k in ('body0', 'body1')} - set(bodies))
    if missing_b:
        raise RuntimeError(f'USD has no rigid body for loop members {missing_b} - wrong URDF?')
    loop_bodies = sorted({bodies[c['body0']] for c in loops} | {bodies[c['body1']] for c in loops})
    res['loop_joints'] = [dict(name=c['name'], body0=c['body0'], body1=c['body1'],
                               localPos0=c['localPos0'], localPos1=c['localPos1'])
                          for c in loops]
    # the loop-closure prims the USD actually carries (authored by author_loop_usd.py)
    res['loop_prims_in_usd'] = [p.GetPath().pathString for p in stage.Traverse()
                                if p.IsA(UsdPhysics.SphericalJoint)]
    if len(res['loop_prims_in_usd']) != len(loops):
        raise RuntimeError(f'USD has {len(res["loop_prims_in_usd"])} spherical joints, '
                           f'MJCF has {len(loops)} connects - run author_loop_usd.py first')

    art = Articulation(root, name='robot')
    by_name = {p.GetName(): p.GetPath().pathString for p in stage.Traverse()
               if p.HasAPI(UsdPhysics.RigidBodyAPI)}
    missing = [f for f in FEET if f not in by_name]
    if missing:
        raise RuntimeError(f'foot links not found as rigid bodies: {missing}')
    foot_paths = [by_name[f] for f in FEET]
    feet = RigidPrim(prim_paths_expr=foot_paths, name='feet', track_contact_forces=True,
                     contact_filter_prim_paths_expr=[[ground] for _ in foot_paths],
                     disable_stablization=True)
    probe = RigidPrim(prim_paths_expr=loop_bodies, name='loop_bodies')

    world.reset()
    art.initialize()
    feet.initialize()
    probe.initialize()
    from isaacsim.core.simulation_manager import SimulationManager
    cv = feet._contact_view
    if cv.num_shapes is None:
        cv.initialize(SimulationManager.get_physics_sim_view())
    res['contact_view'] = dict(num_shapes=int(cv.num_shapes), num_filters=int(cv.num_filters))
    try:
        K['runtime_solver_iters'] = [
            int(np.asarray(art.get_solver_position_iteration_counts()).flatten()[0]),
            int(np.asarray(art.get_solver_velocity_iteration_counts()).flatten()[0])]
    except Exception as e:
        K['runtime_solver_iters_err'] = f'{type(e).__name__}: {e}'
    if K.get('runtime_solver_iters') != ITERS:
        raise RuntimeError(f'PhysX ingested {K.get("runtime_solver_iters")}, asked for {ITERS}')

    isaac_names = list(art.dof_names)
    n_all = len(isaac_names)
    res['dof_names'] = isaac_names
    miss_dof = [n for n in mj_names if n not in isaac_names]
    if miss_dof:
        raise RuntimeError(f'USD is missing DOFs the mjlab model has: {miss_dof}')
    a2i = np.array([isaac_names.index(n) for n in act_names])       # action -> isaac dof
    o2i = np.array([isaac_names.index(n) for n in obs_names])       # obs    -> isaac dof
    m2i = np.array([isaac_names.index(n) for n in mj_names])
    upper = [i for i, n in enumerate(isaac_names) if n not in mj_names]
    res['upper_body_dofs'] = [isaac_names[i] for i in upper]

    art.set_gains(kps=np.zeros((1, n_all)), kds=np.zeros((1, n_all)))
    arma = np.zeros(n_all); visc = np.zeros(n_all); fric = np.zeros(n_all)
    for jn, prop in C['dof_props'].items():
        i = isaac_names.index(jn)
        arma[i] = prop['armature']; visc[i] = prop['damping']; fric[i] = prop['frictionloss']
    art.set_armatures(arma.reshape(1, -1))
    res['dof_props_injected'] = dict(
        n=len(C['dof_props']),
        armature_range=[float(arma[m2i].min()), float(arma[m2i].max())],
        note='URDF carries none of these; without armature the software PD is unstable at 200 Hz')

    masses = np.asarray(art.get_body_masses()).flatten()
    M = float(masses.sum())
    BW = M * 9.81
    res.update(total_mass_kg=round(M, 5), BW_N=round(BW, 3),
               mjlab_mass_kg=C['total_mass_kg'],
               mass_delta_g=round(1000 * (M - C['total_mass_kg']), 2),
               n_bodies=len(list(art.body_names)))

    # --- the reset pose: ALL 29 joints, or the closure tears open (IsaacLab #1250) -------------
    q_init = np.zeros(n_all)
    for jn, q in q0_all.items():
        q_init[isaac_names.index(jn)] = q
    abd = np.radians(-ARM_ABD)
    upper_target = {}
    for i in upper:
        n = isaac_names[i]
        upper_target[n] = abd if n.endswith('_shoulder_roll_joint') else 0.0
        q_init[i] = upper_target[n]
    res['upper_body_hold_rad'] = upper_target
    res['arm_abduction_deg'] = ARM_ABD
    spawn_z = C['spawn_base_z']
    res['spawn_base_z'] = spawn_z

    def reset_robot():
        art.set_joint_positions(q_init.reshape(1, -1))
        art.set_joint_velocities(np.zeros((1, n_all)))
        art.set_world_poses(positions=[[0.0, 0.0, spawn_z]],
                            orientations=[[1.0, 0.0, 0.0, 0.0]])
        art.set_velocities(np.zeros((1, 6)))

    def quat_rot(q, v):
        w, x, y, z = q
        u = np.array([x, y, z])
        return v + 2.0 * (np.cross(u, np.cross(u, v)) + w * np.cross(u, v))

    def quat_rot_inv(q, v):
        w, x, y, z = q
        u = np.array([x, y, z])
        return v + 2.0 * np.cross(u, np.cross(u, v) - w * v)

    where = {p: i for i, p in enumerate(list(probe.prim_paths))}
    lp0 = np.array([loops[i]['localPos0'] for i in range(len(loops))])
    lp1 = np.array([loops[i]['localPos1'] for i in range(len(loops))])
    i0 = [where[bodies[c['body0']]] for c in loops]
    i1 = [where[bodies[c['body1']]] for c in loops]
    loop_names = [c['name'] for c in loops]
    res['loop_names'] = loop_names

    def loop_drift_mm():
        pos, quat = probe.get_world_poses()
        pos = np.asarray(pos); quat = np.asarray(quat)
        out = np.empty(len(loops))
        for k in range(len(loops)):
            a = pos[i0[k]] + quat_rot(quat[i0[k]], lp0[k])
            b = pos[i1[k]] + quat_rot(quat[i1[k]], lp1[k])
            out[k] = np.linalg.norm(a - b) * 1e3
        return out

    def read_contacts():
        net = np.asarray(feet.get_net_contact_forces(dt=dt_phys)).reshape(len(FEET), 3)
        mat = np.asarray(feet.get_contact_force_matrix(dt=dt_phys)).reshape(len(FEET), -1, 3)
        return net, mat.sum(axis=1)

    def efforts(q_t):
        """The command this script applies: policy PD + T-N clamp on the 12 motors, the model's
        own viscous+Coulomb friction on every DOF, a stiff hold on the 5 welded upper joints."""
        q_all = np.asarray(art.get_joint_positions()).flatten()
        dq_all = np.asarray(art.get_joint_velocities()).flatten()
        tau = np.zeros(n_all)
        raw = np.clip(kp * (q_t - q_all[a2i]) - kd * dq_all[a2i], -frc, frc)
        tau[a2i] = tn_clamp_vec(raw, dq_all[a2i])
        tau -= visc * dq_all + fric * np.tanh(dq_all / 0.05)
        for i in upper:
            tau[i] = 400.0 * (q_init[i] - q_all[i]) - 20.0 * dq_all[i]
        art.set_joint_efforts(tau.reshape(1, -1))
        return tau, q_all, dq_all

    def measured():
        try:
            return np.asarray(art.get_measured_joint_efforts()).flatten()
        except Exception:
            return np.full(n_all, np.nan)

    # ---- calibration 1: the force convention -------------------------------------------------
    reset_robot()
    conv = None
    q0_act = np.array([q0_all[n] for n in act_names])
    for _ in range(int(0.6 / dt_phys)):
        efforts(q0_act)
        world.step(render=False)
        f_force = np.asarray(feet.get_net_contact_forces(dt=dt_phys)).reshape(len(FEET), 3)
        f_imp = np.asarray(feet.get_net_contact_forces(dt=1.0)).reshape(len(FEET), 3)
        if np.abs(f_force[:, 2]).sum() > 1.0 and conv is None:
            conv = dict(force_N=round(float(f_force[:, 2].sum()), 4),
                        impulse_Ns=round(float(f_imp[:, 2].sum()), 6),
                        ratio=round(float(f_force[:, 2].sum() / max(1e-12, f_imp[:, 2].sum())), 2),
                        expected_ratio=round(1 / dt_phys, 2))
    res['dt_convention_check'] = conv

    # ---- calibration 2: the loop closes at the spawn pose, before any contact -----------------
    reset_robot()
    d_spawn = loop_drift_mm()
    res['loop_drift_at_spawn_mm'] = {n: round(float(v), 6) for n, v in zip(loop_names, d_spawn)}
    json.dump(res, open(RES, 'w'), indent=1)

    # ---- the gait -----------------------------------------------------------------------------
    reset_robot()
    last_act = np.zeros(12, dtype=np.float32)
    g_w = np.array([0.0, 0.0, -1.0])
    steps = int(SECONDS / dt_ctrl)
    Fbuf, Fzbuf, devbuf = [], [], []
    TAUa, TAUm, DRIFT, QB, DQB, QT = [], [], [], [], [], []
    log = {'t': [], 'base_z': [], 'vx_b': [], 'fell': False}

    for k in range(steps):
        pos, quat = art.get_world_poses()
        quat = np.asarray(quat).flatten()
        vel = np.asarray(art.get_velocities()).flatten()
        ang_b = quat_rot_inv(quat, vel[3:6])
        grav_b = quat_rot_inv(quat, g_w)
        q_all = np.asarray(art.get_joint_positions()).flatten()
        dq_all = np.asarray(art.get_joint_velocities()).flatten()
        q_rel = q_all[o2i] - np.array([q0_all[n] for n in obs_names])
        cmd_now = [CMD[0] * min(1.0, k * dt_ctrl / 2.0), CMD[1], CMD[2]]
        obs = np.concatenate([ang_b, grav_b, q_rel, dq_all[o2i], last_act,
                              cmd_now]).astype(np.float32)
        if k == 0:
            res['obs_dim_built'] = int(obs.size)
            if obs.size != C['obs_dim']:
                raise RuntimeError(f'obs is {obs.size}, contract says {C["obs_dim"]}')
        act = sess.run(None, {'obs': obs.reshape(1, -1)})[0].flatten()
        if k < 3:
            res.setdefault('diag', []).append(dict(
                k=k, base_z=round(float(np.asarray(pos).flatten()[2]), 4),
                grav_b=[round(float(v), 4) for v in grav_b],
                act=[round(float(v), 3) for v in act]))
        last_act = act.copy()
        q_t = q0_act + scale * act

        for _ in range(decim):
            tau, qa, dqa = efforts(q_t)
            world.step(render=False)
            net, mat = read_contacts()
            Fbuf.append(np.linalg.norm(net, axis=1))
            Fzbuf.append(net[:, 2])
            devbuf.append(float(np.abs(mat - net).max()))
            TAUa.append(tau[m2i].copy())
            TAUm.append(measured()[m2i])
            DRIFT.append(loop_drift_mm())
            QB.append(qa[m2i].copy())
            DQB.append(dqa[m2i].copy())
            QT.append(q_t.copy())

        pos_q = art.get_world_poses()
        pos = np.asarray(pos_q[0]).flatten()
        vb = quat_rot_inv(np.asarray(pos_q[1]).flatten(),
                          np.asarray(art.get_velocities()).flatten()[:3])
        log['t'].append(round(k * dt_ctrl, 3))
        log['base_z'].append(round(float(pos[2]), 4))
        log['vx_b'].append(round(float(vb[0]), 4))
        if pos[2] < 0.45:
            log['fell'] = True
            break

    F = np.asarray(Fbuf) / BW
    Fz = np.asarray(Fzbuf) / BW
    TAUa = np.asarray(TAUa); TAUm = np.asarray(TAUm); DRIFT = np.asarray(DRIFT)
    QB = np.asarray(QB); DQB = np.asarray(DQB); QT = np.asarray(QT)
    w0 = int(WARM / dt_phys)
    Fa = F[w0:][:, None, :]
    vx = np.array(log['vx_b'][int(2.0 / dt_ctrl):])
    res.update(fell=log['fell'], sim_seconds=log['t'][-1] if log['t'] else 0,
               vx_mean=float(vx.mean()) if len(vx) else None,
               vx_err=float(np.mean(np.abs(vx - CMD[0]))) if len(vx) else None,
               base_z_mean=float(np.mean(log['base_z'])),
               filter_check=dict(max_abs_dev_N=round(float(np.max(devbuf)), 4)))
    res['support_check'] = dict(
        mean_total_Fz_BW=round(float(Fz[w0:].sum(axis=1).mean()), 4),
        note='time-average vertical GRF over the analysed window; must be 1.000 BW')
    res['isaac'] = summarise(Fa, dt_phys, f'IsaacSim AB (PhysX {ITERS[0]}/{ITERS[1]}, 1 env, no DR)')

    # ---- joint torque statistics, the quantity the load study wants --------------------------
    def tstats(A, names_):
        out = {}
        for i, n in enumerate(names_):
            a = A[w0:, i]
            if not np.all(np.isfinite(a)):
                a = a[np.isfinite(a)]
            if a.size == 0:
                continue
            out[n] = dict(rms=round(float(np.sqrt(np.mean(a ** 2))), 4),
                          p99=round(float(np.percentile(np.abs(a), 99)), 4),
                          p95=round(float(np.percentile(np.abs(a), 95)), 4),
                          max=round(float(np.abs(a).max()), 4),
                          mean=round(float(a.mean()), 4))
        return out
    res['torque_applied'] = tstats(TAUa, mj_names)
    res['torque_measured'] = tstats(TAUm, mj_names)
    res['torque_note'] = ('applied = this script\'s PD+T-N+friction command; measured = '
                          'Articulation.get_measured_joint_efforts(), the DOF force PhysX '
                          'resolved. On the passive ankle/rod hinges the applied column is '
                          'friction only, so measured-minus-applied there IS the loop transmission.')

    # ---- loop drift under dynamic load -------------------------------------------------------
    D = DRIFT[w0:]
    _, _, _, _, _, t_td = strike_stats(Fa, dt_phys)
    win = int(0.06 / dt_phys)
    td_slices = [slice(t, min(t + win, D.shape[0])) for t in t_td]
    d_land = np.concatenate([D[s] for s in td_slices]) if td_slices else D
    res['loop_drift_mm'] = dict(
        per_joint={n: dict(mean=round(float(D[:, i].mean()), 6),
                           p99=round(float(np.percentile(D[:, i], 99)), 6),
                           max=round(float(D[:, i].max()), 6))
                   for i, n in enumerate(loop_names)},
        all_mean=round(float(D.mean()), 6), all_p99=round(float(np.percentile(D, 99)), 6),
        all_max=round(float(D.max()), 6),
        landing_window_max=round(float(d_land.max()), 6),
        landing_window_p99=round(float(np.percentile(d_land, 99)), 6),
        n_landing_windows=len(td_slices),
        static_reference_mm=0.0003,
        note='world distance between each closure joint\'s two anchor points, mm')

    # ---- the MuJoCo side, recomputed with THIS code so the detector is identical --------------
    try:
        d = np.load(MJ_NPZ)
        Fm = d['F'].astype(np.float64)
        dtm = float(d['dt'])
        mj = summarise(Fm, dtm, 'MuJoCo mjlab AB (24 envs, no DR)')
        res['mujoco'] = mj
        res['mujoco_published'] = json.load(open(MJ_JSON))
        rows = []
        for key, unit in [('peak_BW_med', 'BW'), ('peak_BW_p90', 'BW'), ('peak_BW_max', 'BW'),
                          ('rate_BWs_med', 'BW/s'), ('rate_BWs_p90', 'BW/s'),
                          ('impulse60ms_BWs_med', 'BW*s'), ('width_above_1BW_ms_med', 'ms'),
                          ('strikes_per_s_per_env', '1/s/env'), ('duty', '-'),
                          ('mean_total_BW', 'BW')]:
            a, b = res['isaac'].get(key), mj.get(key)
            rows.append(dict(metric=key, unit=unit,
                             isaac=None if a is None else round(a, 4),
                             mujoco=None if b is None else round(b, 4),
                             ratio=None if not a or not b else round(a / b, 3),
                             pct_diff=None if not a or not b else round(100 * (a / b - 1), 1)))
        res['comparison'] = rows
    except Exception as e:
        res['mujoco_error'] = f'{type(e).__name__}: {e}'

    np.savez_compressed(TRACE, F_BW=F.astype(np.float32), Fz_BW=Fz.astype(np.float32),
                        tau_applied=TAUa.astype(np.float32),
                        tau_measured=TAUm.astype(np.float32),
                        loop_drift_mm=DRIFT.astype(np.float32),
                        q=QB.astype(np.float32), dq=DQB.astype(np.float32),
                        q_target=QT.astype(np.float32),
                        dt=dt_phys, BW_N=BW, warm_s=WARM, feet=np.array(FEET),
                        dof_names=np.array(mj_names), act_names=np.array(act_names),
                        loop_names=np.array(loop_names), iters=np.array(ITERS),
                        t_ctrl=np.array(log['t']), base_z=np.array(log['base_z']),
                        vx_b=np.array(log['vx_b']))
    res['ok'] = True
    res['trace_npz'] = TRACE
    json.dump(res, open(RES, 'w'), indent=1)
    app.close()
except Exception as e:
    import traceback
    res.update(error=f'{type(e).__name__}: {e}', tb=traceback.format_exc()[-2500:])
    json.dump(res, open(RES, 'w'), indent=1)
