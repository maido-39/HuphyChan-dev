"""The TX panel must show the settings that are actually in force (2026-09-07 bench).

Two separate faults, found in one sitting, that between them made the TX panel actively
misleading:

1. **The form never reflected reality.** ``renderTxSectionHtml()`` emitted fixed HTML
   defaults - ``host=127.0.0.1``, ``kp max=5`` - and nothing ever wrote the live config back
   into those boxes. On the bench the server actually held ``10.8.0.14`` and ``kp_max=305``
   while the panel read ``127.0.0.1`` and ``5``. This is not cosmetic: ``pushTxConfig()``
   reads those exact boxes, so pressing "1. configure" - or merely ticking a motor checkbox,
   which re-pushes the config - would have silently re-pointed transmission at loopback,
   where nothing listens. The symptom is identical to "the robot stopped responding": the
   panel stays green and the sequence counter climbs while no packet reaches a motor.
   The user's question that opened this - "IP 이상태면 RX 안떠야되지않나?" - also has a
   real answer worth keeping: no. Telemetry (robot -> PC, port 9870) is pushed by the robot
   and is entirely independent of this host box, which only names the COMMAND target
   (PC -> robot, port 9872). RX being up says nothing about TX being aimed correctly.

2. **Every reconfigure destroyed the sync.** ``POST /tx/config`` called
   ``hw_sync.invalidate("TX reconfigured (POST /tx/config)")`` unconditionally, and the
   dashboard re-pushes that endpoint on every motor checkbox toggle - so the ordinary
   "0. sync from hardware, then tick the joints you want" workflow left the panel permanently
   stuck on ``sync invalid: TX reconfigured (POST /tx/config)`` (user: "계속 뜨면서 이상한데").
   The invalidation was also redundant: ``POST /tx/arm`` already refuses when the enable list
   contains a joint the sync does not cover (``hw_sync.check_arm_ready``'s ``missing`` check).
   What genuinely invalidates a sync is the TARGET moving - a different host/port may be a
   different robot in a different pose - so that is now the only trigger.
"""

from __future__ import annotations

import math
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pygviewer import CACHE_DIR
from pygviewer.api import build_app
from pygviewer.contract import load_contract
from pygviewer.schema import JointState
from pygviewer.sim_core import SimCore
from pygviewer.tx import DEFAULT_TX_PORT, TxState, _env_tx_target

VARIANT = "LegOnly-AB"
DASHBOARD_JS = Path(__file__).resolve().parents[1] / "pygviewer" / "static" / "dashboard.js"

HOST_A, HOST_B = "10.8.0.14", "10.8.0.99"
PORT = 9872


def _contract():
  try:
    return load_contract(CACHE_DIR, VARIANT)
  except FileNotFoundError:
    pytest.skip(f"no baked contract for {VARIANT}")


def _core_client():
  core = SimCore(_contract(), realtime=False)
  core.reset("knees_bent")
  core.mode = "manual"
  core.step_n(1)
  return core, TestClient(build_app(core, core.c.freshness()))


def _ingest(core: SimCore, values: dict[str, float]) -> None:
  names = list(values)
  core.real.ingest_joint_state(
    JointState(
      t_ns=time.monotonic_ns(), seq=1, src="dummy", joint_names=names,
      q=[values[n] for n in names],
    )
  )


def _two_joints(core: SimCore) -> tuple[str, str]:
  """Two actuated joints of this variant, whatever they happen to be named."""
  return core.act_names[0], core.act_names[1]


# --------------------------------------------------------------- fault 2: sync invalidation
def test_reconfigure_to_the_same_target_keeps_the_sync():
  """The exact bench sequence: sync, then tick another joint (which re-pushes /tx/config).
  Before the fix this printed "sync invalid: TX reconfigured" and the ARM button stayed dead
  no matter how many times the operator pressed "0. sync from hardware"."""
  core, client = _core_client()
  try:
    a, b = _two_joints(core)
    _ingest(core, {a: 0.1, b: 0.2})
    assert client.post("/tx/config", json={"host": HOST_A, "port": PORT, "enable": [a]}).status_code == 200
    assert client.post("/sync_from_real").status_code == 200
    assert client.get("/tx/status").json()["sync"]["valid"] is True

    # the checkbox toggle: same host/port, one more joint enabled
    r = client.post("/tx/config", json={"host": HOST_A, "port": PORT, "enable": [a, b]})
    assert r.status_code == 200, r.text
    assert r.json()["sync"]["valid"] is True, r.json()["sync"]["reason"]
  finally:
    core.stop()


