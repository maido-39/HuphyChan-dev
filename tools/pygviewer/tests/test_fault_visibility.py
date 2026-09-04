"""Fault visibility (2026-09-05, docs/121 section 12c, docs/124) - the VIEWER side: wire
fields (`schema.JointState.stuck/fault_le/fault_be`), `bridge/huphy_udp.py`'s bridging of them
into a canonical `JointState`, `telemetry.RealState`'s ingest/violation-recording, and the
`GET /health` `fault_reason` string that must show red REGARDLESS of the ok/warn/dead
connectivity verdict (the docs/124 incident: comm/ack/miss all looked healthy while the joint
was genuinely stuck).

The robot-side judgement logic itself (StuckDetector/FaultPoller/decode_fault_word) is tested
in tests/test_motor_fault.py; the wiring from RemoteMotion into these fields is tested in
tests/test_remote_motion.py. This file covers only the RECEIVE side.
"""

import pytest

from pygviewer.schema import JointState
from pygviewer.telemetry import RealState
from pygviewer.violations import ViolationLog


def test_schema_joint_state_has_the_three_new_fields():
  assert "stuck" in JointState.model_fields
  assert "fault_le" in JointState.model_fields
  assert "fault_be" in JointState.model_fields


def test_huphy_bridge_parses_stuck_and_fault_fields_into_joint_state():
  from pygviewer import CACHE_DIR
  from pygviewer.bridge.huphy_udp import HuphyBridge, JointMap
  from pygviewer.contract import load_contract

  try:
    c = load_contract(CACHE_DIR, "LegOnly-AB")
  except FileNotFoundError:
    pytest.skip("no baked contract for LegOnly-AB")
  bridge = HuphyBridge(c, JointMap())
  msg = bridge.parse_fast({
    "left_leg/knee/stuck": 1.0,
    "left_leg/knee/fault_le": 8.0,
    "left_leg/knee/fault_be": 134217728.0,  # 0x08000000
  })
  assert msg is not None
  by_name_stuck = dict(zip(msg.joint_names, msg.stuck))
  by_name_fle = dict(zip(msg.joint_names, msg.fault_le))
  by_name_fbe = dict(zip(msg.joint_names, msg.fault_be))
  assert by_name_stuck["L_knee_joint"] == pytest.approx(1.0)
  assert by_name_fle["L_knee_joint"] == pytest.approx(8.0)
  assert by_name_fbe["L_knee_joint"] == pytest.approx(134217728.0)


def _joint_state(**stuck_fault_kwargs):
  return JointState(
    t_ns=1, seq=1, src="real", joint_names=["j1"], q=[2.4680],  # 141.4 deg in rad
    target=[1.9897],  # 114.0 deg in rad
    tau_est=[0.0], **stuck_fault_kwargs,
  )


# =========================================================================== overheat cutoff
def test_schema_joint_state_has_temp_valid_and_cutoff_fields():
  assert "temp_valid" in JointState.model_fields
  assert "cutoff" in JointState.model_fields


def test_huphy_bridge_parses_temp_valid_and_cutoff_fields():
  from pygviewer import CACHE_DIR
  from pygviewer.bridge.huphy_udp import HuphyBridge, JointMap
  from pygviewer.contract import load_contract

  try:
    c = load_contract(CACHE_DIR, "LegOnly-AB")
  except FileNotFoundError:
    pytest.skip("no baked contract for LegOnly-AB")
  bridge = HuphyBridge(c, JointMap())
  msg = bridge.parse_fast({
    "left_leg/knee/temp_valid": 0.0,
    "left_leg/knee/cutoff": 1.0,
  })
  assert msg is not None
  assert dict(zip(msg.joint_names, msg.temp_valid))["L_knee_joint"] == pytest.approx(0.0)
  assert dict(zip(msg.joint_names, msg.cutoff))["L_knee_joint"] == pytest.approx(1.0)


def test_real_state_fault_reason_shows_cutoff_and_unreadable_temperature():
  rs = RealState(["j1"], {"j1": (-10.0, 10.0)}, "sha")
  rs.ingest_joint_state(_joint_state(cutoff=[1.0]))
  assert "과열로 힘을 끊음" in rs.health()["joints"]["j1"]["fault_reason"]

  rs2 = RealState(["j1"], {"j1": (-10.0, 10.0)}, "sha")
  rs2.ingest_joint_state(_joint_state(temp_valid=[0.0]))
  assert "온도를 읽을 수 없음" in rs2.health()["joints"]["j1"]["fault_reason"]


def test_real_state_records_a_cutoff_transition_violation():
  log = ViolationLog()
  rs = RealState(["j1"], {"j1": (-10.0, 10.0)}, "sha", violations=log)
  msg = JointState(
    t_ns=1, seq=1, src="real", joint_names=["j1"], q=[0.0], temp_c=[51.0], cutoff=[1.0],
  )
  rs.ingest_joint_state(msg)
  recs = log.list(side="cutoff")
  assert len(recs) == 1
  assert "과열로 힘을 끊음" in recs[0]["reason"]
  # a second tick still cut - no NEW transition record (only the edge is recorded)
  rs.ingest_joint_state(msg)
  assert len(log.list(side="cutoff")) == 1


