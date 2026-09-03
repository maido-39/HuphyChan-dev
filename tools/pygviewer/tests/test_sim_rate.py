"""Real-time and footprint: the viewer has to co-exist with a GPU training run.

Budget: >= 195 Hz of physics wall-clock (the contract's own rate is 200 Hz) and < 600 MB
resident, on the CPU, with no GPU touched.
"""

import os
import resource

import pytest

from pygviewer import CACHE_DIR
from pygviewer.contract import load_contract
from pygviewer.sim_core import SimCore

MIN_HZ = 195.0
MAX_RSS_MB = 600.0


@pytest.mark.parametrize("variant", ["LegOnly-AB", "LegOnly-RP"])
def test_realtime_and_footprint(variant):
  assert os.environ.get("CUDA_VISIBLE_DEVICES", "") == "", "run the tests CPU-only"
  core = SimCore(load_contract(CACHE_DIR, variant), realtime=True)
  try:
    core.run_blocking(5.0)
    s = core.snapshot()
    hz = s["rates"]["phys_hz"]
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    assert hz >= MIN_HZ, f"{variant}: physics only {hz:.1f} Hz (need {MIN_HZ})"
    assert s["rates"]["drops"] == 0, f"{variant}: dropped {s['rates']['drops']} substeps"
    assert rss < MAX_RSS_MB, f"{variant}: RSS {rss:.0f} MB (cap {MAX_RSS_MB})"
    assert s["t"] == pytest.approx(5.0, abs=0.2), "sim clock left the wall clock"
  finally:
    core.stop()


def test_snapshot_is_latest_only_and_does_not_accumulate():
  """A long run must not grow the snapshot or the command queue."""
  core = SimCore(load_contract(CACHE_DIR, "LegOnly-AB"), realtime=False)
  try:
    for _ in range(50):
      core.submit({"op": "target", "values": {"L_knee_joint": 0.4}})
    core.step_n(400)
    assert len(core._cmds) == 0
    s1 = core.snapshot()
    core.step_n(400)
    s2 = core.snapshot()
    assert set(s1) == set(s2)
    assert len(s2["q"]) == core.c.raw["n_dof"]
  finally:
    core.stop()


def test_control_cadence_survives_single_substep_calls():
  """``step_n(1)`` in a loop must still tick the controller at the decimation rate.

  With a loop-local substep counter it did not: every call restarted the phase, so the
  policy ran at 200 Hz instead of the trainer's 50 Hz.  Nothing looked broken - the robot
  still stood and still walked - it just walked 0.12 m/s slower than the same checkpoint in
  mjlab.  This pins the phase.
  """
  core = SimCore(load_contract(CACHE_DIR, "LegOnly-AB"), realtime=False)
  try:
    ticks = {"n": 0}
    real_drain = core._drain

    def counting_drain():
      ticks["n"] += 1
      real_drain()

    core._drain = counting_drain
    for _ in range(400):
      core.step_n(1)
    assert ticks["n"] == 400 // core.decimation, (
      f"controller ticked {ticks['n']} times in 400 substeps; expected "
      f"{400 // core.decimation} at decimation {core.decimation}"
    )
  finally:
    core.stop()


def test_step_n_batched_and_single_agree():
  """The same number of substeps must be the same trajectory either way."""
  import numpy as np

  out = []
  for chunk in (1, 40):
    c = SimCore(load_contract(CACHE_DIR, "LegOnly-AB"), realtime=False)
    try:
      c.set_base(mode="fixed", pos=[0.0, 0.0, 0.95])
      c.reset("knees_bent")
      c.set_target({"L_knee_joint": c.c.default_q("L_knee_joint") + 0.3})
      n = 0
      while n < 400:
        c.step_n(chunk)
        n += chunk
      out.append(c.d.qpos.copy())
    finally:
      c.stop()
  assert np.allclose(out[0], out[1], atol=1e-12), "stepping granularity changed the result"
