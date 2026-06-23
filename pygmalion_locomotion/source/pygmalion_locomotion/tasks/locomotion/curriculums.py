# -*- coding: utf-8 -*-
"""Custom curriculum terms for the biped velocity env.

Isaac Lab 2.2 ships only a TERRAIN curriculum (terrain_levels_vel); G1/H1 use fixed command
ranges. The wide forward-speed range we want (up to 2.0 m/s ~= Fr 0.51, the walk-run boundary)
cannot be trained from a cold range because early high-speed commands are infeasible and return
~0 tracking reward, which collapses PPO (Margolis "Rapid Locomotion", RSS 2022). So we ramp the
forward lin_vel_x ceiling over training: start where the warm-start teacher already walks and
linearly widen to the target. The command sampler reads ``cfg.ranges.lin_vel_x`` at every resample
(velocity_command.py), so mutating it here takes effect live.
"""

from __future__ import annotations

import torch


def command_lin_vel_x_levels(env, env_ids, start_max: float = 1.0, final_max: float = 2.0,
                             ramp_steps: int = 15000, backward_max: float = 1.0,
                             command_name: str = "base_velocity"):
    """Linearly widen the forward lin_vel_x command ceiling ``start_max`` -> ``final_max`` over the
    first ``ramp_steps`` environment steps. Returns the current ceiling (logged as the curriculum
    level). ``env_ids`` is ignored on purpose: this is a GLOBAL command range, not per-env."""
    try:
        cmd = env.command_manager.get_term(command_name)
        frac = min(1.0, float(env.common_step_counter) / float(max(1, ramp_steps)))
        cur_max = start_max + frac * (final_max - start_max)
        cmd.cfg.ranges.lin_vel_x = (-float(backward_max), float(cur_max))
    except Exception:  # noqa: BLE001 - never let a curriculum hiccup crash training
        cur_max = final_max
    return torch.tensor(float(cur_max), device=env.device)


def command_levels_g1(env, env_ids, reward_term_name: str = "track_lin_vel_xy_exp",
                      lin_x_limit=(-0.5, 1.0), lin_y_limit=(-0.3, 0.3),
                      delta: float = 0.1, threshold_ratio: float = 0.8,
                      command_name: str = "base_velocity"):
    """G1-style REWARD-GATED command curriculum (port of unitree_rl_lab ``lin_vel_cmd_levels``).

    Start from a tiny command box (set in the env cfg, e.g. +-0.1 m/s) and widen the lin_vel_x /
    lin_vel_y ranges by ``delta`` toward the limit ONLY at episode boundaries when the mean
    per-step linear-tracking reward exceeds ``threshold_ratio`` x term weight. ang_vel_z is left
    untouched (G1 does not curriculum the yaw command). Returns the current forward ceiling so it
    logs the same way as the old time-based curriculum. ``env_ids`` ignored (GLOBAL range)."""
    cmd = env.command_manager.get_term(command_name)
    ranges = cmd.cfg.ranges
    try:
        rew_cfg = env.reward_manager.get_term_cfg(reward_term_name)
        reward = torch.mean(env.reward_manager._episode_sums[reward_term_name][env_ids]) / env.max_episode_length_s
        if env.common_step_counter % env.max_episode_length == 0 and reward > rew_cfg.weight * threshold_ratio:
            ranges.lin_vel_x = [max(float(lin_x_limit[0]), ranges.lin_vel_x[0] - delta),
                                min(float(lin_x_limit[1]), ranges.lin_vel_x[1] + delta)]
            ranges.lin_vel_y = [max(float(lin_y_limit[0]), ranges.lin_vel_y[0] - delta),
                                min(float(lin_y_limit[1]), ranges.lin_vel_y[1] + delta)]
    except Exception:  # noqa: BLE001 - never let a curriculum hiccup crash training
        pass
    return torch.tensor(float(ranges.lin_vel_x[1]), device=env.device)
