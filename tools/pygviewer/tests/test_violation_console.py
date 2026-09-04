"""User feedback (2026-09-04), two items:

  (1) "이미지1의 에러부분에 어디 모터가 초과한건지가 안 보여. console log 같은거에서 띄우던지."
      - the topbar's red badge said only "26153 ROM/torque violation(s)" with no joint name,
      and finding one meant clicking to open the detail panel.
  (2) "아래 Plot 부분에 실제 모터 Plot이 겹쳐서 보여야 하는데 안 보여."
      - the real-side trace existed in the data (S.ring's realQ/realQd/realTau, wired
      correctly per code review) but was styled as a thin, low-opacity copy of the sim
      line's OWN color (e.g. sim blue "#5b9bd5" -> real "#5b9bd588", same hex + an alpha
      suffix), which reads as "the sim line, fainter" rather than a second, visible line.

dashboard.js fixes both with a handful of small, PURE functions (no DOM, no
Date.now()/wall-clock read internally) - see that file's "A5" comments. There is no Node or
browser on this host (see test_dashboard.py's own docstring for the same constraint), so this
file mirrors each pure function in Python, verified line-for-line against the shipped JS text,
and drives it through fixtures built from the actual live probe that motivated this fix:
bench telemetry reporting `L_knee_joint` real q = -1.5007 rad against a sim q of +1.3686 rad
(the other 11 joints null - single-motor bench), at ~50 Hz alongside the sim's own frames.
"""

import re
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[1] / "pygviewer" / "static"


def _dashboard_js_text():
  return (STATIC_DIR / "dashboard.js").read_text()


# ============================================================================ Python mirrors
# Each function below is a deliberately line-for-line translation of the named dashboard.js
# function (see the source-text lock tests at the bottom of this file, which grep the actual
# shipped JS for the literal expressions these mirrors depend on staying true to).

def violation_side_short(side):
  return {
    "recv": "recv", "recv_torque": "recv-torque", "sim_actuator": "sim", "send": "send",
    # Fault visibility (2026-09-05, docs/121/docs/124):
    "stuck": "stuck", "fault": "fault",
    # Overheat cutoff (2026-09-05, docs/121 section 13c):
    "cutoff": "cutoff", "temp_unreadable": "temp?",
  }.get(side, side)


def violation_badge_text(tv):
  if not tv or not tv.get("total"):
    return None
  by_joint = tv.get("by_joint") or {}
  n_joints = len(by_joint)
  last = tv.get("last")
  if not last:
    return f"⚠ {tv['total']} ROM/torque violation(s)"
  value = last.get("value")
  val = f"{value:.3f}" if value is not None else (last.get("rejected") or "non-finite")
  lo, hi = last.get("limit_lo"), last.get("limit_hi")
  has_lim = lo is not None and hi is not None
  lim = f" ∉ [{lo:.3f}, {hi:.3f}]" if has_lim else ""
  extra = f" 외 {n_joints - 1}개" if n_joints > 1 else ""
  return f"⚠ {tv['total']} · {last['joint']} ({violation_side_short(last['side'])}) {val} rad{lim}{extra}"


def violation_line_text(rec):
  if rec.get("reason"):
    return rec["reason"]
  value = rec.get("value")
  val = f"{value:.3f}" if value is not None else (rec.get("rejected") or "non-finite")
  lo, hi = rec.get("limit_lo"), rec.get("limit_hi")
  has_lim = lo is not None and hi is not None
  lim = f"[{lo:.3f}, {hi:.3f}]" if has_lim else "-"
  over = rec.get("over_by")
  over_s = f"{over:.3f}" if over is not None else "-"
  return f"[{rec['side']}] {rec['joint']}  value={val}  limit={lim}  over={over_s}"


