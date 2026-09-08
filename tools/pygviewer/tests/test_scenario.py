"""A setup gets a name only when all three axes match exactly, and loses it the moment one moves.

The point of naming a combination is that an operator can glance at one word and know whether
torque can reach the robot. That only holds if the name is never approximately right - a label
that survives a changed axis is worse than no label, because it is believed.
"""
import re
from pathlib import Path

import pytest

from pygviewer import scenario as S

DRIVE = "drive-both"
ARMED = dict(mode="manual", tx_armed=True, reported_id=S.PROGRAM_REMOTE_MOTION, age_s=0.1)


def test_the_one_combination_that_arms_torque_is_named_and_flagged():
  st = S.status(**ARMED)
  assert st["key"] == DRIVE
  assert st["arms_torque"] is True, "the only setup that reaches the motors must say so"


def test_changing_any_single_axis_removes_the_name():
  for override in ({"mode": "idle"}, {"tx_armed": False},
                   {"reported_id": S.PROGRAM_OBS_STREAMER}):
    st = S.status(**{**ARMED, **override})
    assert st["key"] is None, f"{override} must fall to no-name, not keep a stale one"
    assert st["nearest"]["differences"], "and must say what differs"


def test_a_robot_that_stopped_talking_is_unknown_not_remembered():
  """A name derived from a dead link is exactly the stale confidence this guards against."""
  st = S.status(**{**ARMED, "age_s": S.PROGRAM_STALE_S + 0.1})
  assert st["program"]["confirm"] == "unknown"
  assert st["key"] is None
  assert any("알 수 없" in d for d in st["nearest"]["differences"])


def test_no_report_at_all_is_unknown():
  st = S.status(mode="manual", tx_armed=True, reported_id=None, age_s=None)
  assert st["program"]["confirm"] == "unknown"
  assert st["key"] is None


def test_an_unrecognised_program_is_a_mismatch_not_a_match():
  st = S.status(mode="manual", tx_armed=True, reported_id=99, age_s=0.1)
  assert st["program"]["confirm"] == "mismatch"
  assert st["key"] is None
  assert any("모르는 프로그램" in d for d in st["nearest"]["differences"])


def test_the_nearest_named_combination_is_the_one_with_fewest_differences():
  st = S.status(mode="idle", tx_armed=True, reported_id=S.PROGRAM_REMOTE_MOTION, age_s=0.1)
  assert st["nearest"]["key"] == DRIVE
  assert st["nearest"]["differences"] == ["화면 모드가 'idle' 입니다 (필요: 'manual')"]


def test_arming_warning_appears_only_when_torque_would_actually_turn_on():
  assert S.would_arm_torque(tx_armed=False, key=DRIVE) is True
  assert S.would_arm_torque(tx_armed=True, key=DRIVE) is False, "already armed - no new risk"
  assert S.would_arm_torque(tx_armed=False, key="mirror-hardware") is False


def test_combinations_we_cannot_run_yet_say_why_instead_of_offering_themselves():
  st = S.status(**ARMED)
  for c in st["choices"]:
    if c["key"] == DRIVE:
      assert c["available"] and c["unavailable_reason"] is None
    else:
      assert not c["available"], c["key"]
      assert c["unavailable_reason"], "an unavailable choice must say what is missing"


def test_exactly_one_named_combination_reaches_the_hardware():
  assert sum(1 for s in S.SCENARIOS if s.arms_torque) == 1


def test_every_choice_carries_what_it_would_do_before_it_is_pressed():
  st = S.status(mode="idle", tx_armed=False, reported_id=None, age_s=None)
  for c in st["choices"]:
    assert c["action"], c["key"]
    assert isinstance(c["differences"], list)


def test_the_current_combination_is_marked_among_the_choices():
  st = S.status(**ARMED)
  cur = [c for c in st["choices"] if c["is_current"]]
  assert [c["key"] for c in cur] == [DRIVE]


# ------------------------------------- a mode change must have HAPPENED before it is reported
# 2026-09-08, user: "지금 무엇을 하는가 섹션에서 모드 선택해도 제대로 그 모드로 안바뀌는데"
#
# `SimCore.submit` only queues; `self.mode` changes on the next control tick. Both mode paths
# answered before that, and the scenario panel made the gap visible: it re-derived its own
# response straight after submitting, so the payload the panel redraws from still carried the
# OLD mode - selecting a setup looked like it did nothing, while `done` claimed
# "화면 모드를 '...' 로 바꿨습니다". The same race had already bitten from the other side:
# `POST /tx/arm` refuses outside `manual`, so setting the mode and arming immediately was
# refused with "sim mode is 'idle'" moments after the mode control reported success.

def test_scenario_apply_never_claims_an_unapplied_mode_change():
  """The panel redraws from this very response, so a premature success line is a claim the
  picture immediately contradicts. When the change has not landed it belongs in `todo`."""
  src = (Path(__file__).resolve().parents[1] / "pygviewer" / "api.py").read_text()
  m = re.search(r'core\.submit\(\{"op": "mode", "value": sc\.mode\}\).*?로 바뀌지 않았습니다',
                src, re.S)
  assert m, "the scenario apply path must branch on whether the mode landed"
  assert "if _await_mode(sc.mode):" in src


def test_mode_post_returns_the_real_current_mode():
  src = (Path(__file__).resolve().parents[1] / "pygviewer" / "api.py").read_text()
  assert '"mode": core.mode, "applied": applied' in src, (
    "POST /mode must report the mode it actually left the sim in, not just ok"
  )


def test_the_waiter_reports_failure_rather_than_hanging():
  """A sim that is not stepping must get a plain False, not a stall."""
  src = (Path(__file__).resolve().parents[1] / "pygviewer" / "api.py").read_text()
  m = re.search(r"def _await_mode\(.*?\n    return core\.mode == want", src, re.S)
  assert m, "_await_mode() not found"
  assert "MODE_APPLY_DEADLINE_S" in m.group(0)
