"""Resizable dashboard panes (2026-09-05, docs/121 section 14).

User ask: "지금 창 Pane 들 슬라이더 달아서 슬라이드가능하게 해" (put sliders/handles on the
window's panes so they can be resized) - plus a same-day, higher-priority finding: a headless
screenshot showed the violation-record panel floating `left:8px;right:8px` (the full window
width), sitting directly on top of the right control panel while a real motor was armed - the
operator had no way to reach the sliders/number inputs underneath.

There is no Node or browser on this host to run `dashboard.js` directly (see test_dashboard.py's
own docstring for the same constraint - obscura, a headless browser, exists on the machine that
drives this SESSION but not inside this repo's test host/CI), so - following this test suite's
established pattern (test_violation_console.py) - this file:

  1. mirrors dashboard.js's pure resize-arithmetic functions line-for-line in Python
     (clampColLeft/clampColRight/clampRowPlots/sanitizePaneLayout - no DOM, no globals, so a
     faithful mirror is possible at all), and
  2. locks the mirror against the actual shipped JS text, so a change to the real constants or
     formulas that is not mirrored here fails loudly instead of silently drifting.

Live-browser confirmation (screenshot + DOM query, obscura) that dragging a real divider and the
violation panel no longer overlapping the control pane is recorded in the session report /
docs/121 section 14, not here.
"""

import re
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[1] / "pygviewer" / "static"


def _dashboard_js_text():
  return (STATIC_DIR / "dashboard.js").read_text()


def _dashboard_html_text():
  return (STATIC_DIR / "dashboard.html").read_text()


# ============================================================================ Python mirrors
TOPBAR_H = 38
DIVIDER_PX = 7
PANE_MIN = {"left": 160, "right": 300, "center": 220, "mainH": 160, "plotsH": 120}
PANE_DEFAULTS = {
  "colLeft": 250, "colRight": 340, "rowPlots": 320,
  "leftCollapsed": False, "rightCollapsed": False, "plotsCollapsed": False,
}


def clamp(v, lo, hi):
  return max(lo, min(hi, v))


def clamp_col_left(value, container_w, col_right):
  max_left = container_w - 2 * DIVIDER_PX - col_right - PANE_MIN["center"]
  return clamp(value, PANE_MIN["left"], max(PANE_MIN["left"], max_left))


def clamp_col_right(value, container_w, col_left):
  max_right = container_w - 2 * DIVIDER_PX - col_left - PANE_MIN["center"]
  return clamp(value, PANE_MIN["right"], max(PANE_MIN["right"], max_right))


def clamp_row_plots(value, container_h):
  max_plots = container_h - TOPBAR_H - DIVIDER_PX - PANE_MIN["mainH"]
  return clamp(value, PANE_MIN["plotsH"], max(PANE_MIN["plotsH"], max_plots))


def sanitize_pane_layout(raw, container_w, container_h):
  d = PANE_DEFAULTS
  out = dict(d)
  if not isinstance(raw, dict):
    return out

  def num(v, fallback):
    return v if isinstance(v, (int, float)) and v == v and v not in (float("inf"), float("-inf")) else fallback

  out["leftCollapsed"] = raw.get("leftCollapsed") is True
  out["rightCollapsed"] = raw.get("rightCollapsed") is True
  out["plotsCollapsed"] = raw.get("plotsCollapsed") is True
  out["colLeft"] = clamp_col_left(num(raw.get("colLeft"), d["colLeft"]), container_w, num(raw.get("colRight"), d["colRight"]))
  out["colRight"] = clamp_col_right(num(raw.get("colRight"), d["colRight"]), container_w, out["colLeft"])
  out["colLeft"] = clamp_col_left(out["colLeft"], container_w, out["colRight"])
  out["rowPlots"] = clamp_row_plots(num(raw.get("rowPlots"), d["rowPlots"]), container_h)
  return out


# ============================================================================ clamp behaviour
def test_clamp_col_left_stays_within_min_and_max_on_a_normal_screen():
  # 1920px window, right pane at its default 340px -> plenty of room
  assert clamp_col_left(250, 1920, 340) == 250
  assert clamp_col_left(10, 1920, 340) == PANE_MIN["left"]  # dragged far past the floor
  assert clamp_col_left(100000, 1920, 340) == 1920 - 14 - 340 - PANE_MIN["center"]


def test_clamp_col_right_mirrors_col_left():
  assert clamp_col_right(340, 1920, 250) == 340
  assert clamp_col_right(10, 1920, 250) == PANE_MIN["right"]
  assert clamp_col_right(100000, 1920, 250) == 1920 - 14 - 250 - PANE_MIN["center"]


