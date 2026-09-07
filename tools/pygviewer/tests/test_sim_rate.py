"""Real-time and footprint: the viewer has to co-exist with a GPU training run.

Budget: >= 195 Hz of physics wall-clock (the contract's own rate is 200 Hz) and < 600 MB
resident, on the CPU, with no GPU touched.
"""

import os

import pytest

from pygviewer import CACHE_DIR
from pygviewer.contract import load_contract
from pygviewer.sim_core import SimCore

MIN_HZ = 195.0
SIM_RSS_BUDGET_MB = 400.0
"""How much resident memory ONE SimCore may add.

This used to be an absolute cap of 600 MB read from ``resource.getrusage(...).ru_maxrss``,
which is the PEAK since the process started and never comes down - so it measured the pytest
process's entire history rather than this sim's footprint. Once the suite passed ~600 tests it
reported 882 MB here no matter what SimCore did, and a green suite turned red with no change
to the viewer (2026-09-07). Switching to CURRENT resident size did not fix it either (731 MB):
inside a process that has already loaded 625 tests' worth of contracts and models, no absolute
number means anything.

What the budget in this module's docstring actually asks is "how much does the viewer's sim
cost", and that is the INCREASE across constructing and running one, which is independent of
whatever else the host process is carrying. The end-to-end number - the whole viewer process's
resident size - is reported live by ``GET /status`` as ``rss_mb`` and is the thing to watch on
the machine, not here."""


def _rss_mb() -> float:
  """CURRENT resident size of this process, in MB.

  Was ``resource.getrusage(...).ru_maxrss``, which is the PEAK since the process started and
  never comes down. That measures the pytest process's whole history, not this sim's
  footprint: once the suite grew past ~600 tests it read 882 MB here no matter what SimCore
  did, and the failure looked like a regression in the viewer (2026-09-07). Current RSS is
  what the budget in this module's docstring actually means - "the viewer stays under 600 MB
  while it runs".
  """
  with open("/proc/self/statm", encoding="ascii") as fh:
    pages = int(fh.read().split()[1])
  return pages * os.sysconf("SC_PAGE_SIZE") / (1024.0 * 1024.0)


@pytest.mark.parametrize("variant", ["LegOnly-AB", "LegOnly-RP"])
def test_realtime_and_footprint(variant):
  assert os.environ.get("CUDA_VISIBLE_DEVICES", "") == "", "run the tests CPU-only"
  rss_before = _rss_mb()
  core = SimCore(load_contract(CACHE_DIR, variant), realtime=True)
  try:
    core.run_blocking(5.0)
    s = core.snapshot()
    hz = s["rates"]["phys_hz"]
    grew = _rss_mb() - rss_before
    assert hz >= MIN_HZ, f"{variant}: physics only {hz:.1f} Hz (need {MIN_HZ})"
    assert s["rates"]["drops"] == 0, f"{variant}: dropped {s['rates']['drops']} substeps"
    assert grew < SIM_RSS_BUDGET_MB, (
      f"{variant}: one SimCore added {grew:.0f} MB resident (budget {SIM_RSS_BUDGET_MB})"
    )
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
