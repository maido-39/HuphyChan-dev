"""The SENDING half of docs/123 plan A: a 50 Hz ``JointTarget`` UDP client library.

This is what a viewer-side caller (the UI wiring in ``api.py``/``ui.py`` - a different
coder's file, not touched here) or a standalone script uses to talk to either
``huphy_remote_motion.py`` (real HUPHY) or ``dummy_rx.py`` (no HUPHY needed) on the other
end of UDP :9872.  It never imports ``huphy`` and never touches ``api.py``/``ui.py`` - it is
the primitive those files would call, kept separately testable.

Three independent safety layers, matching docs/123 section 4/§3 exactly, and each one is
enforced HERE, in the sender, not trusted to the far end alone (the receiver still re-checks
everything - defense in depth, not "the sender is trusted"):

  1. ``origin`` is fixed at construction to ``"manual"`` or ``"script"``.  Anything else -
     ``"policy"`` above all - is a ``RuntimeError`` before a socket is even opened.  This is
     on top of, not instead of, ``JointTarget.origin``'s own ``Literal`` type rejecting it a
     second time at message-build time.
  2. ``set_target(..., mode=...)`` refuses to update the target (raises ``RuntimeError``) if
     ``mode`` is one of ``BLOCKED_MODES`` - a caller passes the viewer's OWN current run mode
     each time and gets "policy output can never reach this client" enforced automatically,
     without having to remember a separate check.
  3. Every target is clamped through ``safe_clip`` (ROM) and a per-tick slew limit BEFORE it
     is packed into a message - the receiver's own guards are a second line, not the only
     line (docs/123 section 3: "사전 클램프 safe_clip·슬루" is explicitly the sender's job).

Nothing is sent until ``arm()`` is called, and nothing is sent again once ``disarm()`` is -
nothing about "armed" is encoded in the wire message itself (there is deliberately no
``armed`` field on ``JointTarget``: the UDP stream either exists or it doesn't, and the
receiver's own deadman treats "stream stopped" and "never armed" identically, which is the
same "just stop sending" idea HUPHY's own reference design uses (docs/123 section 3b)).
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from collections import deque
from typing import Callable, Mapping, Sequence

from ..contract import ModelContract
from ..schema import JointTarget, to_jsonl
from .tx_map import clamp_gain

logger = logging.getLogger(__name__)

DEFAULT_PORT = 9872
DEFAULT_HZ = 50.0
DEFAULT_KP_MAX = 5.0
DEFAULT_KD_MAX = 0.5
DEFAULT_TTL_MS = 250
"""Deliberately larger than the standard 0.2s (200ms) deadman default, with margin for a
couple of dropped packets at 50 Hz (20ms apart) - so a receiver's OWN ``deadman_s`` is what
governs staleness by default, not this message's ``ttl_ms`` racing ahead of it. Found the
hard way: ``JointTarget.ttl_ms``'s own schema default (100ms) is TIGHTER than the 200ms
deadman default, so leaving it unset made a receiver configured for "0.2s deadman" actually
trigger at ~0.1s (``DeadmanFilter.update`` takes ``min(deadman_s, ttl_ms/1000)`` - correct
behaviour, but not what a caller expecting the 0.2s number would predict)."""

BLOCKED_MODES = frozenset({"policy_sim", "policy_shadow"})
"""Viewer run-modes this client refuses to transmit from (docs/123 section 4: "policy output
must never reach the wire"). Independent of (not a substitute for) origin="manual"/"script"
at the message level - this catches the case where a caller's ``mode`` and ``origin`` have
drifted apart, e.g. a UI left in ``origin="manual"`` while the sim itself flipped into
``policy_sim`` for an unrelated reason."""


class TxClient:
  """Owns one UDP socket and (optionally) a background send thread.

  Two ways to drive it:

    * ``start()``/``stop()`` - a daemon thread sends the latest armed target at ``hz``,
      exactly the "50 Hz, latest-only, no waiting for an ack" design (docs/123 section 3b).
    * ``tick()`` - send exactly one packet now, for a caller with its own loop, or for a
      deterministic unit test that does not want to race a background thread.

  ``joint_names`` fixes the ORDER and the SET of joints this client will ever send - a
  ``set_target`` call with an unknown name is a configuration error (``ValueError``), not a
  silently-dropped joint (the same "hard failure, not a guess" rule as everywhere else in
  this bridge).
  """

  def __init__(
    self,
    host: str,
    port: int = DEFAULT_PORT,
    *,
    joint_names: Sequence[str],
    arm_token: str,
    origin: str,
    contract: ModelContract | None = None,
    safe_clip: Mapping[str, tuple[float, float]] | None = None,
    hard_range: Mapping[str, tuple[float, float]] | None = None,
    max_delta_rad: float | Mapping[str, float] | None = None,
    hz: float = DEFAULT_HZ,
    kp_max: float = DEFAULT_KP_MAX,
    kd_max: float = DEFAULT_KD_MAX,
    ttl_ms: int = DEFAULT_TTL_MS,
    src: str = "sim",
    frame: str = "model_v30",
    on_violation: Callable[[dict], None] | None = None,
    # First sequence number this client will send. Not 0 when the caller is REPLACING a
    # client that was already talking to a robot: the robot drops any message at or below the
    # highest seq it has accepted (`remote_target.LatestOnly.put`), so restarting the count
    # silently muted every command. See `tx.py::configure`.
    start_seq: int = 0,
  ) -> None:
    if origin not in ("manual", "script"):
      raise RuntimeError(
        f"origin must be 'manual' or 'script', got {origin!r} - policy output must never "
        "be transmitted (docs/123 section 4)"
      )
    if not arm_token:
      raise RuntimeError("arm_token must be non-empty")
    if hz <= 0:
      raise ValueError(f"hz must be > 0, got {hz}")

    self.host = host
    self.port = port
    self.joint_names = list(joint_names)
    self.arm_token = arm_token
    self.origin = origin
    self.hz = float(hz)
    self.ttl_ms = int(ttl_ms)
    self.kp_max = float(kp_max)
    self.kd_max = float(kd_max)
    self.src = src
    self.frame = frame
    self.contract_hash = contract.contract_sha if contract is not None else None
    # A2 (2026-09-04): optional hook, called with {"joint","value","limit_lo","limit_hi"}
    # every time _clamp_positions actually clips a value against safe_clip - lets a caller
    # (pygviewer/tx.py's TxState) forward send-side clamps into the shared violation log
    # without this generic, HUPHY-agnostic client importing anything about that log itself.
    self._on_violation = on_violation

    # safe_clip: explicit dict wins; else derive from the contract (only for joints the
    # contract actually knows). A joint outside that set falls back to `hard_range` (ROM
    # clip task, 2026-09-04: e.g. a per-joint ROM sourced from a joint-map's optional
    # `rom_deg`, converted to rad by the caller) if the caller supplied one for it; only a
    # joint with NEITHER a contract entry NOR an explicit hard_range is sent truly
    # unclamped, with a one-time warning - never silently invented a range for.
    self._safe_clip: dict[str, tuple[float, float]] = dict(safe_clip or {})
    self._hard_range: dict[str, tuple[float, float]] = dict(hard_range or {})
    for n in self.joint_names:
      if n in self._safe_clip:
        continue
      got = None
      if contract is not None:
        try:
          got = contract.clip(n)
        except KeyError:
          got = None  # not an actuated joint of this contract
      if got is None:
        got = self._hard_range.get(n)
      if got is not None:
        self._safe_clip[n] = got
      # else: no explicit safe_clip, no contract entry, no hard_range for this joint -
      # left truly unclamped (`_safe_clip.get(n, ...)` falls through to (-inf, inf) in
      # `_clamp_positions`), exactly today's pre-existing behaviour.

    if isinstance(max_delta_rad, Mapping):
      self._max_delta: dict[str, float] = dict(max_delta_rad)
    elif max_delta_rad is not None:
      self._max_delta = {n: float(max_delta_rad) for n in self.joint_names}
    else:
      self._max_delta = {}

    self._sock: socket.socket | None = None
    self._thread: threading.Thread | None = None
    self._running = False
    self._armed = False
    self._lock = threading.Lock()
    self._pending: dict | None = None
    self._prev_sent: dict[str, float] = {}
    self._seq = int(start_seq)
    self.sent_count = 0
    self.warnings: deque[str] = deque(maxlen=50)

  # ------------------------------------------------------------------------------ read-only
  @property
  def last_sent(self) -> dict[str, float]:
    """The clamped (safe_clip + slew) position of the LAST message actually built by
    :meth:`tick` - for a caller (``pygviewer/tx.py``'s wrapper, in this codebase) that wants
    to display "what was actually sent" without keeping its own copy of every message."""
    return dict(self._prev_sent)

  @property
  def last_seq(self) -> int | None:
    """``seq`` of the last message :meth:`tick` actually sent, or ``None`` if nothing has
    been sent yet on this client."""
    return self._seq - 1 if self._seq > 0 else None

  # ------------------------------------------------------------------------------ lifecycle
  def start(self) -> None:
    if self._sock is None:
      self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if self._thread is None:
      self._running = True
      self._thread = threading.Thread(target=self._loop, name="pygviewer-tx-client", daemon=True)
      self._thread.start()

  def stop(self) -> None:
    self._running = False
    if self._thread is not None:
      self._thread.join(timeout=2.0)
      self._thread = None
    if self._sock is not None:
      self._sock.close()
      self._sock = None

  def __enter__(self) -> "TxClient":
    self.start()
    return self

  def __exit__(self, *exc) -> None:
    self.stop()

  # ---------------------------------------------------------------------------------- arm
  def arm(self) -> None:
    self._armed = True

  def disarm(self) -> None:
    self._armed = False
    with self._lock:
      self._pending = None
    self._prev_sent.clear()  # next arm starts slew fresh, not mid-ramp from a stale pose

  @property
  def armed(self) -> bool:
    return self._armed

  # ------------------------------------------------------------------------------- target
  def set_target(
    self,
    values: Mapping[str, float],
    *,
    kp: Mapping[str, float] | None = None,
    kd: Mapping[str, float] | None = None,
    tau_ff: Mapping[str, float] | None = None,
    mode: str | None = None,
  ) -> None:
    """Replace the target this client will send on its next tick.  Nothing is sent by this
    call itself - only ``tick()``/the background thread ever touch the socket, which is what
    makes "the mouse/key was released, so I called set_target one more time with nothing
    changing and then stopped calling it" (the viewer's keyboard-deadman story) equivalent to
    just not calling this again: the LAST value sits here until ``disarm()`` clears it.

    ``mode``, if given, is checked against ``BLOCKED_MODES`` and raises ``RuntimeError`` for
    ``policy_sim``/``policy_shadow`` - pass the viewer's current run mode here every call and
    this client refuses to update the target while a policy owns the sim (docs/123 section 4).
    """
    if mode is not None and mode in BLOCKED_MODES:
      raise RuntimeError(
        f"mode={mode!r} is blocked - policy output must never be transmitted "
        f"(docs/123 section 4, BLOCKED_MODES={sorted(BLOCKED_MODES)})"
      )
    unknown = sorted(set(values) - set(self.joint_names))
    if unknown:
      raise ValueError(f"unknown joint(s) for this client: {unknown} (configured: {self.joint_names})")
    with self._lock:
      self._pending = dict(values=dict(values), kp=dict(kp) if kp else None,
                           kd=dict(kd) if kd else None, tau_ff=dict(tau_ff) if tau_ff else None)

  # --------------------------------------------------------------------------------- send
  def _clamp_positions(self, values: Mapping[str, float]) -> tuple[list[str], list[float]]:
    names = [n for n in self.joint_names if n in values]
    out: list[float] = []
    for n in names:
      v = float(values[n])
      lo, hi = self._safe_clip.get(n, (float("-inf"), float("inf")))
      clipped = min(max(v, lo), hi)
      if clipped != v:
        self.warnings.append(f"{n}: safe_clip {v:.4f} -> {clipped:.4f} rad")
        if self._on_violation is not None:
          self._on_violation({"joint": n, "value": v, "limit_lo": lo, "limit_hi": hi})
      delta_cap = self._max_delta.get(n)
      prev = self._prev_sent.get(n, clipped)
      if delta_cap is not None:
        step = clipped - prev
        step = min(max(step, -delta_cap), delta_cap)
        clipped = prev + step
      self._prev_sent[n] = clipped
      out.append(clipped)
    return names, out

  def _clamp_gains(self, names: list[str], gains: Mapping[str, float] | None, cap: float,
                    label: str) -> list[float] | None:
    if gains is None:
      return None
    out = []
    for n in names:
      v = float(gains.get(n, 0.0))
      clamped, warns = clamp_gain(v, cap, name=f"{label}[{n}]")
      self.warnings.extend(warns)
      out.append(clamped)
    return out

  def build_message(self) -> JointTarget | None:
    """Build the next ``JointTarget`` from the current pending target, or ``None`` if
    unarmed / nothing has been set yet.  Exposed publicly so a test (or a caller with its own
    transport) can get a fully-clamped message without touching a socket."""
    if not self._armed:
      return None
    with self._lock:
      pending = self._pending
    if pending is None:
      return None
    names, q = self._clamp_positions(pending["values"])
    if not names:
      return None
    kp = self._clamp_gains(names, pending["kp"], self.kp_max, "kp")
    kd = self._clamp_gains(names, pending["kd"], self.kd_max, "kd")
    tau_ff = [float(pending["tau_ff"].get(n, 0.0)) for n in names] if pending["tau_ff"] else None
    msg = JointTarget(
      t_ns=time.monotonic_ns(),
      seq=self._seq,
      src=self.src,
      frame=self.frame,
      contract_hash=self.contract_hash,
      joint_names=names,
      q_target=q,
      kp=kp,
      kd=kd,
      tau_ff=tau_ff,
      ttl_ms=self.ttl_ms,
      arm_token=self.arm_token,
      origin=self.origin,
    )
    self._seq += 1
    return msg

  def tick(self) -> JointTarget | None:
    """Send exactly one packet now (if armed and a target has been set).  Returns the message
    actually sent, or ``None`` if nothing went out this tick - a caller can use the return
    value to know whether the deadman side would see fresh data."""
    msg = self.build_message()
    if msg is None:
      return None
    if self._sock is None:
      self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self._sock.sendto(to_jsonl(msg).strip().encode("utf-8"), (self.host, self.port))
    self.sent_count += 1
    return msg

  def _loop(self) -> None:
    period = 1.0 / self.hz
    while self._running:
      t0 = time.monotonic()
      try:
        self.tick()
      except Exception as e:  # noqa: BLE001 - a send-loop thread must never die silently
        logger.warning("tx_client send failed: %s", e)
      elapsed = time.monotonic() - t0
      time.sleep(max(0.0, period - elapsed))
