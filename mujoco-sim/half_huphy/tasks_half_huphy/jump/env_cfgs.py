"""Half Huphy in-place hop environment.

Stance-first hop schedule with a 5 cm peak clearance target. Training starts
with long standing gaps between hops (balance first), then shortens stance
time via curriculum toward continuous hopping. Policy observes ``sin/cos`` of
the hop phase.
"""

from __future__ import annotations

import math

from mjlab.asset_zoo.robots.half_huphy.half_huphy_constants import (
  JOINT_NAMES,
  STAND_BASE_HEIGHT,
  get_half_huphy_ankle14_robot_cfg,
  get_half_huphy_robot_cfg,
)

# Larger than balance (0.25): raw±1 ≈ ±28.6° so knee crouch is reachable.
_JUMP_ACTION_SCALE = 0.5
from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp import dr
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.managers.action_manager import ActionTermCfg
from mjlab.managers.curriculum_manager import CurriculumTermCfg
from mjlab.managers.event_manager import EventTermCfg
from mjlab.managers.observation_manager import ObservationGroupCfg, ObservationTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.managers.termination_manager import TerminationTermCfg
from mjlab.scene import SceneCfg
from mjlab.sensor import (
  ContactMatch,
  ContactSensorCfg,
  ObjRef,
  RingPatternCfg,
  TerrainHeightSensorCfg,
)
from mjlab.sim import MujocoCfg, SimulationCfg
from mjlab.tasks.half_huphy.jump import mdp as jump_mdp
from mjlab.tasks.velocity import mdp as vel_mdp
from mjlab.terrains import TerrainEntityCfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise
from mjlab.viewer import ViewerConfig

_ACTUATED_JOINTS = SceneEntityCfg("robot", joint_names=JOINT_NAMES)
_ALL_ACTUATORS = SceneEntityCfg("robot", actuator_names=(".*",))

# common_step_counter ≈ learning_iteration × num_steps_per_env (24).
_STEPS = 24


_KNEE_JOINT = SceneEntityCfg("robot", joint_names=("knee_pitch_joint",))


