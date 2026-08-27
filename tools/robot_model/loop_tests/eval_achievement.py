"""Command-achievement rate over the EVALUATOR's episodes, not one rollout.

The fc 121-command grid reported "achievement %" as mean achieved vx / commanded vx over a
settled dwell. This computes the same quantity from the evaluator's raw chunks, per episode, so
a median + p10/p90 spread is available across all 32 independent envs instead of one trajectory
(the single-rollout failure mode: see eval_raw_stats.py docstring). The evaluator writes the 32
episodes as 4 chunks of 8 (max_parallel_envs), so a scenario directory is merged before stats.

Achievement is the velocity PROJECTED ON THE COMMAND direction over |cmd| - the same quantity
stand_still_penalty's rel_floor thresholds, so a rate below 0.3 is exactly a "stalled" step.
For a zero command there is no direction to project on, so |v_xy| is reported instead (the
STANDING check: the fix must not create perpetual stepping at cmd = 0, the documented failure
mode the 0.3 deadband was guarding against).

  .venv/bin/python3 eval_achievement.py <scenario_dir> [<scenario_dir> ...]
  .venv/bin/python3 eval_achievement.py --table <root>      # A/B table over logs/eval/p1ab
"""

import glob
import os
import sys

import numpy as np

REL_FLOOR = 0.3  # stand_still_penalty.rel_floor - the "is this a stall" line


def load(scen_dir: str) -> dict:
  files = sorted(glob.glob(os.path.join(scen_dir, "raw_chunk_*.npz")))
  if not files:
    raise SystemExit(f"no raw_chunk_*.npz under {scen_dir}")
  v, fc, cmd, warm, dt = [], [], None, None, None
  for f in files:
    d = np.load(f, allow_pickle=True)
    warm = int(d["warmup_steps"])
    dt = float(d["time"][1] - d["time"][0])
    cmd = np.asarray(d["command"], float)[:2]
    v.append(np.asarray(d["root_lin_vel_b"], float)[warm:, :, :2])
    fc.append(np.asarray(d["foot_contact"]).astype(bool)[warm:])
  n = min(x.shape[0] for x in v)  # chunks can differ by a step
  vv = np.concatenate([x[:n] for x in v], axis=1)  # [T', E, 2]
  on = np.concatenate([x[:n] for x in fc], axis=1)  # [T', E, F]
  mag = float(np.linalg.norm(cmd))
  E = vv.shape[1]

  speed = np.linalg.norm(vv, axis=-1)
  if mag > 1e-6:
    unit = cmd / mag
    proj = vv @ unit
    ach = np.nanmean(proj, axis=0) / mag
    stall = np.nanmean((proj < REL_FLOOR * mag).astype(float), axis=0)
  else:
    ach = np.nanmean(speed, axis=0)  # residual drift speed, m/s
    stall = np.full(E, np.nan)
  err = np.nanmean(np.linalg.norm(vv - cmd, axis=-1), axis=0)

  steps = np.zeros(E)
  for e in range(E):
    for k in range(on.shape[2]):
      steps[e] += np.count_nonzero(np.diff(on[:, e, k].astype(int)) == 1)
  steps /= on.shape[0] * dt
  flight = np.nanmean((~on.any(axis=2)).astype(float), axis=0)
  # an episode that never terminated has finite velocity all the way through
  alive = np.isfinite(vv).all(axis=(0, 2))
  return dict(cmd=cmd, mag=mag, E=E, ach=ach, err=err, stall=stall, steps=steps,
              flight=flight, alive=alive, dt=dt, T=on.shape[0])


def q(a: np.ndarray) -> tuple:
  a = np.asarray(a, float)
  a = a[np.isfinite(a)]
  if not a.size:
    return (np.nan, np.nan, np.nan)
  return (float(np.median(a)), float(np.percentile(a, 10)), float(np.percentile(a, 90)))


def show(scen_dir: str) -> None:
  r = load(scen_dir)
  lbl = "achievement" if r["mag"] > 1e-6 else "drift |v| m/s"
  print(f"{scen_dir}")
  print(f"  cmd=({r['cmd'][0]:.2f},{r['cmd'][1]:.2f}) |cmd|={r['mag']:.2f}  "
        f"{r['E']} episodes x {r['T'] * r['dt']:.1f} s  alive {int(r['alive'].sum())}/{r['E']}")
  print(f"  {'metric':16s}{'median':>9s}{'p10':>9s}{'p90':>9s}")
  for name, key in ((lbl, "ach"), ("track_err m/s", "err"), ("stall_frac", "stall"),
                    ("touchdown /s", "steps"), ("flight_frac", "flight")):
    m, lo, hi = q(r[key])
    print(f"  {name:16s}{m:9.3f}{lo:9.3f}{hi:9.3f}")
  print()


def table(root: str) -> None:
  arms = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
  speeds = sorted({d.split("_", 1)[1] for a in arms
                   for d in os.listdir(os.path.join(root, a))}, key=float)
  print(f"{'cmd (m/s)':>10s} | " + " | ".join(f"{a:>34s}" for a in arms))
  print(f"{'':>10s} | " + " | ".join(
    f"{'ach':>8s}{'err':>9s}{'td/s':>8s}{'alive':>9s}" for _ in arms))
  print("-" * (12 + 37 * len(arms)))
  for s in speeds:
    cells = []
    for a in arms:
      d = os.path.join(root, a, f"lin_{s}")
      sc = glob.glob(os.path.join(d, "lin_vel_*"))
      if not sc:
        cells.append(f"{'-':>34s}"); continue
      r = load(sc[0])
      cells.append(f"{q(r['ach'])[0]:8.3f}{q(r['err'])[0]:9.3f}"
                   f"{q(r['steps'])[0]:8.2f}{int(r['alive'].sum()):5d}/{r['E']:<3d}")
    print(f"{s:>10s} | " + " | ".join(cells))
  print("\nach at cmd=0.0 is residual drift speed (m/s, lower better); elsewhere it is "
        "velocity along the command / |cmd|.")


if __name__ == "__main__":
  if sys.argv[1] == "--table":
    table(sys.argv[2])
  else:
    for p in sys.argv[1:]:
      show(p)
