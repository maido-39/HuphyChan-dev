# -*- coding: utf-8 -*-
"""Biped velocity-tracking env (rough terrain: flat/stairs/rough/slopes).

Subclasses Isaac Lab's ``LocomotionVelocityRoughEnvCfg`` (NOT modified). ALL body/joint
names come from the YAML robot spec via ``robots.ROLES`` — change the robot by editing the
spec, not this file. A startup event applies the spec's mass/inertia/COM overrides.
"""

from __future__ import annotations

from isaaclab.managers import CurriculumTermCfg as CurrTerm
from isaaclab.managers import EventTermCfg as EventTerm
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils import configclass

from isaaclab_tasks.manager_based.locomotion.velocity.velocity_env_cfg import (
    CurriculumCfg,
    EventCfg,
    LocomotionVelocityRoughEnvCfg,
    RewardsCfg,
)

from ...robots.biped_cfg import BIPED_CFG, ROLES, SPEC
from . import mdp
from . import rewards as pyg_rewards
from .curriculums import command_lin_vel_x_levels

# ---- spec-derived name groups (single source of truth = robot spec YAML) ----
BASE_BODY = ROLES["base"]
FOOT_BODY = ROLES["foot"]
UNDESIRED_BODIES = ROLES["undesired"]
ACTUATED_JOINTS = ROLES["action_joints"]
TARGET_BASE_HEIGHT = ROLES["target_base_height"]
# reward-penalty joint groups, derived from the actuated joints so they track renames
HIP_KNEE_JOINTS = [j for j in ACTUATED_JOINTS if ("hip" in j or "knee" in j)]
LEG_TORQUE_JOINTS = list(ACTUATED_JOINTS)


@configclass
class BipedEventCfg(EventCfg):
    """Base events + a startup event that applies the spec's physical-property overrides."""

    apply_robot_physics = EventTerm(
        func=mdp.apply_robot_physics,
        mode="startup",
        params={"spec_path": None},  # filled with SPEC.path in __post_init__
    )


@configclass
class BipedRewards(RewardsCfg):
    """Human-like walking reward set (G1-derived + shaping)."""

    termination_penalty = RewTerm(func=mdp.is_terminated, weight=-200.0)
    track_lin_vel_xy_exp = RewTerm(
        func=mdp.track_lin_vel_xy_yaw_frame_exp,
        weight=1.0,
        params={"command_name": "base_velocity", "std": 0.5},
    )
    track_ang_vel_z_exp = RewTerm(
        func=mdp.track_ang_vel_z_world_exp,
        weight=2.0,
        params={"command_name": "base_velocity", "std": 0.5},
    )
    feet_air_time = RewTerm(
        func=mdp.feet_air_time_positive_biped,
        weight=0.25,
        params={
            "command_name": "base_velocity",
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=FOOT_BODY),
            "threshold": 0.4,
        },
    )
    feet_slide = RewTerm(
        func=mdp.feet_slide,
        weight=-0.1,
        params={
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=FOOT_BODY),
            "asset_cfg": SceneEntityCfg("robot", body_names=FOOT_BODY),
        },
    )
    dof_pos_limits = RewTerm(
        func=mdp.joint_pos_limits,
        weight=-1.0,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=[".*_ankle_pitch_joint", ".*_ankle_roll_joint"])},
    )
    joint_deviation_hip = RewTerm(
        func=mdp.joint_deviation_l1,
        weight=-0.1,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=[".*_hip_yaw_joint", ".*_hip_roll_joint"])},
    )
    # human-likeness shaping (ours; tune in Phase 4)
    base_height = RewTerm(
        func=mdp.base_height_l2,
        weight=-1.0,
        params={"target_height": TARGET_BASE_HEIGHT, "asset_cfg": SceneEntityCfg("robot")},
    )
    upright = RewTerm(
        func=mdp.upright_posture,
        weight=0.5,
        params={"std": 0.3, "asset_cfg": SceneEntityCfg("robot")},
    )
    # strong anti-scissoring penalty (feet must not cross / overlap)
    feet_distance = RewTerm(
        func=mdp.feet_distance_l1,
        weight=-2.0,
        params={"asset_cfg": SceneEntityCfg("robot", body_names=FOOT_BODY), "min_dist": 0.18, "max_dist": 0.50},
    )
    no_flight = RewTerm(
        func=mdp.no_flight_phase,
        weight=-0.5,
        params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names=FOOT_BODY)},
    )
    # soft torque-limit barrier: keep motors inside their controllable envelope (sim2real +
    # achievable loads for hardware sizing). Penalizes |tau| beyond 85% of effort limit. (moderate)
    torque_soft_limit = RewTerm(
        func=mdp.applied_torque_soft_limit,
        weight=-0.0025,
        params={"soft_ratio": 0.85, "asset_cfg": SceneEntityCfg("robot", joint_names=LEG_TORQUE_JOINTS)},
    )
    # ★ ANKLE_ROLL-ONLY OFFLOAD (was ankle_pitch+roll). The thermal binding joint is ankle_ROLL (RS00 14
    #   N·m, RMS%rated 151%). ankle_PITCH (RS03) is the PUSH-OFF prime mover; penalising its torque 4x
    #   FOUGHT ankle_pushoff (the external toe-roll report verified this self-conflict on our table).
    #   Fix: scope this offload to ankle_ROLL only -> ankle_PITCH is free to plantarflex / load the toe.
    torque_soft_limit_ankle = RewTerm(
        func=mdp.applied_torque_soft_limit,
        weight=-0.01,
        params={"soft_ratio": 0.80,
                "asset_cfg": SceneEntityCfg("robot", joint_names=[".*_ankle_roll_joint"])},
    )


