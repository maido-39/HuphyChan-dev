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
``ImuState``, ``PolicyIO``, ``GainsIn`` and ``ObsSourceIn`` are DEFINED and documented here
but their endpoints are P2/P3 - see ``api.py`` and ``API.md``. ``JointTarget`` is IMPLEMENTED
as a wire type and on the ``bridge/`` transmit side (docs/123 "plan A", 2026-09-04) - see its
own docstring below; ``api.py``/``modes.py`` transmit wiring is separate work, still pending.
"""

from __future__ import annotations

import json
import math
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

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
  run_id: str | None = Field(
    default=None,
    description="P4: set while a POST /script/run target sequence is playing, so compare.py "
    "can align a sim recording against a robot recording of the same script",
  )


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
  """IMPLEMENTED as a wire format and as the transmit side (docs/123 section 4, "plan A"):
  ``bridge/tx_client.py`` is the sending library and ``bridge/huphy_remote_motion.py`` /
  ``bridge/dummy_rx.py`` are the two things that can be on the other end of UDP :9872. There
  is still NO route in ``api.py`` that emits it and ``modes.py`` still hard-codes the shadow
  mode to never transmit (``modes.SHADOW_MAY_TRANSMIT``) - policy output never reaches this
  class's constructor from that path, by construction, not by convention.

  ``origin`` is the second, independent gate a policy output cannot pass even if some future
  caller tried: the ``Literal`` type itself makes ``origin="policy"`` a ``pydantic.
  ValidationError`` at construction time, not a runtime check someone could forget to call.
  Every field is validated at parse time (``from_jsonl``/``model_validate``) so a corrupt or
  hostile line never reaches a robot as a half-built ``Action``:

    * ``origin`` - only ``"manual"`` (a person moved a slider/pressed a key) or ``"script"``
      (``POST /script/run`` style playback) are valid at all; anything else, ``"policy"``
      included, is rejected by the type before any code of ours runs.
    * ``arm_token`` - required, non-empty; the receiver additionally checks it MATCHES its
      own expected token (that check is the receiver's job, this model just refuses to be
      built without one).
    * ``q_target``/``kp``/``kd``/``tau_ff`` - NaN in any element is rejected (a NaN target is
      not "no data", HUPHY already has ``null``/``-1`` for that; a NaN slipping through as a
      float would hit ``guards.apply``'s clip/slew math wrong instead of failing loudly).

  Unknown joint names are NOT checked here (a name is only "unknown" relative to a specific
  robot/contract) - callers use ``validate_joint_names`` against their own allowed set, same
  as every other wire type in this file.
  """

  type: Literal["JointTarget"] = "JointTarget"
  joint_names: list[str]
  q_target: list[float]
  kp: list[float] | None = None
  kd: list[float] | None = None
  tau_ff: list[float] | None = None
  ttl_ms: int = Field(default=100, description="target expires this long after t_ns")
  arm_token: str = Field(description="receiver-checked shared secret; empty is refused here")
  origin: Literal["manual", "script"] = Field(
    description="never 'policy' - the Literal type itself rejects it at construction, "
    "which is the point (docs/123 section 4: policy output must never reach the wire)"
  )

  @field_validator("arm_token")
  @classmethod
  def _arm_token_not_empty(cls, v: str) -> str:
    if not v:
      raise ValueError("arm_token must be non-empty - an empty token is not 'unarmed', it's "
                        "a missing safety check")
    return v

  @field_validator("q_target", "kp", "kd", "tau_ff")
  @classmethod
  def _finite_only(cls, v: list[float] | None) -> list[float] | None:
    if v is None:
      return v
    bad = [i for i, x in enumerate(v) if not math.isfinite(x)]
    if bad:
      raise ValueError(f"non-finite value (NaN/inf) at index {bad} - a target must always "
                        "be finite (use a shorter joint_names/value list to omit a joint, "
                        "never NaN/inf as a sentinel)")
    return v


class PolicyIO(Header):
  """IMPLEMENTED.  What the policy saw and what it produced, this control tick."""

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
  mode: Literal["free", "fixed", "pivot", "string"] = "free"
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
  string: dict[str, Any] | None = Field(
    default=None, description="base mode 'string': z_set, length, ten_length, taut, tension_N"
  )
  contract_stale: bool = False
  contract_checks: dict[str, Any] = {}
  telemetry: dict[str, Any] = Field(default={}, description="P3: rx rate, age, clock offset")
  warnings: list[str] = []
  rss_mb: float | None = None
  imu: dict[str, Any] | None = Field(
    default=None,
    description="UI v2: this SIM's own IMU, {gyro_rad_s, gravity_b} - the same body-frame "
    "values ObsBuilder feeds the policy, derived from the model's own sensors (imu_ang_vel, "
    "-imu_upvector). Present once the sim has run one control tick. The RECEIVED real IMU "
    "(if any) is under telemetry.imu (RealState.imu, unchanged shape) - kept separate so a "
    "client never confuses 'what the sim computed' with 'what a robot reported'.",
  )
  side_mapping_verified: bool | None = Field(
    default=None,
    description="UI v2: bridge/joint_map_huphy.json's own side_mapping_verified flag, read "
    "once at process start - drives the top-bar 'side mapping UNVERIFIED' badge (protocol "
    "steps 2/3, docs/121 section 5). None if the file could not be read.",
  )


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
  orientation free under gravity) / ``string`` (safety tether: a tendon LIMIT holds the base
  no lower than ``z_set`` - slack above it, taut at it - horizontal motion is otherwise free,
  same as a real overhead harness). Gravity is never modified by any of these.
  """

  mode: Literal["free", "fixed", "pivot", "string"] | None = None
  pos: list[float] | None = None
  quat: list[float] | None = None
  rpy: list[float] | None = None
  height: float | None = None
  pivot_offset: list[float] | None = None
  ground: bool | None = None
  z_set: float | None = Field(default=None, description="string mode: catch height [m]")
  hook_offset: list[float] | None = Field(
    default=None, description="string mode: tether attachment point in the BASE frame [m]"
  )
  follow_xy: bool | None = Field(
    default=None,
    description="string mode: False (default) = anchor (x,y) fixed at mode-entry (can swing); "
    "True = anchor tracks the base's (x,y) every tick (vertical rail, no swing)",
  )


class ModeIn(BaseModel):
  """IMPLEMENTED, all six.  ``policy_sim``/``policy_shadow`` need a policy loaded first (409
  otherwise); ``file_replay`` needs a recording loaded first (409 otherwise)."""

  mode: Literal["idle", "manual", "policy_sim", "policy_shadow", "real_replay", "file_replay"]


class ResetIn(BaseModel):
  keyframe: Literal["home", "knees_bent"] = "knees_bent"


class GainsIn(BaseModel):
  """IMPLEMENTED.  Switch the PD source or override per joint.

  ``train`` is the contract's kp/kd - the gains the policy was optimised against.  ``real``
  needs a hardware gain table (contract ``real_gains``); the viewer refuses to invent one,
  because a response overlay between sim and robot is meaningless unless the gains match.
  """

  source: Literal["train", "real"] = "train"
  overrides: dict[str, dict[str, float]] = {}
  clear_overrides: bool = Field(
    default=False,
    description="UI v2: drop every previously-applied per-joint override before applying "
    "source/overrides this call - lets a client return to the contract's un-overridden gains "
    "(e.g. the 'train' preset) without restarting the process. False preserves the old "
    "behaviour (overrides only ever accumulate).",
  )


class ObsSourceIn(BaseModel):
  """IMPLEMENTED.  Per-term request; ``real`` is only ever READ from during ``policy_shadow``
  (``policy_sim`` ignores this and always uses sim). A term that asks for ``real`` but has no
  fresh data falls back to sim for that tick and is reported in ``policy.obs_sources_effective``
  / ``shadow_warnings``, never silently used stale (design item 1)."""

  sources: dict[str, Src]


class PolicyLoadIn(BaseModel):
  """IMPLEMENTED.  Load by baked ``name`` (preferred), or by explicit ``onnx``/``pt`` path.

  A policy is refused unless its contract's ``model_contract_sha`` equals the loaded model's
  and its default pose matches to 1e-4 rad.  ``allow_uncontracted`` skips the check for a
  throwaway file and is deliberately awkward to reach.
  """

  name: str | None = Field(default=None, description="baked policy name (see GET /policy/list)")
  onnx: str | None = None
  pt: str | None = Field(default=None, description="direct .pt: builds an mjlab env, ~11 s, ~1.3 GB")
  allow_uncontracted: bool = False


class TxArmIn(BaseModel):
  """UI v2 TX STUB (docs/121 section 10 / docs/123).  Arm is refused (409) unless the sim
  mode is exactly ``manual`` - policy output must never be transmittable."""

  host: str = Field(description="intended bridge host - not connected to anything yet, stub")
  port: int = Field(description="intended bridge port - not connected to anything yet, stub")


class TxMotorIn(BaseModel):
  """UI v2 TX STUB.  Per-motor opt-in; a motor not explicitly enabled is never sent."""

  joint_name: str
  enabled: bool


class PresetSaveIn(BaseModel):
  """UI v2 (Gains tab).  Save a named per-joint kp/kd table to ``tools/pygviewer/presets/``.

  ``train`` and ``real`` are reserved (built-in, not files): ``train`` is the contract's own
  gains, ``real`` is HUPHY's uniform kp=10/kd=1 start point
  (``~/external_repos/HUPHY/config/robot_v1.0.yaml``) - see ``GET /presets``.
  """

  name: str = Field(description="preset name; 'train' and 'real' are reserved")
  gains: dict[str, dict[str, float]] = Field(description="{joint_name: {kp, kd}}")


class PresetApplyIn(BaseModel):
  """UI v2 (Gains tab).  Apply a preset by name: ``train`` (clears overrides, contract
  gains), ``real`` (HUPHY kp=10/kd=1 on every actuated joint) or a custom name from
  ``GET /presets``."""

  name: str


class CmdIn(BaseModel):
  """IMPLEMENTED.  Velocity command the policy tracks."""

  vx: float = 0.0
  vy: float = 0.0
  wz: float = 0.0


class ShadowFollowIn(BaseModel):
  """IMPLEMENTED (P4).  ``policy_shadow`` only: does the shadow-computed action actually
  step the LOCAL sim forward, or does the policy only observe+display while sim keeps
  running under manual/idle. Never touches anything outside this process."""

  enabled: bool = False


class ScriptRunIn(BaseModel):
  """IMPLEMENTED (P4).  Play a ``scripts/*.json`` target-q sequence in ``manual`` mode.

  ``run_id`` is written into ``core.snapshot()['script']`` and, if a recording is active,
  becomes part of what ``compare.py`` can later use to align two files that both played the
  same script (one in sim, one - by convention, not by this API - driven through the same
  file on the robot's own bridge).
  """

  path: str
  run_id: str | None = None


# ----------------------------------------------------------------- P3 wire helpers
# One message per line, exactly ``model_dump_json()`` - this is the ONLY place that
# decides which pydantic class a "type" field maps to, so the recorder, the replayer, the
# WS /ws/in ingest and the dummy transmitter can never disagree with each other about it.
MESSAGE_TYPES: dict[str, type[Header]] = {
  "JointState": JointState,
  "ImuState": ImuState,
  "JointTarget": JointTarget,
  "PolicyIO": PolicyIO,
  "Status": Status,
}


def to_jsonl(msg: Header) -> str:
  """One wire message -> one JSONL line (newline included)."""
  return msg.model_dump_json() + "\n"


def from_jsonl(line: str) -> Header:
  """One JSONL line -> the typed message it names in ``type``.

  Raises ``ValueError`` for anything that is not valid JSON, has no recognised ``type``, or
  fails the model's own validation (e.g. a header field of the wrong shape). A caller that
  wants to survive a corrupt line should catch ``ValueError``, not assume this always
  succeeds - a dropped or torn UDP/websocket frame is a normal event on this project.
  """
  line = line.strip()
  if not line:
    raise ValueError("empty line")
  try:
    obj = json.loads(line)
  except json.JSONDecodeError as exc:
    raise ValueError(f"not valid JSON: {exc}") from exc
  typ = obj.get("type") if isinstance(obj, dict) else None
  cls = MESSAGE_TYPES.get(typ)
  if cls is None:
    raise ValueError(f"unknown or missing 'type' {typ!r}; have {sorted(MESSAGE_TYPES)}")
  return cls.model_validate(obj)


def validate_joint_names(names: list[str], allowed: set[str] | list[str]) -> list[str]:
  """Return the subset of ``names`` NOT in ``allowed``.  Empty = all recognised.

  This is the single gate that makes "reject an unknown joint name" true everywhere: the
  ``/ws/in`` handler, the HUPHY UDP bridge and the dummy transmitter's own self-check all
  call it instead of inventing their own regex or default.  There is no fallback path - an
  unknown name is a configuration error (wrong joint_map, wrong model variant) and must be
  visible, not silently dropped or silently accepted.
  """
  allowed = set(allowed)
  return [n for n in names if n not in allowed]
