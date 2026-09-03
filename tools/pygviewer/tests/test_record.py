"""P3 items 5/6/8: record -> replay is a bit-identical round trip, recording does not grow
RSS, and ``real_replay`` actually drives the sim joints from injected telemetry (direct
joints snapped, AB cranks PD-tracked) while forcing the base to ``fixed`` for safety."""

import gzip
import json
import os

import numpy as np
import pytest

from pygviewer import CACHE_DIR
from pygviewer.contract import load_contract
from pygviewer.record import Replayer
from pygviewer.schema import JointState
from pygviewer.sim_core import SimCore

VARIANT = "LegOnly-AB"


def _core():
  try:
    c = load_contract(CACHE_DIR, VARIANT)
  except FileNotFoundError:
    pytest.skip(f"no baked contract for {VARIANT}")
  core = SimCore(c, realtime=False)
  core.reset("knees_bent")
  return core


def _rss_mb() -> float:
  with open("/proc/self/statm") as f:
    return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1e6


def test_record_stop_refuses_when_not_recording():
  core = _core()
  with pytest.raises(RuntimeError):
    core.stop_recording()
  core.stop()


def test_record_start_refuses_a_second_recording(tmp_path):
  core = _core()
  core.start_recording(str(tmp_path / "a.jsonl.gz"))
  with pytest.raises(RuntimeError):
    core.start_recording(str(tmp_path / "b.jsonl.gz"))
  core.stop_recording()
  core.stop()


def test_record_replay_roundtrip_is_bit_identical(tmp_path):
  core = _core()
  path = tmp_path / "rec.jsonl.gz"
  core.start_recording(str(path))
  core.step_n(50)  # a handful of control ticks worth of physics substeps
  info = core.stop_recording()
  core.stop()

  assert info["n_lines"] > 0
  assert info["errors"] == 0
  assert os.path.exists(path)

  # Read the raw file directly - this is the ground truth for "bit identical".
  with gzip.open(path, "rt") as f:
    lines = f.readlines()
  assert len(lines) == info["n_lines"] + 1  # header + N JointState lines
  header = json.loads(lines[0])
  assert header["contract_hash"] == core.c.contract_sha
  rows = [json.loads(line) for line in lines[1:]]
  for row in rows:
    assert row["type"] == "JointState"
    assert row["contract_hash"] == core.c.contract_sha

  rep = Replayer(path, expected_contract_hash=core.c.contract_sha)
  assert rep.header == header
  assert len(rep.rows) == len(rows)
  assert rep.rows == rows  # exact structural equality: the round trip lost nothing


def test_replay_refuses_a_foreign_contract_hash(tmp_path):
  core = _core()
  path = tmp_path / "rec.jsonl.gz"
  core.start_recording(str(path))
  core.step_n(10)
  core.stop_recording()
  core.stop()
  with pytest.raises(ValueError, match="contract_hash"):
    Replayer(path, expected_contract_hash="0" * 64)


def test_recording_ten_seconds_does_not_grow_rss(tmp_path):
  core = _core()
  path = tmp_path / "ten_s.jsonl.gz"
  core.start_recording(str(path))
  before = _rss_mb()
  n_steps = int(10.0 / core.dt)  # 10 s of physics at the model's own timestep
  core.step_n(n_steps)
  after = _rss_mb()
  info = core.stop_recording()
  core.stop()
  assert info["n_lines"] > 0
  growth = after - before
  assert growth < 20.0, f"RSS grew {growth:.1f} MB over a 10 s recording ({info['n_lines']} lines)"


def test_real_replay_snaps_direct_joints_exactly():
  """The strong, exact guarantee (design item 6): hips/knee (everything but an AB crank)
  are kinematically snapped to the received value, every control tick, to 1e-6 rad."""
  core = _core()
  core.set_base(mode="free")
  core.submit({"op": "mode", "value": "real_replay"})
  core.step_n(core.decimation)
  assert core.mode == "real_replay"
  assert core.base_mode == "fixed"  # forced by the mode switch, not a leftover default

  targets = {n: core.default_q_map[n] + 0.05 for n in core.act_names}
  msg = JointState(t_ns=1, seq=1, src="dummy", joint_names=list(targets), q=list(targets.values()))
  core.real.ingest_joint_state(msg)
  core.step_n(core.decimation * 5)

  for i, n in enumerate(core.act_names):
    if "_crank_" not in n:
      q = float(core.d.qpos[core.a_q[i]])
      assert q == pytest.approx(targets[n], abs=1e-6), f"{n} (direct-drive)"
  core.stop()


