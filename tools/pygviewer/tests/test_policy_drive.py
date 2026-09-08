"""Letting a policy's own output reach the motors, and what that costs.

2026-09-08, user: "Policy 출력 실제로 모터 제어하는거 시작해줘", after being told the bench
has 2 of 12 joints and that a policy's output for a robot that is not there is not a gait.

## What actually stood in the way

Nothing needed rewiring. In ``policy_sim`` the policy writes straight into ``SimCore.target``
- the very attribute TX reads - so the target was always reaching the send path. The property
"policy output must never be transmittable" was carried entirely by the mode gate. Opening it
is therefore a decision, not a feature: three lines of predicate, and the wiring underneath is
untouched.

## What replaces it

``allow_policy`` is off by default, and with it off every path behaves exactly as before.
Turning it on is refused unless a per-packet step cap comes with it, because the guards that
protect a manual session do not protect a policy one:

* the sync gate, the arm-jump ceiling and the mode check all run ONCE, at arm time
* an operator's target then moves as fast as a hand moves a slider
* a policy rewrites all of them every 20 ms, so after the first packet only a per-packet cap
  is still doing anything

The cap is anchored to the previous COMMAND, not to the measurement - the distinction this
project paid for twice (docs/124 section 2-2): anchoring to the measurement turns a speed
limit into a torque cap and stalls the command whenever the motor lags.

``policy_shadow`` is never allowed. It exists to watch a policy without letting it drive, and
a shadow that reaches the motors is a contradiction.
"""

from __future__ import annotations

import math
import time

import pytest

from pygviewer import CACHE_DIR
from pygviewer.bridge.tx_client import BLOCKED_MODES, TxClient
from pygviewer.contract import load_contract
from pygviewer.tx import POLICY_MODES, TxNotAllowed, TxState

VARIANT = "LegOnly-AB"
HOST, PORT = "10.8.0.14", 9872


def _contract():
  try:
    return load_contract(CACHE_DIR, VARIANT)
  except FileNotFoundError:
    pytest.skip(f"no baked contract for {VARIANT}")


def _tx():
  c = _contract()
  return TxState(list(c.action_joint_names), c), c


# ------------------------------------------------------------------- off by default
def test_policy_is_refused_unless_asked_for():
  tx, c = _tx()
  a = c.action_joint_names[0]
  tx.configure(HOST, PORT, [a])
  tx.set_enabled(True)
  assert tx.allow_policy is False
  assert tx.mode_allowed("manual") is True
  for m in ("policy_sim", "policy_shadow", "file_replay", "idle"):
    assert tx.mode_allowed(m) is False, m
  with pytest.raises(TxNotAllowed) as e:
    tx.check_armable("policy_sim")
  assert "allow_policy" in str(e.value)


def test_turning_it_on_needs_a_per_packet_cap():
  """The one guard that still works once a policy is writing 50 targets a second. Refused
  rather than warned about, so it cannot be the thing someone forgets."""
  tx, c = _tx()
  a = c.action_joint_names[0]
  for bad in (None, 0.0, -1.0):
    with pytest.raises(TxNotAllowed) as e:
      tx.configure(HOST, PORT, [a], allow_policy=True, max_step_deg=bad)
    assert "max_step_deg" in str(e.value)
  assert tx.allow_policy is False, "a refused configure must not half-apply"


def test_shadow_is_never_allowed():
  """A mode whose entire purpose is to not drive."""
  tx, c = _tx()
  a = c.action_joint_names[0]
  tx.configure(HOST, PORT, [a], allow_policy=True, max_step_deg=0.5)
  assert "policy_shadow" not in POLICY_MODES
  assert tx.mode_allowed("policy_sim") is True
  assert tx.mode_allowed("policy_shadow") is False
  with pytest.raises(TxNotAllowed):
    tx.check_armable("policy_shadow")


# ------------------------------------------------------------------- once it is on
def test_a_policy_mode_can_arm_and_stays_armed():
  tx, c = _tx()
  a = c.action_joint_names[0]
  tx.configure(HOST, PORT, [a], allow_policy=True, max_step_deg=0.5)
  tx.set_enabled(True)
  tx.arm("policy_sim")
  assert tx.armed
  tx.check_mode_gate("policy_sim")
  assert tx.armed, "the every-tick gate must not disarm a mode that was opted into"


