"""pygviewer/bridge/motor_fault.py - fault visibility (2026-09-05, docs/121/docs/124).

Every class/function tested here is pure (no huphy, no CAN, no socket) - see that module's
own docstring. The values reproduce the exact bench incident in docs/124: two motors cut
their own torque (overvoltage) while the knee froze at 141.40 deg for 170s and comm/ack/miss
stayed healthy, and the fault query came back as raw bytes that decode to 0x08000000 one way
and 0x00000008 (bit 3, overvoltage) the other.
"""

import pytest

from pygviewer.bridge.motor_fault import (
  FAULT_QUERY_WAIT_S,
  OVERHEAT_CUTOFF_C,
  OVERHEAT_RESUME_C,
  STUCK_ERR_DEG,
  STUCK_HOLD_S,
  STUCK_POS_DEADBAND_DEG,
  STUCK_TAU_ZERO_NM,
  TEMP_VALID_MAX_C,
  TEMP_VALID_MIN_C,
  FaultPoller,
  StuckDetector,
  ThermalCutoff,
  build_mit_frame_data,
  decode_fault_word,
  describe_cutoff_simple,
  describe_fault_simple,
  describe_stuck_simple,
  named_fault_bits,
  query_fault_raw,
)


# =========================================================================== StuckDetector
def test_stuck_detector_flags_frozen_value_after_hold_duration():
  """The exact docs/124 shape: target far from measured, measured barely moves, torque ~0,
  held for >= STUCK_HOLD_S."""
  d = StuckDetector()
  target, pos, tau = 114.0, 141.4, 0.0
  t = 0.0
  # ticks before STUCK_HOLD_S has elapsed: not yet reported
  for _ in range(9):
    assert d.update("knee", t, target, pos, tau) is None
    t += STUCK_HOLD_S / 10.0
  # crossing the hold duration: now reported
  t = STUCK_HOLD_S + 0.01
  result = d.update("knee", t, target, pos, tau)
  assert result is not None
  assert result["target_deg"] == pytest.approx(target)
  assert result["pos_deg"] == pytest.approx(pos)
  assert result["tau_nm"] == pytest.approx(tau)
  assert result["duration_s"] > 0


def test_stuck_detector_never_fires_during_normal_tracking():
  """Target close to measured (within STUCK_ERR_DEG) the whole time - must never flag,
  however long it runs."""
  d = StuckDetector()
  t = 0.0
  for i in range(50):
    t += 0.05
    assert d.update("knee", t, 20.0, 20.0 + 0.5 * (i % 3), 1.2) is None


def test_stuck_detector_never_fires_when_torque_is_nonzero():
  """Far from target, barely moving, but real torque present - a joint straining against a
  mechanical load, not a fault - must not be flagged."""
  d = StuckDetector()
  t = 0.0
  for _ in range(30):
    t += STUCK_HOLD_S / 10.0
    assert d.update("knee", t, 0.0, 20.0, 5.0) is None


def test_stuck_detector_resets_on_real_motion():
  """A joint slowly limping toward its target (moving more than the deadband inside the
  window) must never be called frozen, even if it never actually reaches the target."""
  d = StuckDetector()
  t = 0.0
  pos = 0.0
  for _ in range(40):
    t += STUCK_HOLD_S / 10.0
    pos += STUCK_POS_DEADBAND_DEG * 2  # always exceeds the deadband -> window keeps resetting
    assert d.update("knee", t, 100.0, pos, 0.0) is None


def test_stuck_detector_ignores_missing_data_and_resets():
  d = StuckDetector()
  t = 0.0
  for _ in range(15):
    t += STUCK_HOLD_S / 10.0
    d.update("knee", t, 114.0, 141.4, 0.0)
  # one tick of missing torque must reset the window, not silently continue counting
  t += 0.1
  assert d.update("knee", t, 114.0, 141.4, None) is None
  t += STUCK_HOLD_S - 0.05
  assert d.update("knee", t, 114.0, 141.4, 0.0) is None  # window restarted, not yet elapsed


def test_stuck_detector_boundary_err_and_tau_do_not_trigger():
  """Exactly at the thresholds is "not yet exceeding" - only strictly past them counts."""
  d = StuckDetector()
  t = 0.0
  for _ in range(20):
    t += STUCK_HOLD_S / 10.0
    assert d.update("knee", t, 0.0, STUCK_ERR_DEG, STUCK_TAU_ZERO_NM) is None


def test_describe_stuck_simple_matches_brief_format():
  result = dict(target_deg=114.0, pos_deg=141.4, tau_nm=0.0, duration_s=12.0)
  text = describe_stuck_simple("무릎", result)
  assert text == "무릎: 명령을 따르지 않음 (고장 의심) — 목표 114.0 (deg), 실측 141.4 (deg), 토크 0.00 N·m, 12초째"


