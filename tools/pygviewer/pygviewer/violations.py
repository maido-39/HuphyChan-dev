"""A2 (2026-09-04, plan ``optimized-leaping-hamster.md``): ONE shared ROM/torque violation
record log, threaded through every point in this process that clamps or refuses a joint
value against a limit -

  * ``side="recv"``        - ``telemetry.py``'s ``RealState.ingest_joint_state`` (a received
                              ``q`` outside the joint's contract range)
  * ``side="recv_torque"`` - the same ingest path, when a received ``tau_est`` exceeds the
                              contract's effort limit
  * ``side="sim_actuator"``- ``sim_core.py``'s ``_tn_clamp`` (the measured T-N curve
                              saturating the PD torque before it ever reaches
                              ``qfrc_applied`` - a torque limit hit INSIDE this process, not
                              received from outside it)
  * ``side="send"``        - ``bridge/tx_client.py``'s pre-send ``safe_clip`` and
                              ``pygviewer/tx.py``'s mode-gate refusal, plus a rejected
                              NaN/inf ``POST /target``/``/ankle`` request

This is deliberately a SEPARATE structure from ``telemetry.py``'s own ``range_violations``
(per-joint count only) and ``sim_core.py``'s ``replay_clamp`` (``clamped_now``/
``clamp_count``) - those stay exactly as they are (the dashboard and existing tests already
read them) - this module answers the different question those were never designed to answer:
"where, which joint, what value, against what limit, when" - for ``GET /violations`` and the
dashboard's red panel. Every one of those older counters records into this log TOO wherever
this task modifies its call site, so a client never has to reconcile more than one source of
truth for "did a violation just happen".

Thread-safety: one lock, short critical sections - the same pattern ``telemetry.RealState``
already uses, because this is written from the sim thread (recv/recv_torque/sim_actuator) and
from other threads calling into ``TxState``/the API layer's exception handler (send/reject).
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Any

MAX_RECORDS = 200
"""Ring buffer size across ALL sides combined - 200 most recent records. At 50 Hz telemetry
with every joint failing every tick this is only a few seconds of raw history, by design
(item 6 of the task): the per-(side, joint) cumulative COUNT in ``counts_by_joint()`` never
thins out even after its own individual records have aged out of the ring, so "how often has
this joint been over limit, ever" survives independently of "the last N samples"."""


class ViolationLog:
  """One shared instance per ``SimCore`` process (``SimCore.violations``), passed into
  ``RealState``/``TxState`` at construction so every side records into the SAME ring buffer
  and the SAME per-(side, joint) cumulative counters."""

  def __init__(self, max_records: int = MAX_RECORDS):
    self._lock = threading.Lock()
    self._records: deque[dict[str, Any]] = deque(maxlen=max_records)
    self._counts: dict[tuple[str, str], int] = {}
    self._rate_last: dict[tuple[str, str], float] = {}
    self._seq = 0

  def record(
    self,
    *,
    side: str,
    joint: str,
    value: float | None,
    limit_lo: float | None = None,
    limit_hi: float | None = None,
    src: str | None = None,
    extra: dict[str, Any] | None = None,
    rate_limit_s: float | None = None,
  ) -> dict[str, Any] | None:
    """Append one violation record and bump its cumulative (side, joint) count.

    ``rate_limit_s``, when given, suppresses a new RECORD for the same (side, joint) pair
    inside that window - ``sim_actuator``, called every substep at 200 Hz, would otherwise
    fill the whole ring buffer with one joint's saturation in well under a second. The
    cumulative COUNT still increments on every call regardless of the rate limit, so "how
    often" is never lost even though the individual-sample ring thins itself out. Returns the
    stored record (a copy), or ``None`` if this call only bumped the count (rate-limited).

    ``value``/``limit_lo``/``limit_hi`` may be ``None`` (e.g. a rejected NaN/inf request has
    no finite offending value to report) - never NaN/inf themselves, since these records are
    served as JSON (``JSONResponse``'s ``allow_nan=False``, same rule ``api.py``'s own 422
    handler already follows for exactly this reason).
    """
    now = time.monotonic()
    key = (side, joint)
    over_by = None
    if (
      value is not None
      and limit_lo is not None
      and limit_hi is not None
      and math.isfinite(value)
    ):
      over_by = max(limit_lo - value, value - limit_hi, 0.0)
    with self._lock:
      self._counts[key] = self._counts.get(key, 0) + 1
      if rate_limit_s is not None:
        last = self._rate_last.get(key)
        if last is not None and (now - last) < rate_limit_s:
          return None
      self._rate_last[key] = now
      self._seq += 1
      rec: dict[str, Any] = dict(
        seq=self._seq,
        t_mono=now,
        side=side,
        joint=joint,
        value=value,
        limit_lo=limit_lo,
        limit_hi=limit_hi,
        over_by=over_by,
        src=src,
      )
      if extra:
        rec.update(extra)
      self._records.append(rec)
      return dict(rec)

  def list(self, limit: int | None = None, side: str | None = None) -> list[dict[str, Any]]:
    """Most recent records first constructed, oldest-to-newest (matches the ring buffer's own
    order) - copies, so a caller mutating the result (e.g. adding ``age_s``) never corrupts
    what is actually stored."""
    with self._lock:
      recs = [dict(r) for r in self._records]
    if side is not None:
      recs = [r for r in recs if r["side"] == side]
    if limit is not None:
      recs = recs[-limit:]
    return recs

  def counts_by_joint(self) -> dict[str, dict[str, int]]:
    """``{joint: {side: count, ..., "total": n}}`` across every side that has ever recorded
    for that joint - survives the ring buffer's own 200-record cap (see the module
    docstring)."""
    with self._lock:
      items = dict(self._counts)
    out: dict[str, dict[str, int]] = {}
    for (side, joint), c in items.items():
      row = out.setdefault(joint, {"total": 0})
      row[side] = row.get(side, 0) + c
      row["total"] += c
    return out

  def last(self) -> dict[str, Any] | None:
    with self._lock:
      return dict(self._records[-1]) if self._records else None

  def total_count(self, side: str | None = None) -> int:
    with self._lock:
      if side is None:
        return sum(self._counts.values())
      return sum(c for (s, _j), c in self._counts.items() if s == side)

  def summary(self) -> dict[str, Any]:
    """The ``Status.telemetry`` shape (item 4): total count, per-joint cumulative counts,
    and the single most recent record - never the full ring buffer (``GET /violations`` is
    the place for that)."""
    return dict(total=self.total_count(), by_joint=self.counts_by_joint(), last=self.last())

  def clear(self) -> None:
    """Drops every record and every cumulative count. ``seq`` is deliberately NOT reset - a
    client that has already seen ``seq`` N must never see a smaller ``seq`` after a clear
    (the same "counters only ever go up, or are explicitly reset together" spirit as
    ``RealState.rx_count``)."""
    with self._lock:
      self._records.clear()
      self._counts.clear()
      self._rate_last.clear()
