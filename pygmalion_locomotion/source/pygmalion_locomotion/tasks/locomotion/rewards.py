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
