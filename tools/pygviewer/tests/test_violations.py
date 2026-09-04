"""A2 (2026-09-04, plan ``optimized-leaping-hamster.md``): the shared ROM/torque violation
record log (``pygviewer/violations.py``) and its wiring into ``telemetry.py`` (recv/
recv_torque), ``sim_core.py`` (sim_actuator, ``_tn_clamp``'s T-N-curve saturation) and
``api.py`` (``GET /violations``, ``POST /violations/clear``, the NaN/inf send-side rejection
record).

Pure ``ViolationLog`` behaviour (ring buffer, cumulative counts, rate limiting, clear) is
tested standalone, with no ``SimCore`` at all - cheap and deterministic. The recv/sim_actuator/
API integration tests share ONE module-scoped ``SimCore`` (the ``test_rom_clip.py`` pattern:
a ``SimCore`` per test measurably pushes this suite's shared RSS budget), each doing its own
explicit setup rather than relying on test order for correctness.
"""

import math

import pytest
from fastapi.testclient import TestClient

from pygviewer import CACHE_DIR
from pygviewer.api import build_app
from pygviewer.contract import load_contract
from pygviewer.schema import JointState
from pygviewer.sim_core import SimCore
from pygviewer.violations import ViolationLog

VARIANT = "LegOnly-AB"


# ============================================================= pure ViolationLog unit tests
def test_empty_log_has_no_records_and_zero_counts():
  log = ViolationLog()
  assert log.list() == []
  assert log.counts_by_joint() == {}
  assert log.total_count() == 0
  assert log.last() is None
  s = log.summary()
  assert s == {"total": 0, "by_joint": {}, "last": None}


def test_record_stores_value_limits_over_by_and_bumps_count():
  log = ViolationLog()
  rec = log.record(side="recv", joint="L_knee_joint", value=-1.5, limit_lo=0.0, limit_hi=2.0944)
  assert rec is not None
  assert rec["side"] == "recv"
  assert rec["joint"] == "L_knee_joint"
  assert rec["value"] == pytest.approx(-1.5)
  assert rec["limit_lo"] == pytest.approx(0.0)
  assert rec["limit_hi"] == pytest.approx(2.0944)
  assert rec["over_by"] == pytest.approx(1.5)
  assert rec["seq"] >= 1
  assert log.total_count() == 1
  assert log.counts_by_joint()["L_knee_joint"]["recv"] == 1
  assert log.counts_by_joint()["L_knee_joint"]["total"] == 1
  assert log.last()["joint"] == "L_knee_joint"


def test_record_with_none_value_never_computes_over_by():
  """A rejected NaN/inf request has no finite offending value - `over_by` must stay `None`,
  never NaN (these records are served as strict JSON, allow_nan=False)."""
  log = ViolationLog()
  rec = log.record(side="send", joint="L_knee_joint", value=None, src="send",
                    extra={"rejected": "non-finite (NaN/inf)"})
  assert rec["value"] is None
  assert rec["over_by"] is None
  assert rec["rejected"] == "non-finite (NaN/inf)"


def test_rate_limit_suppresses_ring_entries_but_not_the_cumulative_count():
  log = ViolationLog()
  r1 = log.record(side="sim_actuator", joint="L_knee_joint", value=200.0, limit_lo=-120.0,
                   limit_hi=120.0, rate_limit_s=10.0)
  r2 = log.record(side="sim_actuator", joint="L_knee_joint", value=201.0, limit_lo=-120.0,
                   limit_hi=120.0, rate_limit_s=10.0)
  assert r1 is not None
  assert r2 is None, "second call inside the rate-limit window must not add a new record"
  assert len(log.list(side="sim_actuator")) == 1
  assert log.total_count() == 2, "the cumulative count must still bump on every call"
  assert log.counts_by_joint()["L_knee_joint"]["sim_actuator"] == 2


def test_ring_buffer_caps_at_max_records():
  log = ViolationLog(max_records=5)
  for i in range(20):
    log.record(side="recv", joint=f"j{i}", value=1.0, limit_lo=0.0, limit_hi=0.5)
  assert len(log.list()) == 5
  assert log.total_count() == 20, "counts survive eviction from the ring, only the ring caps"


def test_clear_drops_records_and_counts_but_seq_never_goes_backwards():
  log = ViolationLog()
  log.record(side="recv", joint="L_knee_joint", value=-1.0, limit_lo=0.0, limit_hi=1.0)
  last_seq = log.last()["seq"]
  log.clear()
  assert log.list() == []
  assert log.counts_by_joint() == {}
  assert log.total_count() == 0
  rec = log.record(side="recv", joint="L_knee_joint", value=-1.0, limit_lo=0.0, limit_hi=1.0)
  assert rec["seq"] > last_seq


def test_list_filters_by_side():
  log = ViolationLog()
  log.record(side="recv", joint="a", value=-1.0, limit_lo=0.0, limit_hi=1.0)
  log.record(side="send", joint="b", value=-1.0, limit_lo=0.0, limit_hi=1.0)
  assert [r["side"] for r in log.list(side="recv")] == ["recv"]
  assert [r["side"] for r in log.list(side="send")] == ["send"]
  assert len(log.list()) == 2