@configclass
class BipedCurriculumCfg(CurriculumCfg):
    """Base terrain curriculum + a forward-speed command curriculum (ramp lin_vel_x ceiling
    1.0 -> 2.0 m/s so PPO doesn't collapse on early-infeasible high-speed commands)."""

    command_vel_x = CurrTerm(
        func=command_lin_vel_x_levels,
        params={"start_max": 1.0, "final_max": 2.0, "ramp_steps": 15000, "backward_max": 1.0},
    )


@configclass
class BipedRoughEnvCfg(LocomotionVelocityRoughEnvCfg):
    rewards: BipedRewards = BipedRewards()
    events: BipedEventCfg = BipedEventCfg()
    curriculum: BipedCurriculumCfg = BipedCurriculumCfg()

    def __post_init__(self):
        super().__post_init__()

        # --- PhysX GPU buffers: self-collision + many envs + terrain overflow the defaults
        #     (PhysX error "PxGpuDynamicsMemoryConfig::collisionStackSize buffer overflow" ->
        #      some envs explode -> huge -reward). Enlarge the collision/pair buffers. ---
        self.sim.physx.gpu_collision_stack_size = 2**28            # default 2**26
        self.sim.physx.gpu_found_lost_pairs_capacity = 2**23       # default 2**21
        self.sim.physx.gpu_total_aggregate_pairs_capacity = 2**23  # default 2**21

        # --- Scene: spec-driven robot + sensors anchored on the base body ---
        # NOTE: the MJCF->USD converter nests all rigid bodies one level deep under a
        # container Xform named after the root body, i.e. /Robot/base_link/<body>
        # (standard robots are flat: /Robot/<body>). Isaac Lab prim-path regex matches ONE
        # path segment, so the default contact sensor "/Robot/.*" misses the bodies. We point
        # the sensors at the nested level. (BODY_PARENT = the container = root body name.)
        BODY_PARENT = BASE_BODY  # container Xform is named after the root body
        self.scene.robot = BIPED_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")
        # contact sensor must match the nested bodies, else "no bodies with contact reporter API"
        self.scene.contact_forces.prim_path = "{ENV_REGEX_NS}/Robot/" + BODY_PARENT + "/.*"
        # height scanner attaches to the actual root rigid body (inside the container)
        self.scene.height_scanner.prim_path = "{ENV_REGEX_NS}/Robot/" + BODY_PARENT + "/" + BASE_BODY
        if self.scene.terrain.terrain_generator is not None:
            self.scene.terrain.terrain_generator.num_rows = 8
            self.scene.terrain.terrain_generator.num_cols = 8

        # --- Actions: policy controls the motor joints (passive toe excluded) ---
        self.actions.joint_pos.joint_names = ACTUATED_JOINTS

        # --- Events / Domain Randomization (sim2real robustness) ---
        # ★ body weight (mass) DR: randomize base mass ±5 kg each startup
        self.events.add_base_mass.params["asset_cfg"].body_names = BASE_BODY
        self.events.add_base_mass.params["mass_distribution_params"] = (-5.0, 5.0)
        self.events.add_base_mass.params["operation"] = "add"
        # ★ COM DR
        self.events.base_com.params["asset_cfg"].body_names = BASE_BODY
        # ★ friction DR: dry asphalt (rubber mu ~1.0+) down to a SLIPPERY floor. Biomechanics
        #   floor for a biped to still walk ~mu 0.20 (RCOF). make_consistent=True so each sample
        #   has dynamic<=static. CRITICAL: randomize_rigid_body_material draws the ROBOT foot mu;
        #   default AVERAGE-combine with the ground compresses the low tail (foot 0.2 + ground 0.5
        #   -> contact 0.35, never slippery). Set ground mu=1.0 + MULTIPLY-combine so the contact
        #   friction EQUALS the randomized foot mu (0.20..1.25 actually reaches the feet).
        self.events.physics_material.params["static_friction_range"] = (0.30, 1.25)
        self.events.physics_material.params["dynamic_friction_range"] = (0.20, 1.10)
        self.events.physics_material.params["num_buckets"] = 128
        self.events.physics_material.params["make_consistent"] = True
        self.scene.terrain.physics_material.friction_combine_mode = "multiply"
        self.scene.terrain.physics_material.static_friction = 1.0
        self.scene.terrain.physics_material.dynamic_friction = 1.0
        self.events.base_external_force_torque.params["asset_cfg"].body_names = BASE_BODY
        # randomized spawn: pose + small initial velocity (disturbance at reset)
        self.events.reset_base.params = {
            "pose_range": {"x": (-0.4, 0.4), "y": (-0.4, 0.4), "yaw": (-3.14, 3.14)},
            "velocity_range": {"x": (-0.3, 0.3), "y": (-0.3, 0.3), "z": (-0.1, 0.1),
                               "roll": (-0.2, 0.2), "pitch": (-0.2, 0.2), "yaw": (-0.2, 0.2)},
        }
        # ★ randomize initial joint pose (vary the starting posture)
        self.events.reset_robot_joints.params["position_range"] = (0.7, 1.3)
        # ★ disturbance push: STRONGER (+-1.2 m/s ~= 62 Ns impulse < recoverable ceiling ~65 Ns
        #   for a 51.8 kg base) + FASTER (3-6 s, high-freq beats rare-big per HuB/G1) + a YAW kick
        #   (+-0.6 rad/s trains turn-recovery). velocity-push (push_by_setting_velocity), not a
        #   1-step external force (that lasts a single dt -> ~50x too small).
        self.events.push_robot.interval_range_s = (3.0, 6.0)
        self.events.push_robot.params["velocity_range"] = {"x": (-1.2, 1.2), "y": (-1.2, 1.2), "yaw": (-0.6, 0.6)}
        # spec physics override is MEASUREMENT-ONLY (scripts use mass_utils). For TRAINING, the
        # add_base_mass/base_com DR events own the mass -> disable the startup spec event here.
        self.events.apply_robot_physics = None

        # --- Rewards: remap penalties to our joints, enable upright ---
        self.rewards.lin_vel_z_l2.weight = -0.2
        self.rewards.ang_vel_xy_l2.weight = -0.05
        self.rewards.flat_orientation_l2.weight = -1.0
        self.rewards.action_rate_l2.weight = -0.008  # ★ slightly stronger 1st-order action smoothness
        # ★ GAIT-FIDELITY fixes (user 2026-06-22 close-up video audit): legs SCISSOR, foot-EDGE walking
        #   (-> ankle_roll OVERLOAD), knee 0..-10deg (unstable). Re-enable thigh/shin contact penalty +
        #   add lateral-cross, foot-flatness, knee-straight penalties. Tune weights in a config-test.
        self.rewards.undesired_contacts = RewTerm(
            func=mdp.undesired_contacts, weight=-1.0,
            params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names=UNDESIRED_BODIES), "threshold": 1.0})
        # ★ gaitfix_v4 (research wycgc5rlb): edge-walking/ankle_roll-overload is a STANCE-WIDTH deficit forcing
        #   lateral balance through the ankle (CoP capped by foot width). WIDEN the stance + use a FOOT-BODY
        #   flatness penalty (not the joint-angle one). reward_research note 2026-06-22_foot_flat_ankle_roll_stance.
        self.rewards.feet_distance.weight = -3.0
        self.rewards.feet_distance.params["min_dist"] = 0.24       # ★ WIDER stance target (was 0.20) -> lateral CoP from a wide base, not the ankle edge
        self.rewards.feet_lateral_sep = RewTerm(   # anti-cross the euclidean feet_distance misses
            func=pyg_rewards.feet_lateral_separation, weight=-3.0,
            params={"asset_cfg": SceneEntityCfg("robot", body_names=FOOT_BODY), "min_lat": 0.18})  # wider (was 0.14)
        self.rewards.foot_roll_flat = RewTerm(     # ★ FOOT-BODY orientation flatness (research: > joint-angle); MODEST weight (roll is load-bearing for balance)
            func=pyg_rewards.foot_flat_orientation, weight=-0.3,
            params={"asset_cfg": SceneEntityCfg("robot", body_names=FOOT_BODY)})
        self.rewards.knee_straight = RewTerm(      # no knee 0..-10deg (keep flexed)
            func=pyg_rewards.knee_straight_penalty, weight=-5.0,
            params={"asset_cfg": SceneEntityCfg("robot", joint_names=[".*_knee_joint"]), "min_flexion": -0.17})
        self.rewards.dof_acc_l2.weight = -1.25e-7
        # ★ FOOT VIBRATION FIX (rank-1, research wuq4tvpfa): regularize ALL actuated joints incl. the
        #   ANKLES (were excluded -> ankle/toe had ZERO accel penalty -> high-freq buzz, confirmed in
        #   data: >5Hz torque energy knee 40%/toe 41%/ankle 17-23%). Was HIP_KNEE_JOINTS only.
        self.rewards.dof_acc_l2.params["asset_cfg"] = SceneEntityCfg("robot", joint_names=LEG_TORQUE_JOINTS)
        self.rewards.dof_torques_l2.weight = -1.5e-6
        self.rewards.dof_torques_l2.params["asset_cfg"] = SceneEntityCfg("robot", joint_names=LEG_TORQUE_JOINTS)

        # --- Commands (omnidirectional). Forward up to 2.0 m/s (~Fr 0.51, walk-run boundary;
        #     2.5 m/s would be a running/flight regime -> unstable for walking PPO + unrepresentative
        #     joint loads). The wide vx range is reached via a COMMAND CURRICULUM (see curriculum
        #     cfg) so PPO doesn't collapse on early-infeasible high-speed commands. ---
        self.commands.base_velocity.ranges.lin_vel_x = (-1.0, 2.0)
        self.commands.base_velocity.ranges.lin_vel_y = (-0.6, 0.6)
        self.commands.base_velocity.ranges.ang_vel_z = (-1.57, 1.57)

        # --- Terminations: fall = base body touches ground ---
        self.terminations.base_contact.params["sensor_cfg"].body_names = BASE_BODY


@configclass
class BipedRoughEnvCfg_PLAY(BipedRoughEnvCfg):
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
        # ★ no command curriculum in PLAY -> cfg.ranges stays at the FULL range so the keyboard
        #   teleop (and eval) can command the whole trained envelope (vx up to 2.0 m/s).
        self.curriculum.command_vel_x = None
        self.events.base_external_force_torque = None
        self.events.push_robot = None
        # ★ deterministic for MEASUREMENT: no mass/COM/friction randomization
        #   (sweep mass deliberately via measure.py --base_mass / --mass_scale instead)
        self.events.add_base_mass = None
        self.events.base_com = None
        self.events.physics_material.params["static_friction_range"] = (0.9, 0.9)
        self.events.physics_material.params["dynamic_friction_range"] = (0.7, 0.7)