def test_reconfigure_gains_only_keeps_the_sync():
  """kp/kd/ttl are transmit caps, not poses - they cannot make a measured baseline wrong."""
  core, client = _core_client()
  try:
    a, _ = _two_joints(core)
    _ingest(core, {a: 0.1})
    client.post("/tx/config", json={"host": HOST_A, "port": PORT, "enable": [a]})
    client.post("/sync_from_real")
    r = client.post("/tx/config", json={
      "host": HOST_A, "port": PORT, "enable": [a], "kp_max": 12.0, "kd_max": 1.0, "ttl_ms": 300,
    })
    assert r.status_code == 200, r.text
    assert r.json()["sync"]["valid"] is True
    assert r.json()["kp_max"] == 12.0
  finally:
    core.stop()


@pytest.mark.parametrize(
  "changed", [{"host": HOST_B, "port": PORT}, {"host": HOST_A, "port": PORT + 1}]
)
def test_pointing_at_a_different_target_does_invalidate_the_sync(changed):
  """The one case the invalidation exists for: the baselines were measured from one receiver,
  and a different address may be a different robot standing in a different pose."""
  core, client = _core_client()
  try:
    a, _ = _two_joints(core)
    _ingest(core, {a: 0.1})
    client.post("/tx/config", json={"host": HOST_A, "port": PORT, "enable": [a]})
    client.post("/sync_from_real")
    r = client.post("/tx/config", json={**changed, "enable": [a]})
    assert r.status_code == 200, r.text
    sync = r.json()["sync"]
    assert sync["valid"] is False
    assert "target changed" in (sync["reason"] or "")
    assert f"{changed['host']}:{changed['port']}" in sync["reason"]
  finally:
    core.stop()


def test_a_joint_added_after_the_sync_still_cannot_be_armed():
  """Why dropping the blanket invalidation is safe: the arm gate, not the config endpoint, is
  what actually protects an un-synced joint. Only `a` has telemetry, so a sync covers `a`
  alone; enabling `b` afterwards must still be refused."""
  core, client = _core_client()
  try:
    a, b = _two_joints(core)
    _ingest(core, {a: 0.1})  # b never receives anything
    client.post("/tx/config", json={"host": HOST_A, "port": PORT, "enable": [a]})
    client.post("/sync_from_real")
    client.post("/tx/config", json={"host": HOST_A, "port": PORT, "enable": [a, b]})
    client.post("/tx/enable", json={"on": True})
    r = client.post("/tx/arm")
    assert r.status_code == 409, r.text
    assert b in r.json()["detail"]
  finally:
    core.stop()


# ------------------------------------------------------ fault 1: the form must show the truth
def test_status_reports_every_field_the_form_shows():
  """The dashboard can only mirror what the server reports. Each of the five TX form fields
  needs a matching key in ``GET /tx/status`` or the backfill has nothing to read."""
  core, client = _core_client()
  try:
    a, _ = _two_joints(core)
    client.post("/tx/config", json={
      "host": HOST_A, "port": PORT, "enable": [a], "kp_max": 7.5, "kd_max": 0.75, "ttl_ms": 300,
    })
    st = client.get("/tx/status").json()
    assert (st["host"], st["port"]) == (HOST_A, PORT)
    assert (st["kp_max"], st["kd_max"], st["ttl_ms"]) == (7.5, 0.75, 300)
  finally:
    core.stop()


def test_env_seeds_the_pre_configure_target(monkeypatch):
  """Before "1. configure" is ever pressed there is no config to mirror, so the box would fall
  back to whatever HTML default it carries - which is exactly how it came to say 127.0.0.1.
  The launcher now sets PYG_TX_HOST, and the seeded value shows up in /tx/status."""
  monkeypatch.setenv("PYG_TX_HOST", HOST_A)
  monkeypatch.setenv("PYG_TX_PORT", "9999")
  assert _env_tx_target() == (HOST_A, 9999)

  monkeypatch.delenv("PYG_TX_HOST")
  monkeypatch.setenv("PYG_TX_PORT", "not-a-number")
  assert _env_tx_target() == (None, DEFAULT_TX_PORT)


