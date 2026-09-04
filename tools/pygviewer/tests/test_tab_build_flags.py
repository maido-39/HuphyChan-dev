"""A6 crash fix (2026-09-04): "TypeError: can't access property 'dataset', sub is null" at
renderJointsPanel <- renderTabControl <- renderRightTab <- renderTick, reported from the
user's actual browser console (repeating).

Root cause (see dashboard.js's own comment above `tabNeedsBuild`): six tab renderers
(Model/Base link/Telemetry/Script/Status share `#left-body`; Control/Gains/Obs share
`#right-body`) each stamped a per-tab "already built" boolean onto the SHARED body element's
`dataset` to avoid rebuilding its innerHTML on every 20 Hz tick. Three of them
(Base/Telemetry/Script) used the exact same bare `dataset.built` key; the other three each
used their own name (`builtControl`/`builtGains`/`builtObs`) but never cleared the other two's
flags. `body.innerHTML = ...` only replaces an element's CHILDREN, never its own attributes -
so switching Control -> Gains -> Control left `dataset.builtControl === "1"` even though the
DOM under `#right-body` was now Gains' table, and `renderTabControl` skipped rebuilding,
handed `renderJointsPanel` a `null` `#control-sub`, and crashed every render tick thereafter -
freezing the ENTIRE render loop downstream of that crash (including `renderPlots()`, which is
what the "real motor plot never shows" report actually was; see docs/121 sec 10 and the git
log for the companion fix that added the render-loop's per-stage try/catch).

There is no Node/browser on this host (see test_dashboard.py's own docstring for the same
constraint), so this file mirrors the tiny pure decision function `tabNeedsBuild` in Python
and drives it through the exact tab-switch sequences that reproduced the bug, then locks the
actual shipped dashboard.js text down so the old per-tab-boolean pattern cannot silently come
back.
"""

import re
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[1] / "pygviewer" / "static"


def tab_needs_build(current_built_tab, tab_name, force=False):
  """Python mirror of dashboard.js's `tabNeedsBuild(currentBuiltTab, tabName, force)` -
  see that function's docstring in dashboard.js. Kept intentionally trivial (one line) so a
  divergence between this and the shipped JS would have to be a copy-paste mistake, not a
  subtle algorithmic difference - the JS text impersonation test below guards against that."""
  return current_built_tab != tab_name or bool(force)


# ---------------------------------------------------------------------- the decision function
def test_same_tab_rerendered_does_not_ask_to_rebuild():
  # this is the perf property the flag exists for at all: a tab re-rendering itself every
  # 20 Hz tick must NOT rebuild its innerHTML (destroying focus, scroll position, etc) each time
  assert tab_needs_build("control", "control") is False
  assert tab_needs_build("base", "base") is False


def test_different_tab_on_the_same_shared_body_asks_to_rebuild():
  assert tab_needs_build("control", "gains") is True
  assert tab_needs_build(None, "base") is True  # nothing built yet


def test_force_flag_rebuilds_even_the_same_tab():
  # renderTabControl(body, force) uses this for e.g. the unit-toggle's Joints-panel refresh
  assert tab_needs_build("control", "control", force=True) is True


def test_control_gains_control_sequence_reproduces_then_fixes_the_crash():
  """The exact sequence from the bug report: Control -> Gains -> back to Control. Under the
  OLD per-tab-boolean scheme this last step would have found `builtControl` still "1" (it was
  never cleared by Gains building into the same shared body) and skipped rebuilding
  `#control-sub` - which is the null `sub` that crashed `renderJointsPanel`. The unified
  `builtTab` string this function drives cannot make that mistake: arriving at Control after
  Gains built into the same body is always a different `tab_name`, so it always rebuilds."""
  built = None
  assert tab_needs_build(built, "control") is True
  built = "control"
  assert tab_needs_build(built, "control") is False  # steady-state re-render: no rebuild
  assert tab_needs_build(built, "gains") is True
  built = "gains"
  assert tab_needs_build(built, "control") is True  # <- this one is exactly the crash site
  built = "control"
  assert tab_needs_build(built, "control") is False


def test_base_telemetry_script_sequence_reproduces_then_fixes_the_crash():
  """Same bug, left-hand side: Base/Telemetry/Script all shared one bare `dataset.built` key,
  so this sequence used to leave Telemetry (and then Script) permanently un-buildable after
  the first tab (Base) had already set that shared flag once."""
  built = None
  for tab in ("base", "telemetry", "script", "base"):
    assert tab_needs_build(built, tab) is True, tab
    built = tab
  # and steady-state on whichever tab is current never rebuilds
  assert tab_needs_build(built, built) is False


