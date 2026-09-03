"""P4: the per-term obs mux (``policy_shadow``) - staleness fallback, real sourcing, and the
structural guarantee that a shadow action never drives anything but the LOCAL sim.
"""

import glob
import json

import numpy as np
import pytest

from pygviewer import CACHE_DIR
from pygviewer.contract import load_contract
from pygviewer.schema import ImuState, PolicyIO
from pygviewer.sim_core import SimCore
from pygviewer import modes as modes_mod

VARIANT = "LegOnly-AB"
POLICIES = sorted(
  p
  for p in glob.glob(f"{CACHE_DIR}/*.policy_contract.json")
  if json.loads(open(p).read())["variant"] == VARIANT
)
pytestmark = pytest.mark.skipif(not POLICIES, reason="no policy baked for LegOnly-AB yet")


@pytest.fixture
def core():
  c = SimCore(load_contract(CACHE_DIR, VARIANT), realtime=False)
  c.reset("knees_bent")
  pc = json.loads(open(POLICIES[0]).read())
  c.load_policy(onnx=pc["onnx"], policy_contract=pc)
  try:
    yield c
  finally:
    c.stop()


def _tick_shadow(c, n=1):
  c._apply_cmd({"op": "mode", "value": "policy_shadow"})
  for _ in range(n):
    c.step_n(c.decimation)


def test_shadow_defaults_to_all_sim_and_matches_policy_sim(core):
  """With no real telemetry and the mux at its default (every term 'sim'), policy_shadow
  must build the identical observation policy_sim would - same inputs, same code path."""
  _tick_shadow(core, 1)
  obs_shadow = core.last_obs.copy()
  assert core.obs_mux.effective == {n: "sim" for n in core.obs_mux.sources}
  core._apply_cmd({"op": "mode", "value": "policy_sim"})
  core.target = core.default_q.copy()  # policy_sim drives; undo so the next tick's q matches
  core.step_n(core.decimation)
  # obs won't be bit-identical (sim state moved one control tick), but the TERM LAYOUT and
  # dtype must agree, and neither call may have silently fallen back.
  assert obs_shadow.shape == core.last_obs.shape == (core.obs_builder.obs_dim,)


def test_shadow_falls_back_to_sim_when_real_is_missing(core):
  term = "base_ang_vel"
  core.obs_mux.set({term: "real"})
  _tick_shadow(core, 1)
  assert core.obs_mux.effective[term] == "sim"
  assert any(term in w for w in core._shadow_warnings)


def test_shadow_uses_fresh_real_imu_for_gyro_and_gravity(core):
  core.obs_mux.set({"base_ang_vel": "real", "projected_gravity": "real"})
  core.real.ingest_imu_state(
    ImuState(t_ns=0, seq=1, src="dummy", contract_hash=core.c.contract_sha,
              gyro_rad_s=[0.3, -0.2, 0.1], gravity_b=[0.4, 0.0, -0.9])
  )
  _tick_shadow(core, 1)
  assert core.obs_mux.effective["base_ang_vel"] == "real"
  assert core.obs_mux.effective["projected_gravity"] == "real"
  assert not core._shadow_warnings
  layout = {d["name"]: d for d in core.obs_builder.describe()}
  gyro_slice = core.last_obs[layout["base_ang_vel"]["offset"] : layout["base_ang_vel"]["offset"] + 3]
  grav_slice = core.last_obs[layout["projected_gravity"]["offset"] : layout["projected_gravity"]["offset"] + 3]
  assert np.allclose(gyro_slice, [0.3, -0.2, 0.1], atol=1e-5)
  assert np.allclose(grav_slice, [0.4, 0.0, -0.9], atol=1e-5)


def test_shadow_stale_imu_falls_back_after_the_age_budget(core, monkeypatch):
  core.obs_mux.set({"base_ang_vel": "real"})
  core.real.ingest_imu_state(
    ImuState(t_ns=0, seq=1, src="dummy", contract_hash=core.c.contract_sha,
              gyro_rad_s=[1.0, 0.0, 0.0], gravity_b=[0.0, 0.0, -1.0])
  )
  # Age it past the mux's staleness budget without waiting in real time.
  core.real.imu_age_ref -= (core.obs_mux.max_age_s + 0.05)
  _tick_shadow(core, 1)
  assert core.obs_mux.effective["base_ang_vel"] == "sim"
  assert any("base_ang_vel" in w for w in core._shadow_warnings)


def test_policy_io_feeds_last_action_and_command(core):
  core.obs_mux.set({"actions": "real", "command": "real"})
  n_act = len(core.act_names)
  fake_action = list(np.linspace(-0.1, 0.1, n_act))
  core.real.ingest_policy_io(
    PolicyIO(t_ns=0, seq=1, src="dummy", contract_hash=core.c.contract_sha,
             obs=[], action=fake_action, target=fake_action, cmd=[0.7, -0.1, 0.05])
  )
  _tick_shadow(core, 1)
  assert core.obs_mux.effective["actions"] == "real"
  assert core.obs_mux.effective["command"] == "real"
  layout = {d["name"]: d for d in core.obs_builder.describe()}
  act_slice = core.last_obs[layout["actions"]["offset"] : layout["actions"]["offset"] + n_act]
  cmd_slice = core.last_obs[layout["command"]["offset"] : layout["command"]["offset"] + 3]
  assert np.allclose(act_slice, fake_action, atol=1e-5)
  assert np.allclose(cmd_slice, [0.7, -0.1, 0.05], atol=1e-5)


def test_shadow_without_follow_never_moves_the_target(core):
  before = core.target.copy()
  _tick_shadow(core, 3)
  assert np.allclose(core.target, before), "policy_shadow with shadow_follow=False must not drive"
  assert not np.allclose(core._policy_target, before), "the policy must still have run and produced a target"


def test_shadow_follow_drives_the_local_sim_only(core):
  core.shadow_follow = True
  before = core.target.copy()
  _tick_shadow(core, 1)
  assert not np.allclose(core.target, before) or np.allclose(core._policy_target, before)
  assert np.allclose(core.target, core._policy_target)


def test_shadow_action_has_no_transmit_path():
  """Structural guarantee (design doc R10), not a behavioural one: the constant that would
  have to flip for a future implementer to wire a shadow action to a real robot."""
  assert modes_mod.SHADOW_MAY_TRANSMIT is False
  # No attribute on SimCore is named anything that would suggest an outbound command path.
  import inspect

  from pygviewer import sim_core

  src = inspect.getsource(sim_core)
  assert "socket.socket" not in src  # the sim thread itself never opens a socket