def test_seeding_does_not_make_tx_sendable(monkeypatch):
  """A seeded host is display only. It must not stand in for an actual configure - nothing is
  sendable until a TxClient exists, which is what every send path checks."""
  monkeypatch.setenv("PYG_TX_HOST", HOST_A)
  core, client = _core_client()
  try:
    assert client.get("/tx/status").json()["host"] == HOST_A
    r = client.post("/tx/enable", json={"on": True})
    assert r.status_code == 409
    assert "no TX config yet" in r.json()["detail"]
  finally:
    core.stop()


# ------------------------------------------------------------------- the dashboard side of it
def test_dashboard_does_not_hardcode_a_loopback_host():
  js = DASHBOARD_JS.read_text()
  m = re.search(r'id="tx-host"[^>]*>', js)
  assert m, "tx-host input not found in dashboard.js"
  assert "127.0.0.1" not in m.group(0), (
    "the host box must not open pre-filled with loopback - that is how transmission got "
    f"silently aimed at this laptop: {m.group(0)}"
  )
  assert "placeholder=" in m.group(0)


def test_dashboard_backfills_every_tx_form_field():
  """``txFormFields()`` is the single pairing of form field -> /tx/status key, read by the
  backfill in ``renderTxStatusLive``. If a field is added to the panel and not to this list it
  silently goes back to lying, so assert all five are present."""
  js = DASHBOARD_JS.read_text()
  m = re.search(r"function txFormFields\(\)\s*\{.*?\n\}", js, re.S)
  assert m, "txFormFields() not found"
  body = m.group(0)
  for field, key in [
    ("tx-host", "host"), ("tx-port", "port"), ("tx-kpmax", "kp_max"),
    ("tx-kdmax", "kd_max"), ("tx-ttlms", "ttl_ms"),
  ]:
    assert f'"{field}"' in body, field
    assert f"tx.{key}" in body, key
  assert "renderTxStatusLive" in js and "txFormFields()" in js.split("function txFormFields")[0] + js


def test_dashboard_refuses_a_blank_host():
  js = DASHBOARD_JS.read_text()
  m = re.search(r"async function pushTxConfig\(\)\s*\{.*?\n\}", js, re.S)
  assert m, "pushTxConfig() not found"
  body = m.group(0)
  assert "if (!host)" in body, "blank host must be refused, not posted"
  assert "return null" in body


# ------------------------------------------------------------------ why ARM stayed dead
def test_arm_is_refused_in_idle_mode_and_says_so():
  """The bench sequence that produced "2. activate TX panel 했는데 왜 ARM 이 안되지?":
  everything in the TX panel reported success, and step 3 was refused purely because the sim
  was in `idle`. The refusal must name the mode - it is the only clue an operator gets."""
  core, client = _core_client()
  try:
    a, _ = _two_joints(core)
    _ingest(core, {a: 0.1})
    client.post("/tx/config", json={"host": HOST_A, "port": PORT, "enable": [a]})
    client.post("/sync_from_real")
    client.post("/tx/enable", json={"on": True})
    core.mode = "idle"
    r = client.post("/tx/arm")
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert "manual" in detail and "idle" in detail, detail
  finally:
    core.stop()


def test_joints_tab_leaves_idle_for_manual():
  """``setControlMode("joints")`` used to request manual ONLY when a policy was running, so a
  freshly started viewer (which comes up in `idle`) never left idle by opening the manual
  control tab - and TX could then never be armed at all."""
  js = DASHBOARD_JS.read_text()
  m = re.search(r"function setControlMode\(mode\)\s*\{.*?\n\}", js, re.S)
  assert m, "setControlMode() not found"
  body = m.group(0)
  joints_branch = body.split('if (mode === "joints")')[1].split("else if")[0]
  assert '"idle"' in joints_branch, (
    "opening the Joints tab must also rescue the sim out of idle, not only out of policy modes"
  )
  assert 'mode: "manual"' in joints_branch


