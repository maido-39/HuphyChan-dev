"""pygviewer -> HUPHY transmit schema (docs/123 plan A, item 1): ``JointTarget`` is now the
one message the robot side actually reads, so this file locks down the safety properties the
whole design leans on - ``origin`` can never be ``"policy"``, ``arm_token`` is mandatory, NaN
never sneaks onto the wire, and an unknown joint name is caught by the same gate every other
bridge in this repo uses (``validate_joint_names``).  None of this touches ``api.py``/
``modes.py`` - those still never call this constructor with policy output (docs/123 section
4); this file only proves the message TYPE itself is safe to add a transmit path for.
"""

import math

import pytest
from pydantic import ValidationError

from pygviewer.schema import JointTarget, from_jsonl, to_jsonl, validate_joint_names


def _msg(**overrides):
  base = dict(
    t_ns=1_000,
    seq=1,
    src="sim",
    contract_hash="deadbeef",
    joint_names=["L_hip_pitch_joint", "L_knee_joint"],
    q_target=[0.1, 0.35],
    arm_token="bench-token-1",
    origin="manual",
  )
  base.update(overrides)
  return JointTarget(**base)


def test_valid_message_round_trips_through_jsonl():
  msg = _msg(kp=[5.0, 5.0], kd=[0.5, 0.5], ttl_ms=100)
  line = to_jsonl(msg)
  back = from_jsonl(line)
  assert isinstance(back, JointTarget)
  assert back == msg


def test_origin_policy_is_rejected_by_the_type_itself():
  with pytest.raises(ValidationError):
    _msg(origin="policy")


def test_origin_anything_else_is_also_rejected():
  for bad in ("real", "replay", "dummy", "", "MANUAL"):
    with pytest.raises(ValidationError):
      _msg(origin=bad)


def test_origin_script_is_allowed():
  msg = _msg(origin="script")
  assert msg.origin == "script"


def test_arm_token_is_required_and_non_empty():
  with pytest.raises(ValidationError):
    JointTarget(
      t_ns=1, seq=1, joint_names=["L_knee_joint"], q_target=[0.0], origin="manual",
    )  # arm_token omitted entirely - no default, must be refused
  with pytest.raises(ValidationError):
    _msg(arm_token="")


def test_nan_in_q_target_is_rejected():
  with pytest.raises(ValidationError):
    _msg(q_target=[0.1, float("nan")])


def test_nan_in_kp_kd_tau_ff_is_rejected():
  with pytest.raises(ValidationError):
    _msg(kp=[float("nan"), 1.0])
  with pytest.raises(ValidationError):
    _msg(kd=[1.0, float("nan")])
  with pytest.raises(ValidationError):
    _msg(tau_ff=[float("nan"), 0.0])


def test_unknown_joint_names_are_caught_by_the_shared_gate_not_by_the_model():
  msg = _msg(joint_names=["L_hip_pitch_joint", "made_up_joint"], q_target=[0.1, 0.2])
  allowed = {"L_hip_pitch_joint", "L_knee_joint", "R_hip_pitch_joint", "R_knee_joint"}
  unknown = validate_joint_names(msg.joint_names, allowed)
  assert unknown == ["made_up_joint"]


def test_ttl_ms_defaults_to_100():
  msg = _msg()
  assert msg.ttl_ms == 100


def test_default_origin_is_required_not_a_silent_manual():
  # 'origin' has no default (unlike ttl_ms) - forgetting it must fail loudly, never silently
  # become "manual".
  with pytest.raises(ValidationError):
    JointTarget(
      t_ns=1, seq=1, joint_names=["L_knee_joint"], q_target=[0.0], arm_token="x",
    )


def test_message_type_is_message_types_registered():
  from pygviewer.schema import MESSAGE_TYPES

  assert MESSAGE_TYPES["JointTarget"] is JointTarget


def test_inf_in_q_target_is_also_rejected():
  # inf is just as unsendable as NaN for a PD target - guards against a validator that only
  # checks isnan and lets +-inf slip through.
  with pytest.raises(ValidationError):
    _msg(q_target=[0.1, math.inf])
  with pytest.raises(ValidationError):
    _msg(q_target=[-math.inf, 0.1])