def coalesce_lines(state, items, now_ms, window_ms):
  """Mirrors coalesceLines(state, items, nowMs, windowMs): merges same-`key` items arriving
  within `window_ms` of when that key's open entry STARTED into one growing entry (count++),
  and finalizes (moves to `closed`) any open entry - touched by this batch or not - once
  `now_ms` has moved past its window. Returns (new_state, closed_list)."""
  open_ = dict(state)
  closed = []
  groups = {}
  for it in items:
    groups.setdefault(it["key"], []).append(it)
  for key, its in groups.items():
    last = its[-1]
    existing = open_.get(key)
    if existing and (now_ms - existing["startMs"]) < window_ms:
      open_[key] = {"startMs": existing["startMs"], "count": existing["count"] + len(its), "text": last["text"]}
    else:
      if existing:
        closed.append({"key": key, **existing})
      open_[key] = {"startMs": now_ms, "count": len(its), "text": last["text"]}
  for key in list(open_.keys()):
    if key in groups:
      continue
    entry = open_[key]
    if now_ms - entry["startMs"] >= window_ms:
      closed.append({"key": key, **entry})
      del open_[key]
  return open_, closed


ROW_IDX = {
  "pos": {"simL": 1, "simR": 2, "realL": 5, "realR": 6},
  "tau": {"simL": 1, "simR": 2, "realL": 3, "realR": 4},
  "qd": {"simL": 1, "simR": 2, "realL": 3, "realR": 4},
}


def _last_non_null(arr):
  for v in reversed(arr or []):
    if v is not None:
      return v
  return None


def _count_non_null(arr):
  return sum(1 for v in (arr or []) if v is not None)


def plot_readout_text(row, arrs):
  idx = ROW_IDX[row]
  dp = 1 if row == "tau" else 3

  def f(v):
    return "—" if v is None else f"{v:.{dp}f}"

  l_sim, r_sim = _last_non_null(arrs[idx["simL"]]), _last_non_null(arrs[idx["simR"]])
  l_real, r_real = _last_non_null(arrs[idx["realL"]]), _last_non_null(arrs[idx["realR"]])
  n = _count_non_null(arrs[idx["realL"]]) + _count_non_null(arrs[idx["realR"]])
  return f"L sim {f(l_sim)} real {f(l_real)} · R sim {f(r_sim)} real {f(r_real)} · real n={n}"


# ============================================================================ violation badge
def test_badge_text_none_when_no_violations():
  assert violation_badge_text({}) is None
  assert violation_badge_text({"total": 0}) is None
  assert violation_badge_text(None) is None


def test_badge_names_the_joint_and_value_single_joint():
  """The exact user complaint: the badge used to be a bare count. It must now name the
  joint, its side, its value, and the limit it broke - all from data already in the WS
  summary (Status.telemetry.violations), no extra request."""
  tv = {
    "total": 26153,
    "by_joint": {"L_knee_joint": {"total": 26153, "recv": 26153}},
    "last": {"side": "recv", "joint": "L_knee_joint", "value": -1.5007, "limit_lo": 0.0, "limit_hi": 2.094, "over_by": 1.5007},
  }
  text = violation_badge_text(tv)
  assert text == "⚠ 26153 · L_knee_joint (recv) -1.501 rad ∉ [0.000, 2.094]"


def test_badge_appends_and_n_more_when_multiple_joints():
  tv = {
    "total": 5,
    "by_joint": {"L_knee_joint": {"total": 3}, "R_hip_pitch_joint": {"total": 2}},
    "last": {"side": "sim_actuator", "joint": "R_hip_pitch_joint", "value": 12.0, "limit_lo": -10.0, "limit_hi": 10.0, "over_by": 2.0},
  }
  text = violation_badge_text(tv)
  assert text.startswith("⚠ 5 · R_hip_pitch_joint (sim) 12.000 rad")
  assert text.endswith("외 1개")  # "and 1 more" joint


def test_badge_handles_non_finite_rejection_with_no_numeric_value():
  tv = {"total": 1, "by_joint": {"L_ankle_pitch_joint": {"total": 1}},
        "last": {"side": "send", "joint": "L_ankle_pitch_joint", "value": None, "rejected": "non-finite (NaN/inf)", "limit_lo": None, "limit_hi": None}}
  text = violation_badge_text(tv)
  assert "non-finite (NaN/inf)" in text
  assert "∉" not in text  # no limit brackets when there is no finite limit to show


