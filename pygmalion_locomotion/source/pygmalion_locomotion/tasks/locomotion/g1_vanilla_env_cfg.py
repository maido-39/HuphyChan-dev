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
from isaaclab.managers import ObservationGroupCfg as ObsGroup
from isaaclab.managers import ObservationTermCfg as ObsTerm
from isaaclab.utils import configclass
from isaaclab.utils.noise import AdditiveUniformNoiseCfg as Unoise
from isaaclab_tasks.manager_based.locomotion.velocity.velocity_env_cfg import RewardsCfg

from . import mdp
from .velocity_env_cfg import FOOT_BODY, BipedRoughEnvCfg, ACTUATED_JOINTS
from .flat_env_cfg import BipedFlatEnvCfg, BipedFlatForefootEnvCfg   # FLAT base; Forefoot = OUR gaitfix reward
from . import rewards as pyg_rewards   # custom reward funcs for the minimal targeted additions


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


# ============================================================================================
# OUR latest gaitfix reward UNDER G1-MATCHED CONDITIONS (fair reward A/B vs full-G1).
# user 2026-06-22: full-G1 LOOKS unstable (wobble) despite 0% falls; isolate the REWARD by matching DR+commands.
# ============================================================================================
@configclass
class BipedFlatForefootG1CondEnvCfg(BipedFlatForefootEnvCfg):
    """OUR latest gaitfix reward (BipedFlatForefootEnvCfg = v3-v7 set) but with G1-MATCHED conditions: light DR
    (push/mass/com OFF + deterministic reset) + forward-only commands + no curriculum. Now ONLY the reward
    differs from full-G1 (BipedG1VanillaEnvCfg) -> a clean reward A/B (does OUR reward look more stable?)."""

    def __post_init__(self):
        super().__post_init__()                       # our gaitfix reward + OUR heavy DR + omni commands
        # ★ G1-matched conditions (identical to BipedG1VanillaEnvCfg): light DR + forward-only
        self.events.push_robot = None
        self.events.add_base_mass = None
        self.events.base_com = None
        self.events.reset_robot_joints.params["position_range"] = (1.0, 1.0)
        self.curriculum.command_vel_x = None
        self.commands.base_velocity.ranges.lin_vel_x = (0.0, 1.0)
        self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
        self.commands.base_velocity.ranges.ang_vel_z = (-1.0, 1.0)


@configclass
class BipedFlatForefootG1CondEnvCfg_PLAY(BipedFlatForefootG1CondEnvCfg):
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


# ============================================================================================
# ★ G1 vanilla base + ONLY the truly-necessary additions (user 2026-06-22): ground-IMPACT reduction +
#   no knee hyperextension. NOT the 20-term gaitfix mess -- minimal & targeted (the G1 reward WALKS; just
#   tame the impact + protect the knee, for HW survival 1.5-2.7 kN). Keeps G1 conditions (fwd-only, light DR).
# ============================================================================================
@configclass
class BipedG1ImpactEnvCfg(BipedG1VanillaEnvCfg):
    """G1 vanilla reward + 3 targeted terms: foot_landing_vel + foot_impact_force (low-impact landing) +
    knee_straight (no 0..-10deg hyperextension). Nothing else."""

    def __post_init__(self):
        super().__post_init__()                       # G1 vanilla rewards + G1 conditions (fwd-only, light DR)
        # ★ ground-IMPACT reduction (soft landing -> connection-load survival within 1.5-2.7 kN)
        self.rewards.foot_landing_vel = RewTerm(
            func=pyg_rewards.foot_landing_vel, weight=-1.0,
            params={"asset_cfg": SceneEntityCfg("robot", body_names=FOOT_BODY), "height_thresh": 0.12})
        self.rewards.foot_impact_force = RewTerm(
            func=pyg_rewards.foot_impact_force, weight=-0.005,
            params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names=FOOT_BODY),
                    "force_soft": 650.0, "cap_over": 1500.0})
        # ★ no knee hyperextension (knee 0..-10deg forbidden mid-walk -- stated hard requirement; only fires near the limit)
        self.rewards.knee_straight = RewTerm(
            func=pyg_rewards.knee_straight_penalty, weight=-5.0,
            params={"asset_cfg": SceneEntityCfg("robot", joint_names=[".*_knee_joint"]), "min_flexion": -0.17})


@configclass
class BipedG1ImpactEnvCfg_PLAY(BipedG1ImpactEnvCfg):
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


