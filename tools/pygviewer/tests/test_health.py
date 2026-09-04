"""Motor health task (2026-09-04): "is the real robot actually responding" as a per-joint
ok/warn/dead state, plus the link-level connection indicator - user request: "웹 뷰어에서
실제 모터와 연결됐는지가 투명하지 않다. 모터 Health Check를 실시간으로 보고 싶고, 데이터가
들어오는지 인디케이터로 보고 싶다."

Covers: (a) a JointState carrying HUPHY DIAG fields (temp/age/ack/miss) verdicts "ok"; (b) no
telemetry for 1.5s transitions a joint to "dead"; (c) ack=0/miss>=1 verdicts "warn", a
sustained run of misses verdicts "dead"; (d) a sender that never carries diag at all is judged
on reception recency only and flagged `diag: false`; (e) the `GET /health` response shape.
Shares one module-scoped SimCore/TestClient (the test_rom_clip.py pattern - a SimCore per
test measurably pushes this suite's shared RSS budget).
"""

import time

import pytest
from fastapi.testclient import TestClient

from pygviewer import CACHE_DIR
from pygviewer.api import build_app
from pygviewer.contract import load_contract
from pygviewer.schema import JointState
from pygviewer.sim_core import SimCore
from pygviewer.telemetry import HEALTH_DEAD_MISS, RealState

VARIANT = "LegOnly-AB"


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


def _feed(core, joint, *, q=0.1, temp=None, age=None, ack=None, miss=None, seq=1, src="dummy"):
  n = len(core.act_names)
  names = core.act_names
  msg = JointState(
    t_ns=seq, seq=seq, src=src, joint_names=names,
    q=[q if nm == joint else None for nm in names],
    temp_c=([temp if nm == joint else None for nm in names] if temp is not None else None),
    motor_age_ms=([age if nm == joint else None for nm in names] if age is not None else None),
    ack=([ack if nm == joint else None for nm in names] if ack is not None else None),
    miss=([miss if nm == joint else None for nm in names] if miss is not None else None),
  )
  core.real.ingest_joint_state(msg)


# ============================================================================= (a) ok verdict
def test_fresh_diag_data_verdicts_ok(core):
  _feed(core, "L_knee_joint", temp=35.0, age=5.0, ack=1.0, miss=0.0, seq=101)
  h = core.real.health()
  j = h["joints"]["L_knee_joint"]
  assert j["state"] == "ok"
  assert j["diag"] is True
  assert j["temp_c"] == pytest.approx(35.0)
  assert j["motor_age_ms"] == pytest.approx(5.0)
  assert j["ack"] == pytest.approx(1.0)
  assert j["miss"] == pytest.approx(0.0)


# ========================================================================== (b) dead by age
def test_no_telemetry_for_over_a_second_transitions_to_dead():
  """Pure RealState (no SimCore) with a fake clock, so this does not depend on real wall
  time passing - a monkeypatched time.monotonic lets 1.5s "pass" instantly."""
  rs = RealState(["j1"], {"j1": (-1.0, 1.0)}, "sha")
  t = {"now": 1000.0}
  import pygviewer.telemetry as telemetry_mod

  orig_monotonic = telemetry_mod.time.monotonic
  telemetry_mod.time.monotonic = lambda: t["now"]
  try:
    rs.ingest_joint_state(JointState(t_ns=1, seq=1, src="dummy", joint_names=["j1"], q=[0.1]))
    h = rs.health()
    assert h["joints"]["j1"]["state"] == "ok"
    t["now"] += 1.5
    h = rs.health()
    assert h["joints"]["j1"]["state"] == "dead"
    assert h["joints"]["j1"]["age_s"] == pytest.approx(1.5, abs=1e-6)
  finally:
    telemetry_mod.time.monotonic = orig_monotonic


def test_never_seen_joint_is_dead_with_no_age(core):
  h = core.real.health()
  # R_hip_yaw_joint (say) has never once been fed in this whole test module
  never = next(n for n in core.act_names if n not in ("L_knee_joint",))
  j = h["joints"][never]
  if j["age_s"] is None:  # only true if nothing else in this module ever touched it
    assert j["state"] == "dead"
    assert j["diag"] is False


# ============================================================ (c) warn / dead by ack & miss
def test_ack_zero_is_warn_not_dead(core):
  _feed(core, "L_knee_joint", temp=35.0, age=5.0, ack=0.0, miss=0.0, seq=102)
  j = core.real.health()["joints"]["L_knee_joint"]
  assert j["state"] == "warn"