def test_real_replay_routes_received_values_into_the_crank_pd_target():
  """The crank is PD-tracked, not snapped (a snap tears the closed loop open - module
  docstring). This checks the PLUMBING that item 6 actually specifies: a received crank
  value becomes ``self.target`` for that joint. Whether the PD then reaches it is a separate,
  load-dependent question - with the base forced ``fixed`` (item 6's safety rule) the whole
  leg hangs off the hip with its own weight resting on the ankle mechanism, and this
  contract's crank Kp is "the physical anchor value, not a free knob" (bake.py), so it is
  NOT retuned to force convergence against that load; see docs/121 section 9 for the
  measurement. A mechanically-VALID (non-independent) crank pair is used, via the same
  ankle_inverse the UI/policy use - two raw crank targets picked independently of the loop's
  own geometry can be infeasible and jam, which is a property of the mechanism, not a bug."""
  core = _core()
  core.set_base(mode="fixed")  # settle once, in the pose real_replay will force anyway
  core.submit({"op": "mode", "value": "manual"})
  core.step_n(core.decimation)
  core.step_n(200)  # let the post-reset loop-closure transient settle BEFORE commanding
  (pl, ph), (rl, rh) = core.ankle_inverse.bounds()
  a, b = core.ankle_inverse("L", 0.5 * (pl + ph) + 0.03, 0.5 * (rl + rh))

  core.submit({"op": "mode", "value": "real_replay"})
  core.step_n(core.decimation)
  msg = JointState(
    t_ns=1, seq=1, src="dummy",
    joint_names=["L_crank_A_joint", "L_crank_B_joint"], q=[a, b],
  )
  core.real.ingest_joint_state(msg)
  core.step_n(core.decimation)  # one control tick is enough to route the target

  iA = core.act_names.index("L_crank_A_joint")
  iB = core.act_names.index("L_crank_B_joint")
  assert core.target[iA] == pytest.approx(a, abs=1e-6)
  assert core.target[iB] == pytest.approx(b, abs=1e-6)
  core.stop()


def test_real_replay_with_no_telemetry_is_identical_to_manual_mode():
  """Regression test for the exact bug this file caught: with nothing received at all,
  entering real_replay must be numerically INDISTINGUISHABLE from staying in ``manual`` for
  every direct-drive joint - both dispatch to the identical ordinary-PD code path (item 6:
  "no data" holds default, never free-floats). Before the fix, ``_substep`` zeroed torque
  for every direct-drive index whenever the MODE was a replay mode, regardless of whether
  that specific joint had fresh data - so the two paths would have diverged immediately.

  This is a DIFFERENTIAL test (identical starting qpos/qvel/target, two code paths, compare
  trajectories) rather than an absolute "it should not move" test: this model's serial
  hip/knee chain is still gently damping a slow mode many seconds after reset (confirmed
  independently - even a joint on the untouched right leg keeps drifting for several more
  seconds), so there is no clean "at rest" baseline to compare an absolute tolerance against.
  The two code paths ARE, by construction, required to compute bit-identical dynamics from
  the same state - that is what this checks, at 1e-9, well below floating-point noise."""
  core = _core()
  core.set_base(mode="fixed")
  core._apply_cmd({"op": "mode", "value": "manual"})
  core.step_n(400)
  qpos0, qvel0, target0 = core.d.qpos.copy(), core.d.qvel.copy(), core.target.copy()

  core.step_n(core.decimation * 20)
  manual_traj = core.d.qpos.copy()

  core.d.qpos[:], core.d.qvel[:], core.target[:] = qpos0, qvel0, target0
  core._apply_cmd({"op": "mode", "value": "real_replay"})  # base already fixed -> no snap
  core.step_n(core.decimation * 20)
  replay_traj = core.d.qpos.copy()

  assert np.allclose(manual_traj, replay_traj, atol=1e-9), "real_replay with no data diverged from manual"
  core.stop()


def test_real_replay_does_not_couple_across_legs():
  """One joint on the LEFT leg reports a step change; a joint on the RIGHT leg must be
  UNAFFECTED. With the base welded (fixed, immovable), the two legs are independent
  kinematic trees hanging off a static frame - there is no physical path for torquing
  L_hip_pitch to move anything on the R side (unlike a same-leg neighbour, which DOES see
  real gravitational coupling through the shared thigh/shank link - see the plumbing test
  above for what a same-leg joint is checked for instead).

  Differential again, for the same reason as the test above: compare the R-side trajectory
  WITH vs WITHOUT the L-side command, from an identical restored starting state, rather than
  asserting an absolute "did not move" against a baseline that is itself still settling."""
  core = _core()
  core.set_base(mode="fixed")
  core._apply_cmd({"op": "mode", "value": "manual"})
  core.step_n(400)
  qpos0, qvel0, target0 = core.d.qpos.copy(), core.d.qvel.copy(), core.target.copy()
  core._apply_cmd({"op": "mode", "value": "real_replay"})

  core.d.qpos[:], core.d.qvel[:], core.target[:] = qpos0, qvel0, target0
  core.step_n(core.decimation * 20)
  r_no_data = {n: float(core.d.qpos[core.a_q[i]]) for i, n in enumerate(core.act_names) if n.startswith("R_")}

  core.d.qpos[:], core.d.qvel[:], core.target[:] = qpos0, qvel0, target0
  l_i = core.act_names.index("L_hip_pitch_joint")
  l_before = float(qpos0[core.a_q[l_i]])
  step = 0.1
  msg = JointState(t_ns=1, seq=1, joint_names=["L_hip_pitch_joint"], q=[l_before + step])
  core.real.ingest_joint_state(msg)
  core.step_n(core.decimation * 20)

  assert float(core.d.qpos[core.a_q[l_i]]) == pytest.approx(l_before + step, abs=1e-6)
  for i, n in enumerate(core.act_names):
    if n.startswith("R_") and "_crank_" not in n:
      q = float(core.d.qpos[core.a_q[i]])
      assert q == pytest.approx(r_no_data[n], abs=1e-4), f"{n} moved from a LEFT-leg command"
  core.stop()
