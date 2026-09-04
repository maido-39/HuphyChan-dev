"""UI v2 (layout B) dashboard: server-side surface a pytest can actually exercise.

The dashboard itself is plain JS with no build step and no Node/browser available on this
host (docs/121 section 10, README "Tests" - the project's own documented fallback for a
front-end change like this is a live process + `curl`/Python `websockets`, done by hand
during development; see the report). What THIS file locks in with pytest, so it regresses
loudly instead of only "looking right in a screenshot nobody can take here":

  * the page and its local vendor assets actually serve (no CDN - LAN-offline is the point)
  * the new additive endpoints (`/presets`, `/presets/apply`, `GainsIn.clear_overrides`)
    behave the way `dashboard.js`'s Gains tab assumes
  * the exact REST sequence the Policy tab's "load" button performs (`/policy/load` ->
    `/policy/cmd {0,0,0}` -> `/mode policy_sim`) actually lands the sim in that state -
    the orchestration decision lives in JS (docs/121 section 10 rationale: keep backend mode
    semantics untouched), but the sequence it relies on is backend behaviour and IS testable
  * the deg<->rad conversion dashboard.js relies on for the Joints tab's unit toggle is
    extracted from the shipped source text and checked for round-trip correctness, so a typo
    in the formula fails a test instead of only showing up as a mis-scaled slider
"""

import glob
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pygviewer import CACHE_DIR
from pygviewer.api import build_app
from pygviewer.contract import load_contract
from pygviewer.sim_core import SimCore

VARIANT = "LegOnly-AB"
STATIC_DIR = Path(__file__).resolve().parents[1] / "pygviewer" / "static"
PRESETS_DIR = Path(__file__).resolve().parents[1] / "presets"


@pytest.fixture(scope="module")
def client():
  """Module-scoped deliberately: a fresh SimCore per test (15 of them in this file) pushed
  the FULL SUITE's ru_maxrss over test_sim_rate.py's 600 MB budget - that check is a whole-
  process peak (resource.getrusage), not this file's own footprint, so every extra
  MjModel+onnx load in the same pytest session counts against it. The tests below are
  written to tolerate a shared core: read-only checks run first, and every test that mutates
  gains/policy/telemetry either cleans up after itself or is immune to what ran before it
  (see each test's own note) - this is a real ordering dependency, not a free lunch, so keep
  new tests either read-only or self-contained the same way."""
  c = SimCore(load_contract(CACHE_DIR, VARIANT), realtime=False)
  c.reset("knees_bent")
  c.step_n(1)
  (PRESETS_DIR / "pytest_tmp_preset.json").unlink(missing_ok=True)  # a crashed prior run's leftover
  app = build_app(c, c.c.freshness())
  try:
    yield TestClient(app), c
  finally:
    c.stop()


# ------------------------------------------------------------------ page + static assets
def test_dashboard_page_and_alias_serve(client):
  c, _ = client
  for path in ("/", "/dash"):
    r = c.get(path)
    assert r.status_code == 200, (path, r.text)
    assert "pygviewer" in r.text.lower()


def test_static_vendor_and_own_js_serve(client):
  c, _ = client
  for path in ("/static/dashboard.js", "/static/vendor/three.min.js", "/static/vendor/uPlot.iife.min.js", "/static/vendor/uPlot.min.css"):
    r = c.get(path)
    assert r.status_code == 200, path
    assert len(r.content) > 1000, f"{path} suspiciously small ({len(r.content)} bytes)"


def test_static_unknown_path_is_404_not_500(client):
  c, _ = client
  r = c.get("/static/does-not-exist.js")
  assert r.status_code == 404


# ------------------------------------------------------------------ Status additions
def test_status_carries_sim_imu_and_side_mapping_flag(client):
  c, core = client
  r = c.get("/status")
  assert r.status_code == 200
  body = r.json()
  assert body["imu"] is not None
  assert len(body["imu"]["gravity_b"]) == 3
  # standing upright, gravity in the body frame points -Z (the model's own imu_upvector
  # sensor negated) - a sanity check that api.py's sign convention matches ObsBuilder's.
  assert body["imu"]["gravity_b"][2] < -0.9
  assert body["side_mapping_verified"] is False  # bridge/joint_map_huphy.json's own flag


# ------------------------------------------------------------------ /presets, /presets/apply
def test_presets_list_has_builtins(client):
  """Only checks the builtin keys and that `custom` is a list - NOT that it's empty, since
  this fixture is module-scoped (see the fixture's docstring) and another test in this file
  may have already saved one."""
  c, _ = client
  r = c.get("/presets")
  assert r.status_code == 200
  body = r.json()
  assert set(body["builtin"]) == {"train", "real"}
  assert isinstance(body["custom"], list)


def test_presets_save_then_apply_round_trip(client):
  c, core = client
  name = "pytest_tmp_preset"
  path = PRESETS_DIR / f"{name}.json"
  try:
    gains = {"L_knee_joint": {"kp": 42.0, "kd": 3.0}}
    r = c.post("/presets", json={"name": name, "gains": gains})
    assert r.status_code == 200, r.text
    assert path.exists()

    r = c.get("/presets")
    assert any(p["name"] == name for p in r.json()["custom"])

    r = c.post("/presets/apply", json={"name": name})
    assert r.status_code == 200, r.text
    assert r.json()["gains"]["L_knee_joint"]["kp"] == 42.0
    assert r.json()["gains"]["L_knee_joint"]["kd"] == 3.0
  finally:
    path.unlink(missing_ok=True)


def test_presets_apply_real_is_uniform_kp10_kd1(client):
  c, core = client
  r = c.post("/presets/apply", json={"name": "real"})
  assert r.status_code == 200, r.text
  table = r.json()["gains"]
  for n in core.act_names:
    assert table[n]["kp"] == 10.0
    assert table[n]["kd"] == 1.0


