# -*- coding: utf-8 -*-
"""Custom reward terms for ENERGY-efficient + TOE-loading gait (research wseyrv4mz / docs/22).

Two terms designed to be ADDED to BipedRewards for a "forefoot-rollover" experiment (transfer from a
converged flat policy so the gait is already stable -> no annealing needed; keep tracking dominant):

  * power_cot          : vel-normalized cost-of-transport reward. Rewards LOW mechanical power per
                         commanded speed -> offloads effort + improves efficiency. Velocity-normalized
                         so "stand still" is NOT a free optimum (the binding degeneracy per Adaptive
                         Energy Regularization). Use a POSITIVE weight.
  * toe_load_stance    : rewards LOADING the passive toe spring while the foot is in contact -> the only
                         gradient that makes the policy roll onto the forefoot (the toe is passive, so a
                         power term alone offloads to the KNEE, not the toe -- confirmed in stage-3).
                         Bounded [0,1] per foot and gated on contact to avoid tip-toe degeneracy.

NOT yet wired into any cfg (current runs unaffected). Wire + config-test + tune scale/weights before a
real run. See docs/22 for weights, guards, and the validation plan ([[19_toe_ablation]]).
"""

from __future__ import annotations

import torch
from isaaclab.managers import SceneEntityCfg


def power_cot(env, asset_cfg: SceneEntityCfg, command_name: str = "base_velocity",
              scale: float = 0.003, sigma: float = 1.0, eps: float = 0.1):
    """exp(-scale * sum_j |tau_j * omega_j| / (sigma*|v_cmd| + eps)).  [num_envs] in (0,1].

    asset_cfg must select the ACTUATED joints (joint_names=ACTUATED_JOINTS). Returns ~1 when the gait
    is cheap-per-speed, ~0 when wasteful. Tune `scale` so the typical value sits ~0.3-0.7 (check in a
    config-test; if it saturates near 0/1, scale is too large/small)."""
    asset = env.scene[asset_cfg.name]
    jid = asset_cfg.joint_ids
    tau = asset.data.applied_torque[:, jid]
    omega = asset.data.joint_vel[:, jid]
    power = torch.sum(torch.abs(tau * omega), dim=1)
    vcmd = torch.norm(env.command_manager.get_command(command_name)[:, :2], dim=1)
    return torch.exp(-scale * power / (sigma * vcmd + eps))


def toe_load_stance(env, toe_cfg: SceneEntityCfg, sensor_cfg: SceneEntityCfg,
                    tau_ref: float = 27.0, contact_thresh: float = 5.0, late_time: float = 0.15):
    """H1 (toe-use research wljkv3uu8): reward loading the passive toe at LATE SINGLE SUPPORT — the only
    direct gradient onto the forefoot, since the toe is passive and a power term alone offloads to the
    KNEE (stage-3). The late-single-support gate is NON-NEGOTIABLE: it prevents the static toe-curl
    degeneracy (pressing toes down without rolling). Per foot, reward clamp(|tau_toe|/tau_ref, 0,1) when:
      (this foot in contact) AND (other foot in swing = single support) AND (base moving forward)
      AND (contact age > late_time, i.e. terminal stance — used if the sensor tracks air time).
    toe_cfg selects the two toe joints, sensor_cfg the matching foot bodies in the SAME L,R order
    (verify in a config-test). Returns [num_envs] (~[0,2])."""
    asset = env.scene[toe_cfg.name]
    tau_toe = torch.abs(asset.data.applied_torque[:, toe_cfg.joint_ids])          # [E, nfoot] (L,R)
    sensor = env.scene.sensors[sensor_cfg.name]
    f = sensor.data.net_forces_w[:, sensor_cfg.body_ids, :]                        # [E, nfoot, 3]
    in_contact = torch.norm(f, dim=-1) > contact_thresh                           # [E, nfoot] bool
    other_swing = ~in_contact[:, [1, 0]]                                          # other foot not in contact
    fwd = (asset.data.root_lin_vel_b[:, 0] > 0.0).unsqueeze(1)                    # [E, 1] forward progress
    try:  # terminal-stance gate (needs track_air_time); fall back to single-support if unavailable
        late = sensor.data.current_contact_time[:, sensor_cfg.body_ids] > late_time
    except Exception:  # noqa: BLE001
        late = torch.ones_like(in_contact)
    gate = (in_contact & other_swing & late & fwd).float()                        # [E, nfoot]
    load = torch.clamp(tau_toe / tau_ref, max=1.0)                                # [E, nfoot]
    return torch.sum(load * gate, dim=1)


