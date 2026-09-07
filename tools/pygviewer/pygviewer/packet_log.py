"""Packet-level debug log of everything this process puts on, and takes off, the wire.

2026-09-07, user: "시뮬로는 검증이 안되는게 너무 많아. 입/출력을 패킷 / debug 레벨로
로깅하고 분석해."

Two joint movements happened on the bench today that nobody could explain afterwards
(docs/127 section 8). The reason they could not be explained is that NOTHING kept a record of
what was actually sent: ``/tx/status`` reports ``last_sent_target``, which is the newest value
only, and it is wiped whenever the client is rebuilt. By the time anyone asks "what did we
command at that moment", the evidence is gone. Every diagnosis in this session has come from
reading real bytes; this makes those bytes survive.

Design notes, all of them consequences of how the previous logs failed:

* **One line per packet, JSONL, append-only.** Not a summary, not a rate - the individual
  packet is the unit that matters, because the question is always "which one carried the bad
  value". Parsable by anything without a schema.
* **Every line carries the measured pose alongside the command.** A command without the state
  it was computed against cannot be judged after the fact: "target 0 deg" is correct or a
  disaster depending on where the joint actually was.
* **Monotonic AND wall clock.** Monotonic to order events within a run, wall clock to line up
  against the robot's own log on the other machine.
* **Bounded.** 50 Hz of packets is ~4 MB/hour; the file rotates so an all-day session cannot
  fill the disk, and the rotation keeps one previous file so a rollover mid-incident does not
  lose the evidence.
* **Off unless asked for.** Enabled by ``PYG_TX_LOG=<path>``; when unset this class is never
  constructed and the send path is untouched.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

DEFAULT_MAX_BYTES = 64 * 1024 * 1024
"""Rotate at 64 MB - about 16 hours of 50 Hz transmission. One previous file is kept."""


class PacketLog:
  """Append-only JSONL log with size rotation. Never raises into the caller.

  A logger that can take the control path down with it is worse than no logger, so every
  write is wrapped: a full disk, a deleted directory or a permissions change costs the log,
  never the robot.
  """

  def __init__(self, path: str | os.PathLike, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    self.path = Path(path)
    self.max_bytes = int(max_bytes)
    self._lock = threading.Lock()
    self._fh = None
    self.write_errors = 0
    self.last_error: str | None = None
    self.lines = 0
    self._open()

  def _open(self) -> None:
    try:
      self.path.parent.mkdir(parents=True, exist_ok=True)
      self._fh = self.path.open("a", buffering=1, encoding="utf-8")   # line buffered
    except OSError as e:
      self._fh = None
      self.write_errors += 1
      self.last_error = f"open failed: {e}"

  def _rotate_if_needed(self) -> None:
    if self._fh is None:
      return
    try:
      if self._fh.tell() < self.max_bytes:
        return
      self._fh.close()
      prev = self.path.with_suffix(self.path.suffix + ".1")
      if prev.exists():
        prev.unlink()
      self.path.rename(prev)
    except OSError as e:
      self.write_errors += 1
      self.last_error = f"rotate failed: {e}"
    self._open()

  def write(self, kind: str, payload: dict) -> None:
    """One event. ``kind`` says which direction and which stage, so a reader can filter
    without guessing at the shape of the rest of the line."""
    rec = {
      "t_mono": round(time.monotonic(), 6),
      "t_wall": round(time.time(), 6),
      "kind": kind,
      **payload,
    }
    with self._lock:
      if self._fh is None:
        self._open()
        if self._fh is None:
          return
      try:
        self._fh.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.lines += 1
      except (OSError, ValueError, TypeError) as e:
        self.write_errors += 1
        self.last_error = f"write failed: {e}"
        return
      self._rotate_if_needed()

  def status(self) -> dict:
    return {
      "path": str(self.path),
      "lines": self.lines,
      "write_errors": self.write_errors,
      "last_error": self.last_error,
    }

  def close(self) -> None:
    with self._lock:
      if self._fh is not None:
        try:
          self._fh.close()
        except OSError:
          pass
        self._fh = None


def from_env(var: str = "PYG_TX_LOG") -> PacketLog | None:
  """A log only when one was asked for. Returns ``None`` otherwise, and the caller's send
  path stays exactly as it was."""
  raw = (os.environ.get(var) or "").strip()
  if not raw:
    return None
  try:
    return PacketLog(raw)
  except Exception:      # a logger must never prevent the process from starting
    return None
