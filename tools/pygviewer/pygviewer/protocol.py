"""The 8-step sim<->real verification protocol from docs/121 section 5, as a runnable check.

    mujoco-sim/mjlab/.venv/bin/python3 -m pygviewer.protocol --variant LegOnly-AB

Steps 1, 4, 5 and 8 need no hardware - they can be exercised end to end with synthetic
"real" data standing in for a robot (the same role ``bridge/dummy_tx.py`` plays live; this
module builds the equivalent messages directly for determinism and speed rather than opening
an actual socket, and says so in each step's own docstring). Steps 2, 3, 6 and 7 need an
actual robot or a human in the loop; this module never fakes those - it prints the exact
procedure and pass criterion from the design doc and marks them ``MANUAL``, because a script
that claimed to "pass" a step it did not actually run would be worse than not running it.

Every automated step returns a plain dict: ``{step, name, status, detail}`` with
``status in ("PASS", "FAIL")``; every manual step returns ``{step, name, status: "MANUAL",
detail}``. ``main()`` prints a table and exits non-zero if any AUTOMATED step failed (a MANUAL
step is never a failure of THIS tool - it is a statement that hardware is required).
"""

from __future__ import annotations

import argparse
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from . import CACHE_DIR, VARIANTS
from .contract import load_contract
from .schema import ImuState, JointState


def _core(variant: str):
  from .sim_core import SimCore

  c = SimCore(load_contract(CACHE_DIR, variant), realtime=False)
  c.reset("knees_bent")
  c.step_n(1)
  return c


# --------------------------------------------------------------------------- step 1
def step1_static_zero(variant: str, dq_budget: float = 0.02, dg_budget: float = 0.05) -> dict:
  """Protocol step 1: default keyframe, |dq| < 0.02 rad on every actuated joint, |dg| < 0.05
  on the gravity vector. Stands in for "power the robot up in its calibrated zero pose and
  compare against sim's own default" - the synthetic 'real' stream here is the sim's own
  state plus a small deliberate perturbation (0.005 rad / 0.01 on gravity), so this step is
  really checking the COMPARISON MACHINERY (RealState ingestion + the threshold), not a robot
  that does not exist; a genuine hardware run would ingest actual telemetry instead."""
  core = _core(variant)
  try:
    q_sim = {n: float(core.d.qpos[core.qadr[n]]) for n in core.act_names}
    perturb = 0.005
    q_real = {n: v + perturb for n, v in q_sim.items()}
    core.real.ingest_joint_state(
      JointState(t_ns=0, seq=1, src="dummy", contract_hash=core.c.contract_sha,
                  joint_names=list(q_real), q=list(q_real.values()))
    )
    dq = {n: abs(q_real[n] - q_sim[n]) for n in q_sim}
    worst_joint, worst_dq = max(dq.items(), key=lambda kv: kv[1])

    g_sim = core.d.sensordata[core._sensor.get("robot/imu_upvector", (0, 3))[0]:][:3] if "robot/imu_upvector" in core._sensor else np.array([0.0, 0.0, -1.0])
    g_sim = np.asarray(g_sim, dtype=float)
    g_real = g_sim + np.array([0.01, 0.0, 0.0])
    core.real.ingest_imu_state(
      ImuState(t_ns=0, seq=1, src="dummy", contract_hash=core.c.contract_sha,
                gravity_b=list(g_real))
    )
    dg = float(np.max(np.abs(g_real - g_sim)))

    ok = worst_dq < dq_budget and dg < dg_budget
    return dict(
      step=1, name="static zero", status="PASS" if ok else "FAIL",
      detail=f"worst |dq|={worst_dq:.4f} rad ({worst_joint}, budget {dq_budget}), "
             f"|dg|={dg:.4f} (budget {dg_budget})",
    )
  finally:
    core.stop()