def half_huphy_jump_env_cfg(
  play: bool = False,
  *,
  knee_crouch: bool = False,
  knee_target_deg: float = 40.0,
  knee_extend_vel_scale: float = 4.0,
  ankle14: bool = False,
  torque_softlimit: bool = False,
  push_xy_scale: float = 1.0,
  ground_friction_dr: bool = False,
) -> ManagerBasedRlEnvCfg:
  """Create the flat-ground single-leg hop task.

  Args:
    play: Disable DR / noise for visualization.
    knee_crouch: Add explicit pre-jump knee flexion + early-flight extend rewards.
    knee_target_deg: Late-stance knee flexion target (degrees).
    knee_extend_vel_scale: Extension speed (rad/s) for full ``knee_extend_push`` reward.
    ankle14: Use ankle motors at ±14 Nm, armature 0.002, frictionloss 0.116.
      DR still scales armature/friction by 0.5–1.5 from those baselines.
    torque_softlimit: Penalise |τ|/τ_lim above 90% (weight matches hop_clearance).
    push_xy_scale: Multiplier on hop-schedule push amplitudes (2.0 → max ±1.0 m/s).
    ground_friction_dr: Scale ground/foot sliding friction by 0.5–1.5 on reset.
  """
  robot_cfg = (
    get_half_huphy_ankle14_robot_cfg() if ankle14 else get_half_huphy_robot_cfg()
  )

  foot_height_scan = TerrainHeightSensorCfg(
    name="foot_height_scan",
    frame=(ObjRef(type="site", name="foot", entity="robot"),),
    ray_alignment="yaw",
    pattern=RingPatternCfg.single_ring(radius=0.02, num_samples=4),
    max_distance=1.0,
    exclude_parent_body=True,
    include_geom_groups=(0,),
    debug_vis=True,
  )
  foot_ground_cfg = ContactSensorCfg(
    name="foot_ground_contact",
    primary=ContactMatch(
      mode="subtree",
      pattern=r"^foot_link_1$",
      entity="robot",
    ),
    secondary=ContactMatch(mode="body", pattern="terrain"),
    fields=("found", "force"),
    reduce="netforce",
    num_slots=1,
    track_air_time=True,
  )

  actor_terms = {
    "base_ang_vel": ObservationTermCfg(
      func=envs_mdp.builtin_sensor,
      params={"sensor_name": "robot/imu_ang_vel"},
      noise=Unoise(n_min=-0.2, n_max=0.2),
    ),
    "projected_gravity": ObservationTermCfg(
      func=envs_mdp.projected_gravity,
      noise=Unoise(n_min=-0.05, n_max=0.05),
    ),
    "joint_pos": ObservationTermCfg(
      func=envs_mdp.joint_pos_rel,
      noise=Unoise(n_min=-0.01, n_max=0.01),
    ),
    "joint_vel": ObservationTermCfg(
      func=envs_mdp.joint_vel_rel,
      noise=Unoise(n_min=-1.5, n_max=1.5),
    ),
    "actions": ObservationTermCfg(func=envs_mdp.last_action),
    # Gait-clock style hop schedule for the policy.
    "hop_phase": ObservationTermCfg(func=jump_mdp.hop_phase_obs),
  }

  observations = {
    "actor": ObservationGroupCfg(
      terms=actor_terms,
      concatenate_terms=True,
      enable_corruption=True,
    ),
    "critic": ObservationGroupCfg(
      terms={
        **actor_terms,
        "base_lin_vel": ObservationTermCfg(
          func=envs_mdp.builtin_sensor,
          params={"sensor_name": "robot/imu_lin_vel"},
        ),
      },
      concatenate_terms=True,
      enable_corruption=False,
    ),
  }

  actions: dict[str, ActionTermCfg] = {
    "joint_pos": JointPositionActionCfg(
      entity_name="robot",
      actuator_names=(".*",),
      scale=_JUMP_ACTION_SCALE,
      use_default_offset=True,
    )
  }

  events = {
    "reset_base": EventTermCfg(
      func=envs_mdp.reset_root_state_uniform,
      mode="reset",
      params={
        "pose_range": {
          "x": (-0.05, 0.05),
          "y": (-0.05, 0.05),
          "z": (0.0, 0.02),
          "roll": (-0.05, 0.05),
          "pitch": (-0.05, 0.05),
          "yaw": (-0.2, 0.2),
        },
        "velocity_range": {
          "x": (-0.1, 0.1),
          "y": (-0.1, 0.1),
          "z": (-0.05, 0.05),
          "roll": (-0.2, 0.2),
          "pitch": (-0.2, 0.2),
          "yaw": (-0.2, 0.2),
        },
      },
    ),
    # Randomize each actuated joint ±20° from the straight (0) pose, then clamp
    # to soft joint limits (e.g. knee_pitch cannot go below 0).
    "reset_robot_joints": EventTermCfg(
      func=envs_mdp.reset_joints_by_offset,
      mode="reset",
      params={
        "position_range": (-math.radians(20.0), math.radians(20.0)),
        "velocity_range": (0.0, 0.0),
        "asset_cfg": _ACTUATED_JOINTS,
      },
    ),
    # Push amplitude is curriculum-ramped (base ends at ±0.5 m/s; see push_xy_scale).
    "push_robot": EventTermCfg(
      func=envs_mdp.push_by_setting_velocity,
      mode="interval",
      interval_range_s=(1.0, 3.0),
      params={
        "velocity_range": {
          "x": (0.0, 0.0),
          "y": (0.0, 0.0),
        },
      },
    ),
    "pd_gains": EventTermCfg(
      mode="reset",
      func=dr.pd_gains,
      params={
        "asset_cfg": _ALL_ACTUATORS,
        "kp_range": (0.8, 1.2),
        "kd_range": (0.8, 1.2),
        "operation": "scale",
        "distribution": "uniform",
      },
    ),
    "joint_armature": EventTermCfg(
      mode="reset",
      func=dr.joint_armature,
      params={
        "asset_cfg": _ACTUATED_JOINTS,
        "operation": "scale",
        "ranges": (0.5, 1.5),
        "distribution": "uniform",
      },
    ),
    "joint_frictionloss": EventTermCfg(
      mode="reset",
      func=dr.joint_friction,
      params={
        "asset_cfg": _ACTUATED_JOINTS,
        "operation": "scale",
        "ranges": (0.5, 1.5),
        "distribution": "uniform",
      },
    ),
    "joint_damping": EventTermCfg(
      mode="reset",
      func=dr.joint_damping,
      params={
        "asset_cfg": _ACTUATED_JOINTS,
        "operation": "abs",
        "ranges": (0.0, 0.1),
        "distribution": "uniform",
      },
    ),
  }
  if ground_friction_dr:
    events["ground_friction"] = EventTermCfg(
      mode="reset",
      func=jump_mdp.ground_friction_scale,
      params={"ranges": (0.5, 1.5)},
    )

  rewards = {
    "is_alive": RewardTermCfg(func=envs_mdp.is_alive, weight=1.0),
    "upright": RewardTermCfg(
      func=vel_mdp.upright,
      weight=1.0,
      params={
        "std": math.sqrt(0.2),
        "asset_cfg": SceneEntityCfg("robot", body_names=("base_link",)),
      },
    ),
    # Track scheduled peak clearance (curriculum up to 20 cm).
    "hop_clearance": RewardTermCfg(
      func=jump_mdp.hop_clearance_reward,
      weight=3.0,
      params={"height_sensor_name": "foot_height_scan", "std": 0.03},
    ),
    # Flight ↔ air, stance ↔ contact.
    "hop_phase_contact": RewardTermCfg(
      func=jump_mdp.hop_phase_contact_reward,
      weight=2.0,
      params={"sensor_name": "foot_ground_contact"},
    ),
    # Longer air-time window for taller hops (~0.12–0.55 s).
    "hop_air_time": RewardTermCfg(
      func=jump_mdp.hop_air_time_reward,
      weight=1.0,
      params={
        "sensor_name": "foot_ground_contact",
        "threshold_min": 0.12,
        "threshold_max": 0.55,
      },
    ),
    # If foot clears ≥20 cm: 3× sum of current hop weights (3+2+1)*3 = 18.
    "high_clearance_bonus": RewardTermCfg(
      func=jump_mdp.high_clearance_bonus,
      weight=18.0,
      params={
        "height_sensor_name": "foot_height_scan",
        "threshold": jump_mdp.HIGH_CLEARANCE_BONUS_M,
      },
    ),
    # Soft-bounded (tanh); keep light so falls don't dominate the return.
    "xy_drift": RewardTermCfg(
      func=jump_mdp.base_xy_drift_penalty,
      weight=-0.1,
    ),
    "action_rate_l2": RewardTermCfg(func=envs_mdp.action_rate_l2, weight=-0.01),
  }

  if knee_crouch:
    # (1) Late stance: crouch knee toward target angle.
    rewards["knee_prejump_flexion"] = RewardTermCfg(
      func=jump_mdp.knee_prejump_flexion_reward,
      weight=1.5,
      params={
        "asset_cfg": _KNEE_JOINT,
        "target_angle": math.radians(knee_target_deg),
        "std": 0.30,
        "late_stance_frac": 0.30,
      },
    )
    # (2) Early flight: extend knee (negative q̇) after crouch.
    rewards["knee_extend_push"] = RewardTermCfg(
      func=jump_mdp.knee_extend_push_reward,
      weight=1.5,
      params={
        "asset_cfg": _KNEE_JOINT,
        "early_flight_frac": 0.45,
        "vel_scale": knee_extend_vel_scale,
      },
    )

  if torque_softlimit:
    # Soft torque cap: |τ|/τ_lim > 0.9 → proportional penalty.
    # Weight magnitude matches hop_clearance (3.0); one joint at 100% ⇒ −0.3/step.
    rewards["joint_torque_excess"] = RewardTermCfg(
      func=jump_mdp.joint_torque_excess_penalty,
      weight=-3.0,
      params={"threshold": 0.9},
    )

  terminations = {
    "time_out": TerminationTermCfg(func=envs_mdp.time_out, time_out=True),
    "fell_over": TerminationTermCfg(
      func=envs_mdp.bad_orientation,
      params={"limit_angle": math.radians(55.0)},
    ),
    "base_too_low": TerminationTermCfg(
      func=envs_mdp.root_height_below_minimum,
      params={"minimum_height": STAND_BASE_HEIGHT - 0.20},
    ),
  }

  # Stance shortens; peak clearance rises to 20 cm; flight window lengthens.
  # Play keeps the same stages so checkpoint `common_step_counter` selects the
  # phase clock / clearance the policy was trained with.
  hop_stages = [
    {
      "step": 0,
      "stance_s": 5.0,
      "flight_s": 0.225,
      "clearance_m": 0.05,
      "push_xy": 0.0 * push_xy_scale,
    },
    {
      "step": 3_000 * _STEPS,
      "stance_s": 4.0,
      "flight_s": 0.28,
      "clearance_m": 0.10,
      "push_xy": 0.0 * push_xy_scale,
    },
    {
      "step": 6_000 * _STEPS,
      "stance_s": 3.0,
      "flight_s": 0.35,
      "clearance_m": 0.15,
      "push_xy": 0.25 * push_xy_scale,
    },
    {
      "step": 10_000 * _STEPS,
      "stance_s": 1.5,
      "flight_s": 0.45,
      "clearance_m": 0.20,
      "push_xy": 0.5 * push_xy_scale,
    },
  ]
  curriculum = {
    "hop_schedule": CurriculumTermCfg(
      func=jump_mdp.hop_schedule_curriculum,
      params={"stages": hop_stages},
    ),
  }

  cfg = ManagerBasedRlEnvCfg(
    scene=SceneCfg(
      terrain=TerrainEntityCfg(terrain_type="plane"),
      entities={"robot": robot_cfg},
      sensors=(foot_height_scan, foot_ground_cfg),
      num_envs=1,
      extent=2.0,
    ),
    observations=observations,
    actions=actions,
    events=events,
    rewards=rewards,
    terminations=terminations,
    curriculum=curriculum,
    viewer=ViewerConfig(
      origin_type=ViewerConfig.OriginType.ASSET_BODY,
      entity_name="robot",
      body_name="base_link",
      distance=1.5,
      elevation=-10.0,
      azimuth=90.0,
    ),
    sim=SimulationCfg(
      nconmax=40,
      njmax=300,
      mujoco=MujocoCfg(
        timestep=0.005,
        iterations=10,
        ls_iterations=20,
      ),
    ),
    decimation=4,
    # Long enough for a couple of 5 s stand → hop cycles early in curriculum.
    episode_length_s=15.0,
  )

  if play:
    cfg.episode_length_s = int(1e9)
    cfg.observations["actor"].enable_corruption = False
    cfg.events["reset_base"].params["pose_range"] = {
      "x": (0.0, 0.0),
      "y": (0.0, 0.0),
      "z": (0.0, 0.0),
      "yaw": (0.0, 0.0),
    }
    cfg.events["reset_base"].params["velocity_range"] = {}
    cfg.events["reset_robot_joints"].params["position_range"] = (0.0, 0.0)
    for name in (
      "push_robot",
      "pd_gains",
      "joint_armature",
      "joint_frictionloss",
      "joint_damping",
      "ground_friction",
    ):
      cfg.events.pop(name, None)

  return cfg