# ============================================================================================
# ★ G1 + impact + VERIFIED anti-trembling/saturation fixes (user 2026-06-28).
#   ROOT-CAUSE research docs/reward_research/2026-06-28_g1_trembling_saturation: vanilla G1 EXCLUDED the ankle
#   from dof_acc (-> high-freq foot buzz = 발 떨림) + weak action_rate; our gaitfix INCLUDED ankle dof_acc -3e-7
#   + action_rate -0.01 and measured 2-3x less torque chatter. FIX = include ankle in dof_acc(-3e-7) + action_rate
#   -0.01. Saturation handled STRUCTURALLY by the ankle_roll RS00->DM-J4340-2EC upgrade (clip 14->40, rated 5->14).
#   Terrain-agnostic helper -> identical reward on FLAT + ROUGH (obs match, 239-dim) so flat ckpt transfers.
# ============================================================================================
def _apply_g1_impact_stable(env):
    """Full G1-vanilla reward swap + impact terms + verified anti-trembling fixes. Terrain-agnostic (flat/rough)."""
    env.rewards = G1VanillaRewards()
    env.rewards.lin_vel_z_l2.weight = 0.0
    env.rewards.undesired_contacts = None
    env.rewards.flat_orientation_l2.weight = -1.0
    # ★ anti-trembling (verified, gaitfix-proven values): ankle INCLUDED in dof_acc + stronger action_rate
    env.rewards.action_rate_l2.weight = -0.01
    env.rewards.dof_acc_l2.weight = -3.0e-7
    env.rewards.dof_acc_l2.params["asset_cfg"] = SceneEntityCfg(
        "robot", joint_names=[".*_hip_.*", ".*_knee_joint", ".*_ankle_.*"])
    env.rewards.dof_torques_l2.weight = -1.5e-7
    env.rewards.dof_torques_l2.params["asset_cfg"] = SceneEntityCfg(
        "robot", joint_names=[".*_hip_.*", ".*_knee_joint", ".*_ankle_.*"])
    # impact reduction + knee protection (HW survival 1.5-2.7 kN)
    env.rewards.foot_landing_vel = RewTerm(
        func=pyg_rewards.foot_landing_vel, weight=-1.0,
        params={"asset_cfg": SceneEntityCfg("robot", body_names=FOOT_BODY), "height_thresh": 0.12})
    env.rewards.foot_impact_force = RewTerm(
        func=pyg_rewards.foot_impact_force, weight=-0.005,
        params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names=FOOT_BODY),
                "force_soft": 650.0, "cap_over": 1500.0})
    env.rewards.knee_straight = RewTerm(
        func=pyg_rewards.knee_straight_penalty, weight=-5.0,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=[".*_knee_joint"]), "min_flexion": -0.17})
    # ★ anti-tiptoe/anti-shuffle (docs/reward_research/2026-06-28_heeltoe_stride_fix): swing-foot clearance.
    #   A tiptoe/shuffle can't satisfy a swing-height target -> forces a real full-foot lift + longer stride
    #   (Unitree G1 feet_swing_height -20). h_target = standing foot_link z (~0.07) + ~0.06 clearance; verify config-test.
    env.rewards.feet_swing_height = RewTerm(
        func=pyg_rewards.feet_swing_height, weight=-20.0,
        params={"asset_cfg": SceneEntityCfg("robot", body_names=FOOT_BODY),
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=FOOT_BODY), "h_target": 0.12})
    env.rewards.feet_air_time.weight = 0.0   # demote (dead at +0.009; swing_height carries the stride, as in G1)
    # G1 conditions: forward-only commands + light DR (matches the G1 baseline)
    env.curriculum.command_vel_x = None
    env.commands.base_velocity.ranges.lin_vel_x = (0.0, 1.0)
    env.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
    env.commands.base_velocity.ranges.ang_vel_z = (-1.0, 1.0)
    env.events.push_robot = None
    env.events.add_base_mass = None
    env.events.base_com = None
    env.events.reset_robot_joints.params["position_range"] = (1.0, 1.0)


def _play_overrides(env):
    env.scene.num_envs = 32
    env.scene.env_spacing = 2.5
    env.episode_length_s = 40.0
    env.scene.terrain.max_init_terrain_level = None
    if env.scene.terrain.terrain_generator is not None:
        env.scene.terrain.terrain_generator.num_rows = 5
        env.scene.terrain.terrain_generator.num_cols = 5
        env.scene.terrain.terrain_generator.curriculum = False
    env.observations.policy.enable_corruption = False
    env.events.base_external_force_torque = None
    env.events.push_robot = None
    env.events.add_base_mass = None
    env.events.base_com = None
    env.events.physics_material.params["static_friction_range"] = (0.9, 0.9)
    env.events.physics_material.params["dynamic_friction_range"] = (0.7, 0.7)


@configclass
class BipedG1ImpactStableEnvCfg(BipedFlatEnvCfg):
    """FLAT: G1 + impact + verified anti-trembling/saturation fixes (user 2026-06-28). Train FIRST; transfer to rough."""
    def __post_init__(self):
        super().__post_init__()
        _apply_g1_impact_stable(self)


@configclass
class BipedG1ImpactStableEnvCfg_PLAY(BipedG1ImpactStableEnvCfg):
    def __post_init__(self):
        super().__post_init__()
        _play_overrides(self)


@configclass
class BipedG1ImpactStableRoughEnvCfg(BipedRoughEnvCfg):
    """ROUGH: same G1 + impact + anti-trembling reward; resume from the FLAT checkpoint (obs match, 239-dim)."""
    def __post_init__(self):
        super().__post_init__()
        _apply_g1_impact_stable(self)


