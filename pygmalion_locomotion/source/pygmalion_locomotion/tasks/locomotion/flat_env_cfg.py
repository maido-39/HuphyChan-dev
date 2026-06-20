# -*- coding: utf-8 -*-
"""Flat-terrain biped env (subclass of the rough env, plane ground, no height scan)."""

from __future__ import annotations

from isaaclab.managers import SceneEntityCfg
from isaaclab.utils import configclass

from .velocity_env_cfg import BipedRoughEnvCfg, HIP_KNEE_JOINTS


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