def test_dashboard_lists_every_arm_blocker_on_the_page():
  """A disabled button whose reason lives only in `title` is a reason nobody reads."""
  js = DASHBOARD_JS.read_text()
  m = re.search(r"function txArmBlockers\(tx, st, sync\)\s*\{.*?\n\}", js, re.S)
  assert m, "txArmBlockers() not found"
  body = m.group(0)
  for needle in ["1. configure", "0. sync from hardware", "2. activate TX panel", "manual"]:
    assert needle in body, needle
  assert 'id="tx-arm-block"' in js, "the blocker list needs somewhere on the page to render"
  assert "txArmBlockers(tx, st, sync)" in js, "renderTxStatusLive must actually call it"


# ---------------------------------------- plan B: report divergence, never prevent it
def test_releasing_space_no_longer_erases_the_command():
  """`stopTxDeadman` used to POST /sync_from_real, snapping the manual target back onto the
  measured pose the instant Space was released. With the slider lock that made commanding a
  motion nearly impossible - the only window was "hold Space and drag at once", and letting go
  erased it. Measured result: 1722 packets accepted by the robot, every one carrying the
  joint's own present position (docs/127)."""
  js = DASHBOARD_JS.read_text()
  m = re.search(r"function stopTxDeadman\(\)\s*\{.*?\n\}", js, re.S)
  assert m, "stopTxDeadman() not found"
  # the comment explains the removal, so look for an actual CALL, not the word
  code = "\n".join(l for l in m.group(0).splitlines() if not l.strip().startswith("//"))
  assert "sync_from_real" not in code, (
    "releasing the dead-man must not rewrite the operator's target"
  )
  assert "apiOk" not in code, "releasing Space must not post anything at all"


def test_dead_man_no_longer_disables_sliders():
  """Only the sync gate may lock a slider. Space decides where the value goes, not whether the
  operator may set one."""
  js = DASHBOARD_JS.read_text()
  assert "slider.disabled = lock.locked;" in js
  assert "num.disabled = lock.locked;" in js
  assert "const blocked = lock.locked || held;" not in js, "the old dead-man lock is back"


def test_hold_state_reports_delivery_rather_than_refusal():
  js = DASHBOARD_JS.read_text()
  m = re.search(r"function hwHoldState\(txStatus\)\s*\{.*?\n\}", js, re.S)
  assert m, "hwHoldState() not found"
  body = m.group(0)
  assert "delivering" in body, "the state must say whether the value is being DELIVERED"
  assert "holding: true" not in body, "the old refusal shape is back"


def test_every_transmitting_joint_shows_target_minus_measured():
  """The number missing from all seven incidents: asked-for minus measured, on screen at all
  times. A gap that never closes and a gap that is zero because nothing was commanded are
  different faults that used to look identical."""
  js = DASHBOARD_JS.read_text()
  m = re.search(r"function jointDivergence\(name\)\s*\{.*?\n\}", js, re.S)
  assert m, "jointDivergence() not found"
  body = m.group(0)
  assert "diff: tgt - real" in body
  assert "sentDiff" in body, "what was SENT must be tracked separately from the on-screen target"
  assert 'class="jdiv mono"' in js, "the joint row needs somewhere to render it"
  assert ".jdiv{grid-column:1/-1" in (DASHBOARD_JS.parent / "dashboard.html").read_text()


# ------------------------------------------------------- the command path trace (docs/127)
def test_command_path_trace_covers_every_link_in_order():
  js = DASHBOARD_JS.read_text()
  m = re.search(r"function commandPathTrace\(\)\s*\{.*?\n  return rows;\n\}", js, re.S)
  assert m, "commandPathTrace() not found"
  body = m.group(0)
  # in the order a command actually travels
  order = ["목표가 실측과 다른가", "모드 manual", "무장(ARM)", "스페이스 유지",
           "패킷 송신", "로봇이 받아들임", "모터가 따라옴"]
  positions = [body.index(lbl) for lbl in order]
  assert positions == sorted(positions), f"trace rows out of order: {order}"


def test_trace_names_the_first_blocked_link():
  """The whole point: the first failing row is the cause. A list that does not say which one
  is first is just more indicators."""
  js = DASHBOARD_JS.read_text()
  assert "rows.find((r) => r.ok === false)" in js
  assert "첫 막힌 곳" in js
  assert "renderCommandPathTrace();" in js, "the trace must actually be rendered"