def test_clamp_row_plots_stays_within_min_and_max():
  assert clamp_row_plots(320, 1080) == 320
  assert clamp_row_plots(0, 1080) == PANE_MIN["plotsH"]
  assert clamp_row_plots(100000, 1080) == 1080 - TOPBAR_H - DIVIDER_PX - PANE_MIN["mainH"]


def test_clamp_never_returns_a_negative_size_even_on_a_tiny_window():
  # a window too small to fit even the minimums - the clamp must still return SOMETHING
  # sane (the floor), never a negative width that would invert the CSS grid track.
  assert clamp_col_left(999, 50, 999) == PANE_MIN["left"]
  assert clamp_col_right(999, 50, 999) == PANE_MIN["right"]
  assert clamp_row_plots(999, 10) == PANE_MIN["plotsH"]


# ============================================================================ sanitize_pane_layout
def test_sanitize_falls_back_to_defaults_when_nothing_is_stored():
  assert sanitize_pane_layout(None, 1920, 1080) == PANE_DEFAULTS
  assert sanitize_pane_layout({}, 1920, 1080) == PANE_DEFAULTS
  assert sanitize_pane_layout("garbage", 1920, 1080) == PANE_DEFAULTS


def test_sanitize_passes_through_a_valid_layout_unchanged():
  raw = {"colLeft": 300, "colRight": 380, "rowPlots": 260,
         "leftCollapsed": True, "rightCollapsed": False, "plotsCollapsed": False}
  out = sanitize_pane_layout(raw, 1920, 1080)
  assert out["colLeft"] == 300 and out["colRight"] == 380 and out["rowPlots"] == 260
  assert out["leftCollapsed"] is True and out["rightCollapsed"] is False


def test_sanitize_rejects_nan_and_non_numeric_fields_back_to_default():
  raw = {"colLeft": float("nan"), "colRight": "not a number", "rowPlots": None}
  out = sanitize_pane_layout(raw, 1920, 1080)
  assert out["colLeft"] == PANE_DEFAULTS["colLeft"]
  assert out["colRight"] == PANE_DEFAULTS["colRight"]
  assert out["rowPlots"] == PANE_DEFAULTS["rowPlots"]


def test_sanitize_shrinks_a_layout_saved_on_a_much_wider_screen():
  # saved on a 3440px ultrawide, reloaded on a 1024px laptop - must not leave a pane wider
  # than the new window, and must not go negative.
  raw = {"colLeft": 900, "colRight": 1200, "rowPlots": 320}
  out = sanitize_pane_layout(raw, 1024, 768)
  assert out["colLeft"] + out["colRight"] + 2 * DIVIDER_PX + PANE_MIN["center"] <= 1024 + 1  # +1 fp slack
  assert out["colLeft"] >= PANE_MIN["left"]
  assert out["colRight"] >= PANE_MIN["right"]


def test_sanitize_treats_collapsed_flags_as_valid_at_any_size():
  raw = {"leftCollapsed": True, "rightCollapsed": True, "plotsCollapsed": True}
  out = sanitize_pane_layout(raw, 320, 240)  # a tiny window
  assert out["leftCollapsed"] and out["rightCollapsed"] and out["plotsCollapsed"]


# ============================================================================ source-text locks
def test_dashboard_js_pane_constants_match_the_mirror():
  src = _dashboard_js_text()
  assert "const TOPBAR_H = 38;" in src
  assert "const DIVIDER_PX = 7;" in src
  assert "left: 160," in src and "right: 300," in src and "center: 220," in src
  assert "mainH: 160," in src and "plotsH: 120," in src
  assert 'const PANE_LS_KEY = "pygviewer.paneLayout.v1";' in src


def test_dashboard_js_clamp_functions_use_the_expected_formula():
  src = _dashboard_js_text()
  assert "containerW - 2 * DIVIDER_PX - colRight - PANE_MIN.center" in src
  assert "containerW - 2 * DIVIDER_PX - colLeft - PANE_MIN.center" in src
  assert "containerH - TOPBAR_H - DIVIDER_PX - PANE_MIN.mainH" in src


def test_dashboard_js_sanitize_rejects_non_finite_numbers():
  src = _dashboard_js_text()
  m = re.search(r"function sanitizePaneLayout\(raw, containerW, containerH\) \{.*?\n\}", src, re.S)
  assert m, "sanitizePaneLayout not found"
  body = m.group(0)
  assert "Number.isFinite(v)" in body
  assert 'typeof raw !== "object"' in body


