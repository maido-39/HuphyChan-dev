"""UI v2 TX (viewer -> hardware) REAL wiring (docs/121 section 10, docs/123, 2026-09-04
wiring brief) - supersedes ``test_dashboard_tx.py``, which tested the earlier STUB's
different API shape (``/tx/arm{host,port}``, ``/tx/motor``, ``/tx/send`` - all gone now that
``pygviewer/tx.py`` drives a real ``bridge.tx_client.TxClient``).

Three tiers, cheapest first:

  * Pure-Python ``TxState`` unit tests (no MuJoCo, no socket) - the enable/arm/heartbeat/
    mode-gate state machine in isolation.
  * API + control-tick wiring, one module-scoped ``SimCore`` (test_dashboard.py already
    found that piling on function-scoped SimCore fixtures pushes the suite's peak RSS over
    test_sim_rate.py's budget - same care taken here).
  * ONE real end-to-end test over loopback UDP against ``bridge.dummy_rx.DummyRx`` - the
    actual wire, the actual ``SimCore._on_control_tick`` -> ``TxState.on_control_tick`` ->
    ``TxClient.tick()`` path, nothing mocked. This is the test that answers "does the
    dashboard's TX section, wired this way, actually move a (simulated) motor".
"""

from __future__ import annotations

import json
import socket
import time

import pytest
from fastapi.testclient import TestClient

from pygviewer import CACHE_DIR
from pygviewer.api import build_app
from pygviewer.bridge.dummy_rx import DummyRx
from pygviewer.bridge.tx_map import JointTargetMapper, sim_rad_to_cal_deg
from pygviewer.contract import load_contract
from pygviewer.schema import JointState
from pygviewer.sim_core import SimCore
from pygviewer.tx import DEADMAN_TIMEOUT_S, TxNotAllowed, TxState

VARIANT = "LegOnly-AB"
ACT_NAMES = ["L_knee_joint", "R_knee_joint", "L_hip_pitch_joint"]


def _contract():
  try:
    return load_contract(CACHE_DIR, VARIANT)
  except FileNotFoundError:
    pytest.skip(f"no baked contract for {VARIANT}")


def _free_port() -> int:
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  s.bind(("127.0.0.1", 0))
  port = s.getsockname()[1]
  s.close()
  return port


def _target_deg(c, sim_joint: str, rad: float) -> float:
  mapper = JointTargetMapper(c)
  _limb, _motor, row = mapper.motor_row(sim_joint)
  ts = mapper.travel_sign[sim_joint]
  return sim_rad_to_cal_deg(rad, row["sign"], row["offset_rad"], ts)


# ============================================================================= pure TxState
def test_configure_then_enable_then_arm_is_the_required_order():
  tx = TxState(ACT_NAMES)
  with pytest.raises(TxNotAllowed, match="not enabled"):
    tx.arm("manual")
  with pytest.raises(TxNotAllowed, match="no TX config"):
    tx.set_enabled(True)
  tx.configure("127.0.0.1", 9872, ["L_knee_joint"])
  tx.set_enabled(True)
  tx.arm("manual")
  assert tx.armed is True
  st = tx.status()
  assert st["enable"] == ["L_knee_joint"]
  assert st["armed"] is True
  assert st["sending"] is True  # arming itself counts as a fresh heartbeat


def test_configure_rejects_unknown_joint_names():
  tx = TxState(ACT_NAMES)
  with pytest.raises(TxNotAllowed, match="not actuated"):
    tx.configure("127.0.0.1", 9872, ["not_a_joint"])


def test_configure_refused_while_armed():
  tx = TxState(ACT_NAMES)
  tx.configure("127.0.0.1", 9872, ["L_knee_joint"])
  tx.set_enabled(True)
  tx.arm("manual")
  with pytest.raises(TxNotAllowed, match="disarm"):
    tx.configure("127.0.0.1", 9999, ["L_knee_joint"])


def test_arm_refused_outside_manual_mode():
  tx = TxState(ACT_NAMES)
  tx.configure("127.0.0.1", 9872, ["L_knee_joint"])
  tx.set_enabled(True)
  for mode in ("idle", "policy_sim", "policy_shadow", "real_replay", "file_replay"):
    with pytest.raises(TxNotAllowed):
      tx.arm(mode)
    assert tx.armed is False


def test_disabling_stage_1_disarms_stage_2():
  tx = TxState(ACT_NAMES)
  tx.configure("127.0.0.1", 9872, ["L_knee_joint"])
  tx.set_enabled(True)
  tx.arm("manual")
  tx.set_enabled(False)
  assert tx.armed is False
  assert tx.enabled is False