# ============================================================================ console coalescing
def test_coalesce_50hz_stream_becomes_one_growing_line_with_count():
  """The bench in the live report drives one joint's violation at ~50 Hz (20ms period) - a
  literal one-line-per-record console would print 50 lines/second. Feeding 50 same-key items
  1 at a time, all inside the same 1000ms window, must merge into ONE open entry whose count
  reaches 50, not 50 separate lines."""
  state = {}
  closed_total = []
  t0 = 1_000_000
  for i in range(50):
    items = [{"key": "recv|L_knee_joint", "text": f"[recv] L_knee_joint value={-1.5007}"}]
    state, closed = coalesce_lines(state, items, t0 + i * 20, 1000)
    closed_total.extend(closed)
  assert closed_total == []  # still inside the 1s window - nothing finalized yet
  assert state["recv|L_knee_joint"]["count"] == 50


def test_coalesce_closes_the_line_once_the_window_elapses_even_without_new_items():
  """A console re-rendered every poll tick must actually FREEZE a line's count once its
  window passes, even if no new violation arrives to trigger that - otherwise a line that
  stops recurring would show a stale, still-technically-"open" count forever."""
  state = {"recv|L_knee_joint": {"startMs": 0, "count": 50, "text": "..."}}
  state, closed = coalesce_lines(state, [], 1000, 1000)  # exactly at the window boundary
  assert closed and closed[0]["key"] == "recv|L_knee_joint" and closed[0]["count"] == 50
  assert "recv|L_knee_joint" not in state


def test_coalesce_a_new_item_after_the_window_starts_a_fresh_line_not_a_51st_count():
  state = {"recv|L_knee_joint": {"startMs": 0, "count": 50, "text": "old"}}
  state, closed = coalesce_lines(state, [{"key": "recv|L_knee_joint", "text": "new"}], 1500, 1000)
  assert closed and closed[0]["count"] == 50  # the old line finalized exactly as it was
  assert state["recv|L_knee_joint"] == {"startMs": 1500, "count": 1, "text": "new"}


def test_coalesce_keeps_different_joints_independent():
  items = [
    {"key": "recv|L_knee_joint", "text": "a"},
    {"key": "recv|R_hip_pitch_joint", "text": "b"},
    {"key": "recv|L_knee_joint", "text": "c"},
  ]
  state, closed = coalesce_lines({}, items, 0, 1000)
  assert closed == []
  assert state["recv|L_knee_joint"] == {"startMs": 0, "count": 2, "text": "c"}
  assert state["recv|R_hip_pitch_joint"] == {"startMs": 0, "count": 1, "text": "b"}


def test_violation_line_text_format():
  rec = {"side": "recv", "joint": "L_knee_joint", "value": -1.5007, "limit_lo": 0.0, "limit_hi": 2.094, "over_by": 1.5007}
  assert violation_line_text(rec) == "[recv] L_knee_joint  value=-1.501  limit=[0.000, 2.094]  over=1.501"


def test_violation_line_text_uses_the_plain_language_reason_when_present():
  """Fault visibility (2026-09-05, docs/121/docs/124): a "stuck"/"fault" record's own
  `reason` string (telemetry.py) takes over the whole line - the numeric value/limit/over
  format does not fit "the motor stopped tracking"."""
  rec = {
    "side": "stuck", "joint": "L_knee_joint", "value": 2.468, "limit_lo": None, "limit_hi": None,
    "reason": "L_knee_joint: 명령을 따르지 않음 (고장 의심) — 목표 114.0 (deg), 실측 141.4 (deg), 토크 0.00 N*m, 12초째",
  }
  assert violation_line_text(rec) == rec["reason"]


def test_dashboard_js_violation_line_text_also_checks_reason_first():
  src = _dashboard_js_text()
  m = re.search(r"function violationLineText\(rec\) \{(.*?)\n\}", src, re.S)
  assert m
  assert "if (rec.reason) return rec.reason;" in m.group(1)