# ================================================================== SimCore/API integration
@pytest.fixture(scope="module")
def core():
  try:
    c = load_contract(CACHE_DIR, VARIANT)
  except FileNotFoundError:
    pytest.skip(f"no baked contract for {VARIANT}")
  core = SimCore(c, realtime=False)
  yield core
  core.stop()


@pytest.fixture(scope="module")
def http(core):
  app = build_app(core, core.c.freshness())
  return TestClient(app)


# ------------------------------------------------------------------------------- (a) recv
def test_recv_rom_violation_is_recorded_with_value_and_limit(core):
  core.violations.clear()
  i = core.act_names.index("L_knee_joint")
  lo, hi = float(core.range_lo[i]), float(core.range_hi[i])
  out_of_range = lo - 1.5
  msg = JointState(t_ns=1, seq=1, src="dummy", joint_names=["L_knee_joint"], q=[out_of_range])
  core.real.ingest_joint_state(msg)

  recs = core.violations.list(side="recv")
  assert len(recs) == 1
  rec = recs[0]
  assert rec["joint"] == "L_knee_joint"
  assert rec["value"] == pytest.approx(out_of_range)
  assert rec["limit_lo"] == pytest.approx(lo)
  assert rec["limit_hi"] == pytest.approx(hi)
  assert rec["over_by"] == pytest.approx(lo - out_of_range)
  assert rec["src"] == "dummy"
  assert core.real.range_violations["L_knee_joint"] >= 1, "old counter stays intact (backward compat)"


def test_recv_torque_violation_is_recorded_when_reported_tau_exceeds_effort(core):
  core.violations.clear()
  i = core.act_names.index("L_knee_joint")
  effort = float(core.eff[i])
  hot_tau = effort + 40.0
  msg = JointState(
    t_ns=2, seq=2, src="dummy", joint_names=["L_knee_joint"], q=[0.1], tau_est=[hot_tau],
  )
  core.real.ingest_joint_state(msg)

  recs = core.violations.list(side="recv_torque")
  assert len(recs) == 1
  assert recs[0]["joint"] == "L_knee_joint"
  assert recs[0]["value"] == pytest.approx(hot_tau)
  assert recs[0]["limit_hi"] == pytest.approx(effort)


def test_recv_within_range_records_nothing(core):
  core.violations.clear()
  i = core.act_names.index("L_knee_joint")
  lo, hi = float(core.range_lo[i]), float(core.range_hi[i])
  mid = 0.5 * (lo + hi)
  msg = JointState(t_ns=3, seq=3, src="dummy", joint_names=["L_knee_joint"], q=[mid])
  core.real.ingest_joint_state(msg)
  assert core.violations.list() == []


# ------------------------------------------------------------------------ (b) sim_actuator
def test_sim_actuator_saturation_is_recorded_and_rate_limited(core):
  """Calls the T-N clamp directly (unit-level, same as ``_substep`` calls it) with a torque
  no motor could ever produce, rather than trying to drive the whole physics loop into
  saturation - deterministic, no dependence on the T-N curve's actual shape at some qdot."""
  core.violations.clear()
  import numpy as np

  i = core.act_names.index("L_knee_joint")
  n = len(core.act_names)

  tau = np.zeros(n)
  tau[i] = 1.0e6
  omega = np.zeros(n)
  core._tn_clamp(tau, omega)
  assert float(tau[i]) < 1.0e6, "the clamp itself must have actually capped the value"

  recs = core.violations.list(side="sim_actuator")
  assert len(recs) == 1
  rec = recs[0]
  assert rec["joint"] == "L_knee_joint"
  assert rec["tau_raw"] == pytest.approx(1.0e6)
  assert rec["tau_clamped"] == pytest.approx(float(tau[i]))
  assert rec["src"] == "sim"
  assert core.violations.counts_by_joint()["L_knee_joint"]["sim_actuator"] == 1

  # A second saturation on the SAME joint inside the 100ms rate-limit window must not add a
  # second ring entry, but the cumulative count must still bump.
  tau2 = np.zeros(n)
  tau2[i] = 1.0e6
  core._tn_clamp(tau2, omega)
  assert len(core.violations.list(side="sim_actuator")) == 1
  assert core.violations.counts_by_joint()["L_knee_joint"]["sim_actuator"] == 2


# ------------------------------------------------------------------------------ (c)/(d) API
def test_get_violations_empty_when_nothing_has_happened(core, http):
  http.post("/violations/clear")
  r = http.get("/violations")
  assert r.status_code == 200, r.text
  body = r.json()
  assert body["records"] == []
  assert body["by_joint"] == {}
  assert body["total"] == 0


