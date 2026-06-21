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
                    tau_ref: float = 15.0, contact_thresh: float = 5.0):
    """Reward loading the passive toe while its foot is in contact. [num_envs] (sum over feet, ~[0,2]).

    toe_cfg selects the two toe joints; sensor_cfg selects the matching foot contact bodies in the SAME
    L,R order (verify in a config-test). load = clamp(|tau_toe|/tau_ref, 0,1) gated on foot contact."""
    asset = env.scene[toe_cfg.name]
    tau_toe = torch.abs(asset.data.applied_torque[:, toe_cfg.joint_ids])          # [E, nfoot]
    sensor = env.scene.sensors[sensor_cfg.name]
    f = sensor.data.net_forces_w[:, sensor_cfg.body_ids, :]                        # [E, nfoot, 3]
    in_contact = (torch.norm(f, dim=-1) > contact_thresh).float()                 # [E, nfoot]
    load = torch.clamp(tau_toe / tau_ref, max=1.0)                                # [E, nfoot]
    return torch.sum(load * in_contact, dim=1)
