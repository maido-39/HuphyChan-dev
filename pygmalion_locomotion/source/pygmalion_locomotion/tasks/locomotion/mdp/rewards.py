# -*- coding: utf-8 -*-
"""Human-likeness reward shaping terms for the biped (added on top of Isaac Lab's set).

Each function follows the Isaac Lab reward signature ``f(env, ...) -> Tensor[num_envs]``.
Weights are assigned in the env cfg; tune during Phase 4 (see docs/04_reward_experiments).
"""

from __future__ import annotations

import torch
from typing import TYPE_CHECKING

from isaaclab.managers import SceneEntityCfg
from isaaclab.sensors import ContactSensor

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv


def base_height_l2(
    env: "ManagerBasedRLEnv",
    target_height: float,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """Penalize deviation of the base height from a target (encourages upright, no crouch).

    Uses world-frame z (valid on flat ground; on rough terrain pair with a height-scan offset).
    """
    asset = env.scene[asset_cfg.name]
    return torch.square(asset.data.root_pos_w[:, 2] - target_height)


def upright_posture(
    env: "ManagerBasedRLEnv",
    std: float = 0.3,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """Reward an upright torso via the projected-gravity xy components (exp kernel, in [0,1])."""
    asset = env.scene[asset_cfg.name]
    pg_xy = asset.data.projected_gravity_b[:, :2]
    return torch.exp(-torch.sum(torch.square(pg_xy), dim=1) / std**2)


def applied_torque_soft_limit(
    env: "ManagerBasedRLEnv",
    soft_ratio: float = 0.85,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """Soft-barrier penalty for operating near the motor torque limit.

    Penalizes (squared) the amount any joint's |applied_torque| exceeds ``soft_ratio`` of its
    effort limit. Unlike Isaac Lab's ``applied_torque_limits`` (which needs explicit actuators and
    measures the post-clip difference), this uses ``applied_torque`` + ``joint_effort_limits`` and
    works for our implicit actuators. Keeps the policy inside the motor's controllable envelope
    (avoids saturation) -> better sim2real + realistic, achievable loads for hardware sizing.
    See docs/04_reward_experiments (torque-limit research).
    """
    asset = env.scene[asset_cfg.name]
    tau = asset.data.applied_torque[:, asset_cfg.joint_ids].abs()
    limit = asset.data.joint_effort_limits[:, asset_cfg.joint_ids]
    over = (tau - soft_ratio * limit).clamp(min=0.0)
    return torch.sum(over * over, dim=1)


def feet_distance_l1(
    env: "ManagerBasedRLEnv",
    asset_cfg: SceneEntityCfg,
    min_dist: float = 0.15,
    max_dist: float = 0.45,
) -> torch.Tensor:
    """Penalize a foot separation outside [min_dist, max_dist] (no scissoring / no over-wide stance).

    ``asset_cfg.body_names`` must resolve to exactly the two foot bodies.
    """
    asset = env.scene[asset_cfg.name]
    feet_xy = asset.data.body_pos_w[:, asset_cfg.body_ids, :2]  # [N, 2, 2]
    d = torch.norm(feet_xy[:, 0, :] - feet_xy[:, 1, :], dim=-1)  # [N]
    below = (min_dist - d).clamp(min=0.0)
    above = (d - max_dist).clamp(min=0.0)
    return below + above


def no_flight_phase(
    env: "ManagerBasedRLEnv",
    sensor_cfg: SceneEntityCfg,
    force_threshold: float = 1.0,
) -> torch.Tensor:
    """Penalize having *no* foot on the ground (discourages hopping/running; walking keeps >=1 foot down).

    Returns 1.0 for environments in a flight phase, else 0.0.
    ``sensor_cfg.body_names`` should resolve to the two foot bodies.
    """
    cs: ContactSensor = env.scene.sensors[sensor_cfg.name]
    forces = cs.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]  # [N, 2]
    in_contact = forces > force_threshold
    n_contact = in_contact.sum(dim=1)
    return (n_contact == 0).float()
