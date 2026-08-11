"""Rewards, schedule, and curriculum for periodic single-leg hopping."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, TypedDict

import torch

from mjlab.managers.event_manager import requires_model_fields
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import ContactSensor, TerrainHeightSensor

if TYPE_CHECKING:
  from mjlab.envs import ManagerBasedRlEnv
  from mjlab.managers.curriculum_manager import CurriculumTermCfg

# Final hop timing / peak clearance (curriculum end).
FINAL_STANCE_S = 1.5
FINAL_FLIGHT_S = 0.45
FINAL_CLEARANCE_M = 0.20
HIGH_CLEARANCE_BONUS_M = 0.20

# Training starts easy: stand a few seconds, then one short hop, repeat.
DEFAULT_STANCE_S = 5.0
DEFAULT_FLIGHT_S = 0.225
DEFAULT_CLEARANCE_M = 0.05


class HopScheduleStage(TypedDict, total=False):
  step: int
  stance_s: float
  flight_s: float
  push_xy: float
  clearance_m: float


def _resolve_hop_stage(
  stages: list[HopScheduleStage], step_counter: int
) -> tuple[float, float, float, float]:
  stance_s = DEFAULT_STANCE_S
  flight_s = DEFAULT_FLIGHT_S
  push_xy = 0.0
  clearance_m = DEFAULT_CLEARANCE_M
  for stage in stages:
    if step_counter >= stage["step"]:
      if "stance_s" in stage:
        stance_s = float(stage["stance_s"])
      if "flight_s" in stage:
        flight_s = float(stage["flight_s"])
      if "push_xy" in stage:
        push_xy = float(stage["push_xy"])
      if "clearance_m" in stage:
        clearance_m = float(stage["clearance_m"])
  return stance_s, flight_s, push_xy, clearance_m


def _ensure_hop_timing(env: ManagerBasedRlEnv) -> tuple[float, float, float]:
  """Return (stance_s, flight_s, clearance_m), synced to ``common_step_counter``.

  Play restores the counter from the checkpoint after env construction, so we
  re-resolve on every call instead of trusting a one-shot curriculum apply.
  """
  stages = getattr(env, "hop_schedule_stages", None)
  if stages is not None:
    stance_s, flight_s, _, clearance_m = _resolve_hop_stage(
      stages, env.common_step_counter
    )
    env.hop_stance_s = stance_s
    env.hop_flight_s = flight_s
    env.hop_clearance_m = clearance_m
    return stance_s, flight_s, clearance_m
  stance = float(getattr(env, "hop_stance_s", DEFAULT_STANCE_S))
  flight = float(getattr(env, "hop_flight_s", DEFAULT_FLIGHT_S))
  clearance = float(getattr(env, "hop_clearance_m", DEFAULT_CLEARANCE_M))
  return stance, flight, clearance


def hop_phase(env: ManagerBasedRlEnv) -> torch.Tensor:
  """Normalized hop phase in ``[0, 1)``.

  Cycle is stance-first, then flight:
  ``[0, stance_frac)`` = foot down, ``[stance_frac, 1)`` = hop.
  """
  stance_s, flight_s, _ = _ensure_hop_timing(env)
  period = max(stance_s + flight_s, 1e-6)
  t = env.episode_length_buf.float() * env.step_dt
  return torch.remainder(t, period) / period


def hop_phase_obs(env: ManagerBasedRlEnv) -> torch.Tensor:
  """Clock observation ``[sin(2πφ), cos(2πφ)]`` for the hop schedule."""
  phase = hop_phase(env) * (2.0 * math.pi)
  return torch.stack((torch.sin(phase), torch.cos(phase)), dim=-1)


def _in_flight_mask(env: ManagerBasedRlEnv) -> torch.Tensor:
  stance_s, flight_s, _ = _ensure_hop_timing(env)
  period = max(stance_s + flight_s, 1e-6)
  stance_frac = stance_s / period
  return hop_phase(env) >= stance_frac


def scheduled_clearance(env: ManagerBasedRlEnv) -> torch.Tensor:
  """Target foot clearance for the current hop phase."""
  stance_s, flight_s, clearance_m = _ensure_hop_timing(env)
  period = max(stance_s + flight_s, 1e-6)
  stance_frac = stance_s / period
  phase = hop_phase(env)
  in_flight = phase >= stance_frac
  # Progress within the flight window → half-sine peaking at clearance_m.
  s = ((phase - stance_frac) / max(1.0 - stance_frac, 1e-6)).clamp(0.0, 1.0)
  height = clearance_m * torch.sin(math.pi * s)
  return torch.where(in_flight, height, torch.zeros_like(height))


def hop_clearance_reward(
  env: ManagerBasedRlEnv,
  height_sensor_name: str = "foot_height_scan",
  std: float = 0.02,
) -> torch.Tensor:
  """Gaussian reward for matching the scheduled hop clearance."""
  height_sensor = env.scene[height_sensor_name]
  assert isinstance(height_sensor, TerrainHeightSensor), (
    f"hop_clearance_reward requires TerrainHeightSensor, got {type(height_sensor)}"
  )
  foot_height = height_sensor.data.heights  # [B, F]
  target = scheduled_clearance(env).unsqueeze(-1)  # [B, 1]
  error_sq = torch.square(foot_height - target)
  return torch.mean(torch.exp(-error_sq / (std**2)), dim=-1)


def hop_phase_contact_reward(
  env: ManagerBasedRlEnv,
  sensor_name: str = "foot_ground_contact",
) -> torch.Tensor:
  """Reward contact during stance and airtime during flight."""
  sensor: ContactSensor = env.scene[sensor_name]
  found = sensor.data.found
  assert found is not None
  in_contact = (found > 0).any(dim=-1).float()  # [B]
  in_flight = _in_flight_mask(env).float()
  in_stance = 1.0 - in_flight
  return in_flight * (1.0 - in_contact) + in_stance * in_contact


def hop_air_time_reward(
  env: ManagerBasedRlEnv,
  sensor_name: str = "foot_ground_contact",
  threshold_min: float = 0.12,
  threshold_max: float = 0.55,
) -> torch.Tensor:
  """Reward air time in a window consistent with taller scheduled hops."""
  sensor: ContactSensor = env.scene[sensor_name]
  current_air_time = sensor.data.current_air_time
  assert current_air_time is not None
  in_range = (current_air_time > threshold_min) & (current_air_time < threshold_max)
  # Only credit air-time while the schedule is in flight (avoids rewarding falls).
  in_flight = _in_flight_mask(env).unsqueeze(-1)
  return torch.mean((in_range & in_flight).float(), dim=-1)


def high_clearance_bonus(
  env: ManagerBasedRlEnv,
  height_sensor_name: str = "foot_height_scan",
  threshold: float = HIGH_CLEARANCE_BONUS_M,
) -> torch.Tensor:
  """Binary bonus when foot clearance reaches ``threshold`` (default 20 cm)."""
  height_sensor = env.scene[height_sensor_name]
  assert isinstance(height_sensor, TerrainHeightSensor), (
    f"high_clearance_bonus requires TerrainHeightSensor, got {type(height_sensor)}"
  )
  foot_height = height_sensor.data.heights  # [B, F]
  return (foot_height >= threshold).any(dim=-1).float()


def base_xy_drift_penalty(
  env: ManagerBasedRlEnv,
  asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
  """Soft XY drift penalty (tanh-bounded so falls don't dominate the return)."""
  asset = env.scene[asset_cfg.name]
  xy = asset.data.root_link_pos_w[:, :2]
  return torch.tanh(torch.sum(torch.square(xy), dim=-1))


@requires_model_fields("geom_friction")
def ground_friction_scale(
  env: ManagerBasedRlEnv,
  env_ids: torch.Tensor | None,
  ranges: tuple[float, float] = (0.5, 1.5),
) -> None:
  """Scale ground + foot sliding friction by the same factor in ``ranges``.

  MuJoCo combines contact friction from both geoms, so terrain and foot are
  scaled together (shared draw per env) to keep the 50–150% range effective.
  """
  from mjlab.envs.mdp.dr._core import _get_entity_indices, _select_default_values

  if env_ids is None:
    env_ids = torch.arange(env.num_envs, device=env.device, dtype=torch.int)
  else:
    env_ids = env_ids.to(env.device, dtype=torch.int)

  lo, hi = float(ranges[0]), float(ranges[1])
  scales = (hi - lo) * torch.rand(env_ids.shape[0], device=env.device) + lo

  for name, geom_names in (
    ("terrain", ("terrain",)),
    ("robot", ("foot_collision",)),
  ):
    asset_cfg = SceneEntityCfg(name, geom_names=geom_names)
    asset_cfg.resolve(env.scene)
    entity_indices = _get_entity_indices(
      env.scene[name].indexing, asset_cfg, "geom", False
    )
    env_grid, entity_grid = torch.meshgrid(env_ids, entity_indices, indexing="ij")
    base = _select_default_values(env, "geom_friction", env_ids, entity_indices)
    env.sim.model.geom_friction[env_grid, entity_grid, 0] = base[..., 0] * scales[
      :, None
    ]


def joint_torque_excess_penalty(
  env: ManagerBasedRlEnv,
  threshold: float = 0.9,
  asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
  """Penalise |τ|/τ_lim above ``threshold`` (default 90%).

  Per-step cost = Σ_j max(|τ_j|/τ_lim_j − threshold, 0). Each joint at full
  saturation contributes ``1 − threshold`` (0.1 at the default). Uses each
  actuator's ``forcerange`` so ankle±14 / hip-knee±17 are respected.
  """
  del asset_cfg  # all robot actuators; entity already exposes the 6 motors
  asset = env.scene["robot"]
  torque = asset.data.actuator_force  # [B, nu]
  limits = torch.as_tensor(
    env.sim.mj_model.actuator_forcerange[:, 1],
    device=torque.device,
    dtype=torque.dtype,
  )
  excess = torch.clamp(torque.abs() / limits.clamp(min=1e-6) - threshold, min=0.0)
  return excess.sum(dim=-1)


def _knee_joint_q_qd(
  env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg
) -> tuple[torch.Tensor, torch.Tensor]:
  asset = env.scene[asset_cfg.name]
  # joint_ids resolved by manager; fall back to name lookup if needed.
  joint_ids = asset_cfg.joint_ids
  q = asset.data.joint_pos[:, joint_ids]
  qd = asset.data.joint_vel[:, joint_ids]
  if q.ndim == 2 and q.shape[-1] == 1:
    q = q.squeeze(-1)
    qd = qd.squeeze(-1)
  return q, qd


def knee_prejump_flexion_reward(
  env: ManagerBasedRlEnv,
  asset_cfg: SceneEntityCfg = SceneEntityCfg("robot", joint_names=("knee_pitch_joint",)),
  target_angle: float = 0.70,
  std: float = 0.25,
  late_stance_frac: float = 0.30,
) -> torch.Tensor:
  """(1) Late-stance: match a crouched knee angle before takeoff.

  ``knee_pitch`` is 0 when straight and positive when flexed. Default target
  ≈ 40°. Only active in the last ``late_stance_frac`` of the stance window.
  """
  stance_s, flight_s, _ = _ensure_hop_timing(env)
  period = max(stance_s + flight_s, 1e-6)
  stance_frac = stance_s / period
  phase = hop_phase(env)
  late_start = stance_frac * (1.0 - late_stance_frac)
  in_late_stance = (phase >= late_start) & (phase < stance_frac)

  q_knee, _ = _knee_joint_q_qd(env, asset_cfg)
  tracking = torch.exp(-torch.square(q_knee - target_angle) / (std**2))
  return torch.where(in_late_stance, tracking, torch.zeros_like(tracking))


def knee_extend_push_reward(
  env: ManagerBasedRlEnv,
  asset_cfg: SceneEntityCfg = SceneEntityCfg("robot", joint_names=("knee_pitch_joint",)),
  early_flight_frac: float = 0.45,
  vel_scale: float = 4.0,
) -> torch.Tensor:
  """(2) Early-flight: reward knee extension (negative ``q̇``) after crouch.

  Pairs with :func:`knee_prejump_flexion_reward` as crouch → extend.
  """
  stance_s, flight_s, _ = _ensure_hop_timing(env)
  period = max(stance_s + flight_s, 1e-6)
  stance_frac = stance_s / period
  phase = hop_phase(env)
  flight_prog = ((phase - stance_frac) / max(1.0 - stance_frac, 1e-6)).clamp(0.0, 1.0)
  in_early_flight = (phase >= stance_frac) & (flight_prog < early_flight_frac)

  _, qd_knee = _knee_joint_q_qd(env, asset_cfg)
  # Flexion-positive joint: extending ⇒ qd < 0.
  extend = torch.clamp(-qd_knee, min=0.0) / vel_scale
  extend = extend.clamp(0.0, 1.0)
  return torch.where(in_early_flight, extend, torch.zeros_like(extend))


class hop_schedule_curriculum:
  """Shorten stance, raise peak clearance (up to 10 cm), and ramp push.

  ``step`` is ``common_step_counter`` (≈ learning_iteration × num_steps_per_env).
  """

  def __init__(self, cfg: CurriculumTermCfg, env: ManagerBasedRlEnv):
    stages: list[HopScheduleStage] = cfg.params["stages"]
    self._stages = stages
    env.hop_schedule_stages = stages
    self._apply(env, 0)

  def __call__(
    self,
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    stages: list[HopScheduleStage],
  ) -> dict[str, torch.Tensor]:
    del env_ids, stages
    return self._apply(env, env.common_step_counter)

  def _apply(
    self, env: ManagerBasedRlEnv, step_counter: int
  ) -> dict[str, torch.Tensor]:
    stance_s, flight_s, push_xy, clearance_m = _resolve_hop_stage(
      self._stages, step_counter
    )
    env.hop_schedule_stages = self._stages
    env.hop_stance_s = stance_s
    env.hop_flight_s = flight_s
    env.hop_clearance_m = clearance_m

    try:
      push_cfg = env.event_manager.get_term_cfg("push_robot")
    except ValueError:
      push_cfg = None
    if push_cfg is not None:
      push_cfg.params["velocity_range"] = {
        "x": (-push_xy, push_xy),
        "y": (-push_xy, push_xy),
      }

    return {
      "stance_s": torch.tensor(stance_s),
      "flight_s": torch.tensor(flight_s),
      "push_xy": torch.tensor(push_xy),
      "clearance_m": torch.tensor(clearance_m),
    }