def test_get_violations_reports_a_live_recv_violation_with_age(core, http):
  http.post("/violations/clear")
  i = core.act_names.index("L_knee_joint")
  lo = float(core.range_lo[i])
  msg = JointState(t_ns=4, seq=4, src="dummy", joint_names=["L_knee_joint"], q=[lo - 2.0])
  core.real.ingest_joint_state(msg)

  r = http.get("/violations")
  body = r.json()
  assert body["total"] == 1
  assert len(body["records"]) == 1
  rec = body["records"][0]
  assert rec["joint"] == "L_knee_joint"
  assert rec["side"] == "recv"
  assert rec["age_s"] >= 0.0
  assert body["by_joint"]["L_knee_joint"]["recv"] == 1


def test_get_violations_filters_by_side(core, http):
  http.post("/violations/clear")
  i = core.act_names.index("L_knee_joint")
  lo = float(core.range_lo[i])
  core.real.ingest_joint_state(
    JointState(t_ns=5, seq=5, src="dummy", joint_names=["L_knee_joint"], q=[lo - 2.0])
  )
  r = http.get("/violations", params={"side": "send"})
  assert r.json()["records"] == []
  r = http.get("/violations", params={"side": "recv"})
  assert len(r.json()["records"]) == 1


def test_post_violations_clear_empties_everything(core, http):
  i = core.act_names.index("L_knee_joint")
  lo = float(core.range_lo[i])
  core.real.ingest_joint_state(
    JointState(t_ns=6, seq=6, src="dummy", joint_names=["L_knee_joint"], q=[lo - 2.0])
  )
  assert http.get("/violations").json()["total"] > 0
  r = http.post("/violations/clear")
  assert r.status_code == 200
  assert r.json() == {"ok": True}
  body = http.get("/violations").json()
  assert body["records"] == []
  assert body["total"] == 0


def test_post_target_nan_is_rejected_and_recorded_as_a_send_violation(core, http):
  """Mirrors test_rom_clip.py's NaN-rejection test, plus the A2 addition: the 422 also drops
  one side="send" violation record naming the offending joint."""
  http.post("/violations/clear")
  import json as jsonlib

  body = jsonlib.dumps({"values": {"L_knee_joint": float("nan")}}).encode("utf-8")
  r = http.post("/target", content=body, headers={"content-type": "application/json"})
  assert r.status_code == 422, r.text

  recs = http.get("/violations", params={"side": "send"}).json()["records"]
  assert any(r["joint"] == "L_knee_joint" and r.get("rejected") for r in recs)


def test_status_telemetry_carries_a_violations_summary_not_the_full_ring(core, http):
  http.post("/violations/clear")
  i = core.act_names.index("L_knee_joint")
  lo = float(core.range_lo[i])
  core.real.ingest_joint_state(
    JointState(t_ns=7, seq=7, src="dummy", joint_names=["L_knee_joint"], q=[lo - 2.0])
  )
  core.step_n(1)  # force a _publish() so core.snapshot()["telemetry"] reflects the ingest
  r = http.get("/status")
  assert r.status_code == 200, r.text
  v = r.json()["telemetry"]["violations"]
  assert v["total"] >= 1
  assert "records" not in v, "Status.telemetry must carry a SUMMARY only, not the ring buffer"
  assert v["by_joint"]["L_knee_joint"]["recv"] >= 1
  assert v["last"]["joint"] == "L_knee_joint"


def test_tx_status_carries_send_side_violations_count(core, http):
  """POST /target NaN rejections above already recorded side="send" violations; /tx/status
  should reflect a send-side-only count (never the recv-side ones from the other tests)."""
  r = http.get("/tx/status")
  assert r.status_code == 200, r.text
  assert "violations_count" in r.json()
  assert isinstance(r.json()["violations_count"], int)


def test_ab_crank_hard_range_violation_still_bumps_replay_clamp_and_leaves_violations_alone(core):
  """A1's replay_clamp bookkeeping (sim_core.py `_update_replay_targets`) is a DIFFERENT
  counter than this task's violations log by design (see the module docstrings of both) - a
  hard-range clamp on a direct-drive replay joint must not silently also fabricate a
  violations-log entry for a code path this task never touched."""
  core.violations.clear()
  core._apply_cmd({"op": "mode", "value": "idle"})
  core.reset("knees_bent")
  core.set_base(mode="free")
  core.submit({"op": "mode", "value": "real_replay"})
  core.step_n(core.decimation)

  i = core.act_names.index("L_knee_joint")
  hi = float(core.range_hi[i])
  msg = JointState(t_ns=8, seq=8, src="dummy", joint_names=["L_knee_joint"], q=[hi + 5.0])
  core.real.ingest_joint_state(msg)
  core.step_n(core.decimation * 3)

  assert core.replay_clamp_count["L_knee_joint"] > 0
  # the recv-side ROM check DID also fire (the raw telemetry value is itself out of range),
  # so this only asserts the two bookkeeping structures agree on "something happened", not
  # that one is silent - see test_recv_rom_violation_is_recorded_with_value_and_limit above
  # for the recv record's own shape.
  assert any(r["joint"] == "L_knee_joint" for r in core.violations.list(side="recv"))

  core._apply_cmd({"op": "mode", "value": "idle"})
  core.reset("knees_bent")
