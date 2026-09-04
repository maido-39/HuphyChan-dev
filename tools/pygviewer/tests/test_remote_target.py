"""docs/123 plan A item 3: the receive-side safety state machine (``bridge/remote_target.py``)
shared by ``dummy_rx.py`` and ``huphy_remote_motion.py``. All timing here uses an injected
fake clock (``now=``) - never a real ``time.sleep`` - so "0.2s deadman" and "3s return-to-
default" are exact, not "close enough after a real sleep", matching item 7's requirement that
the deadman-trigger timing be verifiable to 0.2 +- 0.05 s.
"""

import pytest

from pygviewer.bridge.remote_target import DeadmanFilter, LatestOnly
from pygviewer.schema import JointTarget


def _msg(seq=1, arm_token="tok", contract_hash="abc", joint_names=("L_knee_joint",),
         q_target=(0.3,), ttl_ms=100, origin="manual"):
  return JointTarget(
    t_ns=1, seq=seq, arm_token=arm_token, origin=origin, contract_hash=contract_hash,
    joint_names=list(joint_names), q_target=list(q_target), ttl_ms=ttl_ms,
  )


# --------------------------------------------------------------------------- LatestOnly
def test_first_message_is_accepted():
  lo = LatestOnly(expected_arm_token="tok")
  assert lo.put(_msg(seq=1), now=0.0) is True
  msg, age = lo.get(now=0.0)
  assert msg is not None and age == pytest.approx(0.0)


def test_nothing_accepted_yet_reports_infinite_age():
  lo = LatestOnly(expected_arm_token="tok")
  msg, age = lo.get(now=5.0)
  assert msg is None
  assert age == float("inf")


def test_seq_regression_is_rejected_and_counted():
  lo = LatestOnly(expected_arm_token="tok")
  lo.put(_msg(seq=5), now=0.0)
  assert lo.put(_msg(seq=3), now=0.1) is False
  assert lo.stats.rejected_seq == 1
  msg, _ = lo.get(now=0.1)
  assert msg.seq == 5  # unchanged - the stale/reordered packet did not overwrite it


def test_duplicate_seq_is_also_rejected():
  lo = LatestOnly(expected_arm_token="tok")
  lo.put(_msg(seq=5), now=0.0)
  assert lo.put(_msg(seq=5), now=0.1) is False
  assert lo.stats.rejected_seq == 1


def test_wrong_arm_token_is_rejected_and_counted():
  lo = LatestOnly(expected_arm_token="expected-tok")
  assert lo.put(_msg(arm_token="wrong-tok"), now=0.0) is False
  assert lo.stats.rejected_arm_token == 1
  assert lo.get(now=0.0)[0] is None


def test_mismatched_contract_hash_is_rejected_and_counted():
  lo = LatestOnly(expected_arm_token="tok", expected_contract_hash="expected-sha")
  assert lo.put(_msg(contract_hash="different-sha"), now=0.0) is False
  assert lo.stats.rejected_contract == 1


def test_none_contract_hash_is_allowed_through_as_unknown_not_wrong():
  lo = LatestOnly(expected_arm_token="tok", expected_contract_hash="expected-sha")
  assert lo.put(_msg(contract_hash=None), now=0.0) is True
  assert lo.stats.rejected_contract == 0


def test_age_advances_with_the_injected_clock():
  lo = LatestOnly(expected_arm_token="tok")
  lo.put(_msg(seq=1), now=10.0)
  _, age = lo.get(now=10.35)
  assert age == pytest.approx(0.35, abs=1e-9)


# --------------------------------------------------------------------------- DeadmanFilter
def test_fresh_message_is_phase_live_with_its_own_target():
  f = DeadmanFilter(default_q={"L_knee_joint": 0.0}, deadman_s=0.2, return_s=3.0)
  msg = _msg(q_target=(0.5,))
  state = f.update(msg, age_s=0.05, now=0.0)
  assert state.phase == "live"
  assert state.target["L_knee_joint"] == pytest.approx(0.5)


