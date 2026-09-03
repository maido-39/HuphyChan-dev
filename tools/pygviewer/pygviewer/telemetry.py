"""P3: the receive-side telemetry buffer.

``RealState`` is the ONE place a value received from outside this process (over ``/ws/in``,
the HUPHY UDP bridge, or the dummy transmitter) lands before anything else reads it.  It is
latest-only per joint (R3: no history is kept beyond what the plot ring buffer separately
samples) and it is the thing that makes R3/R4/R5/R6/R9 checkable rather than aspirational:

  * staleness age and an rx-rate/jitter estimate (R5)
  * a seq-gap counter (R5: dropped frames are counted, never silently absorbed)
  * a moving-median clock offset between the sender's ``t_ns`` and this process's monotonic
    clock (R5), estimated the same way whether the sender is the dummy transmitter, the
    HUPHY bridge or a future real host
  * a ``|dq| > pi`` wrap flag per joint (R3: never auto-unwrapped)
  * a joint-range violation counter (R6: default window sanity, generalised to any sample)
  * a contract_hash mismatch counter (R11: the caller decides whether to refuse an overlay)

This module imports neither mjlab nor torch and never touches MjData - it only stores what
it was given and answers questions about it.  Thread-safety: one lock, short critical
sections, exactly the pattern ``SimCore`` already uses for its own snapshot.
"""

from __future__ import annotations

import math
import statistics
import threading
import time
from collections import deque
from typing import Any

from .schema import ImuState, JointState

MAX_AGE_WARN_S = 0.5
CLOCK_WINDOW = 200
RX_RATE_WINDOW = 100
SIGN_WINDOW_S = 2.0
SIGN_DEADBAND_RAD = 0.05
SIGN_RED_FRACTION = 0.5


