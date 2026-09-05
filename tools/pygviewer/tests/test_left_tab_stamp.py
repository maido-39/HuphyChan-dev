"""Every left-panel tab must stamp which tab the body currently holds.

`tabNeedsBuild(body.dataset.builtTab, name)` decides whether to rebuild. A tab that replaces
`#left-body` WITHOUT stamping leaves the previous tab's name behind, so returning to that tab
skips its build and immediately reads elements that are no longer in the DOM.

Reported from the running viewer, 2026-09-06:
    04:04:09.324 [JS ERROR] renderLeftTab: can't access property "textContent", el(...) is null (x18)

There is no browser or Node on this host (see test_dashboard.py), so this checks the shipped
source text - which is what the bug was: a missing line, not a wrong value.
"""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "pygviewer" / "static"
JS = (STATIC / "dashboard.js").read_text()
HTML = (STATIC / "dashboard.html").read_text()

LEFT_TABS = ["scenario", "model", "base", "telemetry", "script", "status"]


def test_the_html_tab_strip_and_the_js_dispatch_list_the_same_tabs():
  in_html = set(re.findall(r'data-tab="([a-z]+)"', HTML))
  dispatched = set(re.findall(r'case "([a-z]+)": return renderTab', JS))
  assert in_html >= set(LEFT_TABS), f"missing from the HTML strip: {set(LEFT_TABS) - in_html}"
  assert dispatched >= set(LEFT_TABS), f"no renderer dispatched for: {set(LEFT_TABS) - dispatched}"


def test_the_default_tab_matches_the_one_marked_selected():
  """A mismatch renders one tab while highlighting another - and the highlighted one never
  gets its build flag set, which is the null-element crash."""
  strip = re.search(r'id="left-tabs"(.*?)</div>\s*<div class="leftbody"', HTML, re.S)
  assert strip, "left tab strip not found"
  marked = re.search(r'class="tab on" data-tab="([a-z]+)"', strip.group(1))
  assert marked, "exactly one tab must carry class=\"tab on\""
  default = re.search(r'leftTab: "([a-z]+)"', JS)
  assert default, "S.leftTab must have a literal default"
  assert marked.group(1) == default.group(1), (
    f'HTML marks "{marked.group(1)}" selected but S.leftTab starts at "{default.group(1)}"')


def test_only_one_tab_is_marked_selected_in_the_left_strip():
  """The right-hand strip (Control/Gains/Obs) has its own selected tab - scope to the left."""
  strip = re.search(r'id="left-tabs"(.*?)</div>\s*<div class="leftbody"', HTML, re.S)
  assert strip, "left tab strip not found"
  assert len(re.findall(r'class="tab on" data-tab=', strip.group(1))) == 1


def test_every_left_tab_renderer_stamps_the_body_it_built():
  """The stamp is what makes returning to a tab rebuild it."""
  missing = []
  for name in LEFT_TABS:
    fn = name[0].upper() + name[1:]
    m = re.search(r"function renderTab%s\(body\)(.*?)\n}" % fn, JS, re.S)
    assert m, f"renderTab{fn} not found"
    if f'builtTab = "{name}"' not in m.group(1):
      missing.append(name)
  assert not missing, f"these replace #left-body without stamping it: {missing}"