def test_check_mode_gate_disarms_when_mode_leaves_manual():
  tx = TxState(ACT_NAMES)
  tx.configure("127.0.0.1", 9872, ["L_knee_joint"])
  tx.set_enabled(True)
  tx.arm("manual")
  tx.check_mode_gate("policy_sim")
  assert tx.armed is False
  assert "policy_sim" in tx.disarm_reason


def test_check_mode_gate_is_a_noop_while_still_manual():
  tx = TxState(ACT_NAMES)
  tx.configure("127.0.0.1", 9872, ["L_knee_joint"])
  tx.set_enabled(True)
  tx.arm("manual")
  tx.check_mode_gate("manual")
  assert tx.armed is True


def test_heartbeat_requires_armed():
  tx = TxState(ACT_NAMES)
  with pytest.raises(TxNotAllowed):
    tx.heartbeat()


def test_stale_heartbeat_stops_sending_but_does_not_disarm():
  """The module docstring's item 4: a stale keyboard dead-man makes ``sending()`` False
  WITHOUT touching ``armed`` - "hold", not "disarm"."""
  tx = TxState(ACT_NAMES)
  tx.configure("127.0.0.1", 9872, ["L_knee_joint"])
  tx.set_enabled(True)
  tx.arm("manual")
  assert tx.sending() is True
  tx._last_heartbeat -= (DEADMAN_TIMEOUT_S + 0.05)
  assert tx.sending() is False
  assert tx.armed is True  # NOT disarmed
  assert tx.disarm_reason is None
  # a fresh heartbeat resumes sending with no re-arm needed
  tx.heartbeat()
  assert tx.sending() is True


def test_on_control_tick_is_a_noop_when_not_sending():
  """No client configured at all - must not raise, must not do anything observable."""
  tx = TxState(ACT_NAMES)
  tx.on_control_tick("manual", {"L_knee_joint": 0.4})  # must not raise
  assert tx.status()["last_seq"] is None


def test_status_reports_arm_token_for_the_operator_to_copy_to_the_receiver():
  tx1 = TxState(ACT_NAMES)
  tx2 = TxState(ACT_NAMES)
  assert tx1.arm_token and tx2.arm_token
  assert tx1.arm_token != tx2.arm_token  # generated per-instance, never a shared default


# ================================================================= API + control-tick wiring
@pytest.fixture(scope="module")
def client():
  core = SimCore(load_contract(CACHE_DIR, "LegOnly-AB"), realtime=False)
  core.reset("knees_bent")
  core.mode = "manual"
  core.step_n(1)
  app = build_app(core, core.c.freshness())
  try:
    yield TestClient(app), core
  finally:
    core.stop()


def test_arm_before_config_is_409(client):
  c, core = client
  r = c.post("/tx/arm")
  assert r.status_code == 409, r.text
  assert "config" in r.json()["detail"]


def test_config_enable_arm_round_trip(client):
  c, core = client
  assert core.mode == "manual"
  r = c.post("/tx/config", json={"host": "127.0.0.1", "port": 9872, "enable": ["L_knee_joint"]})
  assert r.status_code == 200, r.text
  assert r.json()["enable"] == ["L_knee_joint"]

  r = c.post("/tx/config", json={"host": "x", "port": 1, "enable": ["not_a_joint"]})
  assert r.status_code == 400  # unknown joint rejected before it ever reaches TxState

  r = c.post("/tx/arm")
  assert r.status_code == 409  # stage 1 not enabled yet

  r = c.post("/tx/enable", json={"on": True})
  assert r.status_code == 200, r.text
  assert r.json()["enabled"] is True

  # Sync-before-arm gate (hw_sync.py, docs/123 section 10.2): arm is refused until a
  # POST /sync_from_real covers every TX-enabled joint. Feed fresh real telemetry for
  # L_knee_joint directly into RealState (the same thing WS /ws/in would do) so a sync has
  # something to work with.
  r = c.post("/tx/arm")
  assert r.status_code == 409, r.text
  assert "sync" in r.json()["detail"].lower()

  core.real.ingest_joint_state(
    JointState(t_ns=time.monotonic_ns(), seq=1, src="dummy", joint_names=["L_knee_joint"], q=[0.4])
  )
  r = c.post("/sync_from_real")
  assert r.status_code == 200, r.text
  assert "L_knee_joint" in r.json()["synced"]

  r = c.post("/tx/arm")
  assert r.status_code == 200, r.text
  assert r.json()["armed"] is True

  r = c.post("/tx/config", json={"host": "127.0.0.1", "port": 9872, "enable": ["L_knee_joint"]})
  assert r.status_code == 409  # refused while armed

  r = c.post("/tx/heartbeat")
  assert r.status_code == 200, r.text

  r = c.get("/tx/status")
  body = r.json()
  assert body["armed"] is True
  assert body["sending"] is True
  assert body["kp_max"] == pytest.approx(5.0)
  assert body["kd_max"] == pytest.approx(0.5)
  assert isinstance(body["arm_token"], str) and body["arm_token"]


