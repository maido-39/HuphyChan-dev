"""Half Huphy single-leg balance environment configuration.

Starts from the zero standing pose and trains a policy to stay upright.
Falling over or dropping the base below a height threshold ends the episode.
Body-link relative positions in the MJCF are left unchanged; only the free-base
spawn height is set so the foot plants on the flat ground.
"""

from __future__ import annotations

import math

from mjlab.asset_zoo.robots.half_huphy.half_huphy_constants import (
  HALF_HUPHY_ACTION_SCALE,
  JOINT_NAMES,
  STAND_BASE_HEIGHT,
  get_half_huphy_robot_cfg,
)
from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp import dr
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.managers.action_manager import ActionTermCfg
from mjlab.managers.event_manager import EventTermCfg
from mjlab.managers.observation_manager import ObservationGroupCfg, ObservationTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.managers.termination_manager import TerminationTermCfg
from mjlab.scene import SceneCfg
from mjlab.sim import MujocoCfg, SimulationCfg
from mjlab.tasks.velocity import mdp as vel_mdp
from mjlab.terrains import TerrainEntityCfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise
from mjlab.viewer import ViewerConfig

# Exclude the floating-base freejoint from joint-property DR.
_ACTUATED_JOINTS = SceneEntityCfg("robot", joint_names=JOINT_NAMES)
_ALL_ACTUATORS = SceneEntityCfg("robot", actuator_names=(".*",))


def half_huphy_balance_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
  """Create the flat-ground single-leg balance task."""
  robot_cfg = get_half_huphy_robot_cfg()

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
      scale=HALF_HUPHY_ACTION_SCALE,
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
    # Instantaneous base velocity kick (~2.0 m/s horizontal), every 1–3 s.
    "push_robot": EventTermCfg(
      func=envs_mdp.push_by_setting_velocity,
      mode="interval",
      interval_range_s=(1.0, 3.0),
      params={
        "velocity_range": {
          "x": (-2.0, 2.0),
          "y": (-2.0, 2.0),
        },
      },
    ),
    # XML defaults: kp=20, kv=0.502, armature=0.003, frictionloss=0.125, damping=0.
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
    # Default joint damping is 0, so scale would stay 0. Use absolute Nm·s/rad.
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

  rewards = {
    # Sparse survival signal: stay alive until timeout.
    "is_alive": RewardTermCfg(func=envs_mdp.is_alive, weight=1.0),
    # Keep base upright relative to world gravity.
    "upright": RewardTermCfg(
      func=vel_mdp.upright,
      weight=1.0,
      params={
        "std": math.sqrt(0.2),
        "asset_cfg": SceneEntityCfg("robot", body_names=("base_link",)),
      },
    ),
    "action_rate_l2": RewardTermCfg(func=envs_mdp.action_rate_l2, weight=-0.01),
  }

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

  cfg = ManagerBasedRlEnvCfg(
    scene=SceneCfg(
      terrain=TerrainEntityCfg(terrain_type="plane"),
      entities={"robot": robot_cfg},
      num_envs=1,
      extent=2.0,
    ),
    observations=observations,
    actions=actions,
    events=events,
    rewards=rewards,
    terminations=terminations,
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
    episode_length_s=10.0,
  )

  if play:
    # Keep training-like ±20° joint init + push disturbances for stress tests.
    # Only drop actuator DR and observation noise for cleaner viewing.
    cfg.episode_length_s = int(1e9)
    cfg.observations["actor"].enable_corruption = False
    for name in (
      "pd_gains",
      "joint_armature",
      "joint_frictionloss",
      "joint_damping",
    ):
      cfg.events.pop(name, None)

  return cfg