def test_never_received_anything_goes_straight_to_idle_default():
  f = DeadmanFilter(default_q={"L_knee_joint": 0.7}, deadman_s=0.2, return_s=3.0)
  state = f.update(None, age_s=float("inf"), now=0.0)
  assert state.phase == "idle"
  assert state.target["L_knee_joint"] == pytest.approx(0.7)


def test_deadman_triggers_exactly_at_the_stale_boundary_and_holds_the_last_pose():
  """0.2 +- 0.05 s deadman timing, item 7's own precision requirement."""
  f = DeadmanFilter(default_q={"L_knee_joint": 0.0}, deadman_s=0.2, return_s=3.0)
  msg = _msg(q_target=(0.5,), ttl_ms=1_000_000)  # ttl not the binding constraint here
  f.update(msg, age_s=0.05, now=0.0)  # establish a live target

  just_under = f.update(msg, age_s=0.19, now=0.19)
  assert just_under.phase == "live"

  just_over = f.update(msg, age_s=0.21, now=0.21)
  assert just_over.phase == "hold"
  assert just_over.target["L_knee_joint"] == pytest.approx(0.5)  # frozen at the last live pose


def test_ttl_ms_can_trigger_the_deadman_earlier_than_deadman_s():
  f = DeadmanFilter(default_q={"L_knee_joint": 0.0}, deadman_s=0.2, return_s=3.0)
  msg = _msg(q_target=(0.5,), ttl_ms=50)  # 50ms ttl, stricter than the 0.2s deadman_s
  f.update(msg, age_s=0.01, now=0.0)
  state = f.update(msg, age_s=0.06, now=0.06)  # past ttl (0.05s) but under deadman_s (0.2s)
  assert state.phase == "hold"


def test_returning_interpolates_linearly_between_hold_pose_and_default_over_return_s():
  """``hold_s=0`` isolates the ``returning`` phase's own timing from the (now separate,
  docs/123 section 5) flat-hold phase - the old single-phase "slew starts the instant the
  deadman trips" behaviour, still available as a special case."""
  f = DeadmanFilter(default_q={"L_knee_joint": 0.0}, deadman_s=0.2, hold_s=0.0, return_s=3.0)
  msg = _msg(q_target=(0.6,), ttl_ms=1_000_000)
  f.update(msg, age_s=0.0, now=0.0)              # live, hold pose will be 0.6
  f.update(msg, age_s=1.0, now=1.0)              # deadman trips here, hold_since=1.0

  halfway = f.update(msg, age_s=2.5, now=1.0 + 1.5)   # 1.5s into a 3s return
  assert halfway.phase == "returning"
  assert halfway.target["L_knee_joint"] == pytest.approx(0.3, abs=1e-6)  # halfway to 0.0

  done = f.update(msg, age_s=10.0, now=1.0 + 3.0)     # exactly return_s later
  assert done.phase == "default"
  assert done.target["L_knee_joint"] == pytest.approx(0.0, abs=1e-6)

  after = f.update(msg, age_s=20.0, now=1.0 + 10.0)   # long after - stays at default
  assert after.phase == "default"
  assert after.target["L_knee_joint"] == pytest.approx(0.0, abs=1e-6)


def test_hold_phase_is_flat_for_hold_s_before_any_slew_begins():
  """docs/123 section 5 resolution (2026-09-04): after the deadman trips, the pose is frozen
  (no motion at all) for a flat ``hold_s`` seconds - only then does the ``return_s`` slew
  begin. This is what separates the current 3-knob design from the old 2-knob one."""
  f = DeadmanFilter(default_q={"L_knee_joint": 0.0}, deadman_s=0.2, hold_s=3.0, return_s=2.0)
  msg = _msg(q_target=(0.6,), ttl_ms=1_000_000)
  f.update(msg, age_s=0.0, now=0.0)     # live, hold pose will be 0.6
  f.update(msg, age_s=1.0, now=1.0)     # deadman trips here, hold_since=1.0

  still_holding = f.update(msg, age_s=2.9, now=1.0 + 2.9)  # 2.9s into the 3s flat hold
  assert still_holding.phase == "hold"
  assert still_holding.target["L_knee_joint"] == pytest.approx(0.6)  # unchanged, not moving

  just_after_hold = f.update(msg, age_s=3.1, now=1.0 + 3.1)  # 0.1s into the return
  assert just_after_hold.phase == "returning"
  assert just_after_hold.target["L_knee_joint"] == pytest.approx(0.6 * (1.0 - 0.1 / 2.0), abs=1e-6)

  done = f.update(msg, age_s=10.0, now=1.0 + 3.0 + 2.0)  # hold_s + return_s later
  assert done.phase == "default"
  assert done.target["L_knee_joint"] == pytest.approx(0.0, abs=1e-6)


