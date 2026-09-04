"""docs/123 plan A item 5: ``bridge/tx_client.py``'s three independent safety layers -
origin fixed at construction, mode-gated ``set_target``, and pre-send safe_clip/slew/gain
clamps - plus the "nothing sent until armed" contract the whole design leans on.
"""

import json
import socket

import pytest

from pygviewer.bridge.tx_client import BLOCKED_MODES, TxClient
from pygviewer.schema import JointTarget


def _client(**kw):
  defaults = dict(
    host="127.0.0.1", port=19872, joint_names=["L_knee_joint", "R_knee_joint"],
    arm_token="tok", origin="manual",
  )
  defaults.update(kw)
  return TxClient(**defaults)


# --------------------------------------------------------------------------- construction
def test_origin_policy_is_rejected_at_construction():
  with pytest.raises(RuntimeError):
    _client(origin="policy")


def test_origin_anything_but_manual_or_script_is_rejected():
  for bad in ("real", "replay", "dummy", ""):
    with pytest.raises(RuntimeError):
      _client(origin=bad)


def test_empty_arm_token_is_rejected():
  with pytest.raises(RuntimeError):
    _client(arm_token="")


def test_non_positive_hz_is_rejected():
  with pytest.raises(ValueError):
    _client(hz=0)


def test_ttl_ms_defaults_to_250_and_is_carried_on_the_message():
  c = _client()
  c.arm()
  c.set_target({"L_knee_joint": 0.1})
  msg = c.build_message()
  assert msg.ttl_ms == 250


def test_ttl_ms_is_overridable():
  c = _client(ttl_ms=50)
  c.arm()
  c.set_target({"L_knee_joint": 0.1})
  msg = c.build_message()
  assert msg.ttl_ms == 50


# --------------------------------------------------------------------------- mode gating
def test_set_target_raises_for_blocked_modes():
  c = _client()
  for mode in BLOCKED_MODES:
    with pytest.raises(RuntimeError):
      c.set_target({"L_knee_joint": 0.1}, mode=mode)


def test_set_target_allows_manual_and_idle_modes():
  c = _client()
  c.set_target({"L_knee_joint": 0.1}, mode="manual")
  c.set_target({"L_knee_joint": 0.1}, mode="idle")  # does not raise


def test_set_target_rejects_unknown_joint_name():
  c = _client()
  with pytest.raises(ValueError):
    c.set_target({"not_a_joint": 0.1})


# --------------------------------------------------------------------------- arm gating
def test_nothing_builds_before_arm():
  c = _client()
  c.set_target({"L_knee_joint": 0.1})
  assert c.build_message() is None


def test_message_builds_once_armed():
  c = _client()
  c.arm()
  c.set_target({"L_knee_joint": 0.1})
  msg = c.build_message()
  assert isinstance(msg, JointTarget)
  assert msg.origin == "manual"
  assert msg.arm_token == "tok"
  assert msg.joint_names == ["L_knee_joint"]
  assert msg.q_target == pytest.approx([0.1])


def test_disarm_clears_pending_target():
  c = _client()
  c.arm()
  c.set_target({"L_knee_joint": 0.1})
  c.disarm()
  assert c.build_message() is None


def test_seq_increments_across_messages():
  c = _client()
  c.arm()
  c.set_target({"L_knee_joint": 0.1})
  m1 = c.build_message()
  c.set_target({"L_knee_joint": 0.2})
  m2 = c.build_message()
  assert m2.seq == m1.seq + 1


# --------------------------------------------------------------------------- safe_clip
def test_safe_clip_clamps_out_of_range_target():
  c = _client(safe_clip={"L_knee_joint": (-0.1, 0.5)})
  c.arm()
  c.set_target({"L_knee_joint": 5.0})
  msg = c.build_message()
  assert msg.q_target == pytest.approx([0.5])
  assert any("safe_clip" in w for w in c.warnings)


def test_in_range_target_is_unaffected_by_safe_clip():
  c = _client(safe_clip={"L_knee_joint": (-0.5, 0.5)})
  c.arm()
  c.set_target({"L_knee_joint": 0.2})
  msg = c.build_message()
  assert msg.q_target == pytest.approx([0.2])


# --------------------------------------------------------------------------- slew
def test_slew_limits_a_big_jump_to_max_delta_per_tick():
  c = _client(max_delta_rad=0.05)
  c.arm()
  c.set_target({"L_knee_joint": 0.0})
  c.build_message()  # establishes prev_sent = 0.0
  c.set_target({"L_knee_joint": 10.0})  # far target
  msg = c.build_message()
  assert msg.q_target[0] == pytest.approx(0.05, abs=1e-9)  # capped to one step


def test_slew_allows_the_full_step_when_under_the_cap():
  c = _client(max_delta_rad=0.5)
  c.arm()
  c.set_target({"L_knee_joint": 0.0})
  c.build_message()
  c.set_target({"L_knee_joint": 0.1})
  msg = c.build_message()
  assert msg.q_target[0] == pytest.approx(0.1, abs=1e-9)


def test_disarm_resets_slew_state_so_next_arm_does_not_ramp_from_a_stale_pose():
  c = _client(max_delta_rad=0.05)
  c.arm()
  c.set_target({"L_knee_joint": 0.5})
  c.build_message()
  c.disarm()
  c.arm()
  c.set_target({"L_knee_joint": -0.5})
  msg = c.build_message()
  # with slew state reset, the first post-rearm message is NOT clamped toward the old 0.5
  assert msg.q_target[0] == pytest.approx(-0.5, abs=1e-9)


# --------------------------------------------------------------------------- gain clamp
def test_kp_kd_are_clamped_to_the_configured_max():
  c = _client(kp_max=5.0, kd_max=0.5)
  c.arm()
  c.set_target({"L_knee_joint": 0.1}, kp={"L_knee_joint": 50.0}, kd={"L_knee_joint": 5.0})
  msg = c.build_message()
  assert msg.kp == pytest.approx([5.0])
  assert msg.kd == pytest.approx([0.5])
  assert any("kp" in w for w in c.warnings)
  assert any("kd" in w for w in c.warnings)


# --------------------------------------------------------------------------- wire transmit
def test_tick_sends_nothing_when_disarmed(monkeypatch):
  c = _client()
  c.set_target({"L_knee_joint": 0.1})
  assert c.tick() is None
  assert c.sent_count == 0


def test_tick_sends_a_valid_jsonl_udp_packet_when_armed():
  srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  srv.bind(("127.0.0.1", 0))
  srv.settimeout(2.0)
  port = srv.getsockname()[1]
  try:
    c = _client(port=port)
    c.arm()
    c.set_target({"L_knee_joint": 0.1, "R_knee_joint": -0.1})
    sent = c.tick()
    assert sent is not None
    data, _addr = srv.recvfrom(4096)
    obj = json.loads(data.decode("utf-8"))
    assert obj["type"] == "JointTarget"
    assert obj["origin"] == "manual"
    assert obj["arm_token"] == "tok"
    assert obj["joint_names"] == ["L_knee_joint", "R_knee_joint"]
    assert obj["q_target"] == pytest.approx([0.1, -0.1])
  finally:
    srv.close()
    c.stop()


def test_start_stop_background_thread_does_not_raise():
  c = _client()
  c.start()
  c.arm()
  c.set_target({"L_knee_joint": 0.0})
  c.stop()  # should join cleanly with no exception