def test_trace_admits_when_the_robot_counters_are_missing():
  """`accepted`/`rejected_*` live on the robot and are printed to a log file there. Until they
  are carried back, that row must say so rather than quietly showing a pass."""
  js = DASHBOARD_JS.read_text()
  m = re.search(r'rows\.push\(\{ label: "로봇이 받아들임", ok: null,.*?\}\);', js, re.S)
  assert m, "the unknown-counters branch is missing"
  assert "ok: null" in m.group(0), "an unreported counter is 'unknown', never 'pass'"


# --------------------------------- the backfill must not fight the operator (2026-09-07)
def test_backfill_leaves_an_edited_field_alone():
  """User: "kp max / kd max 값을 못바꾸잖아. 바꾸면 원복되는데 뭔짓을했나?"

  Skipping only the FOCUSED field was not enough. Typing a new cap and then clicking away to
  press "1. configure" blurs the field, and the very next 250 ms poll wrote the still-in-force
  value back over it - so configure pushed the OLD number. Fixing "the form lies" had produced
  "the form cannot be edited", which is worse: the first at least let the operator set a value.
  """
  js = DASHBOARD_JS.read_text()
  m = re.search(r"txFormFields\(\)\.forEach\(\(\[id, val\]\) => \{.*?\n  \}\);", js, re.S)
  assert m, "the backfill loop was not found"
  body = m.group(0)
  assert 'node.dataset.dirty === "1"' in body, "an edited field must be skipped, not overwritten"
  assert "node === document.activeElement" in body, "the focused field must still be skipped"


def test_editing_a_field_marks_it_and_pushing_clears_it():
  js = DASHBOARD_JS.read_text()
  assert 'node.addEventListener("input", () => { node.dataset.dirty = "1"; });' in js, (
    "typing into a TX field must claim it from the backfill"
  )
  m = re.search(r"async function pushTxConfig\(\)\s*\{.*?\n\}", js, re.S)
  assert m
  assert "delete n.dataset.dirty" in m.group(0), (
    "once the server holds the typed values they are no longer pending edits"
  )


def test_an_unapplied_edit_is_stated_on_screen():
  """An edit that has not been pushed must not look applied, and must not be silently thrown
  away either - the panel says which fields are typed but not in force."""
  js = DASHBOARD_JS.read_text()
  assert "typed but NOT applied" in js
  assert "txStatusValue(id, tx)" in js, "the comparison must be form-value against server-value"


# --------------------------------------- what a motor actually receives (2026-09-07)
def test_the_gains_that_went_on_the_wire_are_reported():
  """A cap is not what a motor receives: it is a ceiling applied per joint over the gains
  table. "I typed 30" and "the motor got 30" have to be separately checkable, which is the
  same lesson as docs/127 - report the effect, not the intent."""
  core, client = _core_client()
  try:
    a, _ = _two_joints(core)
    _ingest(core, {a: 0.1})
    client.post("/tx/config", json={"host": HOST_A, "port": PORT, "enable": [a],
                                    "kp_max": 12.0, "kd_max": 0.8})
    st = client.get("/tx/status").json()
    assert "last_sent_gains" in st, "the viewer must report the gains it actually sent"
    assert st["last_sent_gains"] == {}, "nothing sent yet -> nothing to report"
  finally:
    core.stop()


def test_the_cap_is_what_reaches_the_wire_when_it_binds():
  """The end-to-end claim, checked on the real client rather than by reading the code: a gains
  table above the cap must arrive AT the cap, and one below it must arrive unchanged."""
  from pygviewer.bridge.tx_client import TxClient
  core, _ = _core_client()
  try:
    a, b = _two_joints(core)
    c = core.c
    tx = TxClient(HOST_A, PORT, joint_names=[a, b], arm_token="t", origin="manual",
                  contract=c, kp_max=12.0, kd_max=0.8)
    tx.arm()
    tx.set_target({a: 0.0, b: 0.0}, mode="manual",
                  kp={a: 150.0, b: 3.0},      # one far above the cap, one below it
                  kd={a: 5.0, b: 0.2})
    msg = tx.build_message()
    assert msg is not None
    got = dict(zip(msg.joint_names, msg.kp))
    assert got[a] == 12.0, f"a gain above the cap must arrive AT the cap, got {got[a]}"
    assert got[b] == 3.0, f"a gain below the cap must pass through, got {got[b]}"
    gains = tx.last_sent_gains
    assert gains[a]["kp"] == 12.0 and gains[b]["kp"] == 3.0
    assert gains[a]["kd"] == 0.8 and gains[b]["kd"] == 0.2
  finally:
    core.stop()


