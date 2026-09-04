"""Fault visibility (2026-09-05) - docs/121 section 12c, docs/124 section 1/2/6.

Real incident this exists to fix (docs/124, bench 2026-09-05): two motors cut their own
torque (an overvoltage fault) and the dashboard kept reading "normal" the entire time -
communication stayed at 110 Hz, ack=1/miss=0, and the knee angle simply froze at 141.40 deg
for 170 s while the temperature field showed a broken 3308.8 C (a fault-state artifact -
clearing the fault brought it back to 34.0 C). Nothing anywhere flagged that the joint had
stopped moving. This module is the fix, in two independent layers (see the functions/classes
below), plus the raw fault-word decoder that reads a RobStride fault reply correctly (docs/124
section 1: the fault frame is byte-order-DIFFERENT from the state frame, and this robot's
HUPHY checkout may or may not have that fixed yet - so this module never trusts one
interpretation, it always computes both and lets the caller show both).

Everything in this module is pure (no ``huphy`` import, no socket, no CAN) so it is fully
unit-tested without hardware - see ``tests/test_motor_fault.py``. ``huphy_remote_motion.py``
wires it into the live control loop; see that file's own module docstring for what is,
and is not, verified against real HUPHY/CAN internals (motors are off during this change -
hardware verification is reserved for the human operator, not this session).

  * :class:`StuckDetector` - layer (a), "the value froze" - reads ONLY what the control loop
    already has every tick (target, measured position, measured torque). No extra CAN
    traffic, runs unconditionally, every tick, live or not - the whole point of the incident
    above is that a stuck joint must never look normal just because nothing is currently
    commanding it.
  * :class:`FaultPoller` - decides WHEN it is safe to ask the motor directly "why did you
    stop" (layer (b)): never while armed (a fault reply shares its CAN id with a state reply,
    so the control loop could mistake one for the other - docs/124 section 2), once a second
    while idle, and immediately on the instant transmission goes idle (so the very fault that
    just happened is the one asked about, not whatever is live a second later).
  * :func:`decode_fault_word` - the raw 4 fault-value bytes, interpreted BOTH ways (manufacturer
    SDK little-endian, and HUPHY's still-possibly-buggy big-endian), never just one.
  * :func:`query_fault_raw` - the read_fault_raw.py protocol (drain stale, send the MIT fault
    query, collect one reply) as a reusable, transport-injected function.
  * :func:`describe_fault_simple` / :func:`describe_stuck_simple` - the plain-language (easy
    Korean) one-line summaries this task's brief specifies, for logs/telemetry text.
"""

from __future__ import annotations

import dataclasses
import time

# --------------------------------------------------------------------------- stuck detection
STUCK_ERR_DEG = 3.0
"""deg - |target - measured| must exceed this before a joint is even considered for "not
tracking" at all (a joint that is simply mid-move, close to its target, is never flagged)."""

STUCK_POS_DEADBAND_DEG = 0.2
"""deg - the measured position must move LESS than this across the whole STUCK_HOLD_S window
for the joint to count as "frozen" - real motion (even slow tracking) resets the window."""

STUCK_TAU_ZERO_NM = 0.05
"""N*m - the reported torque must stay under this the whole window. This is what
distinguishes "the motor cut its own torque" (docs/124's overvoltage case: tau ~= 0 while
sitting far from target) from "the motor is straining against a real mechanical load" (which
would show non-zero torque even while barely moving) - only the former is a fault."""

STUCK_HOLD_S = 1.0
"""seconds - all three conditions above must hold CONTINUOUSLY this long before this is
reported. Short enough to catch a real stall quickly, long enough that a single noisy sample
or a brief hard stop against a real limit never fires it."""


