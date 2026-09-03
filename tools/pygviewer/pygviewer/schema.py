"""Wire schema v1 - one JSON object per message, canonical names in SIM joint names and SI.

Design rules that are not negotiable, because each one is a sim2real failure we have already
paid for somewhere in this project:

  * **Canonical naming is the sim joint name** (``L_knee_joint``, ``L_crank_A_joint``).  The
    hardware's own limb/motor indices never appear on the wire; the bridge converts.
  * **Units are SI, always rad / rad/s / N*m.**  No degrees on the wire, no auto-unwrap - a
    ``|dq| > pi`` step is flagged, never silently fixed.
  * **Missing is ``null``, never a sentinel.**  HUPHY sends -1.0 for "no data"; the bridge
    turns that into ``null`` and raises a warning on three in a row.
  * **Every message carries ``t_ns`` (sender monotonic), ``seq`` and ``contract_hash``.**
    Without those an overlay of two streams is a guess about time and about which robot.
  * ``tau`` from hardware is a current estimate, so it is labelled ``est.`` at every display
    site; the field name does not lie about it either (``tau_est``).

Implementation status is stated per model below.  P0/P1 implement ``Status``, ``ContractOut``,
``TargetIn``, ``BaseIn``, ``ModeIn`` and the ``JointState`` that ``WS /ws/out`` emits.
``JointTarget``, ``ImuState``, ``PolicyIO``, ``GainsIn`` and ``ObsSourceIn`` are DEFINED and
documented here but their endpoints are P2/P3 - see ``api.py`` and ``API.md``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

WIRE_VERSION = 1

Src = Literal["sim", "real", "policy", "replay", "dummy"]


class Header(BaseModel):
  """Common envelope on every streamed message."""

  v: int = WIRE_VERSION
  type: str
  t_ns: int = Field(description="sender's monotonic clock in nanoseconds")
  seq: int = 0
  src: Src = "sim"
  frame: str = Field(default="model_v30", description="model generation the values belong to")
  contract_hash: str | None = None


class JointState(Header):
  """IMPLEMENTED (out).  The canonical joint vector - sim and real use the same shape.

  ``joint_names`` is always sent so a consumer never has to assume an order.  For the AB
  build the CANONICAL actuated set is hips + knees + cranks; the ankle pitch/roll are
  reported separately in ``ankle_derived`` because on hardware they are computed from the
  crank encoders through the mechanism, not measured.
  """

  type: Literal["JointState"] = "JointState"
  joint_names: list[str]
  q: list[float | None]
  qd: list[float | None] | None = None
  tau_est: list[float | None] | None = Field(
    default=None, description="N*m; from hardware this is a CURRENT ESTIMATE - display as 'est.'"
  )
  target: list[float | None] | None = None
  temp_c: list[float | None] | None = None
  gains: dict[str, Any] | None = Field(
    default=None, description="{joint: {kp, kd, tau_ff, kp_enc_range}} when the source knows them"
  )
  ankle_derived: dict[str, dict[str, float]] | None = Field(
    default=None, description="{'L': {'pitch':rad,'roll':rad}, 'R': ...} - AB only"
  )


class ImuState(Header):
  """DEFINED, P3.  Base IMU as the robot reports it."""

  type: Literal["ImuState"] = "ImuState"
  quat_wxyz: list[float] | None = None
  gyro_rad_s: list[float] | None = None
  acc_m_s2: list[float] | None = None
  gravity_b: list[float] | None = Field(
    default=None, description="gravity in the body frame; derived from quat when absent"
  )
  age_s: float | None = None


class JointTarget(Header):
  """DEFINED AND DOCUMENTED ONLY - **never implemented as an outbound path**.

  The user's decision (docs/121 section 1) is that the viewer receives from the robot and
  does not command it.  This model exists so the wire format is complete and a future
  deployment runtime has an exact contract to implement; ``api.py`` has no route that emits
  it, and ``modes.py`` hard-codes the shadow mode to never transmit.
  """

  type: Literal["JointTarget"] = "JointTarget"
  joint_names: list[str]
  q_target: list[float]
  kp: list[float] | None = None
  kd: list[float] | None = None
  ttl_ms: int = Field(default=100, description="target expires this long after t_ns")


class PolicyIO(Header):
  """DEFINED, P2."""

  type: Literal["PolicyIO"] = "PolicyIO"
  obs: list[float]
  obs_sources: dict[str, Src] = {}
  action: list[float]
  target: list[float]
  cmd: list[float] = Field(default=[0.0, 0.0, 0.0], description="[vx, vy, wz]")


class Rates(BaseModel):
  phys_hz: float = 0.0
  ctrl_hz: float = 0.0
  drops: int = 0
  phys_steps: int = 0


class BaseState(BaseModel):
  mode: Literal["free", "fixed", "pivot"] = "free"
  pos: list[float] = [0.0, 0.0, 0.0]
  quat: list[float] = [1.0, 0.0, 0.0, 0.0]
  rpy: list[float] = [0.0, 0.0, 0.0]
  cmd_pos: list[float] = [0.0, 0.0, 0.0]
  cmd_quat: list[float] = [1.0, 0.0, 0.0, 0.0]
  pivot_offset: list[float] = [0.0, 0.0, 0.0]
  ground: bool = True


class Status(Header):
  """IMPLEMENTED.  Everything a client needs to know whether a number is trustworthy."""

  type: Literal["Status"] = "Status"
  variant: str
  mode: str
  policy: str | None = None
  sim_time_s: float = 0.0
  rates: Rates = Rates()
  base: BaseState = BaseState()
  contract_stale: bool = False
  contract_checks: dict[str, Any] = {}
  telemetry: dict[str, Any] = Field(default={}, description="P3: rx rate, age, clock offset")
  warnings: list[str] = []
  rss_mb: float | None = None


class ContractOut(BaseModel):
  """IMPLEMENTED.  The whole model contract, verbatim, plus its freshness verdict."""

  contract: dict[str, Any]
  freshness: dict[str, Any]


# ----------------------------------------------------------------- request bodies
class TargetIn(BaseModel):
  """IMPLEMENTED.  Joint targets in rad, by canonical name.  Values outside the contract's
  ``safe_clip`` are CLAMPED (not rejected) and the clamped value is echoed back."""

  values: dict[str, float] = Field(
    description="{joint_name: q_target_rad}", examples=[{"L_knee_joint": 0.35}]
  )


class AnkleTargetIn(BaseModel):
  """IMPLEMENTED (AB only).  Foot-space command; converted to cranks by the envelope grid."""

  side: Literal["L", "R"]
  pitch: float = Field(description="ankle pitch [rad]")
  roll: float = Field(description="ankle roll [rad]")


class BaseIn(BaseModel):
  """IMPLEMENTED.  Any subset; omitted fields keep their current value.

  ``mode``: ``free`` (both equalities off) / ``fixed`` (weld: pose fully constrained) /
  ``pivot`` (connect: the point ``pivot_offset`` in the BASE frame is held at ``pos``,
  orientation free under gravity).  Gravity is never modified by any of these.
  """

  mode: Literal["free", "fixed", "pivot"] | None = None
  pos: list[float] | None = None
  quat: list[float] | None = None
  rpy: list[float] | None = None
  height: float | None = None
  pivot_offset: list[float] | None = None
  ground: bool | None = None


class ModeIn(BaseModel):
  """IMPLEMENTED for ``idle``/``manual``.  The rest are P2-P4 and are refused with 501."""

  mode: Literal["idle", "manual", "policy_sim", "policy_shadow", "real_replay", "file_replay"]


class ResetIn(BaseModel):
  keyframe: Literal["home", "knees_bent"] = "knees_bent"


class GainsIn(BaseModel):
  """DEFINED, P2.  Switch the PD source or override per joint."""

  source: Literal["train", "real"] = "train"
  overrides: dict[str, dict[str, float]] = {}


class ObsSourceIn(BaseModel):
  """DEFINED, P4.  Per observation TERM, where its value comes from."""

  sources: dict[str, Src]


class PolicyLoadIn(BaseModel):
  """DEFINED, P2."""

  onnx: str | None = None
  pt: str | None = None
  run_dir: str | None = None
