"""Changing the run mode has to be possible from somewhere obvious.

2026-09-08, user: "그리고 모드 변경은 어디서 하냐고." The answer at the time was: five places,
none of them called "mode".

  * a segmented control inside Control > Policy - only reachable through a sub-tab of a tab
  * a SIDE EFFECT of opening Control > Joints - and broken, because the viewer starts with
    that sub-tab already selected, so the tab-open that requests `manual` never fires
  * a "mode: file_replay" button under Replay, at the bottom of the Telemetry tab
  * the scenario tab's apply, which sets three things at once
  * a fix button added the same day to the ARM blocker line

Meanwhile the one place on screen where the word "mode" appears - the top bar, visible from
every tab - was a read-only caption. So the only label that named the thing was the only
control that could not set it.

These tests are the static half. The half that matters more is `scripts/ux_check.py`, which
opens the running page and actually operates it - reading the source cannot tell you that a
button is unclickable, and that is the failure mode this whole area kept producing.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "pygviewer" / "static"
DASHBOARD_JS = STATIC / "dashboard.js"
DASHBOARD_HTML = STATIC / "dashboard.html"
MODES_PY = Path(__file__).resolve().parents[1] / "pygviewer" / "modes.py"
UX_CHECK = Path(__file__).resolve().parents[1] / "scripts" / "ux_check.py"


def test_the_top_bar_mode_is_a_control_not_a_caption():
  html = DASHBOARD_HTML.read_text()
  assert 'id="mode-select"' in html
  m = re.search(r'<select[^>]*id="mode-select"', html)
  assert m, "it has to be an actual control element, not a styled span"
  assert 'id="pill-mode"' not in html, "the read-only caption should be gone, not duplicated"


def test_it_offers_every_mode_the_server_has():
  """A picker that silently omits modes is how someone concludes a mode does not exist."""
  js = DASHBOARD_JS.read_text()
  m = re.search(r"const MODE_LABELS = \{.*?\n\};", js, re.S)
  assert m, "MODE_LABELS not found"
  labels = m.group(0)
  declared = re.search(r"MODES = \((.*?)\)", MODES_PY.read_text(), re.S).group(1)
  for mode in re.findall(r'"([a-z_]+)"', declared):
    assert f"{mode}:" in labels, f"the picker does not offer {mode!r}"


def test_every_mode_is_described_in_words():
  """`policy_shadow` tells an operator nothing about whether it moves the robot."""
  js = DASHBOARD_JS.read_text()
  labels = re.search(r"const MODE_LABELS = \{.*?\n\};", js, re.S).group(0)
  for line in labels.splitlines():
    if ":" in line and '"' in line:
      text = line.split('"')[1]
      assert " - " in text, f"no plain-language gloss: {text!r}"


def test_the_picker_shows_the_server_mode_not_the_click():
  """The complaint before this one was a mode selection that appeared to work and did not
  (2026-09-08: "지금 무엇을 하는가 섹션에서 모드 선택해도 제대로 그 모드로 안바뀌는데"). A
  picker that keeps whatever was clicked is exactly that bug with a new face."""
  js = DASHBOARD_JS.read_text()
  m = re.search(r"function renderModeSelect\(st\)\s*\{.*?\n\}", js, re.S)
  assert m, "renderModeSelect() not found"
  assert "sel.value = mode" in m.group(0), "it must follow the server's reported mode"
  w = re.search(r"function wireModeSelect\(\)\s*\{.*?\n\}\n", js, re.S)
  assert w, "wireModeSelect() not found"
  body = w.group(0)
  assert "renderModeSelect(S.status)" in body, "a refused change must snap back to the truth"
  assert "r.mode !== want" in body, "an accepted-but-not-applied change counts as not applied"


def test_the_picker_is_wired_at_boot():
  js = DASHBOARD_JS.read_text()
  boot = re.search(r"function boot\(\)\s*\{.*?\n\}", js, re.S).group(0)
  assert "wireModeSelect()" in boot


def test_unavailable_modes_are_greyed_with_the_reason_not_hidden():
  """"policy_sim is missing" is a worse puzzle than "policy_sim (load a policy first)"."""
  js = DASHBOARD_JS.read_text()
  m = re.search(r"function modeUnavailableReason\(mode, st\)\s*\{.*?\n\}", js, re.S)
  assert m, "modeUnavailableReason() not found"
  assert "load a policy first" in m.group(0)
  assert "st.policy" in m.group(0), "the precondition must come from the server, not a guess"
  render = re.search(r"function renderModeSelect\(st\)\s*\{.*?\n\}", js, re.S).group(0)
  assert "disabled" in render and "why" in render


def test_the_picker_is_not_rebuilt_under_an_open_dropdown():
  """renderTopBar runs on every status poll. Rewriting a <select>'s options closes it mid-pick
  - the same class of bug as a button destroyed between press and release."""
  js = DASHBOARD_JS.read_text()
  render = re.search(r"function renderModeSelect\(st\)\s*\{.*?\n\}", js, re.S).group(0)
  assert "sel.dataset.opts !== opts" in render


# ---------------------------------------------------------------- the check that operates it
def test_there_is_a_check_that_actually_presses_things():
  """The standing failure was verifying by reading code. Reading cannot see a disabled button
  swallowing a click, a node replaced mid-press, or a reason rendered below the fold - all
  three shipped. This file is the guard that the operating check keeps existing."""
  assert UX_CHECK.exists(), "scripts/ux_check.py is missing"
  src = UX_CHECK.read_text()
  assert "async_playwright" in src, "it has to drive a real browser"
  for needed in ["is_disabled", "click(", "select_option"]:
    assert needed in src, f"it has to actually operate the page ({needed})"
  assert "no3d=1" in src, "the 3D pane is a separate program with its own errors - exclude it"


def test_the_ux_check_never_arms_the_hardware():
  """It presses ARM on purpose - that is the behaviour under test - so it must only ever do so
  in a state the server refuses, or a check would put torque on the bench motors."""
  src = UX_CHECK.read_text()
  arm = src.split("전송 켜기(ARM)")[1]
  assert 'select_option("#mode-select", "idle")' in src.split("전송 켜기(ARM)")[0][-800:], \
    "it must force a blocked state before pressing ARM"
  assert "blocked" in arm, "and it must assert the press was refused with a reason"