def forefoot_cop(env, foot_cfg: SceneEntityCfg, forefoot_cfg: SceneEntityCfg,
                 contact_thresh: float = 8.0, late_time: float = 0.15):
    """★ Rank-1 INDIRECT reward (direct-vs-indirect research whirkj8ws): reward the CoP advancing onto the
    FOREFOOT in late single support — the legitimate CAUSE that loads the passive toe. This REPLACES the
    direct toe-torque reward (toe_load_stance / H1), which is an anti-pattern: |tau_toe| = k*deflection,
    so it rewards a CORRELATE of the roll and is reward-hackable by a static toe-curl (worse here — the
    toe is over-damped so a held curl is cheap). Rewarding WHERE the foot bears load (forefoot GRF
    fraction = the roll) is far harder to game on the toe and reflects the whole-foot rollover.
    forefoot fraction = forefoot(toe_link) vertical GRF / total foot vertical GRF, gated on (foot in
    contact) AND (other foot swing) AND (forward) AND (terminal stance). foot_cfg = foot_link bodies,
    forefoot_cfg = toe_link bodies, SAME L,R order (verify in a config-test). Returns [num_envs]."""
    sensor = env.scene.sensors[foot_cfg.name]
    fz = sensor.data.net_forces_w[..., 2].abs()                                   # [E, num_bodies] |Fz|
    f_foot = fz[:, foot_cfg.body_ids]                                             # [E, nfoot] heel/plate
    f_fore = fz[:, forefoot_cfg.body_ids]                                         # [E, nfoot] forefoot
    total = f_foot + f_fore
    frac = f_fore / (total + 1e-3)                                                # forefoot CoP fraction
    in_contact = total > contact_thresh
    other_swing = ~in_contact[:, [1, 0]]
    fwd = (env.scene["robot"].data.root_lin_vel_b[:, 0] > 0.0).unsqueeze(1)
    try:
        late = sensor.data.current_contact_time[:, foot_cfg.body_ids] > late_time
    except Exception:  # noqa: BLE001
        late = torch.ones_like(in_contact)
    gate = (in_contact & other_swing & late & fwd).float()                        # [E, nfoot]
    return torch.sum(frac * gate, dim=1)


def joint_overrating_penalty(env, asset_cfg: SceneEntityCfg, rated):
    """T2 thermal/load-balancing penalty (research wyilgvpyj). Per-joint utilization hinge:
    sum_j max((|tau_j|/tau_rated_j)^2 - 1, 0) — ZERO below each joint's CONTINUOUS rating, QUADRATIC above
    (matches tau^2 heating). Normalize by EACH joint's OWN rating (load-balancing, NOT equal load) so it
    pushes load OFF an overloaded joint (our ankle_roll at 151% RMS%rated) ONTO joints with margin
    (hip/knee). Use a NEGATIVE weight. WHY this and not power_cot: power_cot sums |tau*omega| over all 14
    joints and is POWER not HEAT — a holding ankle_roll has omega~0 (~0 power) yet heats as tau^2, so
    power_cot never saw the overload. Summed over an episode this ~ the RMS-over-rating thermal load; a
    stateful EMA-thermal term (T1) is the upgrade. `rated` = continuous-rated torques aligned to
    asset_cfg.joint_ids, VERIFIED datasheet (ankle_roll 5, hip_yaw/ankle_pitch 20, hip 40, knee 120 N*m).
    Returns [num_envs]. See docs/28."""
    asset = env.scene[asset_cfg.name]
    tau = torch.abs(asset.data.applied_torque[:, asset_cfg.joint_ids])             # [E, nj]
    rated_t = torch.tensor(rated, device=tau.device, dtype=tau.dtype)             # [nj]
    u = tau / rated_t                                                              # utilization per joint
    return torch.sum(torch.clamp(u * u - 1.0, min=0.0), dim=1)