def test_dashboard_js_persists_layout_and_violation_open_state_together():
  src = _dashboard_js_text()
  m = re.search(r"function savePaneLayout\(\) \{.*?\n\}", src, re.S)
  assert m, "savePaneLayout not found"
  body = m.group(0)
  for field in ("colLeft", "colRight", "rowPlots", "leftCollapsed", "rightCollapsed", "plotsCollapsed", "violationOpen"):
    assert field in body, f"savePaneLayout does not persist {field}"


def test_dashboard_js_onmove_guards_against_non_finite_pointer_coordinates():
  """Found live (2026-09-05) driving a real pointerdown/move/up sequence through obscura, the
  headless browser used for this feature's own screenshot verification: its PointerEvent did
  not carry clientX/clientY the way the constructor init dict asked for, so onMove computed
  NaN and stored it - which JSON-serializes as `null` and, worse, becomes an INVALID `var()`
  substitution for grid-template-columns/rows in a real browser, breaking the whole grid's
  layout instead of just that one pane. onMove must bail out before the clamp math if either
  coordinate is not finite."""
  src = _dashboard_js_text()
  on_move = re.search(r"function onMove\(mv\) \{.*?\n    \}", src, re.S).group(0)
  assert "Number.isFinite(mv.clientX)" in on_move
  assert "Number.isFinite(mv.clientY)" in on_move


def test_dashboard_js_only_rebuilds_plots_once_after_drag_not_during():
  # the drag-move handler must touch only CSS custom properties (applyPaneSizes), never
  # buildPlotGrid/uPlot directly - the rebuild-once behaviour comes from re-dispatching a
  # "resize" event on pointerup, which the existing debounced window listener picks up.
  src = _dashboard_js_text()
  on_move = re.search(r"function onMove\(mv\) \{.*?\n    \}", src, re.S).group(0)
  assert "buildPlotGrid" not in on_move
  assert "new uPlot" not in on_move
  after_settled = re.search(r"function afterDragSettled\(\) \{.*?\}", src).group(0)
  assert "window.dispatchEvent(new Event(\"resize\"))" in after_settled


def test_dashboard_js_toggle_violation_panel_persists_state():
  src = _dashboard_js_text()
  fn = re.search(r"function toggleViolationPanel\(\) \{.*?\n\}", src, re.S).group(0)
  assert "savePaneLayout()" in fn


# ------------------------------------------------------------------ HTML/CSS structural locks
def test_html_has_three_divider_handles():
  html = _dashboard_html_text()
  for handle_id in ("divider-left", "divider-right", "divider-bottom"):
    assert f'id="{handle_id}"' in html


def test_css_pane_sizes_are_custom_properties_not_hardcoded_literals():
  html = _dashboard_html_text()
  assert "--col-left" in html and "--col-right" in html and "--row-plots" in html
  # the OLD hardcoded grid-template-columns/rows line must be gone
  assert "grid-template-columns:250px 1fr 340px" not in html
  assert "grid-template-rows:38px 1fr 320px" not in html


def test_violation_panel_is_bounded_by_the_same_column_variables_as_the_grid():
  """The root-cause fix for "위반 기록창이 오른쪽 조작판을 통째로 덮고 있었다": left/right on
  the violation panel are pinned to --col-left/--col-right (inherited from .wrap, since the
  panel is one of its children) instead of fixed `8px` from each edge. Because those are the
  SAME custom properties the resizable grid itself uses for the left/right pane widths, the
  panel is structurally confined to the middle (scene) column at any width the user drags the
  left/right panes to - it cannot cover either pane, not just "usually doesn't"."""
  html = _dashboard_html_text()
  m = re.search(r"\.violation-panel\{[^}]*\}", html, re.S)
  assert m, ".violation-panel rule not found"
  rule = m.group(0)
  assert "left:calc(var(--col-left)" in rule.replace(" ", "")
  assert "right:calc(var(--col-right)" in rule.replace(" ", "")
  assert "left:8px" not in rule and "right:8px" not in rule


def test_user_select_none_while_dragging():
  html = _dashboard_html_text()
  assert "user-select:none" in html
  assert "resizing-v" in html and "resizing-h" in html


def test_pane_min_sizes_leave_room_for_the_joint_row_grid():
  """The right pane's floor (300px) must be able to fit the Control tab's own
  .joint-row grid-template-columns (88+1fr+62+52+20, 4 gaps of 6px = 24px fixed overhead)
  plus the .rightbody padding (10px each side) with SOME width left over for the slider
  itself - this is the numeric guarantee behind PANE_MIN.right's comment in dashboard.js."""
  fixed_cols = 88 + 62 + 52 + 20
  gaps = 4 * 6
  padding = 2 * 10
  overhead = fixed_cols + gaps + padding
  assert PANE_MIN["right"] > overhead, "right-pane floor too small to leave any room for the slider track"