# =========================================================================== FaultPoller
def test_fault_poller_never_queries_while_live():
  p = FaultPoller(interval_s=1.0)
  for i in range(20):
    assert p.update(i * 0.1, "live") is False


def test_fault_poller_queries_immediately_on_disarm_edge():
  p = FaultPoller(interval_s=1.0)
  assert p.update(0.0, "live") is False
  assert p.update(0.1, "hold") is True  # the instant transmission goes idle


def test_fault_poller_then_queries_periodically_while_idle():
  p = FaultPoller(interval_s=1.0)
  p.update(0.0, "live")
  assert p.update(0.1, "hold") is True   # disarm edge
  assert p.update(0.2, "hold") is False  # too soon
  assert p.update(0.9, "hold") is False  # still too soon
  assert p.update(1.15, "hold") is True  # >= 1.0s since the last query


def test_fault_poller_rearms_on_a_later_disarm():
  p = FaultPoller(interval_s=1.0)
  p.update(0.0, "live")
  assert p.update(0.1, "hold") is True
  p.update(0.5, "live")  # re-armed before the periodic interval would have fired again
  assert p.update(0.6, "hold") is True  # a NEW disarm edge - queries immediately regardless


def test_fault_poller_never_queries_while_truly_idle_from_the_very_start():
  """Never armed at all (process just started, nothing sent yet) still counts as
  "not live" - queries on the normal periodic cadence, no special-cased crash."""
  p = FaultPoller(interval_s=1.0)
  assert p.update(0.0, "idle") is True  # first-ever query, no _last_query_t yet
  assert p.update(0.5, "idle") is False
  assert p.update(1.01, "idle") is True


# =========================================================================== decode_fault_word
def test_decode_fault_word_both_interpretations_of_the_bench_incident_bytes():
  """docs/124's own reproduction: the fault-value bytes read as 0x08000000 one way (no
  defined bit - what HUPHY showed at the bench) and 0x00000008 (bit 3, overvoltage) the
  other (the correct one, per the manufacturer SDK/manual)."""
  # int.from_bytes(b, "little") == 0x00000008  <=>  bytes are 08 00 00 00
  raw = bytes([0x08, 0x00, 0x00, 0x00])
  reading = decode_fault_word(raw)
  assert reading.little == 0x00000008
  assert reading.little_names == ["overvoltage"]
  assert reading.big == 0x08000000
  assert reading.big_names == []  # bit 27 is not a defined fault bit


def test_named_fault_bits_matches_the_brief_table():
  assert named_fault_bits(1 << 0) == ["overtemperature"]
  assert named_fault_bits(1 << 1) == ["driver_fault"]
  assert named_fault_bits(1 << 2) == ["undervoltage"]
  assert named_fault_bits(1 << 3) == ["overvoltage"]
  assert named_fault_bits(1 << 7) == ["encoder_uncalibrated"]
  assert named_fault_bits(1 << 14) == ["stall_overload"]
  assert named_fault_bits(0) == []
  assert named_fault_bits((1 << 0) | (1 << 3)) == ["overtemperature", "overvoltage"]


def test_describe_fault_simple_uses_little_endian_as_the_correct_reading():
  raw = bytes([0x08, 0x00, 0x00, 0x00])
  reading = decode_fault_word(raw)
  text = describe_fault_simple("무릎", reading)
  assert text == "무릎: 모터가 과전압(으)로 힘을 끊었습니다 (코드 0x00000008)"


def test_describe_fault_simple_handles_no_fault_and_undefined_code():
  zero = decode_fault_word(bytes([0x00, 0x00, 0x00, 0x00]))
  assert describe_fault_simple("무릎", zero) == "무릎: 고장 코드 없음 (0x00000000)"
  undefined = decode_fault_word(bytes([0x00, 0x00, 0x00, 0x08]))  # bit 27 little-endian
  text = describe_fault_simple("무릎", undefined)
  assert "정의되지 않은" in text


# =========================================================================== query_fault_raw
class _FakeBus:
  """No python-can - a minimal fake matching query_fault_raw's injected (send_fn, recv_fn)
  shape: one canned reply per motor id, plus a drain queue of stale frames."""

  def __init__(self, replies: dict[int, bytes | None], stale: list[bytes] | None = None):
    self.replies = dict(replies)
    self._stale = list(stale or [])
    self.sent: list[tuple[int, bytes]] = []

  def send_fn(self, motor_id: int, data: bytes) -> None:
    self.sent.append((motor_id, data))

  def recv_fn(self, timeout_s: float) -> bytes | None:
    if self._stale:
      return self._stale.pop(0)
    if not self.sent:
      return None  # drain-before-any-send case: nothing queued yet
    # the reply for whichever motor was most recently sent to
    mid, _ = self.sent[-1]
    reply = self.replies.get(mid)
    self.replies[mid] = None  # only answer once per query, like a real bus would
    return reply