def test_leaving_the_allowed_modes_still_disarms():
  """The structural gate has to keep working, or the opt-in becomes an opt-out of safety."""
  tx, c = _tx()
  a = c.action_joint_names[0]
  tx.configure(HOST, PORT, [a], allow_policy=True, max_step_deg=0.5)
  tx.set_enabled(True)
  tx.arm("policy_sim")
  tx.check_mode_gate("policy_shadow")
  assert not tx.armed
  assert "policy_shadow" in (tx.disarm_reason or "")


def test_the_arm_check_and_the_tick_gate_agree():
  """One predicate feeds both, so they cannot drift into disagreeing about what is allowed -
  which would show up as a session that arms and then immediately disarms itself."""
  tx, c = _tx()
  a = c.action_joint_names[0]
  for allow in (False, True):
    tx.configure(HOST, PORT, [a], allow_policy=allow,
                 max_step_deg=(0.5 if allow else None))
    tx.set_enabled(True)
    for m in ("manual", "policy_sim", "policy_shadow", "idle", "file_replay"):
      armable = True
      try:
        tx.check_armable(m)
      except TxNotAllowed:
        armable = False
      assert armable == tx.mode_allowed(m), (allow, m)


# ------------------------------------------------------------------- the cap does its job
def test_the_step_cap_limits_a_jump_and_keeps_advancing():
  """Anchored to the previous COMMAND: a far target is approached one step per packet, and the
  approach does NOT stall when the motor fails to keep up (the measured value never changes
  here, which is exactly the case that stalls a measurement-anchored limiter)."""
  c = _contract()
  a = c.action_joint_names[0]
  tx = TxClient(HOST, PORT, joint_names=[a], arm_token="t", origin="manual", contract=c,
                max_delta_rad=math.radians(0.5), allow_modes=frozenset(POLICY_MODES),
                state_fn=lambda: {a: 0.0})
  tx.arm()
  seen = []
  for _ in range(6):
    tx.set_target({a: math.radians(60.0)}, mode="policy_sim")
    msg = tx.build_message()
    seen.append(math.degrees(msg.q_target[0]))
  steps = [round(b - x, 6) for x, b in zip(seen, seen[1:])]
  assert all(abs(s - 0.5) < 1e-6 for s in steps), f"expected 0.5 deg per packet, got {steps}"
  assert seen[-1] < 60.0, "a far target must not be reached in one packet"


def test_the_blocked_mode_net_still_catches_what_was_not_opted_into():
  """Defense in depth survives: a client that opted into policy_sim still refuses the mode
  nobody opted into, which is the drifted-caller case this layer was written for."""
  c = _contract()
  a = c.action_joint_names[0]
  tx = TxClient(HOST, PORT, joint_names=[a], arm_token="t", origin="manual", contract=c,
                max_delta_rad=math.radians(0.5), allow_modes=frozenset({"policy_sim"}))
  tx.arm()
  tx.set_target({a: 0.1}, mode="policy_sim")          # opted in
  with pytest.raises(RuntimeError) as e:
    tx.set_target({a: 0.1}, mode="policy_shadow")     # not opted in
  assert "policy_shadow" in str(e.value)
  assert "policy_shadow" in BLOCKED_MODES


def test_a_client_with_no_opt_in_refuses_every_blocked_mode():
  """Unchanged behaviour for every existing caller."""
  c = _contract()
  a = c.action_joint_names[0]
  tx = TxClient(HOST, PORT, joint_names=[a], arm_token="t", origin="manual", contract=c)
  tx.arm()
  for m in sorted(BLOCKED_MODES):
    with pytest.raises(RuntimeError):
      tx.set_target({a: 0.1}, mode=m)


def test_status_says_out_loud_that_a_policy_may_drive():
  """"A policy can move the hardware right now" is not a state to leave implicit."""
  tx, c = _tx()
  a = c.action_joint_names[0]
  tx.configure(HOST, PORT, [a], allow_policy=True, max_step_deg=0.4)
  st = tx.status()
  assert st["allow_policy"] is True
  assert st["max_step_deg"] == 0.4