def ankle_pushoff_work(env, ankle_cfg: SceneEntityCfg, sensor_cfg: SceneEntityCfg,
                       contact_thresh: float = 8.0, late_time: float = 0.15, scale: float = 0.02,
                       cap: float = 80.0):
    """Kuo push-off reward ([[Paperreview/kuo-donelan-dynamic-walking]]): reward POSITIVE ankle-pitch WORK
    (plantarflexion power, clamp(tau*omega, >=0)) at LATE single support + forward — the pre-emptive
    push-off Kuo shows is the cheap power source AND the cause that rolls the CoP onto the forefoot and
    loads the passive toe. Stronger + more direct than forefoot_cop's gated GRF-fraction (which was ~0.02%
    of reward and failed to recruit the toe, H-A negative). ankle_cfg = ankle_pitch joints, sensor_cfg =
    matching foot bodies (SAME L,R order). POSITIVE weight. Tune `scale` so the value ~O(0.1-1) in a
    config-test. Returns [num_envs]."""
    asset = env.scene[ankle_cfg.name]
    tau = asset.data.applied_torque[:, ankle_cfg.joint_ids]                        # [E, nfoot]
    omega = asset.data.joint_vel[:, ankle_cfg.joint_ids]                           # [E, nfoot]
    pushoff = torch.clamp(tau * omega, min=0.0, max=cap)                           # capped positive work [W]:
    #   the cap + the terminal-single-support gate block ankle-oscillation reward-farming (research w3g1xw9oq;
    #   my earlier scale=0.1 with no cap reward-HACKED -> reward 324, error_vel 1.56).
    sensor = env.scene.sensors[sensor_cfg.name]
    f = sensor.data.net_forces_w[:, sensor_cfg.body_ids, :]                        # [E, nfoot, 3]
    in_contact = torch.norm(f, dim=-1) > contact_thresh
    other_swing = ~in_contact[:, [1, 0]]
    fwd = (asset.data.root_lin_vel_b[:, 0] > 0.0).unsqueeze(1)
    try:
        late = sensor.data.current_contact_time[:, sensor_cfg.body_ids] > late_time
    except Exception:  # noqa: BLE001
        late = torch.ones_like(in_contact)
    gate = (in_contact & other_swing & late & fwd).float()
    return torch.sum(pushoff * gate, dim=1) * scale


def foot_impact_force(env, sensor_cfg: SceneEntityCfg, force_soft: float = 700.0, cap_over: float = 1500.0):
    """★ HW-SURVIVAL penalty: punish the foot contact-force MAGNITUDE above a soft limit. Our hardware is
    3D-printed + partial aluminium; the MEASURED heel-strike spikes (1.5-2.7 kN ~ 3-5x body weight, see the
    forefoot_cop GRF analysis) would DESTROY it. Only the EXCESS over `force_soft` is penalised (clamped at
    `cap_over` so a single PhysX solver mega-spike can't blow the gradient), so normal ~bodyweight stance
    contact is FREE and only the hard impacts are punished -> drives peak GRF toward human walking
    (~1.1-1.3x BW ~= 560-660 N here). sensor_cfg = foot bodies. NEGATIVE weight. Returns [num_envs]."""
    sensor = env.scene.sensors[sensor_cfg.name]
    f = sensor.data.net_forces_w[:, sensor_cfg.body_ids, :]                        # [E, nfoot, 3]
    fmag = torch.norm(f, dim=-1)                                                   # [E, nfoot] |F|
    over = torch.clamp(fmag - force_soft, min=0.0, max=cap_over)
    return torch.sum(over, dim=1)                                                  # penalty (neg weight)


