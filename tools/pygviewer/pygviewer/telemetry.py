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

from .bridge.motor_fault import (
  FAULT_BIT_NAMES,
  FAULT_BIT_SIMPLE_KO,
  named_fault_bits,
)
from .schema import ImuState, JointState, PolicyIO
from .violations import ViolationLog

MAX_AGE_WARN_S = 0.5
CLOCK_WINDOW = 200
RX_RATE_WINDOW = 100
SIGN_WINDOW_S = 2.0
SIGN_DEADBAND_RAD = 0.05
SIGN_RED_FRACTION = 0.5

# Motor health task (2026-09-04): per-joint ok/warn/dead thresholds. "our age" is this
# process's own reception clock (time since RealState last saw ANY field for that specific
# joint, updated in ingest_joint_state below) - the one signal available even when a sender
# carries no DIAG fields at all (today's bench_telemetry.py). HEALTH_DEAD_MISS turns HUPHY's
# own "miss" counter (consecutive no-response cycles) into the dead threshold: the task
# brief's "ack=0 연속" (consecutive ack=0) IS exactly what `miss` already counts, so a single
# missed cycle is a WARN (see RealState.health()) and only a sustained run of them is DEAD -
# a documented judgement call, not a value HUPHY or the task brief pins down as a number.
HEALTH_OK_AGE_S = 0.2
HEALTH_DEAD_AGE_S = 1.0
HEALTH_DEAD_MISS = 5
HEALTH_DEFAULT_TEMP_LIMIT_C = 60.0