def test_arming_seeds_the_ramp_from_the_measured_pose():
  """Without this the FIRST packet after arming passes the cap untouched - and the first
  packet is the dangerous one, the whole reason hw_sync's arm-jump gate exists. Found by the
  test above coming back with a 0.0 deg step: the ramp had already jumped to the target."""
  c = _contract()
  a = c.action_joint_names[0]
  tx = TxClient(HOST, PORT, joint_names=[a], arm_token="t", origin="manual", contract=c,
                max_delta_rad=math.radians(0.5), state_fn=lambda: {a: math.radians(10.0)})
  tx.arm()
  tx.set_target({a: math.radians(40.0)}, mode="manual")
  first = math.degrees(tx.build_message().q_target[0])
  assert first == pytest.approx(10.5, abs=1e-6), (
    f"the first packet must ramp from the joint (10 deg), not jump; got {first:.2f}"
  )


def test_without_a_state_source_the_first_packet_is_not_seeded():
  """Stated rather than pretended: with nothing to read the pose from there is nothing to
  seed from, and behaviour is what it always was. TxState always supplies one, so this is the
  bare-library case, not the bench's."""
  c = _contract()
  a = c.action_joint_names[0]
  tx = TxClient(HOST, PORT, joint_names=[a], arm_token="t", origin="manual", contract=c,
                max_delta_rad=math.radians(0.5))
  tx.arm()
  # inside this joint's safe_clip, so the only thing that could hold it back is the slew cap
  tx.set_target({a: math.radians(15.0)}, mode="manual")
  assert math.degrees(tx.build_message().q_target[0]) == pytest.approx(15.0, abs=1e-6)


def test_a_broken_state_source_does_not_block_arming():
  c = _contract()
  a = c.action_joint_names[0]

  def boom():
    raise RuntimeError("telemetry thread died")

  tx = TxClient(HOST, PORT, joint_names=[a], arm_token="t", origin="manual", contract=c,
                max_delta_rad=math.radians(0.5), state_fn=boom)
  tx.arm()
  assert tx.armed


# --------------------------------------------- the sync gate has to let a policy session arm
def test_leaving_manual_for_an_allowed_policy_mode_keeps_the_sync():
  """Without this the feature is impossible rather than gated: leaving manual invalidated the
  sync, and a policy mode cannot re-sync (the policy rewrites the target every tick), so the
  arm gate could never be satisfied. Found live - the first policy arm was refused with
  "left manual mode (went to 'policy_sim') while synced".

  Not a loosening: the sync protects against a STALE OPERATOR target going out as the first
  packet. A policy's target is not stale; it is recomputed 50 times a second. The first packet
  is still covered by the arm-jump ceiling, which compares the live target against the live
  measurement and does not care where the target came from.
  """
  from pygviewer.hw_sync import HwSyncState

  st = HwSyncState()
  st.record_sync({"j": 0.1}, {"j": 0.1}, {"j": (-1.0, 1.0)}, "sha")
  st.note_mode("manual", tx_allows=True)
  st.note_mode("policy_sim", tx_allows=True)
  assert st.valid, "an opted-in policy mode must not invalidate the sync"


def test_leaving_manual_for_a_mode_nobody_opted_into_still_invalidates():
  from pygviewer.hw_sync import HwSyncState

  st = HwSyncState()
  st.record_sync({"j": 0.1}, {"j": 0.1}, {"j": (-1.0, 1.0)}, "sha")
  st.note_mode("manual", tx_allows=True)
  st.note_mode("file_replay", tx_allows=False)
  assert not st.valid
  assert "file_replay" in (st.reason or "")


def test_a_sync_made_outside_manual_is_still_not_invalidated_by_the_next_tick():
  """The 2026-09-04 rule this must not regress: syncing while idle, then staying idle, is not
  "leaving manual" and must survive."""
  from pygviewer.hw_sync import HwSyncState

  st = HwSyncState()
  st.record_sync({"j": 0.1}, {"j": 0.1}, {"j": (-1.0, 1.0)}, "sha")
  st.note_mode("idle")
  st.note_mode("idle")
  assert st.valid