def foot_landing_vel(env, asset_cfg: SceneEntityCfg, height_thresh: float = 0.12):
    """★ Soft-landing penalty (targets the CAUSE of the impact / STRUCTURAL-load spike): punish the foot's
    DOWNWARD speed whenever the foot is NEAR THE GROUND (world height < height_thresh) = the descent into
    touchdown. A planted foot has vz~0 so steady stance is FREE; a fast slam-down is punished -> the policy
    approaches the ground slowly and rolls instead of stomping, which drops BOTH the ground force AND the
    link-reaction wrench (the measured 1.5-2.7 kN is the LINK wrench = the real HW-breaking structural load,
    LARGER than the contact sensor reads -> penalising landing VELOCITY is the reliable, sensor-scale-free
    lever). Height-gated (NOT contact-gated: by the time contact registers the slam is already over).
    asset_cfg = foot bodies. NEGATIVE weight. Returns [num_envs]."""
    asset = env.scene[asset_cfg.name]
    vz = asset.data.body_lin_vel_w[:, asset_cfg.body_ids, 2]                       # [E, nfoot] vertical vel
    pz = asset.data.body_pos_w[:, asset_cfg.body_ids, 2]                           # [E, nfoot] foot world height
    down = torch.clamp(-vz, min=0.0)                                               # downward speed [m/s]
    near = (pz < height_thresh).float()                                            # near/at the ground
    return torch.sum(down * near, dim=1)                                           # penalty (neg weight)


# ===================================================================================================
# GAIT-FIDELITY fixes (user 2026-06-22, after auditing the close-up video): the policy scissors its legs,
# walks on the FOOT EDGE (-> ankle_roll overload), and straightens the knee (0..-10deg) -> infeasible /
# unstable motion. These three terms penalize those failure modes. NEGATIVE weights. Tune in a config-test.
# ===================================================================================================
def feet_lateral_separation(env, asset_cfg: SceneEntityCfg, min_lat: float = 0.14):
    """★ Anti-CROSS: legs scissor while walking. feet_distance_l1 uses the EUCLIDEAN gap, which a crossing
    gait satisfies via a fore-aft offset while the feet pass laterally. This penalizes the LATERAL (base-frame
    y) gap dropping below min_lat (or crossing). asset_cfg = the two foot bodies. NEG weight. [num_envs]."""
    from isaaclab.utils.math import quat_rotate_inverse
    asset = env.scene[asset_cfg.name]
    fids = asset_cfg.body_ids
    rel = asset.data.body_pos_w[:, fids, :] - asset.data.root_pos_w[:, None, :]    # [E, 2, 3] world
    q = asset.data.root_quat_w
    rel_b = torch.stack([quat_rotate_inverse(q, rel[:, i, :]) for i in range(rel.shape[1])], dim=1)  # base frame
    gap = torch.abs(rel_b[:, 0, 1] - rel_b[:, 1, 1])                               # lateral (y) distance
    return torch.relu(min_lat - gap)                                              # >0 when too close / crossed


def foot_roll_flat(env, asset_cfg: SceneEntityCfg):
    """★ FOOT-FLATNESS: the policy walks on the foot EDGE -> lateral CoP -> ankle_roll OVERLOAD (user
    hypothesis). Penalize the ankle_ROLL joint deviating from flat (default 0): a flat foot has roll~0; the
    lateral edge deflects it. Keeping the foot flat removes edge contact -> should DROP the roll torque
    (tests whether the roll saturation is a GAIT artifact, not a HW need). asset_cfg = ankle_roll joints.
    NEG weight. [num_envs]."""
    asset = env.scene[asset_cfg.name]
    q = asset.data.joint_pos[:, asset_cfg.joint_ids]                               # [E, 2] ankle_roll angles
    return torch.sum(q ** 2, dim=1)                                               # penalty (neg weight)