def test_reported_gains_are_the_clamped_ones_not_the_requested_ones():
  """The whole point of reporting them: if this echoed back what was asked for, it would agree
  with the form no matter what actually happened, which is exactly the failure mode this
  session has been unpicking."""
  from pygviewer.bridge.tx_client import TxClient
  core, _ = _core_client()
  try:
    a, _ = _two_joints(core)
    tx = TxClient(HOST_A, PORT, joint_names=[a], arm_token="t", origin="manual",
                  contract=core.c, kp_max=5.0, kd_max=0.5)
    tx.arm()
    tx.set_target({a: 0.0}, mode="manual", kp={a: 999.0}, kd={a: 99.0})
    tx.build_message()
    assert tx.last_sent_gains[a]["kp"] == 5.0
    assert tx.last_sent_gains[a]["kd"] == 0.5
  finally:
    core.stop()


# ----------------------------- arming must not silently launch a large first move (2026-09-07)
def test_arm_refuses_a_large_first_move_and_names_the_travel():
  """The bench incident this comes from. `check_arm_ready` skipped its check entirely for any
  target that differed from the synced value - read as "a deliberate command" with NO ceiling
  on its size. So a stale target 40 deg from the measured pose armed without a word, which is
  precisely what docs/123 section 10.2 claims this gate prevents. Measured, once the gain cap
  was restored to a value that can actually move these joints: L_hip_yaw 40.1 -> 0.3 deg and
  L_knee 49.5 -> 5.8 deg in about a second. It had stayed invisible only because the previous
  cap of 5 was too weak to execute any target at all."""
  core, client = _core_client()
  try:
    a, _ = _two_joints(core)
    _ingest(core, {a: 0.1})
    client.post("/tx/config", json={"host": HOST_A, "port": PORT, "enable": [a]})
    client.post("/sync_from_real")
    client.post("/tx/enable", json={"on": True})
    # move the manual target far away from the measured pose, as a stale target would be
    client.post("/target", json={"values": {a: 0.1 + math.radians(40)}})
    r = client.post("/tx/arm")
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert "arming would move the hardware immediately" in detail
    assert a in detail and "of travel" in detail, detail
  finally:
    core.stop()


def test_a_confirmed_large_move_is_allowed():
  """A deliberate large move must stay possible - the check questions the SIZE, it does not
  forbid it. The refusal names the numbers, and confirming is a second, explicit act."""
  core, client = _core_client()
  try:
    a, _ = _two_joints(core)
    _ingest(core, {a: 0.1})
    client.post("/tx/config", json={"host": HOST_A, "port": PORT, "enable": [a]})
    client.post("/sync_from_real")
    client.post("/tx/enable", json={"on": True})
    client.post("/target", json={"values": {a: 0.1 + math.radians(40)}})
    assert client.post("/tx/arm").status_code == 409
    r = client.post("/tx/arm", json={"allow_jump": True})
    assert r.status_code == 200, r.text
  finally:
    core.stop()


def test_a_small_deliberate_move_still_arms_untouched():
  core, client = _core_client()
  try:
    a, _ = _two_joints(core)
    _ingest(core, {a: 0.1})
    client.post("/tx/config", json={"host": HOST_A, "port": PORT, "enable": [a]})
    client.post("/sync_from_real")
    core.step_n(8)      # the queue drains on a CONTROL tick, one per `decimation` physics steps
    client.post("/tx/enable", json={"on": True})
    client.post("/target", json={"values": {a: 0.1 + math.radians(3)}})   # well under the limit
    core.step_n(8)
    r = client.post("/tx/arm")
    assert r.status_code == 200, r.text
  finally:
    core.stop()