def test_presets_apply_train_clears_overrides(client):
  c, core = client
  c.post("/gains", json={"overrides": {"L_knee_joint": {"kp": 1.0, "kd": 1.0}}})
  assert core.gains_overrides  # something is overridden now
  r = c.post("/presets/apply", json={"name": "train"})
  assert r.status_code == 200, r.text
  assert not core.gains_overrides
  n = "L_knee_joint"
  assert r.json()["gains"][n]["kp"] == r.json()["gains"][n]["kp_train"]


def test_presets_save_rejects_reserved_names_and_unknown_joints(client):
  c, _ = client
  r = c.post("/presets", json={"name": "train", "gains": {}})
  assert r.status_code == 400
  r = c.post("/presets", json={"name": "ok_name", "gains": {"not_a_joint": {"kp": 1, "kd": 1}}})
  assert r.status_code == 400


def test_presets_apply_unknown_custom_name_is_404(client):
  c, _ = client
  r = c.post("/presets/apply", json={"name": "definitely_not_saved"})
  assert r.status_code == 404


# ------------------------------------------------------------------ GainsIn.clear_overrides
def test_gains_clear_overrides_flag(client):
  c, core = client
  n = "R_hip_pitch_joint"
  c.post("/gains", json={"overrides": {n: {"kp": 5.0, "kd": 5.0}}})
  assert n in core.gains_overrides
  r = c.post("/gains", json={"source": "train", "clear_overrides": True})
  assert r.status_code == 200, r.text
  assert n not in core.gains_overrides
  assert r.json()["gains"][n]["kp"] == r.json()["gains"][n]["kp_train"]


# ------------------------------------------------------------------ /ws/out real JointState
def test_ws_out_emits_no_real_frame_until_something_arrives(client):
  """The additive src='real' JointState frame on /ws/out must cost nothing when no real
  telemetry has ever been received - every existing test's condition, and most of this
  project's normal operation."""
  c, core = client
  assert core.real.rx_count == 0
  with c.websocket_connect("/ws/out?hz=50&types=JointState") as ws:
    seen_srcs = set()
    for _ in range(3):
      seen_srcs.add(json.loads(ws.receive_text())["src"])
  assert seen_srcs == {"sim"}


def test_ws_out_emits_real_frame_once_telemetry_arrives(client):
  from pygviewer.schema import JointState

  c, core = client
  core.real.ingest_joint_state(
    JointState(t_ns=0, seq=1, src="dummy", contract_hash=core.c.contract_sha,
               joint_names=["L_knee_joint"], q=[0.4])
  )
  with c.websocket_connect("/ws/out?hz=50&types=JointState") as ws:
    srcs = []
    for _ in range(4):
      srcs.append(json.loads(ws.receive_text())["src"])
  assert "sim" in srcs and "real" in srcs


# ------------------------------------------------------------------ Policy tab's load sequence
POLICIES = sorted(
  p for p in glob.glob(f"{CACHE_DIR}/*.policy_contract.json")
  if json.loads(open(p).read())["variant"] == VARIANT
)
pytestmark_policy = pytest.mark.skipif(not POLICIES, reason="no policy baked for LegOnly-AB yet")


@pytestmark_policy
def test_policy_load_then_cmd_zero_then_mode_policy_sim(client):
  """The exact three-call sequence dashboard.js's loadPolicyAndRun() performs (docs/121
  section 10, item 4: "load 즉시 policy_sim 모드 실행, cmd 0 = 제자리 서기")."""
  c, core = client
  pc = json.loads(open(POLICIES[0]).read())
  r = c.post("/policy/load", json={"onnx": pc["onnx"]})
  assert r.status_code == 200, r.text
  assert r.json()["obs_dim"] == 45
  r = c.post("/policy/cmd", json={"vx": 0.0, "vy": 0.0, "wz": 0.0})
  assert r.status_code == 200, r.text
  r = c.post("/mode", json={"mode": "policy_sim"})
  assert r.status_code == 200, r.text
  core.step_n(core.decimation)
  assert core.mode == "policy_sim"
  assert list(core.cmd) == [0.0, 0.0, 0.0]


# ------------------------------------------------------------------ deg/rad conversion (JS source)
def test_dashboard_js_deg_rad_conversion_round_trips():
  """dashboard.js has no build step and no Node/browser runs it on this host (module
  docstring), so this extracts the exact RAD2DEG/DEG2RAD literals from the shipped source and
  evaluates them - catching a typo in the formula itself (e.g. a stray inverse) even though it
  cannot execute displayVal()/internalVal() as JS."""
  src = (STATIC_DIR / "dashboard.js").read_text()
  m_deg = re.search(r"RAD2DEG\s*=\s*([0-9.]+\s*/\s*Math\.PI)", src)
  m_rad = re.search(r"DEG2RAD\s*=\s*(Math\.PI\s*/\s*[0-9.]+)", src)
  assert m_deg and m_rad, "RAD2DEG/DEG2RAD definitions not found in dashboard.js"
  import math

  ns = {"Math": type("Math", (), {"PI": math.pi})}
  rad2deg = eval(m_deg.group(1), ns)
  deg2rad = eval(m_rad.group(1), ns)
  assert abs(rad2deg - 180.0 / math.pi) < 1e-9
  assert abs(deg2rad - math.pi / 180.0) < 1e-9
  assert abs(rad2deg * deg2rad - 1.0) < 1e-9  # round trip: deg->rad->deg is identity
  # and the two "displayVal"/"internalVal" helper functions exist and reference them
  assert "function displayVal" in src and "function internalVal" in src
