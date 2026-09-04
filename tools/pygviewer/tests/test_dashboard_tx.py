"""UI v2 TX (viewer -> hardware) STUB (docs/121 section 10, docs/123): the safety gate is
the whole point of this file - policy output must never be transmittable, and a dead-man
timeout must actually stop a send. ``pygviewer/tx.py``'s module docstring explains the stub
boundary: no ``bridge/tx_client.py`` exists yet, so nothing here puts a byte on a wire; what
IS tested is the arm/disarm/mode-gate/dead-man/per-motor-enable state machine the dashboard's
TX section drives, built so a later real transmit call slots in without changing this
contract.

Most of this is a PURE PYTHON unit test of ``TxState`` (no MuJoCo model, no FastAPI) - the
safety logic does not need either. A fresh SimCore per test would (each loads an MjModel);
test_dashboard.py already found that piling on function-scoped SimCore fixtures pushes the
FULL SUITE's ru_maxrss over test_sim_rate.py's 600 MB budget (that check is a whole-process
peak, so every extra load counts against it everywhere else in the session). Only the last
two tests need a real SimCore, to prove the API layer and the 50 Hz control-tick gate are
actually wired to TxState and not just exercised in isolation - those share ONE module-scoped
core, same pattern and same ordering care as test_dashboard.py's fixture.
"""

import time

import pytest
from fastapi.testclient import TestClient

from pygviewer import CACHE_DIR
from pygviewer.api import build_app
from pygviewer.contract import load_contract
from pygviewer.sim_core import SimCore
from pygviewer.tx import DEADMAN_TIMEOUT_S, TxNotAllowed, TxState

ACT_NAMES = ["L_knee_joint", "R_knee_joint", "L_hip_pitch_joint"]


# ------------------------------------------------------------------ pure TxState unit tests
def test_arm_refused_outside_manual_mode():
  tx = TxState(ACT_NAMES)
  for mode in ("idle", "policy_sim", "policy_shadow", "real_replay", "file_replay"):
    with pytest.raises(TxNotAllowed):
      tx.arm(mode, "127.0.0.1", 9872)
    assert tx.armed is False


def test_arm_allowed_in_manual_mode():
  tx = TxState(ACT_NAMES)
  tx.arm("manual", "127.0.0.1", 9872)
  body = tx.status()
  assert body["armed"] is True
  assert body["active"] is True  # arming itself counts as a fresh heartbeat
  assert body["stub"] is True
  assert "tx_client.py" in body["note"]


def test_send_drops_motors_that_are_not_enabled():
  tx = TxState(ACT_NAMES)
  tx.arm("manual", "127.0.0.1", 9872)
  tx.set_motor("L_knee_joint", True)
  sent = tx.send({"L_knee_joint": 0.4, "R_knee_joint": -0.4})
  assert sent == {"L_knee_joint": 0.4}  # R_knee_joint silently dropped, never enabled


def test_send_refused_without_arming():
  tx = TxState(ACT_NAMES)
  tx.set_motor("L_knee_joint", True)
  with pytest.raises(TxNotAllowed):
    tx.send({"L_knee_joint": 0.4})


def test_deadman_timeout_stops_send():
  """Manipulates the internal clock directly for a fast, deterministic test - see
  test_deadman_timeout_via_real_sleep for the same behaviour with a real wall-clock wait."""
  tx = TxState(ACT_NAMES)
  tx.arm("manual", "127.0.0.1", 9872)
  tx.set_motor("L_knee_joint", True)
  tx._last_heartbeat -= (DEADMAN_TIMEOUT_S + 0.05)
  assert tx.active() is False
  with pytest.raises(TxNotAllowed, match="dead-man"):
    tx.send({"L_knee_joint": 0.4})


def test_deadman_timeout_via_real_sleep():
  tx = TxState(ACT_NAMES)
  tx.arm("manual", "127.0.0.1", 9872)
  tx.set_motor("L_knee_joint", True)
  time.sleep(DEADMAN_TIMEOUT_S + 0.1)
  with pytest.raises(TxNotAllowed):
    tx.send({"L_knee_joint": 0.4})


def test_heartbeat_keeps_send_alive():
  tx = TxState(ACT_NAMES)
  tx.arm("manual", "127.0.0.1", 9872)
  tx.set_motor("L_knee_joint", True)
  tx.heartbeat()
  tx.send({"L_knee_joint": 0.4})  # must not raise


def test_check_mode_gate_disarms_when_mode_leaves_manual():
  tx = TxState(ACT_NAMES)
  tx.arm("manual", "127.0.0.1", 9872)
  tx.check_mode_gate("policy_sim")
  assert tx.armed is False
  assert "policy_sim" in tx.disarm_reason


def test_check_mode_gate_is_a_noop_while_still_manual():
  tx = TxState(ACT_NAMES)
  tx.arm("manual", "127.0.0.1", 9872)
  tx.check_mode_gate("manual")
  assert tx.armed is True


def test_unknown_motor_name_raises_keyerror():
  tx = TxState(ACT_NAMES)
  with pytest.raises(KeyError):
    tx.set_motor("not_a_joint", True)


def test_status_is_honestly_labeled_a_stub():
  tx = TxState(ACT_NAMES)
  body = tx.status()
  assert body["stub"] is True
  assert "nothing is transmitted" in body["note"]


# ------------------------------------------------------------------ API + control-tick wiring
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


def test_api_arm_send_round_trip_and_400s(client):
  c, core = client
  assert core.mode == "manual"
  r = c.post("/tx/arm", json={"host": "127.0.0.1", "port": 9872})
  assert r.status_code == 200, r.text
  r = c.post("/tx/motor", json={"joint_name": "not_a_joint", "enabled": True})
  assert r.status_code == 400
  r = c.post("/tx/motor", json={"joint_name": "L_knee_joint", "enabled": True})
  assert r.status_code == 200, r.text
  r = c.post("/tx/send", json={"values": {"not_a_joint": 0.1}})
  assert r.status_code == 400  # rejected before the TX gate even sees it
  r = c.post("/tx/send", json={"values": {"L_knee_joint": 0.4, "R_knee_joint": -0.4}})
  assert r.status_code == 200, r.text
  assert r.json()["sent"] == {"L_knee_joint": 0.4}
  r = c.get("/tx/status")
  assert r.json()["armed"] is True


def test_api_mode_change_auto_disarms_within_one_control_tick(client):
  """Structural enforcement (SimCore._on_control_tick -> TxState.check_mode_gate), not only
  the API layer's pre-check - the exact pattern this codebase already uses for
  modes.SHADOW_MAY_TRANSMIT. Runs LAST in this module (leaves core.mode != 'manual'; every
  other test in this file that needs 'manual' runs before it - see the fixture's module
  scope)."""
  c, core = client
  assert core.tx.armed is True  # left armed by the previous test
  core.mode = "policy_sim"  # bypasses POST /mode entirely - any path that sets core.mode
  core.step_n(core.decimation)  # one control tick
  assert core.tx.armed is False
  assert "policy_sim" in core.tx.disarm_reason
  r = c.get("/tx/status")
  assert r.json()["armed"] is False
  r = c.post("/tx/arm", json={"host": "x", "port": 1})
  assert r.status_code == 409, r.text
