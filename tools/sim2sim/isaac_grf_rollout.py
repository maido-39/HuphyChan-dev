"""Ground reaction forces in IsaacSim, measured the same way MuJoCo measures them.

This is `isaac_policy_rollout.py` with an instrument bolted on: the same bundleD1_RP policy,
the same 50 Hz / 200 Hz control stack read from the contract, plus a per-physics-substep
record of the contact force under each foot. Those traces then go through the SAME strike
detector as `tools/robot_model/loop_tests/impact_probe_multi.py`, so the Isaac and MuJoCo
numbers can be put in one table without an asterisk on the detector.

WHICH CONTACT API, AND WHY
--------------------------
IsaacSim 5.0 offers three ways to get a contact force headless. Only one of them is both
correct and fast enough to sample every physics substep:

  1. `isaacsim.sensors.physics.ContactSensor` - the per-prim Isaac sensor. It works headless,
     but it is a USD prim per measurement point driven by the contact-report callback, it
     reports a scalar magnitude on its own (sensor-period) schedule rather than the physics
     substep, and reading N of them is N python round trips per step. Wrong sampling
     semantics for a loading-RATE measurement, which lives or dies on the 5 ms grid.
  2. Articulation link "contact force reporting" - there is no such call. `Articulation`
     exposes `get_measured_joint_forces()`, which is the JOINT REACTION wrench (what the
     ankle joint carries), not the ground force under the sole. Related but not the same
     quantity: it excludes nothing distal of the joint and includes the foot's own inertia.
  3. **RigidContactView, reached through `isaacsim.core.prims.RigidPrim(...,
     track_contact_forces=True)`** - the PhysX tensor API. One batched call returns the net
     contact impulse on every requested body for the substep just simulated; divide by the
     physics dt and it is a force in newtons. This is what IsaacLab's own ContactSensor uses.

So: **RigidPrim / RigidContactView**, `get_net_contact_forces(dt=physics_dt)`, read
immediately after each `world.step()` - the exact place mjlab's probe reads its own sensor
(inside the `sim.step` hook), so both engines sample the same instant of the same substep.

Two things make that number trustworthy rather than merely available, and both are asserted
in the output JSON rather than assumed:
  * `support_check`: over the whole analysed window the base neither rises nor falls, so the
    time-average vertical ground force MUST be exactly one body weight. It measures 1.0003 BW.
    This is the calibration that carries the result - it is an identity, not an argument.
  * `dt_convention_check`: the same contact read as a force and as an impulse; the ratio has
    to be 1/dt. If it were not, every number here would be wrong by a factor of 200.
  * `settle_check`: a coarse weight check in the first 0.3 s of a joint-space hold. It is NOT
    a static stand - see the note at the call site.
  * `filter_check`: the view is also built with `contact_filter_prim_paths_expr` pointing at
    the ground collider, so `get_contact_force_matrix()` gives the foot-vs-GROUND force
    specifically. It is compared with the net force every substep. They agree because
    self-collision is off and the ground is the only other body - but that is a fact about
    this scene, and it is now a measured fact.

MODEL: this runs `pygmalion_v3_printed` (35.3475 kg), NOT the v4 build the earlier tracking
rollout used. bundleD1_RP trained on v3 and the MuJoCo GRF reference was measured on v3; a
4 kg mass difference is not something to normalise away in a load study. 1 BW = 346.76 N on
both sides. Pass a different USD as argv[1] to check the mass sensitivity.

Everything is written to JSON BEFORE app.close(), because close() hard-exits and Kit eats
stdout - the same trap the other scripts in this directory document.

  OMNI_KIT_ACCEPT_EULA=YES ~/isaacsim_venv/bin/python3 tools/sim2sim/isaac_grf_rollout.py \
      [usd] [seconds]
"""
import json
import os
import sys

os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
USD = sys.argv[1] if len(sys.argv) > 1 else '/home/syaro/pyg_fea/usd/pygmalion_v3_printed.usd'
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0
ONNX = (f'{REPO}/mujoco-sim/mjlab/logs/rsl_rl/pygmalion_velocity/'
        '2026-08-26_15-45-16_bundleD1_RP/2026-08-26_15-45-16_bundleD1_RP.onnx')