class RealState:
  """Everything received from the outside world for one model variant."""

  def __init__(self, act_names: list[str], joint_ranges: dict[str, tuple[float, float]],
               contract_sha: str, range_margin_rad: float = 0.05):
    self.act_names = list(act_names)
    self.joint_ranges = dict(joint_ranges)
    self.contract_sha = contract_sha
    self.range_margin_rad = float(range_margin_rad)

    self._lock = threading.Lock()
    self.q: dict[str, float | None] = {n: None for n in act_names}
    self.qd: dict[str, float | None] = {n: None for n in act_names}
    self.tau: dict[str, float | None] = {n: None for n in act_names}
    self.target: dict[str, float | None] = {n: None for n in act_names}
    self.ankle_derived: dict[str, dict[str, float]] = {}
    self.imu: dict[str, Any] | None = None
    self.imu_age_ref: float | None = None

    self.rx_count = 0
    self.seq_gaps = 0
    self.last_seq: int | None = None
    self.contract_mismatches = 0
    self.wrap_events = 0
    self.range_violations: dict[str, int] = {n: 0 for n in act_names}
    self.warnings: deque[str] = deque(maxlen=20)
    self.last_error: str | None = None
    self.bridge_errors = 0
    self.bridge_last_error: str | None = None

    self._last_rx_mono: float | None = None
    self._rx_times: deque[float] = deque(maxlen=RX_RATE_WINDOW)
    self._clock_offsets_s: deque[float] = deque(maxlen=CLOCK_WINDOW)
    self._minus_one_streak: dict[str, int] = {}

    self._sign_hist: dict[str, deque[tuple[float, bool, bool]]] = {n: deque() for n in act_names}

  # -------------------------------------------------------------------- ingest
  def ingest_joint_state(self, msg: JointState) -> None:
    now = time.monotonic()
    with self._lock:
      self.rx_count += 1
      self._last_rx_mono = now
      self._rx_times.append(now)
      offset_s = (time.monotonic_ns() - msg.t_ns) / 1e9
      self._clock_offsets_s.append(offset_s)
      if self.last_seq is not None and msg.seq > self.last_seq + 1:
        self.seq_gaps += msg.seq - self.last_seq - 1
      if self.last_seq is None or msg.seq > self.last_seq:
        self.last_seq = msg.seq
      if msg.contract_hash and msg.contract_hash != self.contract_sha:
        self.contract_mismatches += 1

      qd_list = msg.qd or [None] * len(msg.joint_names)
      tau_list = msg.tau_est or [None] * len(msg.joint_names)
      tgt_list = msg.target or [None] * len(msg.joint_names)
      for n, q, qd, tau, tgt in zip(msg.joint_names, msg.q, qd_list, tau_list, tgt_list):
        if n not in self.q:
          continue  # the ws/in route already rejected unknown names; defensive only
        prev = self.q[n]
        if q is not None and prev is not None and abs(q - prev) > math.pi:
          self.wrap_events += 1
          self.warnings.append(f"{n}: |dq|>pi jump ({prev:+.3f} -> {q:+.3f} rad)")
        if q is not None and n in self.joint_ranges:
          lo, hi = self.joint_ranges[n]
          if q < lo - self.range_margin_rad or q > hi + self.range_margin_rad:
            self.range_violations[n] += 1
        self.q[n] = q
        self.qd[n] = qd
        self.tau[n] = tau
        self.target[n] = tgt
      if msg.ankle_derived:
        self.ankle_derived = msg.ankle_derived

  def ingest_imu_state(self, msg: ImuState) -> None:
    now = time.monotonic()
    with self._lock:
      self.rx_count += 1
      self._last_rx_mono = now
      self._rx_times.append(now)
      if msg.contract_hash and msg.contract_hash != self.contract_sha:
        self.contract_mismatches += 1
      self.imu = dict(
        quat_wxyz=msg.quat_wxyz,
        gyro_rad_s=msg.gyro_rad_s,
        acc_m_s2=msg.acc_m_s2,
        gravity_b=msg.gravity_b,
        age_s=msg.age_s,
      )
      self.imu_age_ref = now

  def note_bridge_error(self, msg: str) -> None:
    """A bridge (HUPHY UDP adapter, etc.) hit a hard failure - e.g. a (limb, motor) pair not
    in its explicit joint map.  Counted and surfaced in Status, never silently absorbed."""
    with self._lock:
      self.bridge_errors += 1
      self.bridge_last_error = msg
      self.warnings.append(f"bridge: {msg}")

  def note_sentinel(self, field: str, is_missing: bool) -> None:
    """Track "N in a row reported as missing" for a field the bridge translated from a
    HUPHY -1 sentinel.  Three in a row raises a warning (design doc R3/bridge contract)."""
    with self._lock:
      if is_missing:
        n = self._minus_one_streak.get(field, 0) + 1
        self._minus_one_streak[field] = n
        if n == 3:
          self.warnings.append(f"{field}: -1 (missing) three packets in a row")
      else:
        self._minus_one_streak[field] = 0

  # -------------------------------------------------------------------- read
  def age_s(self) -> float | None:
    with self._lock:
      if self._last_rx_mono is None:
        return None
      return time.monotonic() - self._last_rx_mono

  def rx_hz(self) -> float:
    with self._lock:
      if len(self._rx_times) < 2:
        return 0.0
      span = self._rx_times[-1] - self._rx_times[0]
      return (len(self._rx_times) - 1) / span if span > 0 else 0.0

  def clock_offset_ms(self) -> tuple[float | None, float | None]:
    """(median, jitter) of local-minus-sender offset in ms, over the recent window."""
    with self._lock:
      if not self._clock_offsets_s:
        return None, None
      vals = list(self._clock_offsets_s)
    med = statistics.median(vals) * 1e3
    jit = (statistics.pstdev(vals) * 1e3) if len(vals) > 1 else 0.0
    return med, jit

  def status(self) -> dict:
    # Each of these acquires and releases self._lock on its own - threading.Lock is not
    # reentrant, so this method must never hold the lock while calling one of them (that
    # was a real self-deadlock caught by test_record.py hanging the whole suite).
    age = self.age_s()
    off_ms, jit_ms = self.clock_offset_ms()
    hz = self.rx_hz()
    with self._lock:
      return dict(
        rx_count=self.rx_count,
        rx_hz=round(hz, 1),
        age_s=(round(age, 3) if age is not None else None),
        stale=(age is None or age > MAX_AGE_WARN_S),
        seq_gaps=self.seq_gaps,
        clock_offset_ms=(round(off_ms, 2) if off_ms is not None else None),
        clock_jitter_ms=(round(jit_ms, 2) if jit_ms is not None else None),
        jitter_grey=(jit_ms is not None and jit_ms > 15.0),
        contract_mismatches=self.contract_mismatches,
        wrap_events=self.wrap_events,
        range_violations={n: c for n, c in self.range_violations.items() if c},
        warnings=list(self.warnings),
        have_imu=self.imu is not None,
        bridge_errors=self.bridge_errors,
        bridge_last_error=self.bridge_last_error,
      )

  def snapshot_joints(self) -> dict[str, dict[str, float | None]]:
    with self._lock:
      return {
        n: dict(q=self.q[n], qd=self.qd[n], tau=self.tau[n], target=self.target[n])
        for n in self.act_names
      }

  # -------------------------------------------------------------------- sign sanity
  def sign_sanity_update(self, t: float, sim_q: dict[str, float], default_q: dict[str, float]) -> None:
    """Feed one (sim, real) sample per joint, gated by the deadband, into the rolling window.

    Called once per control tick from ``SimCore`` regardless of run mode: whenever real
    telemetry is present at all, this is a live cross-check that sim and the incoming real
    stream agree on which WAY a joint moved, not just roughly by how much.
    """
    with self._lock:
      q_real = dict(self.q)
    for n, qr in q_real.items():
      if qr is None or n not in sim_q or n not in default_q:
        continue
      dq_real = qr - default_q[n]
      dq_sim = sim_q[n] - default_q[n]
      if abs(dq_real) < SIGN_DEADBAND_RAD and abs(dq_sim) < SIGN_DEADBAND_RAD:
        continue
      agree = (dq_real >= 0) == (dq_sim >= 0)
      hist = self._sign_hist[n]
      hist.append((t, agree, True))
      while hist and t - hist[0][0] > SIGN_WINDOW_S:
        hist.popleft()

  def sign_sanity(self) -> dict[str, dict]:
    out = {}
    for n, hist in self._sign_hist.items():
      if not hist:
        continue
      n_total = len(hist)
      n_disagree = sum(1 for _, agree, _ in hist if not agree)
      frac = n_disagree / n_total if n_total else 0.0
      out[n] = dict(n=n_total, disagree_frac=round(frac, 3), red=frac > SIGN_RED_FRACTION)
    return out