def knee_straight_penalty(env, asset_cfg: SceneEntityCfg, min_flexion: float = -0.17):
    """★ Penalize the knee TOO STRAIGHT (knee 0..-10deg during walking = unstable). Knee nominal is FLEXED
    (~-0.40 rad); more-negative = more flexed. Penalty grows when the knee is LESS flexed than min_flexion
    (-0.17 rad ~= -10deg), incl. hyperextension. asset_cfg = knee joints. NEG weight. [num_envs].
    NOTE: assumes more-negative = more flexed (matches init -0.40); verify the knee-angle sign in config-test."""
    asset = env.scene[asset_cfg.name]
    q = asset.data.joint_pos[:, asset_cfg.joint_ids]                               # [E, 2] knee angles
    over = torch.relu(q - min_flexion)                                            # >0 when straighter than min
    return torch.sum(over ** 2, dim=1)                                            # penalty (neg weight)


def foot_flat_orientation(env, asset_cfg: SceneEntityCfg, roll_only: bool = False):
    """★ FOOT-BODY flatness (research wycgc5rlb 2026-06-22, replaces the ankle_roll JOINT-angle foot_roll_flat):
    penalize each FOOT LINK's tilt vs the ground = the world gravity direction projected INTO the foot frame,
    xy components (a flat foot has gravity straight down in its frame -> xy~0; an edge-tilted foot -> xy>0).
    Strictly better than the joint-angle penalty: joint angle != contact tilt (base lean / hip-roll / terrain
    confound it); this is the field standard (IsaacLab flat_orientation_l2 ported to the foot; Booster/SoFTA
    feet-roll). Keep weight MODEST (-0.1..-0.5): ankle roll is LOAD-BEARING for lateral balance, so over-
    penalizing trades balance for flatness -- the real fix for edge-walking is a WIDER STANCE (biomech: CoP is
    capped by foot width). asset_cfg = foot bodies. NEG weight. [num_envs]."""
    from isaaclab.utils.math import quat_rotate_inverse
    asset = env.scene[asset_cfg.name]
    quat = asset.data.body_quat_w[:, asset_cfg.body_ids, :]                        # [E, nfoot, 4]
    gvec = torch.zeros(quat.shape[0], 3, device=quat.device); gvec[:, 2] = -1.0    # world gravity direction
    pen = torch.zeros(quat.shape[0], device=quat.device)
    for i in range(quat.shape[1]):
        pg = quat_rotate_inverse(quat[:, i, :], gvec)                             # gravity in this foot's frame
        # x = pitch-tilt (toe up/down = heel-rise), y = roll-tilt (foot edge). roll_only=True penalizes ONLY
        # roll so the foot can PITCH for heel-rise/push-off (research 2026-06-22_13-30 gaitfix_v6).
        pen = pen + (pg[:, 1] ** 2 if roll_only else torch.sum(pg[:, :2] ** 2, dim=1))
    return pen                                                                     # penalty (neg weight)


