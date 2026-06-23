# -*- coding: utf-8 -*-
"""unitree_rl_lab G1 velocity reward recipe on the RobStride biped (flat).

Primitive collision + self_collision=false in the robot spec; replaces gaitfix v3-v7 stack.
Source: unitree_rl_lab/.../g1/29dof/velocity_env_cfg.py RewardsCfg (lower-body adapted).
"""

from __future__ import annotations

import math

from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils import configclass
from isaaclab.envs.mdp import rewards as core_rewards
from isaaclab_tasks.manager_based.locomotion.velocity.velocity_env_cfg import RewardsCfg

from . import mdp
from .curriculums import command_levels_g1
from .flat_env_cfg import BipedFlatEnvCfg
from .velocity_env_cfg import FOOT_BODY, TARGET_BASE_HEIGHT, UNDESIRED_BODIES


@configclass
class UnitreeLabRewards(RewardsCfg):
    """unitree_rl_lab G1 velocity rewards adapted to 12-DOF lower body (no arms/waist)."""

    track_lin_vel_xy_exp = RewTerm(
        func=mdp.track_lin_vel_xy_yaw_frame_exp,
        weight=1.0,
        params={"command_name": "base_velocity", "std": math.sqrt(0.25)},
    )
    track_ang_vel_z_exp = RewTerm(
        func=core_rewards.track_ang_vel_z_exp,
        weight=0.5,
        params={"command_name": "base_velocity", "std": math.sqrt(0.25)},
    )
    alive = RewTerm(func=core_rewards.is_alive, weight=0.15)

    lin_vel_z_l2 = RewTerm(func=mdp.lin_vel_z_l2, weight=-2.0)
    ang_vel_xy_l2 = RewTerm(func=mdp.ang_vel_xy_l2, weight=-0.05)
    joint_vel = RewTerm(func=core_rewards.joint_vel_l2, weight=-0.001)
    dof_acc_l2 = RewTerm(func=core_rewards.joint_acc_l2, weight=-2.5e-7)
    action_rate_l2 = RewTerm(func=mdp.action_rate_l2, weight=-0.05)
    dof_pos_limits = RewTerm(func=mdp.joint_pos_limits, weight=-5.0)
    energy = RewTerm(func=mdp.energy, weight=-2e-5)

    joint_deviation_legs = RewTerm(
        func=mdp.joint_deviation_l1,
        weight=-1.0,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=[".*_hip_roll_joint", ".*_hip_yaw_joint"])},
    )

    flat_orientation_l2 = RewTerm(func=mdp.flat_orientation_l2, weight=-5.0)
    base_height = RewTerm(
        func=mdp.base_height_l2,
        weight=-10.0,
        params={"target_height": TARGET_BASE_HEIGHT, "asset_cfg": SceneEntityCfg("robot")},
    )

    gait = RewTerm(
        func=mdp.feet_gait,
        weight=0.5,
        params={
            "period": 0.8,
            "offset": [0.0, 0.5],
            "threshold": 0.55,
            "command_name": "base_velocity",
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=FOOT_BODY),
        },
    )
    feet_slide = RewTerm(
        func=mdp.feet_slide,
        weight=-0.2,
        params={
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=FOOT_BODY),
            "asset_cfg": SceneEntityCfg("robot", body_names=FOOT_BODY),
        },
    )
    feet_clearance = RewTerm(
        func=mdp.foot_clearance_reward,
        weight=1.0,
        params={
            "std": 0.05,
            "tanh_mult": 2.0,
            "target_height": 0.1,
            "asset_cfg": SceneEntityCfg("robot", body_names=FOOT_BODY),
        },
    )
    undesired_contacts = RewTerm(
        func=mdp.undesired_contacts,
        weight=-1.0,
        params={
            "threshold": 1.0,
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=UNDESIRED_BODIES),
        },
    )

    # Disable Isaac Lab defaults not used in unitree recipe.
    feet_air_time = None
    dof_torques_l2 = None
    termination_penalty = None


@configclass
class BipedFlatUnitreeLabEnvCfg(BipedFlatEnvCfg):
    """Flat terrain + unitree_rl_lab G1 reward stack (primitive collision asset)."""

    def __post_init__(self):
        super().__post_init__()
        self.rewards = UnitreeLabRewards()
        # Softer push for smoke / early training (unitree default is ±0.5 m/s).
        self.events.push_robot.interval_range_s = (5.0, 5.0)
        self.events.push_robot.params["velocity_range"] = {"x": (-0.5, 0.5), "y": (-0.5, 0.5)}

        # ===== G1-alignment (user 2026-06-23) =====
        # (1) OBS: drop the height-map term (blind policy) + stack 5-step history like G1.
        self.observations.policy.height_scan = None
        self.observations.policy.history_length = 5
        # (2) COMMANDS: G1 setting. Direct yaw command (heading_command=False) + tiny start box
        #     grown by the reward-gated curriculum toward G1 limits (lin_x -0.5..1.0, lin_y ±0.3).
        #     yaw stays fixed at ±0.1 (G1 does not curriculum it).
        self.commands.base_velocity.heading_command = False
        self.commands.base_velocity.ranges.lin_vel_x = (-0.1, 0.1)
        self.commands.base_velocity.ranges.lin_vel_y = (-0.1, 0.1)
        self.commands.base_velocity.ranges.ang_vel_z = (-0.1, 0.1)
        # (3) CURRICULUM: replace our time-based vx ramp with the G1 reward-gated level scheme
        #     (reuse the existing registered slot so it still logs as Curriculum/command_vel_x).
        self.curriculum.command_vel_x.func = command_levels_g1
        self.curriculum.command_vel_x.params = {
            "reward_term_name": "track_lin_vel_xy_exp",
            "lin_x_limit": (-0.5, 1.0),
            "lin_y_limit": (-0.3, 0.3),
            "delta": 0.1,
            "threshold_ratio": 0.8,
        }
        # (4) DR: base mass ±3 kg (was ±5) to match the tighter G1 mass-randomization band.
        self.events.add_base_mass.params["mass_distribution_params"] = (-3.0, 3.0)


@configclass
class BipedFlatUnitreeLabEnvCfg_PLAY(BipedFlatUnitreeLabEnvCfg):
    def __post_init__(self):
        super().__post_init__()
        self.scene.num_envs = 32
        self.scene.env_spacing = 2.5
        self.observations.policy.enable_corruption = False
        # No curriculum in PLAY -> open the command box to the FULL G1 limit range for eval
        # (parent starts it tiny at ±0.1; without this the robot would barely move in play).
        self.curriculum.command_vel_x = None
        self.commands.base_velocity.ranges.lin_vel_x = (-0.5, 1.0)
        self.commands.base_velocity.ranges.lin_vel_y = (-0.3, 0.3)
        self.commands.base_velocity.ranges.ang_vel_z = (-0.2, 0.2)
        self.events.base_external_force_torque = None
        self.events.push_robot = None
        self.events.add_base_mass = None
        self.events.base_com = None
        self.events.physics_material.params["static_friction_range"] = (0.9, 0.9)
        self.events.physics_material.params["dynamic_friction_range"] = (0.7, 0.7)
