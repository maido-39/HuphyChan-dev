"""P3 item 1: the wire schema round-trips, enforces its required fields, and the joint-name
gate used by ``/ws/in``/the bridges actually rejects what it says it rejects."""

import pytest
from pydantic import ValidationError

from pygviewer.schema import (
  ImuState,
  JointState,
  PolicyIO,
  Status,
  from_jsonl,
  to_jsonl,
  validate_joint_names,
)


def test_joint_state_round_trips_through_jsonl():
  msg = JointState(
    t_ns=123456789,
    seq=1,
    src="sim",
    contract_hash="deadbeef",
    joint_names=["L_knee_joint", "R_knee_joint"],
    q=[0.35, -0.35],
    qd=[0.0, 0.0],
    tau_est=[1.2, None],
    target=[0.35, -0.35],
  )
  line = to_jsonl(msg)
  assert line.endswith("\n")
  back = from_jsonl(line)
  assert isinstance(back, JointState)
  assert back == msg


def test_imu_state_round_trips_with_missing_fields_as_null():
  msg = ImuState(t_ns=1, seq=1, src="dummy", gravity_b=[0.0, 0.0, -1.0])
  back = from_jsonl(to_jsonl(msg))
  assert isinstance(back, ImuState)
  assert back.quat_wxyz is None
  assert back.gyro_rad_s is None
  assert back.gravity_b == [0.0, 0.0, -1.0]


def test_status_round_trips():
  msg = Status(t_ns=1, seq=1, variant="LegOnly-AB", mode="idle")
  back = from_jsonl(to_jsonl(msg))
  assert isinstance(back, Status)
  assert back.variant == "LegOnly-AB"


def test_policy_io_requires_obs_action_target():
  with pytest.raises(ValidationError):
    PolicyIO(t_ns=1, seq=1)  # obs/action/target have no default


def test_header_requires_t_ns():
  with pytest.raises(ValidationError):
    JointState(seq=1, joint_names=["L_knee_joint"], q=[0.0])


def test_from_jsonl_rejects_unknown_type():
  with pytest.raises(ValueError, match="unknown or missing 'type'"):
    from_jsonl('{"type": "NotAThing", "t_ns": 1, "seq": 1}')


def test_from_jsonl_rejects_invalid_json():
  with pytest.raises(ValueError, match="not valid JSON"):
    from_jsonl("{not json")


def test_from_jsonl_rejects_empty_line():
  with pytest.raises(ValueError):
    from_jsonl("   \n")


def test_validate_joint_names_flags_only_the_unknown_ones():
  allowed = {"L_knee_joint", "R_knee_joint", "L_hip_pitch_joint"}
  assert validate_joint_names(["L_knee_joint", "R_knee_joint"], allowed) == []
  assert validate_joint_names(["L_knee_joint", "bogus_joint"], allowed) == ["bogus_joint"]
  assert set(validate_joint_names(["a", "b", "L_knee_joint"], allowed)) == {"a", "b"}


def test_joint_target_is_defined_in_the_wire_schema():
  """The wire schema is complete (JointTarget exists and round-trips) even though no
  endpoint emits it - the design's explicit "receive only" decision (docs/121 section 1)."""
  from pygviewer.schema import JointTarget, MESSAGE_TYPES

  assert "JointTarget" in MESSAGE_TYPES
  msg = JointTarget(t_ns=1, seq=1, joint_names=["L_knee_joint"], q_target=[0.35])
  back = from_jsonl(to_jsonl(msg))
  assert isinstance(back, JointTarget)
  assert back.q_target == [0.35]