def test_real_state_records_a_temp_unreadable_violation_for_the_docs124_incident_value():
  """The exact docs/124 incident number - 3308.8 C, a fault-state artifact, not a real
  temperature - must be recorded as unreadable."""
  log = ViolationLog()
  rs = RealState(["j1"], {"j1": (-10.0, 10.0)}, "sha", violations=log)
  msg = JointState(t_ns=1, seq=1, src="real", joint_names=["j1"], q=[0.0], temp_c=[3308.8], temp_valid=[0.0])
  rs.ingest_joint_state(msg)
  recs = log.list(side="temp_unreadable")
  assert len(recs) == 1
  assert "온도를 읽을 수 없음" in recs[0]["reason"]


def test_real_state_stores_stuck_and_fault_without_affecting_ok_warn_dead():
  """The docs/124 point exactly: a joint flagged stuck must still show connectivity state
  'ok' (comm is fine) while ALSO carrying a non-null fault_reason."""
  rs = RealState(["j1"], {"j1": (-10.0, 10.0)}, "sha")
  rs.ingest_joint_state(_joint_state(stuck=[1.0]))
  h = rs.health()
  j = h["joints"]["j1"]
  assert j["state"] == "ok"  # comm/reception is fine - this is the whole point of the bug
  assert j["fault_reason"] is not None
  assert "명령을 따르지 않음" in j["fault_reason"]


def test_real_state_fault_reason_none_when_nothing_is_wrong():
  rs = RealState(["j1"], {"j1": (-10.0, 10.0)}, "sha")
  rs.ingest_joint_state(_joint_state(stuck=[0.0], fault_le=[0.0], fault_be=[0.0]))
  h = rs.health()
  assert h["joints"]["j1"]["fault_reason"] is None


def test_real_state_fault_reason_names_the_bit_from_fault_le():
  rs = RealState(["j1"], {"j1": (-10.0, 10.0)}, "sha")
  rs.ingest_joint_state(_joint_state(fault_le=[8.0], fault_be=[134217728.0]))
  h = rs.health()
  reason = h["joints"]["j1"]["fault_reason"]
  assert reason is not None
  assert "0x00000008" in reason
  assert "과전압" in reason  # bit 3 = overvoltage, simple Korean phrase


def test_real_state_records_a_stuck_violation_with_a_plain_language_reason():
  log = ViolationLog()
  rs = RealState(["j1"], {"j1": (-10.0, 10.0)}, "sha", violations=log)
  rs.ingest_joint_state(_joint_state(stuck=[1.0]))
  recs = log.list(side="stuck")
  assert len(recs) == 1
  assert recs[0]["joint"] == "j1"
  assert "명령을 따르지 않음" in recs[0]["reason"]
  assert "114.0" in recs[0]["reason"] and "141.4" in recs[0]["reason"]


def test_real_state_records_a_fault_violation_with_a_plain_language_reason():
  log = ViolationLog()
  rs = RealState(["j1"], {"j1": (-10.0, 10.0)}, "sha", violations=log)
  rs.ingest_joint_state(_joint_state(fault_le=[8.0], fault_be=[134217728.0]))
  recs = log.list(side="fault")
  assert len(recs) == 1
  assert "과전압" in recs[0]["reason"]
  assert "0x00000008" in recs[0]["reason"]


def test_real_state_never_records_a_fault_violation_for_a_zero_code():
  log = ViolationLog()
  rs = RealState(["j1"], {"j1": (-10.0, 10.0)}, "sha", violations=log)
  rs.ingest_joint_state(_joint_state(fault_le=[0.0], fault_be=[0.0]))
  assert log.list(side="fault") == []


def test_real_state_stuck_duration_grows_across_ticks_and_resets_on_clear():
  log = ViolationLog()
  rs = RealState(["j1"], {"j1": (-10.0, 10.0)}, "sha", violations=log)
  import pygviewer.telemetry as telemetry_mod

  t = {"now": 1000.0}
  orig = telemetry_mod.time.monotonic
  telemetry_mod.time.monotonic = lambda: t["now"]
  try:
    rs.ingest_joint_state(_joint_state(stuck=[1.0]))
    t["now"] += 5.0
    rs.ingest_joint_state(_joint_state(stuck=[1.0]))
    recs = log.list(side="stuck")
    assert recs[-1]["duration_s"] >= 4.9
    rs.ingest_joint_state(_joint_state(stuck=[0.0]))  # recovered
    t["now"] += 3.0  # past ViolationLog's own rate_limit_s=2.0 for this (side, joint)
    rs.ingest_joint_state(_joint_state(stuck=[1.0]))  # stuck again - a NEW episode
    recs = log.list(side="stuck")
    assert recs[-1]["duration_s"] < 1.0
  finally:
    telemetry_mod.time.monotonic = orig
