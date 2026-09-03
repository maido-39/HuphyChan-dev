"""P4: the same-target-sequence player (``modes.TargetScript`` / ``SimCore.run_script``)."""

import json

import pytest
from fastapi.testclient import TestClient

from pygviewer import CACHE_DIR
from pygviewer.api import build_app
from pygviewer.contract import load_contract
from pygviewer.modes import TargetScript
from pygviewer.sim_core import SimCore

VARIANT = "LegOnly-AB"
SCRIPTS_DIR = __file__.rsplit("/tests/", 1)[0] + "/scripts"
SINE = f"{SCRIPTS_DIR}/sine_hips_knees_1hz_20deg.json"
STEP = f"{SCRIPTS_DIR}/step_knee_5x10deg.json"


@pytest.fixture
def core():
  c = SimCore(load_contract(CACHE_DIR, VARIANT), realtime=False)
  c.reset("knees_bent")
  try:
    yield c
  finally:
    c.stop()


def test_sample_scripts_only_name_actuated_joints():
  c = load_contract(CACHE_DIR, VARIANT)
  for path in (SINE, STEP):
    s = TargetScript(path)
    unknown = [n for n in s.joint_names if n not in c.action_joint_names]
    assert not unknown, f"{path}: {unknown}"


def test_target_script_interpolates_linearly(tmp_path):
  p = tmp_path / "s.json"
  p.write_text(json.dumps({"joint_names": ["a"], "rows": [[0.0, 0.0], [1.0, 1.0]]}))
  s = TargetScript(str(p))
  s.start(sim_time_s=10.0)
  assert s.at(10.0)["a"] == pytest.approx(0.0)
  assert s.at(10.5)["a"] == pytest.approx(0.5)
  assert s.at(11.0)["a"] == pytest.approx(1.0)
  assert s.at(11.5)["a"] == pytest.approx(1.0)  # clamps past the end, one-shot
  assert s.is_finished(11.0)


def test_target_script_loops(tmp_path):
  p = tmp_path / "s.json"
  p.write_text(json.dumps({"joint_names": ["a"], "rows": [[0.0, 0.0], [1.0, 1.0]], "loop": True}))
  s = TargetScript(str(p))
  s.start(sim_time_s=0.0)
  assert s.at(1.5)["a"] == pytest.approx(0.5)
  assert not s.is_finished(100.0)


def test_run_script_switches_to_manual_and_drives_targets(core):
  info = core.run_script(STEP)
  assert core.mode == "manual"
  assert core.script_run_id == info["run_id"]
  core.step_n(core.decimation)
  assert core.script is not None
  # first row of step_knee_5x10deg.json is the knee's own default (step 0)
  first_row_q = core.script.rows[0][1]
  i = core.act_names.index("L_knee_joint")
  assert core.target[i] == pytest.approx(first_row_q, abs=1e-6)


def test_run_script_refuses_a_joint_this_variant_does_not_actuate(core, tmp_path):
  p = tmp_path / "bad.json"
  p.write_text(json.dumps({"joint_names": ["not_a_real_joint"], "rows": [[0.0, 0.0]]}))
  with pytest.raises(KeyError):
    core.run_script(str(p))


def test_run_script_refused_during_policy_or_replay_mode(core):
  core.set_base(mode="fixed")
  core._apply_cmd({"op": "mode", "value": "real_replay"})
  with pytest.raises(RuntimeError):
    core.run_script(STEP)


def test_stop_script_clears_state(core):
  core.run_script(SINE)
  core.stop_script()
  assert core.script is None
  assert core.script_run_id is None
  with pytest.raises(RuntimeError):
    core.stop_script()


def test_script_finishes_on_its_own_and_clears_run_id(core):
  info = core.run_script(STEP)
  # step_knee_5x10deg.json runs ~6 s; step past its end in one call.
  core.step_n(int((core.script.duration_s + 0.5) / core.dt))
  assert core.script is None
  assert core.script_run_id is None


def test_recorded_joint_state_carries_the_run_id(core):
  info = core.run_script(SINE)
  s = core.step_n(core.decimation) or core.snapshot()
  snap = core.snapshot()
  assert snap["script_run_id"] == info["run_id"]


@pytest.fixture
def client():
  c = SimCore(load_contract(CACHE_DIR, VARIANT), realtime=False)
  c.reset("knees_bent")
  c.step_n(1)
  app = build_app(c, c.c.freshness())
  try:
    yield TestClient(app), c
  finally:
    c.stop()


def test_api_script_run_and_stop(client):
  c, core = client
  r = c.post("/script/run", json={"path": STEP, "run_id": "test-run-1"})
  assert r.status_code == 200, r.text
  assert r.json()["run_id"] == "test-run-1"
  core.step_n(core.decimation)
  assert core.mode == "manual"
  r = c.post("/script/stop")
  assert r.status_code == 200, r.text
  r = c.post("/script/stop")
  assert r.status_code == 409, r.text


def test_api_script_run_missing_file_is_404(client):
  c, _ = client
  r = c.post("/script/run", json={"path": "/no/such/script.json"})
  assert r.status_code == 404, r.text