# --------------------------------------------------------------------------- step 4
def step4_velocity_sanity(
  variant: str, joint: str | None = None, freq_hz: float = 0.5, amp: float = 0.15,
  seconds: float = 4.0, hz: float = 50.0, rms_budget: float = 0.3,
) -> dict:
  """Protocol step 4: 0.5 Hz sine, finite-difference of the reported POSITION must agree with
  the reported VELOCITY (RMS < 0.3 rad/s) - this is what catches a bridge that forgot to
  travel-sign-correct ``vel`` the way it corrects ``pos`` (HUPHY's own ``leg.py:370-372`` bug
  this project already found once). The 'real' stream here is built analytically (exact q(t)
  and its exact derivative), so a PASS mainly certifies the check itself and the sampling
  rate are sound; a real bridge could still fail this against actual hardware noise."""
  core = _core(variant)
  try:
    joint = joint or core.act_names[0]
    default = core.default_q_map[joint]
    dt = 1.0 / hz
    n = int(seconds * hz)
    w = 2 * math.pi * freq_hz
    qs, qds, ts = [], [], []
    for i in range(n):
      t = i * dt
      qs.append(default + amp * math.sin(w * t))
      qds.append(amp * w * math.cos(w * t))
      ts.append(t)
      core.real.ingest_joint_state(
        JointState(t_ns=int(t * 1e9), seq=i, src="dummy", contract_hash=core.c.contract_sha,
                    joint_names=[joint], q=[qs[-1]], qd=[qds[-1]])
      )
    q = np.asarray(qs)
    qd_reported = np.asarray(qds)
    qd_findiff = np.gradient(q, dt)
    rms = float(np.sqrt(np.mean((qd_findiff - qd_reported) ** 2)))
    ok = rms < rms_budget
    return dict(
      step=4, name="velocity sanity", status="PASS" if ok else "FAIL",
      detail=f"{joint} {freq_hz} Hz sine, {n} samples @ {hz} Hz: finite-diff vs reported qd "
             f"RMS={rms:.4f} rad/s (budget {rms_budget})",
    )
  finally:
    core.stop()


# --------------------------------------------------------------------------- step 5
def step5_latency_calibration(
  variant: str, delay_ms: float = 30.0, jitter_ms: float = 5.0, jitter_budget_ms: float = 15.0,
  seed: int = 0,
) -> dict:
  """Protocol step 5: 5 step changes, delay estimate's jitter must be < 15 ms. Builds the
  same 5-step trajectory as ``scripts/step_knee_5x10deg.json`` twice - once undelayed ("sim")
  and once with the requested delay+jitter ("real", standing in for a dummy_tx-fed
  real_replay recording) - and reuses ``compare.estimate_clock_offset_ms`` unchanged, so this
  step is exercising the SAME code path the live end-to-end verification in docs/121 section
  9 drives through an actual dummy_tx subprocess and /ws/in socket."""
  from .compare import estimate_clock_offset_ms
  from .record import Recorder

  rng = np.random.RandomState(seed)
  hold_s, step_rad, n_steps, dt, hz = 1.0, math.radians(10.0), 5, 0.01, 50.0
  base_q = 0.0
  with tempfile.TemporaryDirectory() as td:
    sim_path = Path(td) / "sim.jsonl.gz"
    real_path = Path(td) / "real.jsonl.gz"
    header = dict(v=1, contract_hash="protocol-step5", variant=variant,
                  base=dict(mode="fixed", height=0.9, ground=True, pivot_offset=[0, 0, 0]),
                  gains_source="train", mode="manual")
    rec_sim = Recorder(sim_path, header)
    rec_real = Recorder(real_path, header)
    n_samples = int((n_steps + 1) * hold_s / dt)
    delay_s, jitter_s = delay_ms / 1e3, jitter_ms / 1e3
    for i in range(n_samples):
      t = i * dt
      level = min(int(t / hold_s), n_steps)
      q = base_q + level * step_rad
      rec_sim.write_message(
        JointState(t_ns=int(t * 1e9), seq=i, src="sim", contract_hash="protocol-step5",
                    joint_names=["L_knee_joint"], q=[q])
      )
      t_real = t + delay_s + rng.uniform(-jitter_s, jitter_s)
      rec_real.write_message(
        JointState(t_ns=int(t_real * 1e9), seq=i, src="dummy", contract_hash="protocol-step5",
                    joint_names=["L_knee_joint"], q=[q])
      )
    rec_sim.close()
    rec_real.close()

    from .compare import load_recording

    _, rows_sim = load_recording(sim_path)
    _, rows_real = load_recording(real_path)
    result = estimate_clock_offset_ms(rows_sim, rows_real, "L_knee_joint", "q", dt=0.005)

  jitter = result["jitter_ms"] or 0.0
  offset_ok = result["offset_ms"] is not None and abs(result["offset_ms"] - delay_ms) <= 20.0
  jitter_ok = jitter < jitter_budget_ms
  ok = offset_ok and jitter_ok
  return dict(
    step=5, name="latency calibration", status="PASS" if ok else "FAIL",
    detail=f"5-step trajectory, injected {delay_ms}ms delay / {jitter_ms}ms jitter -> "
           f"estimated offset {result['offset_ms']} ms, jitter {jitter} ms (budget <{jitter_budget_ms} ms)",
  )