def test_arming_right_after_a_sync_still_needs_no_confirmation():
  """The normal path: sync sets the target to the measured pose, so the first packet commands
  no motion and nothing is questioned."""
  core, client = _core_client()
  try:
    a, _ = _two_joints(core)
    _ingest(core, {a: 0.1})
    client.post("/tx/config", json={"host": HOST_A, "port": PORT, "enable": [a]})
    r = client.post("/sync_from_real").json()
    core.step_n(8)      # the queue drains on a CONTROL tick, one per `decimation` physics steps
    client.post("/tx/enable", json={"on": True})
    ar = client.post("/tx/arm")
    assert ar.status_code == 200, ar.text
    assert "applied" in r, "the sync must say whether the target actually took"
  finally:
    core.stop()


def test_the_dashboard_confirms_rather_than_dead_ends():
  js = DASHBOARD_JS.read_text()
  assert "armJumpConfirmUntil" in js
  assert "arming would move the hardware immediately" in js
  assert "allow_jump: true" in js
  assert "S.lastApiError = e.message" in js, "apiOk must keep the refusal text for the caller"


# --------------------------------- the policy opt-in is set from the panel (2026-09-08)
def test_the_panel_can_set_the_step_cap_and_the_policy_opt_in():
  """User: "이것도 Telemetry 섹션에서 설정가능하게 해줘." Both were API-only, so the one
  setting that still guards a policy session could not be seen or changed where the operator
  actually works."""
  js = DASHBOARD_JS.read_text()
  assert 'id="tx-maxstep"' in js and 'id="tx-allowpolicy"' in js
  m = re.search(r"async function pushTxConfig\(\)\s*\{.*?\n\}", js, re.S)
  assert m
  body = m.group(0)
  assert "max_step_deg:" in body and "allow_policy:" in body
  assert 'el("tx-maxstep").value || ""' in body, (
    "an empty box means 'no cap' and must send null - not 0, which the server rejects"
  )


def test_the_step_cap_is_shown_in_degrees_per_second_too():
  """0.3 deg/packet is not a number anyone has intuition for; 15 deg/s is."""
  js = DASHBOARD_JS.read_text()
  assert 'id="tx-maxstep-dps"' in js
  assert "deg/s @50Hz" in js


def test_one_rule_decides_whether_the_panel_thinks_it_may_send():
  """The ARM button's enabled state and the blocker list must not disagree - that is a panel
  that greys out a button and then lists no reason, or the reverse."""
  js = DASHBOARD_JS.read_text()
  hits = re.findall(r'tx\.allow_policy && st\.mode === "policy_sim"', js)
  assert len(hits) == 2, f"both the button and the blocker list must use it, found {len(hits)}"


def test_the_panel_says_when_a_policy_may_drive():
  js = DASHBOARD_JS.read_text()
  assert "POLICY MAY DRIVE" in js, "this is not a state to leave implicit in a toast"


# ------------------------------- a refusal has to say why, on the panel (2026-09-08)
def test_the_pending_note_names_the_arm_as_the_blocker():
  """User: "값 바꾸고, 1. 눌렀는데도 값 반영 안된다고." TX was armed, and `configure` is
  refused while armed so the joint set cannot change mid-stream. The panel said only "typed
  but NOT applied - press 1. configure", which is advice that could not work; pressing it
  again is the natural response and looks like nothing happens.

  The refusal existed - as a four-second toast. That is not where a persistent condition
  belongs."""
  js = DASHBOARD_JS.read_text()
  assert "TX is ARMED" in js
  assert 'Press "disarm" first' in js
  m = re.search(r"if \(pending\.length\) \{.*?\} else \{", js, re.S)
  assert m and "tx.armed" in m.group(0), "the note must branch on the actual blocker"


def test_the_configure_button_is_disabled_while_armed():
  """A button that cannot work should look like it cannot work."""
  js = DASHBOARD_JS.read_text()
  assert 'cfgBtn.disabled = !!tx.armed;' in js
  assert "disarm first" in js


def test_a_step_cap_above_the_motor_says_it_is_not_a_cap():
  """100 deg/packet at 50 Hz is 5000 deg/s, five times the RS04's rated 1002 - a number that
  looks like a limit and is not one."""
  js = DASHBOARD_JS.read_text()
  assert "1002" in js
  assert "no real cap" in js