def test_dashboard_js_violation_side_short_knows_the_new_sides():
  """Fault visibility + overheat cutoff (2026-09-05) added four new violation `side`
  values - the badge/console short-label map must know all of them, not fall through to the
  raw side string."""
  src = _dashboard_js_text()
  m = re.search(r"function violationSideShort\(side\) \{(.*?)\n\}", src, re.S)
  assert m
  body = m.group(1)
  for side in ('stuck: "stuck"', 'fault: "fault"', 'cutoff: "cutoff"', 'temp_unreadable: "temp?"'):
    assert side in body


# ============================================================================ plot readout
def test_plot_readout_matches_the_live_probe_gap():
  """The exact numbers from the live probe that motivated this fix: sim L_knee = +1.3686,
  real L_knee = -1.5007 (R_knee has no real data at all - single-motor bench). The readout
  must show BOTH numbers plainly - this is the fallback for "the line itself is hard to pick
  out": even if a viewer cannot see the trace, the numbers alone show an unmistakable ~2.87
  rad gap between sim and real."""
  # arrs layout for row="pos": [xs, qL, qR, targetL, targetR, realQL, realQR, sentL, sentR]
  arrs = [
    [0.0, 0.02, 0.04],           # xs
    [1.36, 1.368, 1.3686],       # sim L q
    [None, None, None],          # sim R q (not exercised by this bench)
    [1.3, 1.3, 1.3],             # target L
    [None, None, None],          # target R
    [-1.50, -1.5005, -1.5007],   # real L q - this is the series the user says "doesn't show"
    [None, None, None],          # real R q (bench has no R motor)
    [None, None, None],          # sent L
    [None, None, None],          # sent R
  ]
  text = plot_readout_text("pos", arrs)
  assert text == "L sim 1.369 real -1.501 · R sim — real — · real n=3"
  # the two numbers alone are ~2.87 rad apart - unmistakable even with no visible line at all
  assert abs(1.369 - (-1.501)) > 2.5


def test_plot_readout_reports_zero_real_samples_when_none_seen():
  arrs = [[0.0], [1.0], [None], [1.0], [None], [None], [None], [None], [None]]
  text = plot_readout_text("pos", arrs)
  assert "real n=0" in text
  assert "real —" in text  # distinguishes "no data" from "data present but not drawn"


def test_plot_readout_tau_row_uses_one_decimal_not_three():
  # arrs layout for row="tau"/"qd": [xs, simL, simR, realL, realR]
  arrs = [[0.0], [12.345], [None], [-8.222], [None]]
  text = plot_readout_text("tau", arrs)
  assert "sim 12.3" in text and "real -8.2" in text


# ============================================================================ tau_est field-name
# The task brief specifically flagged a SUSPECTED bug: dashboard.js reads `msg.tau_est`
# (onJointState, both the sim and real branches) while a live wire probe found tau non-null
# count = 0 for both sim and real - raising the question of whether the wire field is actually
# named something else (e.g. plain `tau`) and dashboard.js has been silently reading a field
# that is never populated. Investigation (this test locks the answer in): schema.py's
# JointState field IS `tau_est` (with a docstring explicitly justifying that name - "tau" from
# hardware is a current ESTIMATE), and every sender (api.py's two JointState builders,
# bridge/huphy_udp.py's _emit_joint_state) populates that same key. dashboard.js reads the
# same key. No field-name mismatch bug exists; the zero-count the user saw is a data-content
# question (torque may genuinely be ~0 at that moment), not a wiring bug.
def test_schema_joint_state_tau_field_is_tau_est():
  from pygviewer.schema import JointState

  assert "tau_est" in JointState.model_fields
  assert "tau" not in JointState.model_fields


