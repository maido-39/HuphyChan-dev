"""P3: streaming jsonl.gz recorder and replayer.

Shape on disk (one file):
  * line 1: a plain JSON header (NOT a wire message) -
    ``{v, contract_hash, variant, base:{mode,height,ground,pivot_offset}, gains_source,
    env_toggles, bake_mjb_sha256, started_utc}``.  Everything a consumer needs to decide
    whether an overlay against another recording (or the live model) is even meaningful,
    without opening the model contract separately (R9/R11).
  * every line after that: one wire object exactly as ``schema.to_jsonl`` writes it -
    currently always ``JointState``, one per published snapshot while recording is on.

Written with ``gzip.open(..., "wt")`` and flushed after every line: append-and-flush, never
an in-memory list, so a 10 s recording does not move RSS (measured in the P3 verification,
see docs/121 section 9).
"""

from __future__ import annotations

import gzip
import json
import threading
import time
from pathlib import Path
from typing import Any

from .schema import JointState

RECORD_DIR = "/home/syaro/pyg_fea/pygviewer/records"


def header_from_core(core) -> dict[str, Any]:
  c = core.c
  return dict(
    v=1,
    contract_hash=c.contract_sha,
    variant=c.variant,
    base=dict(
      mode=core.base_mode,
      height=float(core.base_pos[2]),
      ground=core.ground,
      pivot_offset=[float(x) for x in core.pivot_offset],
    ),
    gains_source=core.gains_source,
    env_toggles=c.raw.get("env_toggles"),
    bake_mjb_sha256=c.raw.get("mjb_sha256"),
    started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
  )


class Recorder:
  """One open jsonl.gz file.  ``write_snapshot`` is safe to call from the sim thread hook -
  it never blocks on anything slower than a gzip buffer append, and never raises into the
  caller (a bad write must not kill the sim loop; it counts an error instead)."""

  def __init__(self, path: str | Path, header: dict[str, Any]):
    self.path = Path(path)
    self.path.parent.mkdir(parents=True, exist_ok=True)
    self._f = gzip.open(self.path, "wt")
    self._f.write(json.dumps(header, sort_keys=True) + "\n")
    self._f.flush()
    self._lock = threading.Lock()
    self.n_lines = 0
    self.errors = 0
    self._seq = 0
    self.header = header

  def write_message(self, msg: JointState) -> None:
    from .schema import to_jsonl

    with self._lock:
      if self._f is None:
        return
      try:
        self._f.write(to_jsonl(msg))
        self._f.flush()
        self.n_lines += 1
      except Exception:
        self.errors += 1

  def write_snapshot(self, snap: dict, contract_sha: str) -> None:
    """Build the canonical ``JointState`` from a ``SimCore`` snapshot dict and write it."""
    with self._lock:
      self._seq += 1
      seq = self._seq
    names = snap["act_names"]
    idx = [snap["joint_names"].index(n) for n in names]
    msg = JointState(
      t_ns=time.monotonic_ns(),
      seq=seq,
      src="sim",
      contract_hash=contract_sha,
      joint_names=names,
      q=[snap["q"][i] for i in idx],
      qd=[snap["qd"][i] for i in idx],
      tau_est=snap["tau"],
      target=snap["target"],
      ankle_derived=snap.get("ankle_derived"),
    )
    self.write_message(msg)

  def close(self) -> dict[str, Any]:
    with self._lock:
      if self._f is not None:
        self._f.close()
        self._f = None
    return dict(path=str(self.path), n_lines=self.n_lines, errors=self.errors)


class Replayer:
  """Loads a whole recording into memory (recordings in this project's test/dev scope are
  seconds long at control-tick rate, a few thousand lines - not the multi-hour case this
  would need streaming for) and drives ``file_replay`` mode from it.

  ``current_q(t_s)`` is monotonic-cursor: sim time only moves forward between calls, so this
  never re-scans from the start.  ``seek`` resets the cursor for scrubbing.
  """

  def __init__(self, path: str | Path, expected_contract_hash: str | None = None):
    self.path = Path(path)
    rows: list[dict] = []
    with gzip.open(self.path, "rt") as f:
      header_line = f.readline()
      self.header = json.loads(header_line)
      for line in f:
        line = line.strip()
        if not line:
          continue
        rows.append(json.loads(line))
    if not rows:
      raise ValueError(f"{self.path}: no messages after the header")
    self.rows = rows
    self.t0_ns = rows[0]["t_ns"]
    self.duration_s = (rows[-1]["t_ns"] - self.t0_ns) / 1e9
    if expected_contract_hash and self.header.get("contract_hash") != expected_contract_hash:
      raise ValueError(
        f"{self.path}: recorded contract_hash {str(self.header.get('contract_hash'))[:12]} "
        f"does not match the live model {expected_contract_hash[:12]} (R11); pass an "
        "explicit override only if you understand why."
      )
    self._cursor = 0
    self._t_ref: float | None = None
    self.speed = 1.0

  def start(self, sim_time_s: float) -> None:
    self._t_ref = sim_time_s
    self._cursor = 0

  def seek(self, frac: float) -> None:
    frac = max(0.0, min(1.0, frac))
    target_ns = self.t0_ns + frac * (self.rows[-1]["t_ns"] - self.t0_ns)
    lo, hi = 0, len(self.rows) - 1
    while lo < hi:
      mid = (lo + hi) // 2
      if self.rows[mid]["t_ns"] < target_ns:
        lo = mid + 1
      else:
        hi = mid
    self._cursor = lo

  def current_q(self, sim_time_s: float) -> dict[str, float | None] | None:
    """Advance the cursor to the newest row whose recorded time has arrived, and return its
    joint values by name.  ``None`` if playback has not started or the file is exhausted."""
    if self._t_ref is None:
      return None
    elapsed_ns = (sim_time_s - self._t_ref) * self.speed * 1e9
    target_ns = self.t0_ns + elapsed_ns
    while self._cursor + 1 < len(self.rows) and self.rows[self._cursor + 1]["t_ns"] <= target_ns:
      self._cursor += 1
    row = self.rows[self._cursor]
    if row.get("type") != "JointState":
      return None
    return dict(zip(row["joint_names"], row["q"]))

  def progress(self) -> dict:
    if self._t_ref is None:
      return dict(playing=False, cursor=0, n_rows=len(self.rows), duration_s=self.duration_s)
    return dict(
      playing=True,
      cursor=self._cursor,
      n_rows=len(self.rows),
      duration_s=self.duration_s,
      frac=self._cursor / max(len(self.rows) - 1, 1),
      speed=self.speed,
    )