def lateral_foot_placement(env, asset_cfg: SceneEntityCfg, sigma: float = 0.06):
    """★ Lateral foot-placement / capture-point support tracking (research wdi7t94jn; Hof XcoM + MIT footstep-RL
    arXiv 2408.02662): foot PLACEMENT is the PRIMARY frontal-plane balance mechanism (the stance ankle_roll is
    only a saturating supplement bounded by foot half-width). Reward the lateral MIDPOINT of the feet (the support
    center, base frame) tracking the extrapolated CoM XcoM_y = v_y / omega (omega = sqrt(g/h), Hof eigenfrequency)
    -> when the CoM drifts laterally the policy STEPS the support under the XcoM, so lateral disturbance is caught
    by foot placement instead of driving the stance ankle_roll (RS00) to its foot-edge torque floor. Routes the
    PEAK lateral load off the ankle onto the swing leg. POS weight. [num_envs]."""
    from isaaclab.utils.math import quat_rotate_inverse
    asset = env.scene[asset_cfg.name]
    h = asset.data.root_pos_w[:, 2].clamp(min=0.3)                                 # CoM height (base z)
    omega = torch.sqrt(9.81 / h)                                                   # Hof eigenfrequency [E]
    xcom_y = asset.data.root_lin_vel_b[:, 1] / omega                              # extrapolated-CoM lateral offset (base frame) [E]
    foot_w = asset.data.body_pos_w[:, asset_cfg.body_ids, :]                       # feet world pos [E, nf, 3]
    rel_w = foot_w - asset.data.root_pos_w[:, None, :]                             # relative to base [E, nf, 3]
    nf = foot_w.shape[1]
    quat = asset.data.root_quat_w[:, None, :].expand(-1, nf, -1).reshape(-1, 4)
    foot_b = quat_rotate_inverse(quat, rel_w.reshape(-1, 3)).reshape(foot_w.shape) # feet in base frame
    mid_y = foot_b[:, :, 1].mean(dim=1)                                            # lateral support center [E]
    return torch.exp(-((mid_y - xcom_y) ** 2) / (sigma ** 2))                      # POS weight [E]


def cop_progression(env, foot_cfg: SceneEntityCfg, forefoot_cfg: SceneEntityCfg,
                    T_stance: float = 0.35, contact_thresh: float = 8.0):
    """★ TEMPORAL heel->toe CoP progression (research wax3nuuc3 gaitfix_v7, replaces the STATIC forefoot_cop):
    reward the forefoot GRF fraction RISING with normalized stance phase (contact-time as a clock-proxy) so the
    CoP must ROLL forward through stance -> loads the passive toe toward ~human moment WITHOUT cranking the
    (already RS03-saturated) ankle. r = tau_n * frac * gate: early stance (tau_n~0) pays ~0 even at a high
    forefoot fraction -> heel/mid first; terminal stance (tau_n->1) pays only if the forefoot fraction is high
    -> the CoP must have rolled forward. No gait clock (current_contact_time), no heel body (2-segment foot_link
    vs toe_link fraction). foot_cfg=foot_link, forefoot_cfg=toe_link, SAME L,R order. POSITIVE weight. [num_envs]."""
    sensor = env.scene.sensors[foot_cfg.name]
    fz = sensor.data.net_forces_w[..., 2].abs()                                    # [E, nbodies] |Fz|
    f_foot = fz[:, foot_cfg.body_ids]                                              # [E, nfoot] heel/plate
    f_fore = fz[:, forefoot_cfg.body_ids]                                          # [E, nfoot] forefoot(toe)
    total = f_foot + f_fore
    frac = f_fore / (total + 1e-3)                                                 # forefoot CoP fraction [0,1]
    in_contact = total > contact_thresh
    other_swing = ~in_contact[:, [1, 0]]                                           # single support (other foot up)
    fwd = (env.scene["robot"].data.root_lin_vel_b[:, 0] > 0.0).unsqueeze(1)        # [E,1] forward
    try:
        ct = sensor.data.current_contact_time[:, foot_cfg.body_ids]               # [E, nfoot] time in contact
    except Exception:
        ct = torch.zeros_like(frac)
    tau_n = torch.clamp(ct / T_stance, 0.0, 1.0)                                   # normalized stance phase [0,1]
    return torch.sum(tau_n * frac * (in_contact & other_swing & fwd).float(), dim=1)  # POS weight [E]