def test_mode_change_auto_disarms_within_one_control_tick(client):
  """Structural enforcement (SimCore._on_control_tick -> TxState.check_mode_gate), not only
  the API layer's pre-check - the exact pattern this codebase already uses for
  modes.SHADOW_MAY_TRANSMIT. Runs LAST in this module (leaves core.mode != 'manual')."""
  c, core = client
  assert core.tx.armed is True  # left armed by the previous test
  core.mode = "policy_sim"  # bypasses POST /mode entirely
  core.step_n(core.decimation)  # one control tick
  assert core.tx.armed is False
  assert "policy_sim" in core.tx.disarm_reason
  r = c.get("/tx/status")
  assert r.json()["armed"] is False
  r = c.post("/tx/arm")
  assert r.status_code == 409, r.text


# ==================================================================== live end-to-end (UDP)
class _TeleCatcher:
  """Minimal HUPHY-UDP-format telemetry reader (same pattern as test_dummy_rx.py's
  ``TelemetryCatcher`` - kept file-local rather than shared, matching this test suite's
  existing convention of each bridge test file owning its own tiny catcher)."""

  _MAX_DRAIN = 16

  def __init__(self, port: int):
    self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.sock.bind(("127.0.0.1", port))
    self.sock.settimeout(0.01)

  def latest(self, key_prefix: str) -> dict | None:
    out = None
    for _ in range(self._MAX_DRAIN):
      try:
        data, _ = self.sock.recvfrom(4096)
      except socket.timeout:
        break
      obj = json.loads(data.decode("utf-8"))
      if any(k.startswith(key_prefix) for k in obj):
        out = obj
    return out

  def close(self):
    self.sock.close()


def _wait_until(predicate, timeout=3.0, interval=0.02):
  t0 = time.monotonic()
  while time.monotonic() - t0 < timeout:
    v = predicate()
    if v is not None:
      return v
    time.sleep(interval)
  pytest.fail(f"condition not met within {timeout}s")


@pytest.fixture
def live_rig():
  c = _contract()
  core = SimCore(c, realtime=False)
  core.reset("knees_bent")
  core.mode = "manual"
  core.step_n(1)

  listen_port = _free_port()
  tele_port = _free_port()
  rx = DummyRx(
    contract=c, listen_host="127.0.0.1", listen_port=listen_port,
    telemetry_host="127.0.0.1", telemetry_port=tele_port, arm_token=core.tx.arm_token,
    hz=100.0,
  )
  catcher = _TeleCatcher(tele_port)
  app = build_app(core, core.c.freshness())
  client = TestClient(app)
  rx.start()
  try:
    yield dict(c=c, core=core, rx=rx, catcher=catcher, client=client, listen_port=listen_port)
  finally:
    rx.stop()
    catcher.close()
    core.stop()


def _sync_knee(core, client, value: float = 0.3):
  """Sync-before-arm gate (hw_sync.py, docs/123 section 10.2): every ``live_rig`` test below
  arms TX for ``L_knee_joint`` and must feed it a fresh real sample first, same as an
  operator pressing '0. sync from hardware' after a real telemetry stream connects."""
  core.real.ingest_joint_state(
    JointState(t_ns=time.monotonic_ns(), seq=1, src="dummy", joint_names=["L_knee_joint"], q=[value])
  )
  r = client.post("/sync_from_real")
  assert r.status_code == 200, r.text
  return r.json()


def _drive(core, client, seconds: float, heartbeat: bool):
  """Steps the sim in real 20 ms slices (control-tick granularity), optionally sending a
  fresh keyboard dead-man heartbeat every slice - the dashboard's own ~100ms cadence, made
  tighter here only so a short test does not have to wait through many dead periods."""
  end = time.monotonic() + seconds
  while time.monotonic() < end:
    if heartbeat:
      client.post("/tx/heartbeat")
    core.step_n(core.decimation)
    time.sleep(0.02)


def test_live_enable_arm_heartbeat_target_tracks_over_real_udp(live_rig):
  c, core, rx, catcher, client, listen_port = (
    live_rig["c"], live_rig["core"], live_rig["rx"], live_rig["catcher"], live_rig["client"],
    live_rig["listen_port"],
  )
  r = client.post(
    "/tx/config",
    json={"host": "127.0.0.1", "port": listen_port, "enable": ["L_knee_joint"]},
  )
  assert r.status_code == 200, r.text
  assert client.post("/tx/enable", json={"on": True}).status_code == 200
  _sync_knee(core, client)
  assert client.post("/tx/arm").status_code == 200

  target_rad = 0.5
  r = client.post("/target", json={"values": {"L_knee_joint": target_rad}})
  assert r.status_code == 200, r.text
  target_deg = _target_deg(c, "L_knee_joint", target_rad)

  _drive(core, client, seconds=1.5, heartbeat=True)

  def _settled():
    pkt = catcher.latest("left/knee/")
    if pkt is None:
      return None
    return pkt if abs(pkt.get("left/knee/pos", 1e9) - target_deg) < 2.0 else None

  pkt = _wait_until(_settled, timeout=2.0)
  assert abs(pkt["left/knee/pos"] - target_deg) < 2.0
  st = client.get("/tx/status").json()
  assert st["last_seq"] is not None and st["last_seq"] >= 0
  assert st["rate_hz"] > 0
  assert st["last_sent_target"]["L_knee_joint"] == pytest.approx(target_rad, abs=1e-6)