class RealState:
  """Everything received from the outside world for one model variant."""

  def __init__(self, act_names: list[str], joint_ranges: dict[str, tuple[float, float]],
               contract_sha: str, range_margin_rad: float = 0.05,
               violations: ViolationLog | None = None,
               effort_limits: dict[str, float] | None = None):
    self.act_names = list(act_names)
    self.joint_ranges = dict(joint_ranges)
    self.contract_sha = contract_sha
    self.range_margin_rad = float(range_margin_rad)
    # A2 (2026-09-04): the shared violation record log (see violations.py's module
    # docstring) - optional so RealState stays constructible on its own (as it always has
    # been) for a caller/test that has no use for the record side of things; SimCore always
    # passes one. `effort_limits` (contract `gains[name]["effort"]`, N*m) is what makes a
    # RECEIVED tau_est checkable at all - RealState otherwise has no notion of a torque limit.
    self.violations = violations
    self.effort_limits = dict(effort_limits) if effort_limits else {}

    self._lock = threading.Lock()
    self.q: dict[str, float | None] = {n: None for n in act_names}
    self.qd: dict[str, float | None] = {n: None for n in act_names}
    self.tau: dict[str, float | None] = {n: None for n in act_names}
    self.target: dict[str, float | None] = {n: None for n in act_names}
    # Motor health task (2026-09-04): the robot's OWN self-reported diagnostics, per joint -
    # None means "never reported", not "zero". `_has_diag` is sticky-True the first time ANY
    # of temp/age/ack/miss arrives non-None for that joint - it is what tells health() to
    # trust the diag-based verdict instead of falling back to reception-recency-only (a
    # sender that never carries these fields at all, e.g. today's bench_telemetry.py, must
    # never be silently scored as if it were reporting ack=1/miss=0).
    self.temp_c: dict[str, float | None] = {n: None for n in act_names}
    self.motor_age_ms: dict[str, float | None] = {n: None for n in act_names}
    self.ack: dict[str, float | None] = {n: None for n in act_names}
    self.miss: dict[str, float | None] = {n: None for n in act_names}
    self._has_diag: dict[str, bool] = {n: False for n in act_names}
    # Fault visibility (2026-09-05, docs/121/docs/124): a NEW, orthogonal signal from
    # everything above - a joint can be "stuck"/faulted while comm/ack/miss all still look
    # perfectly healthy (that is the whole point of the docs/124 incident this exists to fix),
    # so these are deliberately kept OUT of `_has_diag`/the ok/warn/dead verdict and surfaced
    # as their own `fault_reason` string instead (see `_joint_fault_reason` / `health()`).
    self.stuck: dict[str, float | None] = {n: None for n in act_names}
    self.fault_le: dict[str, float | None] = {n: None for n in act_names}
    self.fault_be: dict[str, float | None] = {n: None for n in act_names}
    self._stuck_since_mono: dict[str, float] = {}
    # This process's OWN reception clock, per joint - the last time ingest_joint_state saw
    # ANY field (fast or diag) not None for that specific joint name. Unlike `_last_rx_mono`
    # (one clock for "any message arrived at all"), this lets one joint go silent while
    # others keep reporting without the silent one hiding behind the others' traffic.
    self._joint_last_update_mono: dict[str, float] = {}
    # P4/R7: the hardware's OWN reported PD gains, when a JointState carries them - kept
    # separately from q/qd/tau/target because unlike those, a gains report is expected to be
    # nearly static (it changes on a config reload, not every packet), so "last received" is
    # simply "current", with no staleness clock of its own.
    self.gains: dict[str, dict | None] = {n: None for n in act_names}
    self.ankle_derived: dict[str, dict[str, float]] = {}
    self.imu: dict[str, Any] | None = None
    self.imu_age_ref: float | None = None
    # P4: a real host's own PolicyIO report (obs/action/target/cmd it computed for ITSELF).
    # This is the only principled source for the "last_action" and "cmd" shadow-mux terms -
    # there is no wire concept of "the robot's commanded velocity" otherwise. Receive-only,
    # same as everything else in this module; nothing here ever originates a PolicyIO.
    self.policy_io: dict[str, Any] | None = None
    self.policy_io_ref: float | None = None

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
      temp_list = msg.temp_c or [None] * len(msg.joint_names)
      age_list = msg.motor_age_ms or [None] * len(msg.joint_names)
      ack_list = msg.ack or [None] * len(msg.joint_names)
      miss_list = msg.miss or [None] * len(msg.joint_names)
      stuck_list = msg.stuck or [None] * len(msg.joint_names)
      fault_le_list = msg.fault_le or [None] * len(msg.joint_names)
      fault_be_list = msg.fault_be or [None] * len(msg.joint_names)
      for n, q, qd, tau, tgt, temp, age, ack, miss, stuck, fault_le, fault_be in zip(
        msg.joint_names, msg.q, qd_list, tau_list, tgt_list, temp_list, age_list, ack_list,
        miss_list, stuck_list, fault_le_list, fault_be_list,
      ):
        if n not in self.q:
          continue  # the ws/in route already rejected unknown names; defensive only
        # Motor health task: "this joint was actually named with real data in THIS message"
        # is the per-joint reception clock - any field, fast or diag, counts. A joint this
        # message never touched at all keeps whatever clock it already had (or none, if it
        # has genuinely never been seen).
        if any(v is not None for v in (q, qd, tau, tgt, temp, age, ack, miss)):
          self._joint_last_update_mono[n] = now
        if temp is not None:
          self.temp_c[n] = temp
          self._has_diag[n] = True
        if age is not None:
          self.motor_age_ms[n] = age
          self._has_diag[n] = True
        if ack is not None:
          self.ack[n] = ack
          self._has_diag[n] = True
        if miss is not None:
          self.miss[n] = miss
          self._has_diag[n] = True
        # Fault visibility (2026-09-05, docs/121/docs/124) - see this class's own module
        # docstring note above `self.stuck`: deliberately NOT folded into `_has_diag`/the
        # ok-warn-dead verdict (a stuck joint can have comm/ack looking perfectly fine - that
        # is exactly the incident this exists to catch). `_stuck_since_mono` is this
        # PROCESS's own duration clock (independent of whatever duration the robot-side log
        # already reported) so a viewer watching only the dashboard, with no terminal access
        # to the robot's own log, still gets a meaningful "how long" in the violation record.
        if stuck is not None:
          was_stuck = bool(self.stuck.get(n))
          self.stuck[n] = stuck
          now_stuck = stuck >= 1.0
          if now_stuck and not was_stuck:
            self._stuck_since_mono[n] = now
          if not now_stuck:
            self._stuck_since_mono.pop(n, None)
          if now_stuck and self.violations is not None:
            since = self._stuck_since_mono.get(n, now)
            duration_s = now - since
            reason = (
              f"{n}: 명령을 따르지 않음 (고장 의심) — 목표 {math.degrees(tgt) if tgt is not None else float('nan'):.1f} (deg), "
              f"실측 {math.degrees(q) if q is not None else float('nan'):.1f} (deg), "
              f"토크 {tau if tau is not None else float('nan'):.2f} N*m, {duration_s:.0f}초째"
            )
            self.violations.record(
              side="stuck", joint=n, value=q, limit_lo=None, limit_hi=None, src=msg.src,
              extra=dict(reason=reason, duration_s=round(duration_s, 1)),
              rate_limit_s=2.0,
            )
        if fault_le is not None:
          self.fault_le[n] = fault_le
          self.fault_be[n] = fault_be
          if fault_le != 0 and self.violations is not None:
            bits = named_fault_bits(int(fault_le))
            simple = "/".join(FAULT_BIT_SIMPLE_KO[b] for b in FAULT_BIT_NAMES if int(fault_le) >> b & 1)
            reason = (
              f"{n}: 모터가 {simple}(으)로 힘을 끊었습니다 (코드 0x{int(fault_le):08X})" if simple
              else f"{n}: 정의되지 않은 고장 코드 0x{int(fault_le):08X}"
            )
            self.violations.record(
              side="fault", joint=n, value=float(fault_le), limit_lo=0.0, limit_hi=0.0,
              src=msg.src, extra=dict(reason=reason, fault_be=fault_be), rate_limit_s=5.0,
            )
        prev = self.q[n]
        if q is not None and prev is not None and abs(q - prev) > math.pi:
          self.wrap_events += 1
          self.warnings.append(f"{n}: |dq|>pi jump ({prev:+.3f} -> {q:+.3f} rad)")
        if q is not None and n in self.joint_ranges:
          lo, hi = self.joint_ranges[n]
          if q < lo - self.range_margin_rad or q > hi + self.range_margin_rad:
            self.range_violations[n] += 1
            if self.violations is not None:
              self.violations.record(
                side="recv", joint=n, value=q, limit_lo=lo, limit_hi=hi, src=msg.src,
              )
        if tau is not None and n in self.effort_limits:
          limit = self.effort_limits[n]
          if abs(tau) > limit and self.violations is not None:
            self.violations.record(
              side="recv_torque", joint=n, value=tau, limit_lo=-limit, limit_hi=limit,
              src=msg.src,
            )
        self.q[n] = q
        self.qd[n] = qd
        self.tau[n] = tau
        self.target[n] = tgt
      if msg.gains:
        for n, g in msg.gains.items():
          if n in self.gains and g:
            self.gains[n] = dict(g)
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

  def ingest_policy_io(self, msg: PolicyIO) -> None:
    """P4: a real host's self-reported obs/action/target/cmd, for the shadow-mux terms that
    have no other real-world analogue (last_action, generated_commands)."""
    now = time.monotonic()
    with self._lock:
      self.rx_count += 1
      self._last_rx_mono = now
      self._rx_times.append(now)
      if msg.contract_hash and msg.contract_hash != self.contract_sha:
        self.contract_mismatches += 1
      self.policy_io = dict(action=list(msg.action), target=list(msg.target), cmd=list(msg.cmd))
      self.policy_io_ref = now

  def policy_io_age_s(self) -> float | None:
    with self._lock:
      if self.policy_io_ref is None:
        return None
      return time.monotonic() - self.policy_io_ref

  def imu_age_s(self) -> float | None:
    with self._lock:
      if self.imu_age_ref is None:
        return None
      return time.monotonic() - self.imu_age_ref

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

  def joint_age_s(self, name: str) -> float | None:
    """Seconds since THIS joint specifically last carried any field (fast or diag) - the same
    per-joint reception clock ``health()`` uses, exposed publicly for the sync-before-arm gate
    (``hw_sync.py``), which needs "is this ONE joint's data fresh enough to sync/trust right
    now" rather than the link-wide ``age_s()`` above (a link can be alive while one specific
    joint's sender has gone quiet - the whole point of the per-joint clock, see this class's
    module docstring)."""
    with self._lock:
      lu = self._joint_last_update_mono.get(name)
    return None if lu is None else time.monotonic() - lu

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
        imu=dict(self.imu) if self.imu is not None else None,
        have_policy_io=self.policy_io is not None,
        bridge_errors=self.bridge_errors,
        bridge_last_error=self.bridge_last_error,
      )

  def snapshot_joints(self) -> dict[str, dict[str, float | None]]:
    with self._lock:
      return {
        n: dict(q=self.q[n], qd=self.qd[n], tau=self.tau[n], target=self.target[n])
        for n in self.act_names
      }

  # -------------------------------------------------------------------- motor health
  def _joint_health_state(
    self, has_diag: bool, our_age: float | None, motor_age_ms: float | None,
    ack: float | None, miss: float | None, temp_c: float | None, temp_limit_c: float,
    expected_period_s: float | None,
  ) -> str:
    """One joint's ok/warn/dead verdict. Reception recency (``our_age``) is checked FIRST
    and unconditionally - a source that has gone silent for this joint is dead regardless of
    whatever diag value it last reported (a stale "ack=1" from 10 minutes ago must never
    read as healthy). Only once recency passes does a diag-aware verdict apply, and ONLY if
    this joint has EVER carried a diag field at all (``has_diag``) - a sender that never
    sends temp/age/ack/miss (today's bench_telemetry.py) is judged on reception recency
    alone, exactly as the task brief specifies, never scored as if diag values of 0/None
    meant something."""
    if our_age is None or our_age > HEALTH_DEAD_AGE_S:
      return "dead"
    if not has_diag:
      return "ok" if our_age < HEALTH_OK_AGE_S else "warn"
    if motor_age_ms is None:
      return "dead"  # the robot itself has never heard back from this motor, ever
    if miss is not None and miss >= HEALTH_DEAD_MISS:
      return "dead"  # a sustained run of consecutive no-response cycles, not just one
    warn = our_age >= HEALTH_OK_AGE_S
    warn = warn or (miss is not None and miss >= 1)
    warn = warn or (ack is not None and ack == 0.0)
    warn = warn or (expected_period_s and motor_age_ms > 3.0 * expected_period_s * 1e3)
    warn = warn or (temp_c is not None and temp_c > temp_limit_c)
    return "warn" if warn else "ok"

  def _joint_fault_reason(self, stuck: float | None, fault_le: float | None) -> str | None:
    """Plain-language reason this joint should show RED regardless of its ok/warn/dead
    connectivity verdict above (docs/124: comm/ack/miss can look perfectly healthy while the
    joint itself is stuck or has cut its own torque - see this class's module docstring note
    above ``self.stuck``). ``None`` means neither condition is currently active."""
    parts = []
    if stuck is not None and stuck >= 1.0:
      parts.append("명령을 따르지 않음 (고장 의심)")
    if fault_le is not None and fault_le != 0:
      code = int(fault_le)
      simple = "/".join(FAULT_BIT_SIMPLE_KO[b] for b in FAULT_BIT_NAMES if code >> b & 1)
      parts.append(f"고장 코드 0x{code:08X}" + (f" ({simple})" if simple else " (정의되지 않음)"))
    return " · ".join(parts) if parts else None

  def health(
    self, expected_period_s: float | None = None, temp_limit_c: float = HEALTH_DEFAULT_TEMP_LIMIT_C,
  ) -> dict:
    """``{joints: {name: {state, age_s, motor_age_ms, ack, miss, temp_c, q, diag}},
    summary: {ok, warn, dead}}`` - ``GET /health``'s payload minus the link-level fields
    (rx rate/age/seq-gaps), which come from :meth:`status` instead (this method only knows
    about individual joints)."""
    now = time.monotonic()
    with self._lock:
      last_update = dict(self._joint_last_update_mono)
      temp_c = dict(self.temp_c)
      age_ms = dict(self.motor_age_ms)
      ack = dict(self.ack)
      miss = dict(self.miss)
      has_diag = dict(self._has_diag)
      qs = dict(self.q)
      stuck = dict(self.stuck)
      fault_le = dict(self.fault_le)
    joints: dict[str, dict] = {}
    summary = {"ok": 0, "warn": 0, "dead": 0}
    for n in self.act_names:
      lu = last_update.get(n)
      our_age = (now - lu) if lu is not None else None
      state = self._joint_health_state(
        has_diag.get(n, False), our_age, age_ms.get(n), ack.get(n), miss.get(n),
        temp_c.get(n), temp_limit_c, expected_period_s,
      )
      summary[state] += 1
      joints[n] = dict(
        state=state,
        age_s=(round(our_age, 3) if our_age is not None else None),
        motor_age_ms=age_ms.get(n),
        ack=ack.get(n),
        miss=miss.get(n),
        temp_c=temp_c.get(n),
        q=qs.get(n),
        diag=has_diag.get(n, False),
        # Fault visibility (2026-09-05, docs/121/docs/124): NEVER folds into `state` above -
        # see `_joint_fault_reason`'s own docstring for why. `None` when neither is active.
        fault_reason=self._joint_fault_reason(stuck.get(n), fault_le.get(n)),
      )
    return dict(joints=joints, summary=summary)

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