def test_query_fault_raw_returns_one_reply_per_motor():
  bus = _FakeBus({3: bytes([0x03, 0x08, 0, 0, 0, 0, 0, 0]), 4: bytes([0x04, 0, 0, 0, 0, 0, 0, 0])})
  out = query_fault_raw([3, 4], bus.send_fn, bus.recv_fn, wait_s=0.05)
  assert out[3] == bytes([0x03, 0x08, 0, 0, 0, 0, 0, 0])
  assert out[4] == bytes([0x04, 0, 0, 0, 0, 0, 0, 0])
  assert bus.sent == [(3, build_mit_frame_data(0xFB, 0x00)), (4, build_mit_frame_data(0xFB, 0x00))]


def test_query_fault_raw_drains_stale_frames_before_querying():
  bus = _FakeBus({3: bytes([0x03] + [0] * 7)}, stale=[bytes([0xAA] * 8), bytes([0xBB] * 8)])
  out = query_fault_raw([3], bus.send_fn, bus.recv_fn, wait_s=0.05)
  assert out[3] == bytes([0x03] + [0] * 7)  # not one of the stale frames


def test_query_fault_raw_none_on_no_reply():
  bus = _FakeBus({5: None})
  out = query_fault_raw([5], bus.send_fn, bus.recv_fn, wait_s=0.02)
  assert out[5] is None


# =========================================================================== ThermalCutoff
def test_thermal_cutoff_cuts_at_50_and_resumes_at_45():
  c = ThermalCutoff()
  r = c.update("knee", 49.9)
  assert r == dict(valid=True, cut=False, transitioned=False, temp_c=49.9)
  r = c.update("knee", OVERHEAT_CUTOFF_C)
  assert r["valid"] and r["cut"] and r["transitioned"]
  r = c.update("knee", 47.0)  # still above resume threshold - stays cut, no re-transition
  assert r["cut"] and not r["transitioned"]
  r = c.update("knee", OVERHEAT_RESUME_C)
  assert r["valid"] and not r["cut"] and r["transitioned"]


def test_thermal_cutoff_never_trusts_an_implausible_reading():
  """The docs/124 incident value (3308.8 C) must never cut, never clear a cut, and must be
  reported as invalid, not silently clamped into range."""
  c = ThermalCutoff()
  r = c.update("knee", 3308.8)
  assert r == dict(valid=False, cut=False, transitioned=False, temp_c=3308.8)
  c.update("knee", OVERHEAT_CUTOFF_C)  # now genuinely cut
  r = c.update("knee", 3308.8)  # implausible again - must NOT clear the real cut
  assert r["valid"] is False and r["cut"] is True and r["transitioned"] is False


def test_thermal_cutoff_boundaries_of_the_valid_range():
  c = ThermalCutoff()
  assert c.update("knee", TEMP_VALID_MIN_C)["valid"] is True
  assert c.update("knee", TEMP_VALID_MAX_C)["valid"] is True
  assert c.update("knee", TEMP_VALID_MIN_C - 0.1)["valid"] is False
  assert c.update("knee", TEMP_VALID_MAX_C + 0.1)["valid"] is False
  assert c.update("knee", None)["valid"] is False


def test_thermal_cutoff_is_per_joint_independent():
  c = ThermalCutoff()
  c.update("knee", OVERHEAT_CUTOFF_C)
  r_hip = c.update("hip_pitch", 30.0)
  assert r_hip["cut"] is False


def test_describe_cutoff_simple_matches_brief_language():
  cut_result = dict(temp_c=51.0)
  assert describe_cutoff_simple("무릎", cut_result, resumed=False) == "무릎: 과열로 힘을 끊음 (온도 51.0도, 기준 50도)"
  resume_result = dict(temp_c=44.0)
  assert describe_cutoff_simple("무릎", resume_result, resumed=True) == "무릎: 식어서 다시 시작 (온도 44.0도)"


def test_module_constants_match_the_brief():
  assert STUCK_ERR_DEG == 3.0
  assert STUCK_POS_DEADBAND_DEG == 0.2
  assert STUCK_TAU_ZERO_NM == 0.05
  assert STUCK_HOLD_S == 1.0
  assert OVERHEAT_CUTOFF_C == 50.0
  assert OVERHEAT_RESUME_C == 45.0
  assert TEMP_VALID_MIN_C == -20.0
  assert TEMP_VALID_MAX_C == 150.0
  assert FAULT_QUERY_WAIT_S > 0