def test_live_heartbeat_stop_halts_sending_within_deadman_timeout(live_rig):
  c, core, rx, catcher, client, listen_port = (
    live_rig["c"], live_rig["core"], live_rig["rx"], live_rig["catcher"], live_rig["client"],
    live_rig["listen_port"],
  )
  client.post("/tx/config", json={"host": "127.0.0.1", "port": listen_port, "enable": ["L_knee_joint"]})
  client.post("/tx/enable", json={"on": True})
  _sync_knee(core, client)
  client.post("/tx/arm")
  client.post("/target", json={"values": {"L_knee_joint": 0.4}})

  _drive(core, client, seconds=0.3, heartbeat=True)
  assert client.get("/tx/status").json()["sending"] is True
  seq_while_sending = client.get("/tx/status").json()["last_seq"]

  # release the (simulated) Space key: keep stepping the sim, but stop heartbeating.
  _drive(core, client, seconds=DEADMAN_TIMEOUT_S + 0.2, heartbeat=False)
  st = client.get("/tx/status").json()
  assert st["armed"] is True  # NOT disarmed - "hold", not "disarm" (module docstring item 4)
  assert st["sending"] is False
  seq_after_silence = st["last_seq"]

  # no NEW packets were sent while heartbeat was stale - seq must not have advanced further
  # than whatever was already in flight when the silence began.
  more_ticks_seq = seq_after_silence
  _drive(core, client, seconds=0.3, heartbeat=False)
  assert client.get("/tx/status").json()["last_seq"] == more_ticks_seq


def test_live_policy_sim_mode_refuses_arm_and_auto_disarms(live_rig):
  c, core, rx, catcher, client, listen_port = (
    live_rig["c"], live_rig["core"], live_rig["rx"], live_rig["catcher"], live_rig["client"],
    live_rig["listen_port"],
  )
  client.post("/tx/config", json={"host": "127.0.0.1", "port": listen_port, "enable": ["L_knee_joint"]})
  client.post("/tx/enable", json={"on": True})
  _sync_knee(core, client)
  assert client.post("/tx/arm").status_code == 200

  core.mode = "policy_sim"  # bypasses POST /mode - only the structural gate should catch this
  core.step_n(core.decimation)
  st = client.get("/tx/status").json()
  assert st["armed"] is False
  assert "policy_sim" in st["disarm_reason"]

  r = client.post("/tx/arm")
  assert r.status_code == 409, r.text
  assert "manual" in r.json()["detail"]


def test_live_joint_outside_enable_list_is_never_transmitted(live_rig):
  c, core, rx, catcher, client, listen_port = (
    live_rig["c"], live_rig["core"], live_rig["rx"], live_rig["catcher"], live_rig["client"],
    live_rig["listen_port"],
  )
  # only the knee is enabled - hip_pitch is commanded too, but must never reach the wire.
  client.post("/tx/config", json={"host": "127.0.0.1", "port": listen_port, "enable": ["L_knee_joint"]})
  client.post("/tx/enable", json={"on": True})
  _sync_knee(core, client)
  client.post("/tx/arm")
  client.post("/target", json={"values": {"L_knee_joint": 0.3, "L_hip_pitch_joint": 0.35}})

  _drive(core, client, seconds=1.0, heartbeat=True)

  knee_deg = _target_deg(c, "L_knee_joint", 0.3)

  def _knee_moved():
    pkt = catcher.latest("left/knee/")
    return pkt if pkt and abs(pkt.get("left/knee/pos", 1e9) - knee_deg) < 2.0 else None

  _wait_until(_knee_moved, timeout=2.0)
  hip_pkt = catcher.latest("left/hip_pitch/")
  hip_default_deg = _target_deg(c, "L_hip_pitch_joint", c.default_q("L_hip_pitch_joint"))
  # never commanded (not in --enable / TxClient.joint_names) - stayed at dummy_rx's own
  # default, not driven toward the 0.35 rad the (never-sent) message would have asked for.
  assert hip_pkt is not None
  assert abs(hip_pkt["left/hip_pitch/pos"] - hip_default_deg) < 1.0