class StuckDetector:
  """Per-joint "not tracking the command, fault suspected" judgement - see the module
  docstring's layer (a). One instance covers every joint on a leg; call :meth:`update` once
  per joint per control tick.
  """

  def __init__(self):
    self._since: dict[str, float] = {}
    self._pos_at_since: dict[str, float] = {}

  def update(
    self, name: str, t: float, target_deg: float | None, pos_deg: float | None,
    tau_nm: float | None,
  ) -> dict | None:
    """One joint, one tick. Returns ``None`` if not (yet, or no longer) stuck, else
    ``{target_deg, pos_deg, tau_nm, duration_s}`` for the caller to log/report.

    Missing data (``None`` in any of the three readings) is never guessed into "not moving" -
    it resets the window and reports "not stuck" for this tick, the same as a genuinely
    tracking joint would.
    """
    if target_deg is None or pos_deg is None or tau_nm is None:
      self._since.pop(name, None)
      self._pos_at_since.pop(name, None)
      return None

    tracking_ok = abs(target_deg - pos_deg) <= STUCK_ERR_DEG
    torque_present = abs(tau_nm) >= STUCK_TAU_ZERO_NM
    if tracking_ok or torque_present:
      self._since.pop(name, None)
      self._pos_at_since.pop(name, None)
      return None

    since = self._since.get(name)
    if since is None:
      self._since[name] = t
      self._pos_at_since[name] = pos_deg
      return None

    moved = abs(pos_deg - self._pos_at_since[name])
    if moved >= STUCK_POS_DEADBAND_DEG:
      # Real motion happened since the window opened - restart the window here rather than
      # calling it stuck (a joint slowly limping toward its target is not "frozen").
      self._since[name] = t
      self._pos_at_since[name] = pos_deg
      return None

    duration = t - since
    if duration < STUCK_HOLD_S:
      return None
    return dict(target_deg=target_deg, pos_deg=pos_deg, tau_nm=tau_nm, duration_s=duration)


def describe_stuck_simple(motor_label: str, result: dict) -> str:
  """Plain-language (easy Korean, per this task's brief) one-line summary of a
  :class:`StuckDetector` hit, in the exact shape the brief specifies."""
  return (
    f"{motor_label}: 명령을 따르지 않음 (고장 의심) — 목표 {result['target_deg']:.1f} (deg), "
    f"실측 {result['pos_deg']:.1f} (deg), 토크 {result['tau_nm']:.2f} N·m, "
    f"{result['duration_s']:.0f}초째"
  )


# --------------------------------------------------------------------------- fault polling
FAULT_POLL_INTERVAL_S = 1.0
"""seconds - how often to query the fault register while transmission is idle (docs/124
section 2's suggestion 2: "낮은 주기로 조회")."""


class FaultPoller:
  """Decides WHEN it is safe to issue a fault-register query, per the module docstring's
  layer (b). Pure state machine over ``(t, phase)`` - ``phase`` is
  ``remote_target.DeadmanState.phase`` (``"idle"``/``"live"``/``"hold"``/``"returning"``/
  ``"default"``); only ``"live"`` counts as "armed/transmitting" here, matching this whole
  bridge's own convention that ``"live"`` is the one phase where a fresh operator command is
  actually driving the motor.
  """

  def __init__(self, interval_s: float = FAULT_POLL_INTERVAL_S):
    self.interval_s = float(interval_s)
    self._last_phase: str | None = None
    self._last_query_t: float | None = None

  def update(self, t: float, phase: str) -> bool:
    """Call once per tick. Returns whether THIS tick should issue a fault query."""
    armed_now = phase == "live"
    was_armed = self._last_phase == "live"
    disarm_edge = was_armed and not armed_now
    self._last_phase = phase

    if armed_now:
      # Never query while armed (docs/124 section 2: a fault reply can be mistaken for a
      # state reply by the control loop). Clear the periodic clock too, so a LATER disarm
      # is always treated as a fresh edge, never as "already queried recently".
      self._last_query_t = None
      return False

    if disarm_edge:
      self._last_query_t = t
      return True

    if self._last_query_t is None or (t - self._last_query_t) >= self.interval_s:
      self._last_query_t = t
      return True
    return False


# --------------------------------------------------------------------------- fault decoding
FAULT_BIT_NAMES = {
  0: "overtemperature",
  1: "driver_fault",
  2: "undervoltage",
  3: "overvoltage",
  7: "encoder_uncalibrated",
  14: "stall_overload",
}
"""Precise (technical) bit names, per this task's brief and docs/124 section 6 (RS03/RS04
manuals, communication type 21's fault-value byte)."""

FAULT_BIT_SIMPLE_KO = {
  0: "과열",
  1: "드라이버 칩 고장",
  2: "저전압",
  3: "과전압",
  7: "엔코더 미보정",
  14: "과부하(스톨)",
}
"""Easy-Korean phrase per bit, for on-screen/log text (user instruction: screen text and docs
use plain language; code/comments keep the precise technical terms above)."""