def test_recovering_before_the_deadman_trips_resets_cleanly_with_no_hold_phase():
  f = DeadmanFilter(default_q={"L_knee_joint": 0.0}, deadman_s=0.2, return_s=3.0)
  msg1 = _msg(q_target=(0.5,), seq=1, ttl_ms=1_000_000)
  f.update(msg1, age_s=0.05, now=0.0)
  msg2 = _msg(q_target=(0.55,), seq=2, ttl_ms=1_000_000)
  state = f.update(msg2, age_s=0.02, now=0.15)  # a fresh packet arrived before 0.2s elapsed
  assert state.phase == "live"
  assert state.target["L_knee_joint"] == pytest.approx(0.55)


def test_recovering_mid_hold_snaps_back_to_live_not_a_blended_value():
  f = DeadmanFilter(default_q={"L_knee_joint": 0.0}, deadman_s=0.2, hold_s=3.0, return_s=2.0)
  msg1 = _msg(q_target=(0.5,), seq=1, ttl_ms=1_000_000)
  f.update(msg1, age_s=0.0, now=0.0)
  f.update(msg1, age_s=1.0, now=1.0)   # deadman trips, enters flat hold
  f.update(msg1, age_s=2.0, now=2.0)   # mid-hold
  msg2 = _msg(q_target=(0.5,), seq=2, ttl_ms=1_000_000)
  state = f.update(msg2, age_s=0.01, now=2.5)   # fresh packet arrives again
  assert state.phase == "live"
  assert state.target["L_knee_joint"] == pytest.approx(0.5)


def test_recovering_mid_return_snaps_back_to_live_not_a_blended_value():
  f = DeadmanFilter(default_q={"L_knee_joint": 0.0}, deadman_s=0.2, hold_s=0.0, return_s=3.0)
  msg1 = _msg(q_target=(0.5,), seq=1, ttl_ms=1_000_000)
  f.update(msg1, age_s=0.0, now=0.0)
  f.update(msg1, age_s=1.0, now=1.0)   # deadman trips, starts returning (hold_s=0)
  f.update(msg1, age_s=2.0, now=2.0)   # mid-return
  msg2 = _msg(q_target=(0.5,), seq=2, ttl_ms=1_000_000)
  state = f.update(msg2, age_s=0.01, now=2.5)   # fresh packet arrives again
  assert state.phase == "live"
  assert state.target["L_knee_joint"] == pytest.approx(0.5)


def test_enable_list_restricts_the_live_target_to_named_joints_only():
  f = DeadmanFilter(
    default_q={"L_knee_joint": 0.0, "L_hip_pitch_joint": 0.0},
    deadman_s=0.2, return_s=3.0, enable={"L_knee_joint"},
  )
  msg = _msg(joint_names=("L_knee_joint", "L_hip_pitch_joint"), q_target=(0.5, 0.4))
  state = f.update(msg, age_s=0.0, now=0.0)
  assert set(state.target) == {"L_knee_joint"}
  assert state.target["L_knee_joint"] == pytest.approx(0.5)


def test_enable_list_also_restricts_the_hold_and_return_targets():
  f = DeadmanFilter(
    default_q={"L_knee_joint": 0.0, "L_hip_pitch_joint": 0.0},
    deadman_s=0.2, return_s=3.0, enable={"L_knee_joint"},
  )
  msg = _msg(joint_names=("L_knee_joint", "L_hip_pitch_joint"), q_target=(0.5, 0.4),
             ttl_ms=1_000_000)
  f.update(msg, age_s=0.0, now=0.0)
  held = f.update(msg, age_s=1.0, now=1.0)
  assert set(held.target) == {"L_knee_joint"}