CONTRACT = '/home/syaro/pyg_fea/work/rp_policy_contract.json'
TAG = os.path.splitext(os.path.basename(USD))[0]
RES = f'/home/syaro/pyg_fea/work/isaac_grf_{TAG}.json'
TRACE = f'/home/syaro/pyg_fea/work/isaac_grf_{TAG}_traces.npz'
# the MuJoCo side of the table: 200 Hz raw traces, 24 envs, DR off, already in BW
MJ_NPZ = '/home/syaro/pyg_fea/work/impact_multi_nodr/bundleD1_RP_raw.npz'
MJ_JSON = '/home/syaro/pyg_fea/work/impact_multi_nodr/bundleD1_RP.json'
CMD = [1.6, 0.0, 0.0]
WARM = 3.0                 # seconds dropped before statistics - same as the MuJoCo probe
FEET = ['L_foot_link', 'R_foot_link']
res = {'ok': False, 'usd': USD, 'seconds_requested': SECONDS}


# --- strike detection: lifted verbatim from impact_probe_multi.py --------------------------
# Schmitt trigger (arm below 0.05 BW, fire above 0.25 BW), 80 ms minimum off-time, 60 ms
# post-touchdown window, onset found by backing up to the last sample below LO. A single
# threshold chatters: soft contact plus the solver crosses 0.05 BW many times per real
# strike. Duplicated rather than imported because that file lives in the mjlab venv.
HI, LO = 0.25, 0.05
def strike_stats(F, dt):
    """F: [T, E, K] contact force magnitude in BW.

    peaks / rates are the probe's two published quantities. impulses and widths are ADDED
    here (they cost nothing and change no published number) because they are what separates
    "the robot lands harder" from "the engine spreads the same landing over fewer samples":
    the vertical impulse of a stride is fixed by the gait and the mass, so if two engines
    disagree on peak but agree on impulse, the difference is contact stiffness, not gait.
    """
    off_min = int(0.08 / dt)
    win = int(0.06 / dt)
    peaks, rates, impulses, widths, n_td = [], [], [], [], 0
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
                    off_run = 0
    return peaks, rates, impulses, widths, n_td


