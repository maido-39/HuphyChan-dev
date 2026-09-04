"""Shared receive-side safety state machine: docs/123 section 3's "0.2 s 데드맨 -> hold ->
3 s 후 default로 슬루 복귀" (0.2s deadman -> hold -> after 3s, slew back to default), plus
seq/arm-token/contract-hash gating.  Factored out of ``dummy_rx.py`` and
``huphy_remote_motion.py`` so BOTH use the exact same logic and the exact same tests - this
module has NO ``huphy`` import and NO socket, so it is the one place the safety-critical
timing can be pinned down with a fake clock instead of a real 0.2s sleep in a test.

**Timing interpretation - RESOLVED 2026-09-04 (docs/123 section 5 update, superseding the
previous "two readings, only (b) implemented" note)**: the spec sentence was genuinely
ambiguous with only one CLI knob (``--default-return-s``). The user has now picked reading
(a) explicitly, with its own knob added: the moment the stream goes stale (age >
``deadman_s`` or the message's own ``ttl_ms``, whichever is stricter), the pose FREEZES at
whatever it last was ("hold") for a flat ``hold_s`` seconds with NO motion at all; only once
that flat hold expires does a linear slew from the held pose to ``default_q`` begin, taking
exactly ``return_s`` seconds. Three independent knobs now exist (``deadman_s``, ``hold_s``,
``return_s`` - CLI ``--deadman-s``/``--hold-s``/``--return-s``), one per phase, so there is no
longer a single parameter doing double duty for two different physical meanings.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Mapping

from ..schema import JointTarget

DEFAULT_DEADMAN_S = 0.2
DEFAULT_HOLD_S = 3.0
DEFAULT_RETURN_S = 2.0


@dataclass
class ReceiveStats:
  """Self-diagnostic counters - never sent anywhere, just for the receiver's own log/CLI
  summary (docs/123 item 3: "contract_hash 불일치 카운트·거부")."""

  accepted: int = 0
  rejected_seq: int = 0
  rejected_arm_token: int = 0
  rejected_contract: int = 0
  parse_errors: int = 0


class LatestOnly:
  """Thread-safe holder of the most recently ACCEPTED ``JointTarget``.

  Three independent rejections, each counted, none of them guessed past:

    * ``seq`` at or behind the last accepted message - a reordered/duplicated UDP packet
      (docs/123 item 3: "seq 역행 무시").
    * ``arm_token`` not equal to the expected one - configuration/safety, never a fallback.
    * ``contract_hash`` present and not equal to the expected one - a different model
      generation talking to this robot is a hard stop, not a "close enough".  ``None`` (a
      sender that has no contract - e.g. a hand-built test message) is allowed through: it is
      "unknown", not "wrong".

  Timestamps are the RECEIVER's own monotonic clock, never the sender's ``t_ns`` - two hosts
  do not share a clock, and the deadman timing must be robust to that.
  """

  def __init__(self, expected_arm_token: str, expected_contract_hash: str | None = None):
    self.expected_arm_token = expected_arm_token
    self.expected_contract_hash = expected_contract_hash
    self.stats = ReceiveStats()
    self._lock = threading.Lock()
    self._msg: JointTarget | None = None
    self._recv_t: float | None = None
    self._last_seq: int | None = None

  def put(self, msg: JointTarget, *, now: float | None = None) -> bool:
    """Returns whether the message was accepted (for a caller that wants to log rejects)."""
    now = time.monotonic() if now is None else now
    if self._last_seq is not None and msg.seq <= self._last_seq:
      self.stats.rejected_seq += 1
      return False
    if msg.arm_token != self.expected_arm_token:
      self.stats.rejected_arm_token += 1
      return False
    if self.expected_contract_hash is not None and msg.contract_hash not in (
      None, self.expected_contract_hash
    ):
      self.stats.rejected_contract += 1
      return False
    with self._lock:
      self._msg = msg
      self._recv_t = now
      self._last_seq = msg.seq
    self.stats.accepted += 1
    return True

  def get(self, *, now: float | None = None) -> tuple[JointTarget | None, float]:
    """``(last accepted message, its age in seconds)``.  Age is ``inf`` if nothing has ever
    been accepted - deliberately not 0 or -1, so a naive "age < deadman_s" check fails safe."""
    now = time.monotonic() if now is None else now
    with self._lock:
      msg, recv_t = self._msg, self._recv_t
    if msg is None:
      return None, float("inf")
    return msg, now - recv_t


@dataclass
class DeadmanState:
  target: dict[str, float]
  phase: str  # "idle" | "live" | "hold" | "returning" | "default"


class DeadmanFilter:
  """Turns ``(message_or_None, age_s)`` into the joint targets that should actually be sent
  to the motors THIS tick, applying the enable list and the hold/return timing.

  Three phases after the stream goes stale, each with its own knob (docs/123 section 5,
  2026-09-04 resolution): ``hold`` (flat, frozen at the last live pose, for ``hold_s``
  seconds) -> ``returning`` (linear slew from that pose to ``default_q`` over ``return_s``
  seconds) -> ``default`` (arrived, stays there). ``hold_s=0`` recovers the OLD single-phase
  behaviour (slew begins the instant the deadman trips) for a caller that wants that.

  ``enable``, if given, restricts which joint names are EVER allowed through - a joint not in
  it never gets a target from this filter, at any phase (docs/123 item 3: a disabled motor
  gets no command at all, so HUPHY's own per-motor hold takes over - never a synthesized
  "safe" value standing in for a real one).
  """

  def __init__(
    self,
    default_q: Mapping[str, float],
    *,
    deadman_s: float = DEFAULT_DEADMAN_S,
    hold_s: float = DEFAULT_HOLD_S,
    return_s: float = DEFAULT_RETURN_S,
    enable: set[str] | None = None,
  ):
    self.default_q = dict(default_q)
    self.deadman_s = float(deadman_s)
    self.hold_s = float(hold_s)
    self.return_s = float(return_s)
    self.enable = set(enable) if enable is not None else None
    self._last_live_target: dict[str, float] | None = None
    self._hold_pose: dict[str, float] | None = None
    self._hold_since: float | None = None

  def _enabled(self, values: Mapping[str, float]) -> dict[str, float]:
    if self.enable is None:
      return dict(values)
    return {k: v for k, v in values.items() if k in self.enable}

  def update(
    self, msg: JointTarget | None, age_s: float, *, now: float | None = None
  ) -> DeadmanState:
    """Call once per control tick with whatever ``LatestOnly.get()`` returned.  Pure function
    of ``(msg, age_s, now)`` plus this filter's own hold-state, so it is fully testable with a
    synthetic clock - no sleeping 0.2s in a test to prove a 0.2s deadman."""
    now = time.monotonic() if now is None else now
    deadline = self.deadman_s if msg is None else min(self.deadman_s, msg.ttl_ms / 1000.0)
    fresh = msg is not None and age_s <= deadline

    if fresh:
      target = self._enabled(dict(zip(msg.joint_names, msg.q_target)))
      self._last_live_target = target
      self._hold_pose = None
      self._hold_since = None
      return DeadmanState(target=target, phase="live")

    # Stale (or nothing ever received). Establish the hold pose from the last LIVE target the
    # very first tick this is observed - not before, and not reset on every subsequent stale
    # tick, or the hold_s/return_s countdown would never advance.
    if self._hold_pose is None:
      if self._last_live_target is None:
        # Never had a live message at all - nothing to hold, go straight to default rather
        # than holding an undefined pose.
        return DeadmanState(target=dict(self._enabled(self.default_q)), phase="idle")
      self._hold_pose = dict(self._last_live_target)
      self._hold_since = now

    held_age = now - self._hold_since
    if held_age <= self.hold_s:
      # Flat hold: frozen at the last live pose, no motion at all yet.
      return DeadmanState(target=dict(self._hold_pose), phase="hold")

    returning_age = held_age - self.hold_s
    frac = 0.0 if self.return_s <= 0 else min(max(returning_age / self.return_s, 0.0), 1.0)
    phase = "returning" if frac < 1.0 else "default"
    target = {
      k: (1.0 - frac) * v + frac * self.default_q.get(k, v) for k, v in self._hold_pose.items()
    }
    return DeadmanState(target=target, phase=phase)