# ---------------------------------------------------------------------- shipped JS text locks
def _dashboard_js_text():
  return (STATIC_DIR / "dashboard.js").read_text()


def _dashboard_js_code_only():
  """Strips `/* ... */` block comments (this file's docstrings freely quote the exact old
  flag names as history/rationale, e.g. inside the tabNeedsBuild docstring above its
  definition - that prose must not trip a check for the flags in actual CODE)."""
  src = _dashboard_js_text()
  return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def test_dashboard_js_defines_tab_needs_build():
  src = _dashboard_js_text()
  assert "function tabNeedsBuild(currentBuiltTab, tabName, force)" in src
  assert "return currentBuiltTab !== tabName || !!force;" in src


def test_dashboard_js_all_six_shared_tab_renderers_route_through_tab_needs_build():
  """The six renderers that share a body element (renderTabBase/Telemetry/Script on
  #left-body, renderTabControl/Gains/Obs on #right-body) must all gate their (re)build on
  `tabNeedsBuild(body.dataset.builtTab, ...)` - a straight substring count is enough here
  since each renderer has exactly one such call at its top."""
  src = _dashboard_js_text()
  calls = re.findall(r"tabNeedsBuild\(body\.dataset\.builtTab,", src)
  assert len(calls) == 6, f"expected exactly 6 call sites (one per shared-body tab renderer), found {len(calls)}"


def test_dashboard_js_stale_per_tab_boolean_flags_are_gone():
  """Locks out a regression back to the exact bug: a per-tab boolean stamped on the SHARED
  body element instead of one "which tab is built" string. `builtJoints`/`builtPolicy` are a
  different, legitimate case (they live on `#control-sub`, a child element recreated fresh
  every time Control's OWN tab-build runs) and must NOT be flagged by this check."""
  src = _dashboard_js_code_only()
  for stale in ("dataset.builtControl", "dataset.builtGains", "dataset.builtObs"):
    assert stale not in src, f"stale per-tab flag {stale!r} reintroduces the cross-tab stale-DOM crash"
  # the bare `.built` flag Base/Telemetry/Script used to share - `builtTab`/`builtJoints`/
  # `builtPolicy` are the only legitimate `dataset.built*` names left.
  assert not re.search(r"dataset\.built(?!Tab\b|Joints\b|Policy\b)", src)


def test_dashboard_js_render_joints_and_policy_panels_guard_null_sub():
  """The direct crash site: `renderJointsPanel`/`renderPolicyPanel` must bail out instead of
  dereferencing `.dataset` on a `sub` that turned out to be null (a stale reference to a node
  another tab's innerHTML replaced) - the null guard is what turns "crashes every tick
  forever" into "silently does nothing this tick", while the builtTab fix above is what stops
  `sub` from ever actually being null in the first place. Both belong in the fix: the guard is
  the last line of defense if a future tab renderer reintroduces a similar bug."""
  src = _dashboard_js_text()
  m = re.search(r"function renderJointsPanel\(sub, force\) \{(.*?)\n\}", src, re.S)
  assert m, "renderJointsPanel not found"
  assert re.search(r"if \(!sub\) return;", m.group(1)), "renderJointsPanel missing its null guard"
  m2 = re.search(r"function renderPolicyPanel\(sub\) \{(.*?)\n\}", src, re.S)
  assert m2, "renderPolicyPanel not found"
  assert re.search(r"if \(!sub\) return;", m2.group(1)), "renderPolicyPanel missing its null guard"


def test_dashboard_js_render_tick_isolates_each_stage():
  """A6 item 3: one stage's exception must never freeze the stages after it (this is why the
  original bug also froze `renderPlots()`, the "real motor plot invisible" report, even though
  the actual defect was in `renderTabControl`, three stages earlier in the same tick)."""
  src = _dashboard_js_text()
  m = re.search(r"function renderTick\(\) \{(.*?)\n\}", src, re.S)
  assert m, "renderTick not found"
  body = m.group(1)
  assert body.count("try {") >= 5, "expected every renderTick stage wrapped in its own try/catch"
  assert "reportRenderError" in body, "caught exceptions must be routed to the operator console, not swallowed"
