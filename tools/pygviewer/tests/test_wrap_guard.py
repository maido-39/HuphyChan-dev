"""The +-180 fold is the one failure on this bench that has already broken hardware.

2026-09-05: the knee sat at raw 271.59 deg. HUPHY converts raw<->cal through wrap180 in both
directions, so that folded to -88.41 deg, and a 6 deg request became a ~195 deg move at about
1072 deg/s. Braking that hard regenerated enough to trip an overvoltage cutout on BOTH motors
on the shared supply.

Nothing anywhere refused that command. These tests pin the guard that now does.

The trigger path is proven here rather than on the motors: driving a real joint to +-180 to
watch the guard fire would be deliberately reproducing the incident that broke it, on
hardware that took hours to recover. Non-interference at the joints' real angles is checked
live instead (see docs/125).
"""
import math

import pytest

from pygviewer.bridge.motor_fault import (
  WRAP_BLOCK_DEG,
  WRAP_JUMP_DEG,
  WRAP_JUMP_WINDOW_S,
  WRAP_WARN_DEG,
  WrapGuard,
  describe_wrap_simple,
)

KNEE = "knee"


def test_a_joint_in_the_middle_is_never_blocked():
  for raw in (0.0, 45.0, -45.0, 102.9, -120.0):
    r = WrapGuard().update(KNEE, raw)
    assert r["state"] == "ok", raw
    assert r["margin_deg"] == pytest.approx(180.0 - abs(raw))


def test_warns_before_it_blocks():
  """There has to be a band where the operator is told but can still drive the joint back."""
  assert WRAP_WARN_DEG < WRAP_BLOCK_DEG
  g = WrapGuard()
  assert g.update(KNEE, WRAP_WARN_DEG + 1.0)["state"] == "warn"
  assert g.update(KNEE, WRAP_BLOCK_DEG + 1.0)["state"] == "blocked"


def test_blocks_symmetrically():
  for sign in (1, -1):
    g = WrapGuard()
    assert g.update(KNEE, sign * (WRAP_BLOCK_DEG + 5))["state"] == "blocked"


def test_the_actual_incident_angle_is_blocked():
  """raw 271.59 folds to -88.41, which looks perfectly safe in joint space. The guard has to
  see it in RAW space or it sees nothing wrong at all."""
  g = WrapGuard()
  assert g.update(KNEE, 271.59)["state"] == "blocked"
  # and the folded value it would have been mistaken for is NOT blocked, which is the point
  folded = math.degrees(math.atan2(math.sin(math.radians(271.59)), math.cos(math.radians(271.59))))
  assert abs(folded - (-88.41)) < 0.01
  assert WrapGuard().update(KNEE, folded)["state"] == "ok"


def test_an_observed_fold_latches_even_once_the_reading_looks_safe_again():
  """After a fold the same raw number means two different physical positions, and nothing on
  the wire says which - so it must stay blocked until a person unwinds it."""
  g = WrapGuard()
  g.update(KNEE, 179.0, now=10.00)
  r = g.update(KNEE, -179.0, now=10.01)   # a 358 deg step one tick later: the fold
  assert r["state"] == "blocked" and r["folded"]
  assert g.update(KNEE, 0.0, now=10.02)["state"] == "blocked", "must not un-block itself"
  g.clear(KNEE)
  assert g.update(KNEE, 0.0, now=10.03)["state"] == "ok"


def test_real_motion_is_not_mistaken_for_a_fold():
  """The fastest thing measured on this bench was 336 deg/s: 3.4 deg per 100 Hz tick. Even the
  RS04 no-load speed is only ~11 deg per tick. A jump has to be far bigger than any of that."""
  g = WrapGuard()
  raw, t = 0.0, 0.0
  for _ in range(200):
    raw += 11.0                        # no-load speed, every tick, still not a fold
    t += 0.01
    if abs(raw) > WRAP_WARN_DEG:
      break
    assert not g.update(KNEE, raw, now=t)["folded"]
  assert WRAP_JUMP_DEG > 100.0


def test_a_missing_reading_does_not_block():
  """A silent motor is the freeze detector's job. Blocking on absent data would withhold
  commands from every empty slot on a partial rig."""
  g = WrapGuard()
  for bad in (None, float("nan"), float("inf")):
    assert g.update(KNEE, bad)["state"] == "unknown"


def test_each_joint_is_tracked_separately():
  g = WrapGuard()
  g.update("knee", 179.0, now=1.00)
  g.update("knee", -179.0, now=1.01)
  assert g.update("knee", 0.0, now=1.02)["state"] == "blocked"
  assert g.update("hip_yaw", 0.0, now=1.02)["state"] == "ok", "one fold must not block another joint"


def test_the_message_says_what_to_do():
  g = WrapGuard()
  msg = describe_wrap_simple("knee", g.update(KNEE, 175.0))
  assert "되감" in msg, "must tell the operator to unwind it, not just report a number"
  assert "명령을 멈춤" in msg


def test_two_readings_far_apart_in_time_are_not_a_fold():
  """A motor that goes quiet and comes back somewhere else has not folded - it just was not
  being watched. Blocking on that would take out a healthy joint after any comms gap."""
  g = WrapGuard()
  g.update(KNEE, 170.0, now=100.0)
  r = g.update(KNEE, -170.0, now=100.0 + WRAP_JUMP_WINDOW_S + 0.1)
  assert not r["folded"], "a stale previous reading must not be compared"
  # ...but the same pair one tick apart IS a fold
  g2 = WrapGuard()
  g2.update(KNEE, 170.0, now=100.0)
  assert g2.update(KNEE, -170.0, now=100.01)["folded"]