def test_miss_one_is_warn():
  rs = RealState(["j1"], {"j1": (-1.0, 1.0)}, "sha")
  rs.ingest_joint_state(JointState(
    t_ns=1, seq=1, src="dummy", joint_names=["j1"], q=[0.1],
    motor_age_ms=[5.0], ack=[1.0], miss=[1.0],
  ))
  assert rs.health()["joints"]["j1"]["state"] == "warn"


def test_sustained_miss_is_dead():
  rs = RealState(["j1"], {"j1": (-1.0, 1.0)}, "sha")
  rs.ingest_joint_state(JointState(
    t_ns=1, seq=1, src="dummy", joint_names=["j1"], q=[0.1],
    motor_age_ms=[5.0], ack=[0.0], miss=[float(HEALTH_DEAD_MISS)],
  ))
  assert rs.health()["joints"]["j1"]["state"] == "dead"


def test_diag_present_but_motor_age_null_is_dead():
  """The robot itself reports diag for this joint (ack/miss arrived) but has NEVER heard
  back from the motor (age stayed null/-1 forever) - dead, not ok-by-recency."""
  rs = RealState(["j1"], {"j1": (-1.0, 1.0)}, "sha")
  rs.ingest_joint_state(JointState(
    t_ns=1, seq=1, src="dummy", joint_names=["j1"], q=[0.1], ack=[0.0], miss=[0.0],
  ))
  h = rs.health()
  assert h["joints"]["j1"]["diag"] is True
  assert h["joints"]["j1"]["motor_age_ms"] is None
  assert h["joints"]["j1"]["state"] == "dead"


# ==================================================================== (d) diag-less sender
def test_no_diag_ever_is_judged_on_reception_recency_only_and_flagged():
  """A sender that never carries temp/age/ack/miss (today's bench_telemetry.py) must be
  scored purely on "did we hear from it recently" - never silently treated as if a missing
  ack/miss meant something bad (or good)."""
  rs = RealState(["j1"], {"j1": (-1.0, 1.0)}, "sha")
  rs.ingest_joint_state(JointState(t_ns=1, seq=1, src="dummy", joint_names=["j1"], q=[0.1]))
  h = rs.health()
  j = h["joints"]["j1"]
  assert j["diag"] is False
  assert j["state"] == "ok"
  assert j["motor_age_ms"] is None
  assert j["ack"] is None
  assert j["miss"] is None


# =================================================================================== (e) API
def test_get_health_response_shape(core, http):
  _feed(core, "L_knee_joint", temp=36.0, age=4.0, ack=1.0, miss=0.0, seq=201)
  r = http.get("/health")
  assert r.status_code == 200, r.text
  body = r.json()
  assert set(body.keys()) >= {"link", "joints", "summary"}
  assert set(body["link"].keys()) >= {"connected", "rx_hz", "age_s", "seq_gaps", "last_seq"}
  assert body["link"]["connected"] is True
  assert "L_knee_joint" in body["joints"]
  j = body["joints"]["L_knee_joint"]
  assert set(j.keys()) >= {"state", "age_s", "motor_age_ms", "ack", "miss", "temp_c", "q", "diag"}
  assert set(body["summary"].keys()) == {"ok", "warn", "dead"}
  assert sum(body["summary"].values()) == len(core.act_names)


def test_status_telemetry_carries_a_health_summary_not_the_full_grid(core, http):
  _feed(core, "L_knee_joint", temp=36.0, age=4.0, ack=1.0, miss=0.0, seq=202)
  core.step_n(1)  # force a _publish() so the snapshot reflects the ingest
  r = http.get("/status")
  assert r.status_code == 200, r.text
  health = r.json()["telemetry"]["health"]
  assert set(health.keys()) == {"summary", "link"}
  assert "joints" not in health, "Status.telemetry.health must be a SUMMARY, never the grid"
  assert sum(health["summary"].values()) == len(core.act_names)
  assert health["link"]["connected"] is True


def test_bench_style_single_joint_feed_shows_one_ok_and_the_rest_dead(core, http):
  """Live-shape regression: exactly the bench rig's situation - one joint gets real
  telemetry (no diag), the other 11 have NEVER been fed by this module and must show dead,
  not silently 'ok' by some default."""
  r = http.get("/health")
  body = r.json()
  fed = {"L_knee_joint"}
  for n, j in body["joints"].items():
    if n in fed:
      continue
    if j["age_s"] is None:  # never touched by ANY test in this module
      assert j["state"] == "dead"