def named_fault_bits(value: int) -> list[str]:
  """``value``'s set bits -> their precise names (:data:`FAULT_BIT_NAMES`), lowest bit first.
  An unrecognised set bit is silently omitted here (the caller can compare popcount(value)
  against ``len(named_fault_bits(value))`` to notice one, same spirit as
  ``read_fault_raw.py``'s reference tool - never claimed as a specific name we do not have)."""
  return [name for bit, name in sorted(FAULT_BIT_NAMES.items()) if value >> bit & 1]


@dataclasses.dataclass
class FaultReading:
  """Both byte-order interpretations of the SAME 4 fault-value bytes - see the module
  docstring and docs/124 section 1. ``little`` is the CORRECT one (manufacturer SDK,
  ``struct.unpack("<LL", data)``, and the RS03/RS04 manual's own byte table); ``big`` is what
  HUPHY's ``decode_fault`` reads today IF this robot's checkout still has the byte-order bug
  fixed in this repo's ``fix-fault-byte-order`` branch (docs/124 section 1) - unknown at any
  given robot's revision, which is exactly why both are always kept, never just one."""

  little: int
  little_names: list[str]
  big: int
  big_names: list[str]


def decode_fault_word(raw4: bytes) -> FaultReading:
  """The 4 raw fault-value bytes (``reply.data[1:5]`` in this robot's 11-bit wiring, per
  ``deploy/bench/read_fault_raw.py`` / docs/124 section 1 - byte 0 is the motor id) ->
  both interpretations. Never guesses which one this robot's HUPHY actually uses - see
  :class:`FaultReading`."""
  raw = bytes(raw4)
  little = int.from_bytes(raw, "little")
  big = int.from_bytes(raw, "big")
  return FaultReading(
    little=little, little_names=named_fault_bits(little),
    big=big, big_names=named_fault_bits(big),
  )


def describe_fault_simple(motor_label: str, reading: FaultReading) -> str:
  """Plain-language (easy Korean) one-line summary, using the LITTLE-endian (CORRECT, docs/124
  section 1) interpretation as the primary statement - the big-endian one is for the technical
  log/telemetry side, not this human-facing sentence."""
  if reading.little == 0:
    return f"{motor_label}: 고장 코드 없음 (0x{reading.little:08X})"
  simple = [FAULT_BIT_SIMPLE_KO[bit] for bit in sorted(FAULT_BIT_NAMES) if reading.little >> bit & 1]
  if simple:
    return (
      f"{motor_label}: 모터가 {'/'.join(simple)}(으)로 힘을 끊었습니다 "
      f"(코드 0x{reading.little:08X})"
    )
  return f"{motor_label}: 정의되지 않은 고장 코드 0x{reading.little:08X}"


# --------------------------------------------------------------------------- raw CAN query
CMD_FAULT = 0xFB
"""RobStride Command 5 (fault query), matching ``deploy/bench/read_fault_raw.py``."""
F_CMD_QUERY = 0x00
"""Anything but 0xFF in the MIT frame's penultimate byte means "query" (read_fault_raw.py)."""
FAULT_QUERY_WAIT_S = 0.3
"""seconds - how long to wait for a fault-query reply, matching read_fault_raw.py's own
default collection window."""


def build_mit_frame_data(command: int, f_cmd: int = 0xFF) -> bytes:
  """The 8-byte MIT command DATA payload (11-bit RobStride wiring): ``FF*6 + f_cmd +
  command`` - the exact shape ``read_fault_raw.py``'s own ``mit()`` sends. Only the data
  bytes; the arbitration id (the motor's CAN id) is the caller's job, since this module has no
  notion of a CAN bus/message type at all (kept import-free and hardware-free on purpose)."""
  return bytes([0xFF] * 6 + [f_cmd & 0xFF, command & 0xFF])


