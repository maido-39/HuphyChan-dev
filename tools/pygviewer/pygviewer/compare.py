"""Offline sim<->real comparison (P4, design doc item 3): overlay two ``jsonl.gz`` recordings.

    mujoco-sim/mjlab/.venv/bin/python3 -m pygviewer.compare \
        --sim recordings/sim.jsonl.gz --real recordings/real.jsonl.gz --joints L_knee_joint

Does exactly what the design asks and nothing it does not:

  * loads both recordings (the plain-JSON header line + one ``JointState`` per line after it -
    ``record.py``'s own format, read directly rather than through ``Replayer`` because
    ``Replayer`` is built to drive a live ``SimCore`` and enforces the contract match as a
    hard error where this tool needs to make it a POLICY choice, see R11 below);
  * refuses two recordings from different model contracts unless ``--i-know`` is passed (R11);
  * warns (does not refuse) when the two headers' base mode/height/ground/gains_source differ,
    because an overlay is still informative, just not a same-conditions comparison (R9);
  * estimates the clock offset between the two streams from the cross-correlation of a
    signal's edges (R5) - by default the recorded ``q`` of the first shared joint, because a
    dummy-transmitter "real" stream sourced from HUPHY-style JointState never carries
    ``target`` (see ``bridge/dummy_tx.py``'s ``_send_ws``, which only sets ``q``);
  * writes one English-labelled PNG per requested joint to ``docs/img/`` overlaying
    target/q/tau, and prints latency/jitter statistics.

This script imports neither mjlab nor torch and does not touch a live ``SimCore`` - it is
pure post-hoc file analysis, safe to run any time regardless of what else is running.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DOCS_IMG_DIR = Path(__file__).resolve().parents[3] / "docs" / "img"


# --------------------------------------------------------------------------- loading
def load_recording(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
  """Header dict + list of ``JointState`` row dicts (as raw JSON, not pydantic - this tool
  reads files a live viewer may have written with a newer/older minor schema revision, and
  should not hard-fail on an extra or missing optional field)."""
  path = Path(path)
  opener = gzip.open if path.suffix == ".gz" else open
  with opener(path, "rt") as f:
    lines = f.readlines()
  if not lines:
    raise ValueError(f"{path}: empty file")
  header = json.loads(lines[0])
  rows = [json.loads(line) for line in lines[1:] if line.strip()]
  rows = [r for r in rows if r.get("type") == "JointState"]
  if not rows:
    raise ValueError(f"{path}: no JointState rows after the header")
  return header, rows


def _series_abs(rows: list[dict], joint: str, field: str) -> tuple[np.ndarray, np.ndarray]:
  """(ABSOLUTE ``t_ns``/1e9 seconds, values), skipping rows with no data for this joint/field.
  Not zeroed to the file's own start - use this (not ``_series``) for anything that compares
  the two files' TIMING, since re-zeroing each file independently throws away exactly the
  delay a clock-offset estimate exists to recover."""
  ts, vs = [], []
  for r in rows:
    names = r.get("joint_names") or []
    if joint not in names:
      continue
    vals = r.get(field)
    if not vals:
      continue
    v = vals[names.index(joint)]
    if v is None:
      continue
    ts.append(r["t_ns"] / 1e9)
    vs.append(v)
  return np.asarray(ts, dtype=float), np.asarray(vs, dtype=float)


def _series(rows: list[dict], joint: str, field: str) -> tuple[np.ndarray, np.ndarray]:
  """(t_seconds since THIS FILE's own first row, values) - for plotting only, where a small
  readable x-axis matters more than preserving an inter-file offset."""
  t0 = rows[0]["t_ns"]
  ts, vs = _series_abs(rows, joint, field)
  return (ts - t0 / 1e9), vs


# --------------------------------------------------------------------------- R11 / R9
class ContractMismatch(SystemExit):
  pass


def check_contracts(hdr_sim: dict, hdr_real: dict, i_know: bool) -> None:
  a, b = hdr_sim.get("contract_hash"), hdr_real.get("contract_hash")
  if a != b and not i_know:
    raise ContractMismatch(
      f"REFUSED (R11): sim recording contract_hash {str(a)[:12]} != real recording "
      f"{str(b)[:12]}. These are not necessarily the same robot/model. Pass --i-know only "
      "if you have verified that yourself."
    )


def condition_warnings(hdr_sim: dict, hdr_real: dict) -> list[str]:
  """R9: an overlay between different base modes/heights/ground/gains is not refused, but
  must never be silently presented as an apples-to-apples comparison."""
  warns = []
  bs, br = hdr_sim.get("base") or {}, hdr_real.get("base") or {}
  for key in ("mode", "height", "ground", "pivot_offset"):
    if bs.get(key) != br.get(key):
      warns.append(f"base.{key}: sim={bs.get(key)!r} vs real={br.get(key)!r}")
  if hdr_sim.get("gains_source") != hdr_real.get("gains_source"):
    warns.append(
      f"gains_source: sim={hdr_sim.get('gains_source')!r} vs real={hdr_real.get('gains_source')!r}"
    )
  if hdr_sim.get("mode") != hdr_real.get("mode"):
    warns.append(f"mode: sim={hdr_sim.get('mode')!r} vs real={hdr_real.get('mode')!r}")
  return warns


# --------------------------------------------------------------------------- R5
def estimate_clock_offset_ms(
  rows_sim: list[dict], rows_real: list[dict], joint: str, field: str = "q",
  dt: float = 0.01, n_segments: int = 4, max_lag_s: float = 0.3,
) -> dict[str, Any]:
  """Cross-correlate ``field`` of ``joint`` between the two streams on a common time grid.

  Uses ABSOLUTE ``t_ns`` (``_series_abs``, not the file-relative ``_series``): the offset this
  function reports is only meaningful when the two recordings' senders share a clock - which
  is exactly the verification procedure in docs/121 section 9 (record the script played
  directly, then record it again through the dummy transmitter's injected latency, from the
  SAME running process, so both files' ``t_ns`` come from the same monotonic clock). Positive
  result: the REAL stream lags the SIM stream by that many ms (matches what a positive
  ``--latency-ms`` on ``dummy_tx`` should produce). Fed two files from unrelated clocks, this
  number is meaningless - that is a property of the two recordings, not something this
  function can detect, so it is documented rather than guarded against.

  Segmenting the overlap window into ``n_segments`` and re-estimating per segment gives a
  jitter proxy (std across segments) without needing any new live instrumentation.
  """
  ts, vs = _series_abs(rows_sim, joint, field)
  tr, vr = _series_abs(rows_real, joint, field)
  if len(ts) < 2 or len(tr) < 2:
    raise ValueError(f"not enough {field!r} samples for {joint!r} in one of the two recordings")
  t0, t1 = max(ts[0], tr[0]), min(ts[-1], tr[-1])
  if t1 - t0 < 3 * dt:
    raise ValueError(f"{joint!r}/{field!r}: overlapping window too short ({t1 - t0:.3f}s)")
  grid = np.arange(t0, t1, dt)
  gs = np.interp(grid, ts, vs)
  gr = np.interp(grid, tr, vr)
  # Correlate EDGES (the gradient), not raw levels - design doc R5's "command edge cross-
  # correlation". A held level (a step signal's long flat plateaus, or the mean of a slowly
  # varying one) correlates with itself at every lag almost equally, which drowns out the
  # timing information; the derivative turns a step into a sharp, well-localised spike and a
  # sine into a phase-shifted cosine, both of which cross-correlate to a clean, unambiguous
  # peak at the true lag. Caught by protocol.py step 5 (a genuine step trajectory): the raw-
  # level version returned 0 ms against a 30 ms injected delay.
  gs_edge = np.gradient(gs, dt)
  gr_edge = np.gradient(gr, dt)

  max_lag_n = max(1, int(round(max_lag_s / dt)))

  def _offset_ms(g_ref: np.ndarray, g_test: np.ndarray) -> float:
    a = g_ref - g_ref.mean()
    b = g_test - g_test.mean()
    if np.allclose(a, 0) or np.allclose(b, 0):
      return float("nan")
    corr = np.correlate(b, a, mode="full")
    zero_k = len(a) - 1  # index of corr[] whose lag is 0
    # Restrict the search to +-max_lag_s: an unbounded 'full' search on a short/edge-sparse
    # segment can lock onto a totally unrelated distant peak (protocol.py step 5 with the
    # unbounded version once returned -965 ms for one segment of a signal with 5 ms of
    # injected jitter, because that segment's edge was weak relative to sidelobes far away).
    # A real transmission delay this tool is meant to catch is on the order of tens of ms,
    # never seconds, so bounding the search is a physically reasonable prior, not a fudge.
    lo, hi = max(0, zero_k - max_lag_n), min(len(corr), zero_k + max_lag_n + 1)
    lag = (lo + np.argmax(corr[lo:hi])) - zero_k  # b lags a by `lag` samples when positive
    return lag * dt * 1e3

  overall = _offset_ms(gs_edge, gr_edge)
  seg_len = len(grid) // n_segments
  per_segment = []
  # A segment with no edge in it (e.g. a flat dwell between two steps of a staircase) has
  # near-zero gradient energy and its cross-correlation peak is noise, not a timing estimate
  # - including it would let one uninformative segment dominate the jitter std with a huge,
  # meaningless outlier (caught by protocol.py step 5: an un-gated version of this reported
  # 430 ms of "jitter" against a signal with 5 ms of injected jitter). Only segments with at
  # least 20% of the WHOLE window's edge energy are counted.
  global_edge_rms = float(np.sqrt(np.mean(gs_edge**2))) if len(gs_edge) else 0.0
  if seg_len >= 10 and global_edge_rms > 0:
    for k in range(n_segments):
      sl = slice(k * seg_len, (k + 1) * seg_len)
      seg_rms = float(np.sqrt(np.mean(gs_edge[sl] ** 2)))
      if seg_rms < 0.2 * global_edge_rms:
        continue
      try:
        v = _offset_ms(gs_edge[sl], gr_edge[sl])
        if np.isfinite(v):
          per_segment.append(v)
      except Exception:
        pass
  jitter_ms = float(np.std(per_segment)) if len(per_segment) > 1 else None
  return dict(
    joint=joint, field=field, offset_ms=round(overall, 2) if np.isfinite(overall) else None,
    window_s=round(t1 - t0, 3), per_segment_ms=[round(v, 2) for v in per_segment],
    jitter_ms=(round(jitter_ms, 2) if jitter_ms is not None else None),
  )


# --------------------------------------------------------------------------- plotting
def plot_joint(
  rows_sim: list[dict], rows_real: list[dict], joint: str, out_dir: Path, tag: str,
) -> Path:
  fig, axes = plt.subplots(3, 1, figsize=(9, 7), sharex=True)
  for ax, field, label in zip(axes, ("target", "q", "tau_est"), ("target [rad]", "q [rad]", "tau [N*m]")):
    ts, vs = _series(rows_sim, joint, field)
    tr, vr = _series(rows_real, joint, field)
    if len(ts):
      ax.plot(ts, vs, "-", color="#4c78a8", label="sim", linewidth=1.5)
    if len(tr):
      ax.plot(tr, vr, "--", color="#f58518", label="real", linewidth=1.5)
    ax.set_ylabel(label)
    ax.grid(alpha=0.3)
    if ax.get_legend_handles_labels()[0]:
      ax.legend(loc="upper right", fontsize=8)
  axes[0].set_title(f"{joint} - sim vs real ({tag})")
  axes[-1].set_xlabel("time since recording start [s]")
  fig.tight_layout()
  out_dir.mkdir(parents=True, exist_ok=True)
  out_path = out_dir / f"compare_{tag}_{joint.replace('_joint', '')}.png"
  fig.savefig(out_path, dpi=130)
  plt.close(fig)
  return out_path


# --------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
  ap = argparse.ArgumentParser(prog="pygviewer.compare", description=__doc__)
  ap.add_argument("--sim", required=True, help="sim recording (.jsonl.gz)")
  ap.add_argument("--real", required=True, help="real (or dummy) recording (.jsonl.gz)")
  ap.add_argument("--joints", default=None, help="comma-separated; default = all joints common to both files")
  ap.add_argument("--offset-joint", default=None, help="joint used for the clock-offset estimate (default: first --joints entry)")
  ap.add_argument("--offset-field", default="q", choices=("q", "target", "tau_est"))
  ap.add_argument("--offset-dt", type=float, default=0.005, help="resample grid for the clock-offset cross-correlation [s]")
  ap.add_argument("--out-dir", default=str(DOCS_IMG_DIR))
  ap.add_argument("--tag", default=None, help="filename tag; default derived from --real's stem")
  ap.add_argument("--i-know", action="store_true", help="override the R11 contract_hash refusal")
  args = ap.parse_args(argv)

  hdr_sim, rows_sim = load_recording(args.sim)
  hdr_real, rows_real = load_recording(args.real)
  check_contracts(hdr_sim, hdr_real, args.i_know)

  warns = condition_warnings(hdr_sim, hdr_real)
  if warns:
    print("WARNING (R9): sim/real recording conditions differ - overlay is not apples-to-apples:")
    for w in warns:
      print(f"  - {w}")

  common = sorted(set(rows_sim[0]["joint_names"]) & set(rows_real[0]["joint_names"]))
  joints = args.joints.split(",") if args.joints else common
  unknown = [j for j in joints if j not in common]
  if unknown:
    print(f"WARNING: not present in both recordings, skipping: {unknown}", file=sys.stderr)
    joints = [j for j in joints if j in common]
  if not joints:
    raise SystemExit("no joints in common between the two recordings")

  offset_joint = args.offset_joint or joints[0]
  try:
    offset = estimate_clock_offset_ms(rows_sim, rows_real, offset_joint, args.offset_field, dt=args.offset_dt)
    print(
      f"clock offset estimate ({offset_joint}/{offset['field']}, {offset['window_s']}s window): "
      f"{offset['offset_ms']} ms  (per-segment: {offset['per_segment_ms']}, "
      f"jitter std {offset['jitter_ms']} ms)"
    )
  except ValueError as exc:
    offset = None
    print(f"clock offset estimate: SKIPPED - {exc}")

  tag = args.tag or Path(args.real).stem.replace(".jsonl", "")
  out_dir = Path(args.out_dir)
  paths = [plot_joint(rows_sim, rows_real, j, out_dir, tag) for j in joints]
  for p in paths:
    print(f"wrote {p}")

  print(
    f"sim: {len(rows_sim)} rows, contract {str(hdr_sim.get('contract_hash'))[:12]}, "
    f"mode {hdr_sim.get('mode')}"
  )
  print(
    f"real: {len(rows_real)} rows, contract {str(hdr_real.get('contract_hash'))[:12]}, "
    f"mode {hdr_real.get('mode')}"
  )
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