@configclass
class BipedG1ImpactStableRoughEnvCfg_PLAY(BipedG1ImpactStableRoughEnvCfg):
    def __post_init__(self):
        super().__post_init__()
        _play_overrides(self)


# ============================================================================================
# ★ OBS RESTRUCTURING (Menlo/Asimov blog review 2026-06-28, docs/reward_research/2026-06-28_menlo_blog_review).
#   Asymmetric actor-critic (Pinto 2017 / Lee 2020 / Berkeley 2024): ACTOR = proprioception only — NO base_lin_vel
#   (deployable; not memoryless-reliant on ground-truth velocity), scoped to ACTUATED_JOINTS so the encoder-less
#   passive TOE stops leaking (verified leak), + 5-step history (Walk-These-Ways: history estimates velocity, so
#   removing base_lin_vel doesn't kill tracking). CRITIC = full obs + privileged base_lin_vel + passive-toe state.
#   rsl_rl 2.3.3: the critic group MUST be named `critic` (auto-detected); the obs_groups API does NOT exist here.
# ============================================================================================
@configclass
class AsymObservationsCfg:
    @configclass
    class PolicyCfg(ObsGroup):
        base_ang_vel = ObsTerm(func=mdp.base_ang_vel, noise=Unoise(n_min=-0.2, n_max=0.2),
                               history_length=5, flatten_history_dim=True)
        projected_gravity = ObsTerm(func=mdp.projected_gravity, noise=Unoise(n_min=-0.05, n_max=0.05),
                                    history_length=5, flatten_history_dim=True)
        velocity_commands = ObsTerm(func=mdp.generated_commands, params={"command_name": "base_velocity"})
        joint_pos = ObsTerm(func=mdp.joint_pos_rel,
                            params={"asset_cfg": SceneEntityCfg("robot", joint_names=ACTUATED_JOINTS)},
                            noise=Unoise(n_min=-0.01, n_max=0.01), history_length=5, flatten_history_dim=True)
        joint_vel = ObsTerm(func=mdp.joint_vel_rel,
                            params={"asset_cfg": SceneEntityCfg("robot", joint_names=ACTUATED_JOINTS)},
                            noise=Unoise(n_min=-1.5, n_max=1.5), history_length=5, flatten_history_dim=True)
        actions = ObsTerm(func=mdp.last_action, history_length=5, flatten_history_dim=True)
        height_scan = ObsTerm(func=mdp.height_scan, params={"sensor_cfg": SceneEntityCfg("height_scanner")},
                              noise=Unoise(n_min=-0.1, n_max=0.1), clip=(-1.0, 1.0))

        def __post_init__(self):
            self.enable_corruption = True
            self.concatenate_terms = True

    @configclass
    class CriticCfg(ObsGroup):
        base_lin_vel = ObsTerm(func=mdp.base_lin_vel)          # ★ privileged (ground-truth)
        base_ang_vel = ObsTerm(func=mdp.base_ang_vel)
        projected_gravity = ObsTerm(func=mdp.projected_gravity)
        velocity_commands = ObsTerm(func=mdp.generated_commands, params={"command_name": "base_velocity"})
        joint_pos = ObsTerm(func=mdp.joint_pos_rel)           # ALL joints incl passive toe (privileged)
        joint_vel = ObsTerm(func=mdp.joint_vel_rel)
        actions = ObsTerm(func=mdp.last_action)
        height_scan = ObsTerm(func=mdp.height_scan, params={"sensor_cfg": SceneEntityCfg("height_scanner")},
                              clip=(-1.0, 1.0))

        def __post_init__(self):
            self.enable_corruption = False                     # critic sees clean ground truth
            self.concatenate_terms = True

    policy: PolicyCfg = PolicyCfg()
    critic: CriticCfg = CriticCfg()


@configclass
class BipedG1ImpactStableAsymObsEnvCfg(BipedG1ImpactStableEnvCfg):
    """FLAT: G1ImpactStable + Menlo-validated obs restructuring (asym actor-critic, base_lin_vel & toe critic-only,
    5-step history). A/B vs the stock-obs baseline (g1is_dm4340_flat). NOTE: obs-dim change -> from-scratch retrain."""
    def __post_init__(self):
        super().__post_init__()
        self.observations = AsymObservationsCfg()


@configclass
class BipedG1ImpactStableAsymObsEnvCfg_PLAY(BipedG1ImpactStableAsymObsEnvCfg):
    def __post_init__(self):
        super().__post_init__()
        _play_overrides(self)


@configclass
class BipedG1ImpactStableAsymObsRoughEnvCfg(BipedG1ImpactStableRoughEnvCfg):
    """ROUGH: same obs restructuring; resume from the FLAT asym-obs checkpoint (obs match)."""
    def __post_init__(self):
        super().__post_init__()
        self.observations = AsymObservationsCfg()


@configclass
class BipedG1ImpactStableAsymObsRoughEnvCfg_PLAY(BipedG1ImpactStableAsymObsRoughEnvCfg):
    def __post_init__(self):
        super().__post_init__()
        _play_overrides(self)