def query_fault_raw(
  motor_ids, send_fn, recv_fn, *, wait_s: float = FAULT_QUERY_WAIT_S,
) -> dict[int, bytes | None]:
  """For each id in ``motor_ids``: drain anything already queued, send the fault-query MIT
  frame, collect one reply (or ``None`` on timeout). Mirrors
  ``deploy/bench/read_fault_raw.py``'s protocol exactly, but with the transport INJECTED
  (``send_fn(motor_id, data_bytes) -> None``, ``recv_fn(timeout_s) -> bytes | None``) so this
  is unit-testable with a fake bus - no ``python-can`` import here at all. The real caller
  (``huphy_remote_motion.py``'s ``run_real()``) adapts a real CAN bus to this shape; see that
  file for what is and is not verified against real hardware.

  ``recv_fn`` is expected to behave like ``can.Bus.recv(timeout=...)``: block up to
  ``timeout_s`` for the next frame, or return ``None``. The drain step calls it with
  ``timeout_s=0.0`` (non-blocking poll) until it returns ``None``.
  """
  out: dict[int, bytes | None] = {}
  for mid in motor_ids:
    while recv_fn(0.0) is not None:
      pass  # drain anything stale - a leftover state frame would be read as the fault word
    send_fn(mid, build_mit_frame_data(CMD_FAULT, F_CMD_QUERY))
    deadline = time.monotonic() + wait_s
    reply: bytes | None = None
    while True:
      remaining = deadline - time.monotonic()
      if remaining <= 0:
        break
      data = recv_fn(remaining)
      if data is not None:
        reply = data
        break
    out[mid] = reply
  return out


# --------------------------------------------------------------------------- thermal cutoff
OVERHEAT_CUTOFF_C = 50.0
"""deg C - manual-stated operating temperature upper bound (docs/124 section 6: "사용 온도
범위 -20 ~ 50도"), well below the 130 C winding limit and the 145 C fault threshold - this is
a PREVENTIVE cutoff, not a reaction to the motor's own fault, by user instruction."""

OVERHEAT_RESUME_C = 45.0
"""deg C - resume threshold, 5 C below the cutoff so a temperature sitting right at 50 C does
not chatter the motor on/off every tick (hysteresis)."""

TEMP_VALID_MIN_C = -20.0
TEMP_VALID_MAX_C = 150.0
"""deg C - the plausible sensor range (manual's -20~50 operating range, extended up to just
above the 145 C hard-fault ceiling to allow for a legitimate fault-adjacent reading). Anything
outside this is treated as UNREADABLE, never as a real temperature - docs/124's own incident
(3308.8 C, a fault-state artifact) is exactly the case this guards against: never cut OR clear
a cutoff from a value this implausible, and never silently clamp/normalise it into range
either (user instruction: "조용히 정규화하지 말 것")."""


class ThermalCutoff:
  """Per-joint hysteretic overheat cutoff - commit 2 of this task. One instance per leg;
  call :meth:`update` once per joint per control tick with that joint's latest reported
  temperature."""

  def __init__(self):
    self._cut: dict[str, bool] = {}

  def update(self, name: str, temp_c: float | None) -> dict:
    """Returns ``{valid, cut, transitioned, temp_c}``. ``valid=False`` means the reading was
    outside :data:`TEMP_VALID_MIN_C`/:data:`TEMP_VALID_MAX_C` (or missing) - the EXISTING
    ``cut`` state is preserved unchanged in that case (never newly cut, never newly cleared,
    from a reading that cannot be trusted either way)."""
    was_cut = self._cut.get(name, False)
    if temp_c is None or not (TEMP_VALID_MIN_C <= temp_c <= TEMP_VALID_MAX_C):
      return dict(valid=False, cut=was_cut, transitioned=False, temp_c=temp_c)

    if not was_cut and temp_c >= OVERHEAT_CUTOFF_C:
      self._cut[name] = True
      return dict(valid=True, cut=True, transitioned=True, temp_c=temp_c)
    if was_cut and temp_c <= OVERHEAT_RESUME_C:
      self._cut[name] = False
      return dict(valid=True, cut=False, transitioned=True, temp_c=temp_c)
    return dict(valid=True, cut=was_cut, transitioned=False, temp_c=temp_c)


def describe_cutoff_simple(motor_label: str, result: dict, *, resumed: bool) -> str:
  """Plain-language (easy Korean) one-line summary of a :class:`ThermalCutoff` transition."""
  if resumed:
    return f"{motor_label}: 식어서 다시 시작 (온도 {result['temp_c']:.1f}도)"
  return f"{motor_label}: 과열로 힘을 끊음 (온도 {result['temp_c']:.1f}도, 기준 {OVERHEAT_CUTOFF_C:.0f}도)"
