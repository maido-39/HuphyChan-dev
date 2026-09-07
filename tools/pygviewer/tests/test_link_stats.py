"""The command receiver's own accept/reject counters, carried back to the viewer.

2026-09-07, docs/127 section 3-1. This is the single biggest observability hole the
root-cause analysis found. The robot has counted these since the day the receiver was
written - accepted, rejected because the message number went backwards, rejected because the
arm token did not match, rejected because the model did not match, and packets it could not
parse at all - and printed them to a log file on the robot every five seconds. Nothing ever
carried them to the operator's screen.

The cost of that: every single diagnosis of "the motors do not move" needed a terminal on the
other machine. Today's incident was settled in one line, ``accepted=1722 rejected_seq=0``,
which proved the link was perfect and moved the search to the command content - but only
because someone could ssh in and read a file. And an earlier incident had ``rejected_seq=5823``
against ``accepted=843`` while a whole measurement run silently did nothing; that counter was
sitting there the entire time saying exactly what was wrong.

They travel as two-segment ``link/<counter>`` keys. That namespace is deliberate: these
describe the LINK, not a joint, and the joint decoder ignores anything that is not
``limb/motor/field`` for free. Smuggling them onto one motor's row (the way ``prog`` is
carried) would make them look joint-specific and would break the moment that motor left the
enable list.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

from pygviewer import CACHE_DIR
from pygviewer.bridge.huphy_udp import HuphyBridge
from pygviewer.contract import load_contract
from pygviewer.schema import JointState
from pygviewer.telemetry import RealState

VARIANT = "LegOnly-AB"
MAP = Path(__file__).resolve().parents[1] / "pygviewer" / "bridge" / "joint_map_biped.json"
REMOTE_MOTION = Path(__file__).resolve().parents[1] / "pygviewer" / "bridge" / "huphy_remote_motion.py"

COUNTERS = {
  "link/accepted": 1722.0,
  "link/rejected_seq": 0.0,
  "link/rejected_arm_token": 0.0,
  "link/rejected_contract": 0.0,
  "link/parse_errors": 0.0,
  "link/seq_restarts": 0.0,
}


def _contract():
  try:
    return load_contract(CACHE_DIR, VARIANT)
  except FileNotFoundError:
    pytest.skip(f"no baked contract for {VARIANT}")


def _bridge():
  return HuphyBridge(_contract())     # default map is joint_map_biped.json


# ------------------------------------------------------------------- the wire decoder
def test_link_counters_are_decoded():
  b = _bridge()
  assert b.parse_link(COUNTERS) is True
  assert b._link_stats["accepted"] == 1722.0
  assert b._link_stats["rejected_seq"] == 0.0


def test_link_counters_ride_along_with_joint_data():
  """They share a packet with the per-motor diagnostic flags, so parse_fast must absorb them
  rather than silently dropping the keys it does not recognise as joints."""
  b = _bridge()
  msg = b.parse_fast({**COUNTERS, "left_leg/knee/pos": 51.3})
  assert msg is not None
  assert msg.link_stats["accepted"] == 1722.0


def test_counters_latch_between_reports():
  """The robot sends them twice a second while joint data flows at ~100 Hz. Every JointState
  built in between must still carry the last known values, or the trace would blink between
  'accepted 1722' and 'not reported'."""
  b = _bridge()
  b.parse_fast(COUNTERS)
  later = b.parse_fast({"left_leg/knee/pos": 51.4})     # no counters in this packet
  assert later is not None
  assert later.link_stats["accepted"] == 1722.0


def test_unknown_counter_names_are_ignored_not_guessed():
  b = _bridge()
  assert b.parse_link({"link/something_new": 5.0}) is False
  assert "something_new" not in b._link_stats


def test_a_sender_that_reports_nothing_leaves_the_field_null():
  """The bench's other senders never carry these. `null` must stay `null` - "not reported" and
  "zero rejections" are different answers."""
  b = _bridge()
  msg = b.parse_fast({"left_leg/knee/pos": 51.3})
  assert msg is not None
  assert msg.link_stats is None


def test_link_keys_are_not_mistaken_for_joints():
  """Two segments, so the three-segment joint path skips them; and no joint may be touched."""
  b = _bridge()
  msg = b.parse_fast(dict(COUNTERS))
  assert msg is None, "counters alone must not fabricate a joint frame"


# ----------------------------------------------------------------------- the viewer side
def test_status_reports_the_counters_once_they_arrive():
  real = RealState(["j1"], {"j1": (-10.0, 10.0)}, "sha")
  assert real.status()["link_stats"] is None, "unknown until a sender reports them"
  real.ingest_joint_state(JointState(
    t_ns=time.monotonic_ns(), seq=1, src="real",
    joint_names=["j1"], q=[0.1],
    link_stats={"accepted": 1722.0, "rejected_seq": 0.0},
  ))
  st = real.status()
  assert st["link_stats"] == {"accepted": 1722.0, "rejected_seq": 0.0}


def test_viewer_latches_the_counters_too():
  real = RealState(["j1"], {"j1": (-10.0, 10.0)}, "sha")
  real.ingest_joint_state(JointState(
    t_ns=time.monotonic_ns(), seq=1, src="real",
    joint_names=["j1"], q=[0.1],
    link_stats={"accepted": 10.0, "rejected_seq": 3.0},
  ))
  real.ingest_joint_state(JointState(                     # a frame with no counters at all
    t_ns=time.monotonic_ns(), seq=2, src="real",
    joint_names=["j1"], q=[0.2],
  ))
  assert real.status()["link_stats"]["accepted"] == 10.0
  real.ingest_joint_state(JointState(                     # a newer report replaces them
    t_ns=time.monotonic_ns(), seq=3, src="real",
    joint_names=["j1"], q=[0.3],
    link_stats={"accepted": 99.0},
  ))
  s = real.status()["link_stats"]
  assert s["accepted"] == 99.0 and s["rejected_seq"] == 3.0, "an update must merge, not replace"


# ------------------------------------------------------------------------- the robot side
def test_robot_emits_every_counter_the_viewer_knows_about():
  src = REMOTE_MOTION.read_text()
  m = re.search(r"def _link_stats_due\(self\).*?\n    return out", src, re.S)
  assert m, "_link_stats_due() not found"
  body = m.group(0)
  for counter in HuphyBridge.LINK_COUNTERS:
    assert f'"link/{counter}"' in body, counter


def test_robot_rate_limits_the_counters():
  """They share the diagnostic packet, which goes out on the control tick; sending six floats
  at 100 Hz to say nothing new would be waste."""
  src = REMOTE_MOTION.read_text()
  assert "LINK_STATS_PERIOD_S = 0.5" in src
  assert "if now - self._link_stats_last_sent < self.LINK_STATS_PERIOD_S:" in src
  assert "return None" in src


def test_counters_go_out_even_when_nothing_is_wrong():
  """`_send_fault_telemetry` returns early when it has nothing to say. The counters are most
  interesting precisely when no fault is being reported, so they must be added first."""
  src = REMOTE_MOTION.read_text()
  m = re.search(r"def _send_fault_telemetry\(.*?\n    try:", src, re.S)
  assert m, "_send_fault_telemetry() not found"
  body = m.group(0)
  assert body.index("if link_stats:") < body.index("if not pkt:"), (
    "the link counters must be in the packet before the empty-packet early return"
  )