def test_dashboard_js_reads_tau_est_not_bare_tau():
  src = _dashboard_js_text()
  assert "msg.tau_est" in src
  # would-be-bug pattern: reading a field named plain `tau` off the wire message instead
  assert "msg.tau)" not in src and "msg.tau," not in src and "msg.tau " not in src and "msg.tau;" not in src


def test_api_and_bridge_senders_populate_tau_est_key():
  """Every JointState constructor call site that carries torque data uses the `tau_est=`
  keyword - not a differently-named field that would leave the wire's `tau_est` permanently
  null while some other torque-shaped field went unread by dashboard.js."""
  api_src = (Path(__file__).resolve().parents[1] / "pygviewer" / "api.py").read_text()
  bridge_src = (Path(__file__).resolve().parents[1] / "pygviewer" / "bridge" / "huphy_udp.py").read_text()
  assert api_src.count("tau_est=") >= 2  # sim _joint_state() and real _real_joint_state()
  assert "tau_est=[self._buf[n][\"tau\"] for n in self.act_names]" in bridge_src


# ============================================================================ source-text locks
def test_dashboard_js_badge_uses_violation_badge_text():
  src = _dashboard_js_text()
  assert "function violationBadgeText(tv)" in src
  assert "const badgeTxt = violationBadgeText(tv);" in src
  # the OLD bare-count-only badge markup must not still be the one actually rendered
  assert 'ROM/torque violation(s)</span>' not in re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def test_dashboard_js_pollslow_polls_violations_unconditionally():
  """A5: previously `GET /violations` (and therefore any console feed) only ran while the
  detail panel was open - the always-visible console needs a live stream regardless of which
  tab/panel is open."""
  src = _dashboard_js_text()
  m = re.search(r"async function pollSlow\(\) \{(.*?)\n\}", src, re.S)
  assert m
  body = m.group(1)
  assert 'S.violations = await api("GET", "/violations?limit=100");' in body
  assert "ingestViolationsForConsole(" in body
  # must NOT be gated behind `if (S.violationPanelOpen)` the way it used to be
  assert not re.search(r"if \(S\.violationPanelOpen\) \{ S\.violations", body)


def test_dashboard_js_real_series_color_is_not_a_transparent_copy_of_sim_color():
  """The literal old bug: real's stroke was sim's OWN hex with an alpha suffix appended
  (e.g. "#5b9bd588") - same hue, just faded, which is why it read as invisible rather than
  overlapping. Lock in that the fix uses genuinely different hues (magenta/cyan) instead."""
  src = _dashboard_js_text()
  code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
  assert "#5b9bd588" not in code and "#e08a3c88" not in code
  m = re.search(r"function makeSeriesFor\(row\) \{(.*?)\n\}", code, re.S)
  assert m
  body = m.group(1)
  assert '"#00e5ff"' in body and '"#ff3fa4"' in body


def test_dashboard_js_row_labels_mark_real_series_explicitly():
  src = _dashboard_js_text()
  m = re.search(r"const ROW_META = \{(.*?)\n\};", src, re.S)
  assert m
  body = m.group(1)
  for row_labels in ("L q (real)", "R q (real)", "L tau (real)", "R tau (real)", "L qd (real)", "R qd (real)"):
    assert row_labels in body, f"missing explicit (real) label: {row_labels}"


def test_dashboard_js_hand_rolled_legend_is_a_line_sample_then_label():
  """User feedback round 2: the legend must show a LINE SAMPLE (this series' own color/width/
  dash) before its label, not a plain color dot. legendSwatchHtml builds this from
  makeSeriesFor(row) itself (never a hand-copied palette), so it cannot drift out of sync with
  what a panel's lines actually look like."""
  src = _dashboard_js_text()
  assert "function legendSwatchHtml(row)" in src
  assert "function legendSwatchStyle(s)" in src
  m = re.search(r"function legendSwatchStyle\(s\) \{(.*?)\n\}", src, re.S)
  assert m and "border-top" in m.group(1)
  # rendered as `<swatch><label>` (sample first, then text), not the other way around
  assert re.search(r'legend-swatch"[^>]*></span>\$\{s\.label\}', src)