def base_height_floor(env, target_height: float, margin: float = 0.06, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")):
    """★ Asymmetric base-height FLOOR (research wax3nuuc3 gaitfix_v7, replaces fixed-target base_height_l2): penalize
    ONLY a sag below (target - margin) -- a squat-collapse safety net -- and leave the whole normal-bob band + the
    single-support VAULT free. A fixed-target L2 fights the metabolically-optimal vault (Ortega&Farley) and our
    measured walking height (82.5cm) is already below the 85cm target; margin 0.06 clears the operating band so the
    pelvis can rise. (IsaacLab G1/H1 drop base_height entirely.) NEG weight. [num_envs]."""
    h = env.scene[asset_cfg.name].data.root_pos_w[:, 2]
    sag = (target_height - margin - h).clamp(min=0.0)                              # 0 above (target-margin); grows on collapse
    return sag * sag


def flat_orientation_deadband(env, deadband: float = 0.122, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")):
    """★ Base-orientation penalty with a DEADBAND (research wax3nuuc3 gaitfix_v7, replaces flat_orientation_l2):
    zero penalty inside a +-deadband cone (projected-gravity xy magnitude ~= sin(tilt); 0.122 = sin 7deg) so the
    natural pelvic tilt/obliquity (4-7deg) is FORMALLY free, square penalty outside (use a STRONG -1.0 weight so
    off-band correction is firmer than v6's -0.5). Fixes v6's 'tilt unchanged' (v6 only scaled the slope, barely
    changing the already-tiny gradient; a deadband changes the SHAPE -> exactly zero pressure in-band). NEG weight."""
    pg = env.scene[asset_cfg.name].data.projected_gravity_b[:, :2]                 # [E,2] = [pitch-tilt, roll-tilt]
    over = (torch.norm(pg, dim=1) - deadband).clamp(min=0.0)
    return over * over                                                             # 0 inside +-7deg, square outside


def double_support_bonus(env, sensor_cfg: SceneEntityCfg, contact_thresh: float = 8.0):
    """★ Restore the step-to-step TRANSITION (research wax3nuuc3 gaitfix_v7 adversarial fix): a 98%-single-support
    flat-foot gait has NO double-support -> no heel-strike/push-off CoM redirection -> NO vault (the pelvis has no
    mechanical reason to bob; Adamczyk&Kuo). A small POSITIVE reward for BOTH feet in contact nudges toward the
    human ~15-20% double-support that PRODUCES the vault. Small weight (counter-balanced by feet_air_time +
    velocity tracking so it can't collapse to standing). POSITIVE weight. [num_envs]."""
    sensor = env.scene.sensors[sensor_cfg.name]
    f = sensor.data.net_forces_w[:, sensor_cfg.body_ids, :]                        # [E, nfoot, 3]
    in_contact = torch.norm(f, dim=-1) > contact_thresh                           # [E, nfoot]
    return in_contact.all(dim=1).float()                                          # [E] both feet down (double support)


def feet_swing_height(env, asset_cfg: SceneEntityCfg, sensor_cfg: SceneEntityCfg,
                      h_target: float = 0.12, contact_thresh: float = 1.0):
    """★ Anti-tiptoe / anti-shuffle (Unitree G1 feet_swing_height; docs/reward_research/2026-06-28_heeltoe_stride_fix).
    Penalize the SWING foot's height error vs h_target while NOT in contact -> forces the policy to LIFT the whole
    foot off the ground each step. A tiptoe/shuffle (forefoot barely leaving the floor) CANNOT satisfy this, so it
    directly cures tiptoe + lengthens stride. h_target = standing foot-body z + desired clearance (the foot_link
    origin sits ~standing z above ground due to the sole-capsule offset). asset_cfg = .*_foot_link bodies, sensor_cfg
    the matching contact bodies (SAME L,R order). Returns sum_feet (z - h_target)^2 * (not in contact)  [num_envs];
    use a NEGATIVE weight."""
    asset = env.scene[asset_cfg.name]
    sensor = env.scene.sensors[sensor_cfg.name]
    foot_z = asset.data.body_pos_w[:, asset_cfg.body_ids, 2]                       # [E, nfoot] world z
    in_contact = torch.norm(sensor.data.net_forces_w[:, sensor_cfg.body_ids, :], dim=-1) > contact_thresh
    err = torch.square(foot_z - h_target) * (~in_contact).float()                 # [E, nfoot] swing-only
    return torch.sum(err, dim=1)                                                  # [E]