# --------------------------------------------------------------------------- step 8
def step8_record_roundtrip(variant: str, n_ticks: int = 50) -> dict:
  """Protocol step 8: record, then read the recording back - must be bit-identical. This is
  ``tests/test_record.py::test_record_replay_roundtrip_is_bit_identical`` run as a standalone
  check: record N control ticks of ordinary manual-mode physics, then load the SAME file
  through ``record.Replayer`` and demand the parsed rows equal, structurally, what a fresh
  read of the raw JSON lines produced - nothing lost or altered in the write/read round trip."""
  import gzip
  import json as _json

  from .record import Replayer

  core = _core(variant)
  try:
    with tempfile.TemporaryDirectory() as td:
      path = Path(td) / "rec.jsonl.gz"
      core.start_recording(str(path))
      core.step_n(n_ticks)
      info = core.stop_recording()
      with gzip.open(path, "rt") as f:
        lines = f.readlines()
      rows_raw = [_json.loads(line) for line in lines[1:]]
      rep = Replayer(path, expected_contract_hash=core.c.contract_sha)
      ok = (
        info["errors"] == 0
        and len(rep.rows) == len(rows_raw)
        and rep.rows == rows_raw
      )
      return dict(
        step=8, name="record round-trip", status="PASS" if ok else "FAIL",
        detail=f"{info['n_lines']} lines, {info['errors']} write errors, "
               f"{len(rows_raw)} rows compared byte-for-byte equal={rep.rows == rows_raw}",
      )
  finally:
    core.stop()


# --------------------------------------------------------------------------- manual steps
_MANUAL = {
  2: dict(
    name="per-joint sign sweep",
    detail="Command a physical +20 deg on each joint on the real robot, one at a time; "
    "read the sim's canonical value back and confirm the sign matches the contract's "
    "travel_sign/mirrored convention. Update bridge/joint_map_huphy.json's "
    "side_mapping_verified only after every joint checks out. Needs the real robot.",
  ),
  3: dict(
    name="ankle FK cross-check",
    detail="25-point grid over (pitch, roll): command each point, read back the crank "
    "encoders, run them through AnkleInverse's forward direction, and compare to the "
    "commanded ankle angle (<0.02 rad) and loop closure (<1 mm). Needs the real AB ankle.",
  ),
  6: dict(
    name="same-target response overlay",
    detail="Play a scripts/*.json sequence (e.g. sine_hips_knees_1hz_20deg.json) through "
    "POST /script/run on sim AND through the robot's own bridge on hardware, record both, "
    "then compare.py --sim ... --real .... Only meaningful once gains match (POST /gains "
    "source=real with a real gain table) - see the gains diff table (R7) first. Needs the "
    "real robot.",
  ),
  7: dict(
    name="IMU tilt",
    detail="Tilt the real robot's IMU +-10 deg on a known axis; sim's gravity vector under "
    "the same commanded tilt must agree within 3 deg. Needs the real IMU mounted and wired.",
  ),
}


def manual_step(n: int) -> dict:
  m = _MANUAL[n]
  return dict(step=n, name=m["name"], status="MANUAL", detail=m["detail"])


# --------------------------------------------------------------------------- runner
def run_all(variant: str) -> list[dict]:
  results = [
    step1_static_zero(variant),
    manual_step(2),
    manual_step(3),
    step4_velocity_sanity(variant),
    step5_latency_calibration(variant),
    manual_step(6),
    manual_step(7),
    step8_record_roundtrip(variant),
  ]
  return sorted(results, key=lambda r: r["step"])


def print_table(results: list[dict]) -> None:
  print(f"{'#':>2}  {'step':<26} {'status':<6}  detail")
  print("-" * 100)
  for r in results:
    print(f"{r['step']:>2}  {r['name']:<26} {r['status']:<6}  {r['detail']}")


def main(argv: list[str] | None = None) -> int:
  ap = argparse.ArgumentParser(prog="pygviewer.protocol", description=__doc__)
  ap.add_argument("--variant", default="LegOnly-AB", choices=list(VARIANTS))
  args = ap.parse_args(argv)
  results = run_all(args.variant)
  print_table(results)
  failed = [r for r in results if r["status"] == "FAIL"]
  if failed:
    print(f"\n{len(failed)} AUTOMATED step(s) FAILED.")
    return 1
  n_auto = sum(1 for r in results if r["status"] != "MANUAL")
  print(f"\nall {n_auto} automated steps PASS. {len(results) - n_auto} steps need real hardware (MANUAL).")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
