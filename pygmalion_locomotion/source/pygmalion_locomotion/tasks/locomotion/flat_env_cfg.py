# -*- coding: utf-8 -*-
"""Flat-terrain biped env (subclass of the rough env, plane ground, no height scan)."""

from __future__ import annotations

from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils import configclass

from . import rewards as pyg_rewards
from .velocity_env_cfg import ACTUATED_JOINTS, BipedRoughEnvCfg, FOOT_BODY, HIP_KNEE_JOINTS


@configclass
class BipedFlatEnvCfg(BipedRoughEnvCfg):
    def __post_init__(self):
        super().__post_init__()

        # flat ground
        self.scene.terrain.terrain_type = "plane"
        self.scene.terrain.terrain_generator = None
        self.curriculum.terrain_levels = None
        # ★ KEEP height_scan on flat (constant ~base height) so the policy's OBS matches the rough
        #   env (239-dim) -> a flat-trained policy can be TRANSFERRED (weight init) into rough.
        #   This makes the flat policy a "teacher"; a blind student is distilled later for deploy.
        #   (docs/13, docs/14)

        # reward tweaks for flat (mirror G1 flat)
        self.rewards.track_ang_vel_z_exp.weight = 1.0
        self.rewards.lin_vel_z_l2.weight = -0.2
        self.rewards.action_rate_l2.weight = -0.005
        self.rewards.dof_acc_l2.weight = -1.0e-7
        self.rewards.feet_air_time.weight = 0.75
        self.rewards.feet_air_time.params["threshold"] = 0.4
        self.rewards.dof_torques_l2.weight = -2.0e-6
        self.rewards.dof_torques_l2.params["asset_cfg"] = SceneEntityCfg("robot", joint_names=HIP_KNEE_JOINTS)

        # commands (omnidirectional). Forward up to 2.0 m/s reached via the command curriculum
        # (curriculum.command_vel_x ramps the lin_vel_x ceiling 1.0 -> 2.0 over ~15k steps so PPO
        # doesn't collapse on early-infeasible high-speed commands). yaw up to 1.57 rad/s.
        self.commands.base_velocity.ranges.lin_vel_x = (-1.0, 2.0)
        self.commands.base_velocity.ranges.lin_vel_y = (-0.6, 0.6)
        self.commands.base_velocity.ranges.ang_vel_z = (-1.57, 1.57)


@configclass
class BipedFlatEnvCfg_PLAY(BipedFlatEnvCfg):
    def __post_init__(self):
        super().__post_init__()
        self.scene.num_envs = 32
        self.scene.env_spacing = 2.5
        self.observations.policy.enable_corruption = False
        # ★ no command curriculum in PLAY -> keyboard/eval gets the FULL range (vx up to 2.0)
        self.curriculum.command_vel_x = None
        self.events.base_external_force_torque = None
        self.events.push_robot = None
        # ★ deterministic for MEASUREMENT: no mass/COM/friction randomization
        #   (sweep mass deliberately via measure.py --base_mass / --mass_scale)
        self.events.add_base_mass = None
        self.events.base_com = None
        self.events.physics_material.params["static_friction_range"] = (0.9, 0.9)
        self.events.physics_material.params["dynamic_friction_range"] = (0.7, 0.7)


@configclass
class BipedFlatForefootEnvCfg(BipedFlatEnvCfg):
    """★ TOE-LOADING experiment (toe-use research wljkv3uu8, docs/23): H1 late-single-support
    forefoot-load reward + H6 vel-norm power-CoT, on the flat env. Warm-start (--init_checkpoint) from a
    converged flat policy. The toe stays PASSIVE / out of the policy; these terms only shape the FOOT /
    stance so the passive toe self-loads at terminal stance (load goes to the toe, not the knee).
    NOTE: tune `scale` (power_cot) + weights in a config-test; obs is UNCHANGED (239) so it transfers."""

    def __post_init__(self):
        super().__post_init__()
        # ★ Rank-1 INDIRECT CoP/forefoot-progression reward (research whirkj8ws). The DIRECT toe-torque
        #   reward (H1) is an anti-pattern: |tau_toe|=k*deflection -> reward-hackable by a static toe-curl
        #   (worse here, the toe is over-damped). Reward WHERE the foot bears load (forefoot GRF fraction
        #   at terminal single support) = the legitimate CAUSE that loads the passive toe, hard to game.
        self.rewards.forefoot_cop = RewTerm(
            func=pyg_rewards.forefoot_cop, weight=0.5,
            params={"foot_cfg": SceneEntityCfg("contact_forces", body_names=".*_foot_link"),
                    "forefoot_cfg": SceneEntityCfg("contact_forces", body_names=".*_toe_link"),
                    "contact_thresh": 8.0, "late_time": 0.15})
        # Rank-2 — vel-normalized power CoT (let the free spring do push-off work; NEVER standalone,
        #   subordinate to CoP + velocity tracking).
        self.rewards.power_cot = RewTerm(
            func=pyg_rewards.power_cot, weight=0.4,
            params={"asset_cfg": SceneEntityCfg("robot", joint_names=ACTUATED_JOINTS), "scale": 0.003})