def summarise(F, dt, label):
    peaks, rates, imps, widths, n_td = strike_stats(F, dt)
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
    from pxr import Usd, UsdPhysics
    from isaacsim.core.api import World
    from isaacsim.core.prims import Articulation, RigidPrim

    C = json.load(open(CONTRACT))
    pol_names = C['joint_names']
    q0 = np.array([C['default_q'][n] for n in pol_names])
    kp = np.array([C['gains_sw'][n]['kp'] for n in pol_names])
    kd = np.array([C['gains_sw'][n]['kd'] for n in pol_names])
    frc = np.array([abs(C['gains'][n]['forcerange'][1]) for n in pol_names])
    tn_w, tn_t = {}, {}
    for fam, pts in C['tn_curves'].items():
        tn_w[fam] = np.array([w for w, _ in pts])
        tn_t[fam] = np.array([t for _, t in pts])
    fam_of = [C['joint_family'][n] for n in pol_names]

    def tn_clamp_vec(tau, omega):
        out = np.empty_like(tau)
        for i, fam in enumerate(fam_of):
            peak = tn_t[fam][0]
            hi = np.interp(omega[i], tn_w[fam], tn_t[fam]) if omega[i] >= 0 else peak
            lo = -(np.interp(-omega[i], tn_w[fam], tn_t[fam]) if omega[i] < 0 else peak)
            out[i] = min(max(tau[i], lo), hi)
        return out
    scale, decim = 0.25, C['decimation']
    dt_phys, dt_ctrl = C['physics_dt'], C['step_dt']

    sess = rt.InferenceSession(ONNX)

    ctx = omni.usd.get_context()
    ctx.open_stage(USD)                       # BEFORE World, or the stage is replaced
    world = World(stage_units_in_meters=1.0, physics_dt=dt_phys, rendering_dt=1 / 25)
    world.scene.add_default_ground_plane(static_friction=1.0, dynamic_friction=1.0,
                                         restitution=0.0)
    stage = ctx.get_stage()
    # The URDF importer puts ArticulationRootAPI on base_link, one level BELOW the robot
    # Xform, and hangs every link off the robot Xform as a sibling of base_link. So the
    # articulation is wrapped at the robot prim (as in isaac_policy_rollout.py) while the
    # feet are found by NAME - guessing the path put them under base_link and the view
    # constructor rejected it.
    root = str(stage.GetDefaultPrim().GetPath()) if stage.GetDefaultPrim() else '/' + TAG
    art_root = None
    for p in stage.Traverse():
        if p.HasAPI(UsdPhysics.ArticulationRootAPI):
            art_root = p.GetPath().pathString
            break
    res['robot_root'] = root
    res['articulation_root_api_on'] = art_root
    # the ground collider, found rather than hardcoded: add_default_ground_plane() has moved
    # its collision prim between releases
    ground = None
    for p in stage.Traverse():
        s = p.GetPath().pathString
        if s.startswith('/World/defaultGroundPlane') and p.HasAPI(UsdPhysics.CollisionAPI):
            ground = s
            break
    res['ground_collider'] = ground

    if ground is None:
        raise RuntimeError('ground collider not found under /World/defaultGroundPlane')
    art = Articulation(root, name='robot')
    by_name = {}
    for p in stage.Traverse():
        if p.HasAPI(UsdPhysics.RigidBodyAPI):
            by_name[p.GetName()] = p.GetPath().pathString
    missing = [f for f in FEET if f not in by_name]
    if missing:
        raise RuntimeError(f'foot links not found as rigid bodies: {missing}; '
                           f'have {sorted(by_name)}')
    foot_paths = [by_name[f] for f in FEET]
    # RigidPrim applies PhysxContactReportAPI (threshold 0) to these prims in its constructor,
    # so it MUST be built before world.reset() creates the physics view.
    #
    # The filter argument HAS to be a list of lists, one per sensor pattern. Measured
    # (tools/sim2sim -> work/contact_api_probe.json): with two sensor paths and either no
    # filter or a flat one-element filter, PhysX silently returns a null contact-view backend
    # and every read dies inside resolve_indices with a NoneType error that names neither the
    # cause nor the fix. [[ground]] * n_feet works. Filtering on the ground XFORM instead of
    # its CollisionPlane also "works" but reports 0 N forever - the filter must name the
    # collider prim, which is why it is discovered rather than hardcoded.
    feet = RigidPrim(prim_paths_expr=foot_paths, name='feet',
                     track_contact_forces=True,
                     contact_filter_prim_paths_expr=[[ground] for _ in foot_paths],
                     disable_stablization=True)
    world.reset()
    art.initialize()
    feet.initialize()
    # RigidPrim.initialize() is a no-op once its own physics handle is valid, and on this
    # build that leaves the CONTACT view uninitialised (num_shapes None -> every read dies in
    # resolve_indices). Initialise it explicitly against the same simulation view.
    from isaacsim.core.simulation_manager import SimulationManager
    cv = feet._contact_view
    if cv.num_shapes is None:
        cv.initialize(SimulationManager.get_physics_sim_view())
    res['contact_view'] = dict(num_shapes=int(cv.num_shapes), num_filters=int(cv.num_filters))
    res['foot_paths'] = list(feet.prim_paths)

    isaac_names = list(art.dof_names)
    n_all = len(isaac_names)
    pol2isaac = np.array([isaac_names.index(n) for n in pol_names])
    upper = [i for i, n in enumerate(isaac_names) if n not in pol_names]

    art.set_gains(kps=np.zeros((1, n_all)), kds=np.zeros((1, n_all)))
    arma = np.zeros(n_all); visc = np.zeros(n_all); fric = np.zeros(n_all)
    for jn, prop in C['dof_props'].items():
        i = isaac_names.index(jn)
        arma[i] = prop['armature']; visc[i] = prop['damping']; fric[i] = prop['frictionloss']
    art.set_armatures(arma.reshape(1, -1))

    masses = np.asarray(art.get_body_masses()).flatten()
    M = float(masses.sum())
    BW = M * 9.81
    res.update(total_mass_kg=round(M, 4), BW_N=round(BW, 2),
               body_names=list(art.body_names))

    q_init = np.zeros(n_all)
    q_init[pol2isaac] = q0
    spawn_z = C.get('spawn_base_z', 0.9085)

    def reset_robot():
        art.set_joint_positions(q_init.reshape(1, -1))
        art.set_joint_velocities(np.zeros((1, n_all)))
        art.set_world_poses(positions=[[0.0, 0.0, spawn_z]],
                            orientations=[[1.0, 0.0, 0.0, 0.0]])
        art.set_velocities(np.zeros((1, 6)))

    def pd_hold(q_t, steps, stiff=False):
        """PD to a fixed joint target for `steps` physics substeps (no policy).

        stiff=True uses the weld gains (400/20) on every joint instead of the policy's own.
        The static calibration needs a RIGID robot standing on two feet; with the trained
        gains the ankle (kp 28.5) cannot hold the crouch open-loop and the robot topples in
        under a second - measured: base_z fell to 0.091 m and the feet read 6 N of the 347 N
        they should carry. That was the instrument reporting a fallen robot correctly, not a
        contact-force bug, but it is useless as a calibration.
        """
        for _ in range(steps):
            q_all = np.asarray(art.get_joint_positions()).flatten()
            dq_all = np.asarray(art.get_joint_velocities()).flatten()
            tau = np.zeros(n_all)
            if stiff:
                tau = 400.0 * (q_init - q_all) - 20.0 * dq_all
            else:
                raw = np.clip(kp * (q_t - q_all[pol2isaac]) - kd * dq_all[pol2isaac], -frc, frc)
                tau[pol2isaac] = tn_clamp_vec(raw, dq_all[pol2isaac])
                tau -= visc * dq_all + fric * np.tanh(dq_all / 0.05)
                for i in upper:
                    tau[i] = 400.0 * (0.0 - q_all[i]) - 20.0 * dq_all[i]
            art.set_joint_efforts(tau.reshape(1, -1))
            world.step(render=False)

    def read_contacts():
        """(per-foot net force [2,3] N, per-foot force against the GROUND [2,3] N).

        dt divides: the view accumulates a contact IMPULSE over the substep, and passing
        dt=physics_dt turns it into newtons. Verified on this build - the same contact read
        with dt=1.0 gave 0.8971 N*s where dt=0.005 gave 179.43 N.
        """
        net = np.asarray(feet.get_net_contact_forces(dt=dt_phys)).reshape(len(FEET), 3)
        mat = np.asarray(feet.get_contact_force_matrix(dt=dt_phys)).reshape(len(FEET), -1, 3)
        return net, mat.sum(axis=1)

    # ---- calibration 1: the force convention ----------------------------------------------
    # The view accumulates a contact IMPULSE per substep; `dt` divides it. Read the SAME
    # contact both ways and check the ratio is exactly 1/dt. If this is ever wrong the whole
    # study is off by a factor of 200 and nothing downstream would look obviously odd.
    reset_robot()
    conv = None
    for _ in range(int(0.6 / dt_phys)):
        pd_hold(q0, 1, stiff=True)
        f_force = np.asarray(feet.get_net_contact_forces(dt=dt_phys)).reshape(len(FEET), 3)
        f_imp = np.asarray(feet.get_net_contact_forces(dt=1.0)).reshape(len(FEET), 3)
        if np.abs(f_force[:, 2]).sum() > 1.0 and conv is None:
            conv = dict(force_N=round(float(f_force[:, 2].sum()), 4),
                        impulse_Ns=round(float(f_imp[:, 2].sum()), 6),
                        ratio=round(float(f_force[:, 2].sum() / f_imp[:, 2].sum()), 2),
                        expected_ratio=round(1 / dt_phys, 2))
    res['dt_convention_check'] = conv

    # ---- calibration 2: a short settle ----------------------------------------------------
    # NOT a proper static stand: holding JOINT angles on a floating-base biped does not hold
    # the BASE upright - there is no ankle strategy when the ankle angle is pinned, so any
    # lean grows and the robot topples in about a second (measured: base_z 0.91 -> 0.08 m,
    # feet reading 24 N of the 347 N they should carry). The first 0.3 s, before the lean
    # develops, is still a usable weight check; the base_z drift says how far to trust it.
    reset_robot()
    z0 = float(np.asarray(art.get_world_poses()[0]).flatten()[2])
    st_net, st_mat = [], []
    for k_ in range(int(0.30 / dt_phys)):
        pd_hold(q0, 1, stiff=True)
        n_, m_ = read_contacts()
        if k_ >= int(0.15 / dt_phys):
            st_net.append(n_); st_mat.append(m_)
    st_net = np.stack(st_net); st_mat = np.stack(st_mat)
    fz = st_net[..., 2].sum(axis=1)
    res['settle_check'] = dict(
        weight_N=round(BW, 2),
        sum_Fz_N_mean=round(float(fz.mean()), 2),
        sum_Fz_over_mg=round(float(fz.mean() / BW), 4),
        per_foot_Fz_N=[round(float(v), 2) for v in st_net[..., 2].mean(axis=0)],
        filtered_vs_net_max_rel=round(float(np.abs(st_mat - st_net).max()
                                            / max(1e-6, np.abs(st_net).max())), 5),
        base_z_drift_mm=round(1000 * (float(np.asarray(art.get_world_poses()[0]).flatten()[2])
                                      - z0), 2))

    # ---- the gait -------------------------------------------------------------------------
    reset_robot()
    last_act = np.zeros(12, dtype=np.float32)
    g_w = np.array([0.0, 0.0, -1.0])
    steps = int(SECONDS / dt_ctrl)

    def quat_rot_inv(q, v):
        w, x, y, z = q
        u = np.array([x, y, z])
        return v + 2.0 * np.cross(u, np.cross(u, v) - w * v)

    Fbuf = []          # [T_phys, 2] force magnitude, N
    Fzbuf = []         # [T_phys, 2] vertical component, N
    devbuf = []        # net vs ground-filtered max abs deviation, N
    log = {'t': [], 'base_z': [], 'vx_b': [], 'fell': False}
    for k in range(steps):
        pos, quat = art.get_world_poses()
        quat = np.asarray(quat).flatten()
        vel = np.asarray(art.get_velocities()).flatten()
        ang_b = quat_rot_inv(quat, vel[3:6])
        grav_b = quat_rot_inv(quat, g_w)
        q_all = np.asarray(art.get_joint_positions()).flatten()
        dq_all = np.asarray(art.get_joint_velocities()).flatten()
        q, dq = q_all[pol2isaac], dq_all[pol2isaac]

        cmd_now = [CMD[0] * min(1.0, k * dt_ctrl / 2.0), CMD[1], CMD[2]]
        obs = np.concatenate([ang_b, grav_b, q - q0, dq, last_act, cmd_now]).astype(np.float32)
        act = sess.run(None, {'obs': obs.reshape(1, -1)})[0].flatten()
        if k < 3:
            res.setdefault('diag', []).append(dict(
                k=k, base_z=round(float(np.asarray(pos).flatten()[2]), 4),
                grav_b=[round(float(v), 4) for v in grav_b],
                act=[round(float(v), 3) for v in act]))
        last_act = act.copy()
        q_t = q0 + scale * act

        for _ in range(decim):
            q_all = np.asarray(art.get_joint_positions()).flatten()
            dq_all = np.asarray(art.get_joint_velocities()).flatten()
            tau = np.zeros(n_all)
            raw = np.clip(kp * (q_t - q_all[pol2isaac]) - kd * dq_all[pol2isaac], -frc, frc)
            tau[pol2isaac] = tn_clamp_vec(raw, dq_all[pol2isaac])
            tau -= visc * dq_all + fric * np.tanh(dq_all / 0.05)
            for i in upper:
                tau[i] = 400.0 * (0.0 - q_all[i]) - 20.0 * dq_all[i]
            art.set_joint_efforts(tau.reshape(1, -1))
            world.step(render=False)
            net, mat = read_contacts()          # read AFTER the step, like the mjlab hook
            Fbuf.append(np.linalg.norm(net, axis=1))
            Fzbuf.append(net[:, 2])
            devbuf.append(float(np.abs(mat - net).max()))

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

    F = np.asarray(Fbuf) / BW                   # [T, 2] in BW
    Fz = np.asarray(Fzbuf) / BW
    w0 = int(WARM / dt_phys)
    Fa = F[w0:][:, None, :]                     # [T, 1 env, 2 feet] - the probe's layout
    vx = np.array(log['vx_b'][int(2.0 / dt_ctrl):])
    res.update(fell=log['fell'], sim_seconds=log['t'][-1] if log['t'] else 0,
               vx_mean=float(vx.mean()) if len(vx) else None,
               vx_err=float(np.mean(np.abs(vx - CMD[0]))) if len(vx) else None,
               base_z_mean=float(np.mean(log['base_z'])),
               filter_check=dict(max_abs_dev_N=round(float(np.max(devbuf)), 4),
                                 note='net contact force vs force filtered against the ground '
                                      'collider; equal => the only contact is the floor'))
    # The calibration that actually matters, and the one the static hold was a proxy for:
    # over whole strides the base neither rises nor falls on average, so the mean vertical
    # ground force MUST be one body weight. Off by 200 and the dt convention is wrong; off by
    # 13 % and the mass is the wrong model.
    res['support_check'] = dict(
        mean_total_Fz_BW=round(float(Fz[w0:].sum(axis=1).mean()), 4),
        note='time-average vertical GRF over the analysed window; must be 1.000 BW')
    isaac = summarise(Fa, dt_phys, 'IsaacSim (PhysX, 1 env, no DR)')
    res['isaac'] = isaac

    # ---- the MuJoCo side, recomputed with THIS code so the detector is identical ----------
    try:
        d = np.load(MJ_NPZ)
        Fm = d['F'].astype(np.float64)          # [T, 24, 2], already BW, warmup already cut
        dtm = float(d['dt'])
        mj = summarise(Fm, dtm, 'MuJoCo mjlab (24 envs, no DR)')
        res['mujoco'] = mj
        res['mujoco_published'] = json.load(open(MJ_JSON))
        rows = []
        for key, unit in [('peak_BW_med', 'BW'), ('peak_BW_p90', 'BW'), ('peak_BW_max', 'BW'),
                          ('rate_BWs_med', 'BW/s'), ('rate_BWs_p90', 'BW/s'),
                          ('impulse60ms_BWs_med', 'BW*s'),
                          ('width_above_1BW_ms_med', 'ms'),
                          ('strikes_per_s_per_env', '1/s/env'), ('duty', '-'),
                          ('mean_total_BW', 'BW')]:
            a, b = isaac.get(key), mj.get(key)
            rows.append(dict(metric=key, unit=unit,
                             isaac=None if a is None else round(a, 4),
                             mujoco=None if b is None else round(b, 4),
                             ratio=None if not a or not b else round(a / b, 3),
                             pct_diff=None if not a or not b else round(100 * (a / b - 1), 1)))
        res['comparison'] = rows
        # Contact models, for the record - this is the difference the table is measuring.
        # MuJoCo values read off the loaded model (mjlab xmls/pygmalion_v3_printed.xml).
        res['contact_models'] = dict(
            mujoco=dict(engine='MuJoCo (mjlab, Newton solver, 100 iters)',
                        solref=[0.02, 1.0], solimp=[0.9, 0.95, 0.001],
                        note='solref[0]=0.02 s is a 20 ms contact time constant: the impact '
                             'is spread over ~4 physics substeps by construction',
                        friction=[1.0, 0.005, 1e-4], timestep=0.005),
            isaac=dict(engine='IsaacSim 5.0 / PhysX (TGS)',
                       restitution=0.0, static_friction=1.0, dynamic_friction=1.0,
                       note='rigid contact resolved inside a single 5 ms substep; no '
                            'compliance term equivalent to solref',
                       timestep=dt_phys))
    except Exception as e:
        res['mujoco_error'] = f'{type(e).__name__}: {e}'

    np.savez_compressed(TRACE, F_BW=F.astype(np.float32), Fz_BW=Fz.astype(np.float32),
                        dt=dt_phys, BW_N=BW, warm_s=WARM, feet=np.array(FEET),
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
