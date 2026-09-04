"""Sync-before-arm gate (``hw_sync.py``, docs/123 section 10.2, 2026-09-04).

The near-miss this fixes, verbatim: the real L_knee sat at 27.8 deg while the Joints tab's
manual target - left over from a previous drag, or just the sim's default pose - showed
66.4 deg. Nothing stopped an ARM at that moment from sending that 38.6 deg jump as the very
first TX packet. ``POST /sync_from_real`` (dashboard: "0. sync from hardware") is the missing
step, and ``POST /tx/arm`` now refuses (409) until it has been run and is still valid.

Six scenarios (task item 5):
  (a) no real telemetry has EVER arrived on this process -> 409, no silent success.
  (b) some joints have real data, most don't (the bench today: 1 of 12) -> synced/skipped
      split correctly, never conflated.
  (c) a real value outside the contract's safe_clip (the bench's -44 deg case) -> recorded in
      ``clipped`` with the raw/applied/range, AND the sim's own manual target actually lands
      inside the safe range - never silently pretending sim can reproduce an out-of-range pose.
  (d) arm without ever syncing -> 409 naming the joint(s) that need a sync.
  (e) sync, then arm -> succeeds.
  (f) sync, then the synced joint's telemetry goes stale -> the sync is invalidated -> a
      later arm is refused again, even though nothing else changed.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pygviewer import CACHE_DIR
from pygviewer.api import build_app
from pygviewer.contract import load_contract
from pygviewer.hw_sync import STALE_INVALIDATE_S
from pygviewer.schema import JointState
from pygviewer.sim_core import SimCore

VARIANT = "LegOnly-AB"
STATIC_DIR = Path(__file__).resolve().parents[1] / "pygviewer" / "static"


def _contract():
  try:
    return load_contract(CACHE_DIR, VARIANT)
  except FileNotFoundError:
    pytest.skip(f"no baked contract for {VARIANT}")


def _fresh_core() -> SimCore:
  core = SimCore(_contract(), realtime=False)
  core.reset("knees_bent")
  core.mode = "manual"
  core.step_n(1)
  return core


@pytest.fixture(scope="module")
def core():
  core = _fresh_core()
  yield core
  core.stop()


@pytest.fixture(scope="module")
def client(core):
  return TestClient(build_app(core, core.c.freshness()))


def _ingest(core: SimCore, values: dict[str, float], seq: int = 1) -> None:
  """Feed real telemetry the same way ``WS /ws/in`` would, for exactly the named joints -
  every other actuated joint is left with no data at all, same as the bench today."""
  names = list(values)
  core.real.ingest_joint_state(
    JointState(
      t_ns=time.monotonic_ns(), seq=seq, src="dummy", joint_names=names,
      q=[values[n] for n in names],
    )
  )


# ------------------------------------------------------------------------------------- (a)
def test_sync_with_no_telemetry_ever_is_409():
  """A totally fresh process that has never received one ``/ws/in`` message - the 409 case is
  specifically "no stream exists at all", not "most joints have no data" (scenario (b) below,
  the bench's actual normal state, must succeed)."""
  core = _fresh_core()
  client = TestClient(build_app(core, core.c.freshness()))
  try:
    r = client.post("/sync_from_real")
    assert r.status_code == 409, r.text
    assert "real telemetry" in r.json()["detail"].lower()
  finally:
    core.stop()


# ------------------------------------------------------------------------------------- (b)
def test_partial_sync_reports_synced_and_skipped_separately(core, client):
  _ingest(core, {"L_knee_joint": 0.5})
  r = client.post("/sync_from_real")
  assert r.status_code == 200, r.text
  body = r.json()
  assert body["synced"] == {"L_knee_joint": pytest.approx(0.5)}
  assert body["clipped"] == {}
  assert len(body["skipped"]) == len(core.act_names) - 1
  assert body["skipped"]["R_knee_joint"] == "no real data"
  assert all(v == "no real data" for v in body["skipped"].values())
  assert body["sync_token"]
  assert body["max_delta_before"] >= 0.0
  assert isinstance(body["t"], float)


# ------------------------------------------------------------------------------------- (c)
def test_out_of_rom_real_value_is_clipped_and_target_stays_in_range(core, client):
  lo, hi = core.c.clip("L_knee_joint")
  out_of_range = lo - 0.5  # e.g. the bench's real -44 deg vs. a safe_clip floor near +6 deg
  _ingest(core, {"L_knee_joint": out_of_range}, seq=2)
  r = client.post("/sync_from_real")
  assert r.status_code == 200, r.text
  body = r.json()
  c = body["clipped"]["L_knee_joint"]
  assert c["real"] == pytest.approx(out_of_range)
  assert c["applied"] == pytest.approx(lo)
  assert c["range"] == pytest.approx([lo, hi])
  assert body["synced"]["L_knee_joint"] == pytest.approx(lo)  # never handed a value sim can't hold

  core.step_n(core.decimation)  # let the queued /target-equivalent command actually apply
  s = core.snapshot()
  applied_target = dict(zip(s["act_names"], s["target"]))["L_knee_joint"]
  assert lo - 1e-9 <= applied_target <= hi + 1e-9


# ------------------------------------------------------------------------------------- (d)
def test_arm_without_sync_is_409_naming_the_joint(core, client):
  assert client.post("/mode", json={"mode": "manual"}).status_code == 200
  r = client.post("/tx/config", json={"host": "127.0.0.1", "port": 9, "enable": ["L_knee_joint"]})
  assert r.status_code == 200, r.text
  assert client.post("/tx/enable", json={"on": True}).status_code == 200
  # POST /tx/config (just above) invalidates any earlier sync (docs/123 section 10.2) - this
  # process is now guaranteed to be in the "never synced (for this config)" state without
  # depending on test execution order.
  r = client.post("/tx/arm")
  assert r.status_code == 409, r.text
  assert "L_knee_joint" in r.json()["detail"]
  assert client.get("/tx/status").json()["sync"]["valid"] is False


# ------------------------------------------------------------------------------------- (e)
def test_sync_then_arm_succeeds(core, client):
  _ingest(core, {"L_knee_joint": 0.4}, seq=3)
  r = client.post("/sync_from_real")
  assert r.status_code == 200, r.text
  assert client.get("/tx/status").json()["sync"]["valid"] is True
  r = client.post("/tx/arm")
  assert r.status_code == 200, r.text
  assert r.json()["armed"] is True
  st = client.get("/tx/status").json()
  assert st["sync"]["valid"] is True
  assert st["sync"]["synced_joints"] == ["L_knee_joint"]


# ------------------------------------------------------------------------------------- (f)
def test_stale_telemetry_after_sync_invalidates_and_blocks_arm(core, client):
  assert client.post("/tx/disarm").status_code == 200
  _ingest(core, {"L_knee_joint": 0.35}, seq=4)
  r = client.post("/sync_from_real")
  assert r.status_code == 200, r.text
  assert client.get("/tx/status").json()["sync"]["valid"] is True

  time.sleep(STALE_INVALIDATE_S + 0.1)  # no further telemetry - L_knee_joint goes quiet

  st = client.get("/tx/status").json()
  assert st["sync"]["valid"] is False
  assert "stale" in st["sync"]["reason"].lower()

  r = client.post("/tx/arm")
  assert r.status_code == 409, r.text
  assert "stale" in r.json()["detail"].lower() or "L_knee_joint" in r.json()["detail"]


# ------------------------------------------------------------------------------------- (g)
def test_sync_in_idle_then_switch_to_manual_stays_valid(core, client):
  """Live bench regression (2026-09-04): an operator synced while the sim was still in
  ``idle`` (never having entered manual yet) and the VERY NEXT control tick invalidated the
  sync with reason "mode changed to 'idle' while synced" - nothing had actually left manual,
  the mode simply was never manual to begin with. ``HwSyncState.note_mode`` must only
  invalidate on a TRANSITION away from manual, never on "current mode happens not to be
  manual" (see its own docstring) - sync is allowed in any mode; only arming still requires
  manual, unchanged."""
  assert client.post("/mode", json={"mode": "idle"}).status_code == 200
  core.step_n(core.decimation)  # apply the queued mode op + run the structural note_mode check
  assert core.mode == "idle"

  r = client.post("/tx/config", json={"host": "127.0.0.1", "port": 9, "enable": ["L_knee_joint"]})
  assert r.status_code == 200, r.text
  assert client.post("/tx/enable", json={"on": True}).status_code == 200
  _ingest(core, {"L_knee_joint": 0.3}, seq=5)
  r = client.post("/sync_from_real")
  assert r.status_code == 200, r.text
  assert client.get("/tx/status").json()["sync"]["valid"] is True

  # switch to manual - a normal, expected order (sync first, then go manual, then arm) - must
  # NOT invalidate.
  assert client.post("/mode", json={"mode": "manual"}).status_code == 200
  core.step_n(core.decimation)
  assert core.mode == "manual"
  assert client.get("/tx/status").json()["sync"]["valid"] is True

  r = client.post("/tx/arm")
  assert r.status_code == 200, r.text
  assert r.json()["armed"] is True

  # NOW actually leave manual while armed/synced - this SHOULD invalidate (unchanged rule).
  core.mode = "policy_sim"  # bypasses POST /mode, same pattern test_tx_wiring.py uses
  core.step_n(core.decimation)
  st = client.get("/tx/status").json()
  assert st["sync"]["valid"] is False
  assert "left manual" in st["sync"]["reason"].lower()
  # back to a clean state for any test appended after this one
  core.mode = "manual"
  core.step_n(core.decimation)


# --------------------------------------------------------------- dashboard.js wiring (text)
# No JS test runner in this repo (test_policy_ui_contract.py's docstring already established
# this - checked again here: no package.json/jest.config under tools/pygviewer) - these check
# the dashboard SOURCE TEXT for the wiring this feature depends on, the same convention
# test_tab_build_flags.py / test_violation_console.py already use for other pure JS pieces.
def _dashboard_js_text() -> str:
  return (STATIC_DIR / "dashboard.js").read_text()


def test_dashboard_js_wires_the_sync_button():
  src = _dashboard_js_text()
  assert 'el("btn-sync-from-real").onclick = doSyncFromReal' in src
  assert "async function doSyncFromReal" in src
  assert 'id="btn-sync-from-real"' in src
  assert "/sync_from_real" in src


def test_dashboard_js_joints_lock_never_fires_without_real_telemetry():
  """jointsLockState's whole point (task requirement 3): a pure-sim session with no real
  telemetry at all must never be locked. Assert the early-return guard is still there
  textually, since this is exactly the kind of one-line safety condition a later edit could
  silently drop."""
  src = _dashboard_js_text()
  assert "function jointsLockState(status, txStatus)" in src
  assert "if (!realConnected) return { locked: false, reason: null };" in src


def test_dashboard_js_arm_button_disabled_considers_sync_valid():
  src = _dashboard_js_text()
  assert "!syncOk" in src
  assert 'el("btn-tx-arm").disabled' in src
