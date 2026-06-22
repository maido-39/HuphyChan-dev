# -*- coding: utf-8 -*-
"""Unitree-G1-VANILLA reward BASELINE on our robot (user 2026-06-22).

HOLD the custom gaitfix reward line (v3-v7) and train our 14-DOF lower body with the STANDARD Unitree G1
locomotion reward set (sim/IsaacLab/.../config/g1/rough_env_cfg.py G1Rewards), to see the natural behavior and
separate "my custom reward set is over-engineered / fighting itself" from a "robot/morphology" problem.

Keeps our robot/scene/sensors (BipedRoughEnvCfg) and REPLACES the whole reward set with the G1 vanilla one --
NO forefoot_cop / ankle_pushoff / cop_progression / foot_roll_flat / lateral_foot_placement / feet_distance /
feet_lateral_sep / upright / base_height / power_cot / knee_straight / double_support, etc. Just G1's terms.
Adapted: feet = foot_link (G1 uses ankle_roll_link); NO arms/fingers/torso joint_deviation (we have none).
"""

from __future__ import annotations

from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils import configclass
from isaaclab_tasks.manager_based.locomotion.velocity.velocity_env_cfg import RewardsCfg

from . import mdp
from .velocity_env_cfg import FOOT_BODY
from .flat_env_cfg import BipedFlatEnvCfg   # ★ FLAT terrain base (was BipedRoughEnvCfg = rough; bug fix)


@configclass
class G1VanillaRewards(RewardsCfg):
    """Unitree G1 G1Rewards adapted to our lower body. The base RewardsCfg supplies lin_vel_z / ang_vel_xy /
    dof_torques / dof_acc / action_rate / undesired_contacts / flat_orientation / dof_pos_limits; the env
    __post_init__ tweaks them exactly as G1RoughEnvCfg does."""

    termination_penalty = RewTerm(func=mdp.is_terminated, weight=-200.0)
    track_lin_vel_xy_exp = RewTerm(
        func=mdp.track_lin_vel_xy_yaw_frame_exp, weight=1.0,
        params={"command_name": "base_velocity", "std": 0.5})
    track_ang_vel_z_exp = RewTerm(
        func=mdp.track_ang_vel_z_world_exp, weight=2.0,
        params={"command_name": "base_velocity", "std": 0.5})
    feet_air_time = RewTerm(
        func=mdp.feet_air_time_positive_biped, weight=0.25,
        params={"command_name": "base_velocity",
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=FOOT_BODY),
                "threshold": 0.4})
    feet_slide = RewTerm(
        func=mdp.feet_slide, weight=-0.1,
        params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names=FOOT_BODY),
                "asset_cfg": SceneEntityCfg("robot", body_names=FOOT_BODY)})
    dof_pos_limits = RewTerm(
        func=mdp.joint_pos_limits, weight=-1.0,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=[".*_ankle_pitch_joint", ".*_ankle_roll_joint"])})
    joint_deviation_hip = RewTerm(
        func=mdp.joint_deviation_l1, weight=-0.1,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=[".*_hip_yaw_joint", ".*_hip_roll_joint"])})


@configclass
class BipedG1VanillaEnvCfg(BipedFlatEnvCfg):
    """Our robot + scene/sensors on FLAT terrain (matches the gaitfix Flat-Forefoot baseline), but the G1
    VANILLA reward set (baseline, user 2026-06-22). Inherits BipedFlatEnvCfg = plane terrain; the flat reward
    tweaks are discarded by the self.rewards swap below."""

    def __post_init__(self):
        super().__post_init__()                       # robot/scene/sensors/events + (discarded) gaitfix rewards
        self.rewards = G1VanillaRewards()             # ★ swap in the G1 vanilla reward set
        # G1RoughEnvCfg reward tweaks (adapted: no arms/torso)
        self.rewards.lin_vel_z_l2.weight = 0.0
        self.rewards.undesired_contacts = None
        self.rewards.flat_orientation_l2.weight = -1.0
        self.rewards.action_rate_l2.weight = -0.005
        self.rewards.dof_acc_l2.weight = -1.25e-7
        self.rewards.dof_acc_l2.params["asset_cfg"] = SceneEntityCfg("robot", joint_names=[".*_hip_.*", ".*_knee_joint"])
        self.rewards.dof_torques_l2.weight = -1.5e-7
        self.rewards.dof_torques_l2.params["asset_cfg"] = SceneEntityCfg("robot", joint_names=[".*_hip_.*", ".*_knee_joint", ".*_ankle_.*"])
        # G1 commands: forward-only, NO lateral, NO command curriculum (vanilla)
        self.curriculum.command_vel_x = None
        self.commands.base_velocity.ranges.lin_vel_x = (0.0, 1.0)
        self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
        self.commands.base_velocity.ranges.ang_vel_z = (-1.0, 1.0)
        # ★ G1 vanilla DR (LIGHT, user 2026-06-22): G1RoughEnvCfg disables push/mass/com randomization +
        #   deterministic joint reset. Without this the baseline was "G1 reward + OUR HEAVY DR" = confounded;
        #   full-G1 (reward + DR both G1) is the clean morphology-vs-our-approach test. (base_external_force +
        #   physics_material friction kept, as G1 does.)
        self.events.push_robot = None
        self.events.add_base_mass = None
        self.events.base_com = None
        self.events.reset_robot_joints.params["position_range"] = (1.0, 1.0)


@configclass
class BipedG1VanillaEnvCfg_PLAY(BipedG1VanillaEnvCfg):
    def __post_init__(self):
        super().__post_init__()
        self.scene.num_envs = 32
        self.scene.env_spacing = 2.5
        self.episode_length_s = 40.0
        self.scene.terrain.max_init_terrain_level = None
        if self.scene.terrain.terrain_generator is not None:
            self.scene.terrain.terrain_generator.num_rows = 5
            self.scene.terrain.terrain_generator.num_cols = 5
            self.scene.terrain.terrain_generator.curriculum = False
        self.observations.policy.enable_corruption = False
        self.events.base_external_force_torque = None
        self.events.push_robot = None
        self.events.add_base_mass = None
        self.events.base_com = None
        self.events.physics_material.params["static_friction_range"] = (0.9, 0.9)
        self.events.physics_material.params["dynamic_friction_range"] = (0.7, 0.7)
