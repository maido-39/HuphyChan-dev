"""UI v2 TX (viewer -> hardware) control plane, wired to a REAL sender, 2026-09-04.

This supersedes the earlier STUB (see ``git log -p -- tools/pygviewer/pygviewer/tx.py`` for
that version's docstring): ``bridge/tx_client.py`` now exists (docs/123 "plan A", built by a
different coder while this module was still a stub) and this file's job is exactly what its
own stub docstring said it would be - "the transmit call is the only thing that needs to
change once tx_client.py lands". Every safety gate below is now load-bearing, not decorative:
:meth:`TxState.on_control_tick` is the one and only place a real UDP packet can leave this
process, and it is called from ``SimCore._on_control_tick`` (50 Hz, matching
``TxClient``'s own nominal send rate 1:1 since this model's control tick already runs at 50
Hz - see ``sim_core.py``'s module docstring) regardless of what the API layer did that tick.

Two-stage arm + a THIRD, independent keyboard dead-man, matching docs/123 section 4 and the
2026-09-04 wiring brief exactly:

  1. ``POST /tx/config`` (:meth:`configure`) - (re)builds the underlying ``TxClient``: host,
     port, and the joint SET this client will ever know about (``enable`` becomes the
     client's own ``joint_names`` - a joint outside it is never sendable at all, not merely
     filtered per-tick, so "enable" is a hard allow-list, not a checkbox on top of a client
     that could send anything). Refused while armed (disarm first) so the wire format never
     changes mid-stream.
  2. ``POST /tx/enable {"on": ...}`` (:meth:`set_enabled`) - stage 1, "is the TX subsystem on
     at all". Requires a prior ``/tx/config``. Turning it off also disarms.
  3. ``POST /tx/arm`` / ``POST /tx/disarm`` (:meth:`arm`/:meth:`disarm`) - stage 2. ``arm`` is
     refused (409) unless stage 1 is on AND the sim mode is exactly ``"manual"`` - the Joints
     tab's live sliders AND a running ``POST /script/run`` sequence both run under
     ``mode="manual"`` (see ``modes.py``'s docstring: there is no separate "script" mode),
     and ``policy_sim``/``policy_shadow`` never do - policy output must never be
     transmittable (docs/121 section 10 TX item).
  4. ``POST /tx/heartbeat`` (:meth:`heartbeat`) - the KEYBOARD dead-man (dashboard: Space,
     held, called every ~100 ms while held). This is deliberately NOT the same thing as
     "armed": while armed but the last heartbeat is older than ``DEADMAN_TIMEOUT_S`` (0.3 s),
     :meth:`on_control_tick` simply stops calling the client's send path - it does **not**
     call ``disarm()``. That is the point (2026-09-04 wiring brief): the viewer goes quiet,
     and the ROBOT's own age-based dead-man (``bridge.remote_target``, 0.2 s) notices the
     stream stopped and runs ITS OWN hold -> return-to-default - exactly as if an operator
     had pulled the ethernet cable, not as if the operator had pressed a "stop" button.
     Calling ``TxClient.disarm()`` here instead would reset its slew-continuity state (see
     that method's own docstring: "next arm starts slew fresh") for no safety benefit, and
     would require a fresh ``POST /tx/arm`` (a mode-gated, 409-able call) just to resume
     sending after letting go of a key for a fraction of a second - releasing Space must be
     cheap to recover from, disarming must not be.
  5. Structural, every control tick, independent of the API layer having been called that
     tick at all: :meth:`check_mode_gate` auto-disarms (both this wrapper's own state AND the
     underlying ``TxClient``) the instant the mode is no longer ``"manual"`` - the same
     "structural, not just a UI checkbox" pattern this codebase already uses for
     ``modes.SHADOW_MAY_TRANSMIT``.

:meth:`on_control_tick` is also the ONLY thing in this module that ever sees a joint target
value, and it is always ``SimCore.target`` (the manual slider / script player's current
command) - a policy's action lives in a completely different code path
(``SimCore._policy_tick`` -> ``self.last_action``/``self._policy_target``) and is never once
passed to this class, by construction, not by a runtime check that could be forgotten.
"""

from __future__ import annotations

import secrets
import time
from collections import deque

from .bridge.tx_client import DEFAULT_KD_MAX, DEFAULT_KP_MAX, DEFAULT_TTL_MS, TxClient

DEADMAN_TIMEOUT_S = 0.3
"""Keyboard dead-man (Space, held) timeout - independent of the robot-side age-based dead-man
in ``bridge.remote_target`` (0.2s deadman_s there); this one governs whether THIS PROCESS
keeps calling the client's send path at all, see the module docstring item 4."""

# docs/123 section 3 (user decision, 2026-09-04): the first hardware experiment is one bench
# motor (RS03) at kp<=5. These are the DEFAULT caps offered in the dashboard's TX panel and
# passed straight to TxClient(kp_max=..., kd_max=...), which enforces them on every message.
DEFAULT_KP_CAP = DEFAULT_KP_MAX
DEFAULT_KD_CAP = DEFAULT_KD_MAX


class TxNotAllowed(RuntimeError):
  """Raised by every TxState method that refuses to act - always a 409 at the API layer."""


class TxState:
  """Owns exactly one (possibly ``None``) :class:`bridge.tx_client.TxClient` and the
  enable/arm/heartbeat state machine wrapped around it."""

  def __init__(self, act_names: list[str], contract=None):
    self.act_names = list(act_names)
    self.contract = contract
    # A shared secret this process makes up once and reports in status() - an operator
    # copies it verbatim into the receiver's own --arm-token (dummy_rx.py /
    # huphy_remote_motion.py both require one; there is deliberately no built-in default so a
    # stale/forgotten value can never match by accident).
    self.arm_token = secrets.token_hex(8)

    self.host: str | None = None
    self.port: int | None = None
    self.enabled_motors: list[str] = []
    self.kp_max = DEFAULT_KP_CAP
    self.kd_max = DEFAULT_KD_CAP
    self.ttl_ms = DEFAULT_TTL_MS

    self._client: TxClient | None = None
    self.enabled = False  # stage 1
    self.armed = False  # stage 2 - mirrors self._client.armed once one exists
    self.disarm_reason: str | None = None
    self.rejected_count = 0
    self._last_heartbeat: float | None = None
    self._send_times: deque[float] = deque(maxlen=200)  # for a MEASURED rate, not nominal

  # -------------------------------------------------------------------------- stage 0: config
  def configure(
    self,
    host: str,
    port: int,
    enable: list[str],
    kp_max: float | None = None,
    kd_max: float | None = None,
    ttl_ms: int | None = None,
  ) -> None:
    if self.armed:
      raise TxNotAllowed("cannot reconfigure while armed - POST /tx/disarm first")
    unknown = sorted(set(enable) - set(self.act_names))
    if unknown:
      raise TxNotAllowed(f"not actuated joints of this model: {unknown}")
    self.host, self.port = host, int(port)
    self.enabled_motors = list(enable)
    self.kp_max = float(kp_max) if kp_max is not None else DEFAULT_KP_CAP
    self.kd_max = float(kd_max) if kd_max is not None else DEFAULT_KD_CAP
    self.ttl_ms = int(ttl_ms) if ttl_ms is not None else DEFAULT_TTL_MS
    if self._client is not None:
      self._client.stop()
    # joint_names fixes the SET this client will ever send (bridge.tx_client.TxClient's own
    # docstring) - an empty `enable` list is a valid, safe default: nothing is ever sendable
    # until an operator opts joints in.
    self._client = TxClient(
      self.host,
      self.port,
      joint_names=self.enabled_motors,
      arm_token=self.arm_token,
      origin="manual",
      contract=self.contract,
      kp_max=self.kp_max,
      kd_max=self.kd_max,
      ttl_ms=self.ttl_ms,
    )
    self.enabled = False
    self.armed = False
    self.disarm_reason = None

  # -------------------------------------------------------------------------- stage 1: enable
  def set_enabled(self, on: bool) -> None:
    if on:
      if self._client is None:
        raise TxNotAllowed("no TX config yet - POST /tx/config first (host/port/enable)")
      self.enabled = True
    else:
      self.enabled = False
      self.disarm(reason="TX panel deactivated")

  # -------------------------------------------------------------------------- stage 2: arm
  def arm(self, mode: str) -> None:
    if not self.enabled or self._client is None:
      raise TxNotAllowed(
        "TX arm refused: the TX panel is not enabled - POST /tx/config then "
        'POST /tx/enable {"on": true} first'
      )
    if mode != "manual":
      raise TxNotAllowed(
        f"TX arm refused: sim mode is {mode!r}. Only 'manual' (the Joints tab, or a "
        "running POST /script/run sequence) may arm TX - policy output must never be "
        "transmittable (docs/121 section 10 TX item)."
      )
    self._client.arm()
    self.armed = True
    self.disarm_reason = None
    self._last_heartbeat = time.monotonic()

  def disarm(self, reason: str = "operator") -> None:
    was_armed = self.armed
    self.armed = False
    if was_armed:
      self.disarm_reason = reason
    if self._client is not None:
      self._client.disarm()

  def heartbeat(self) -> None:
    if not self.armed:
      raise TxNotAllowed("cannot heartbeat: not armed")
    self._last_heartbeat = time.monotonic()

  def check_mode_gate(self, mode: str) -> None:
    """Call every control tick (``SimCore._on_control_tick``) regardless of what the API
    layer checked - structural enforcement, not a UI-only checkbox."""
    if self.armed and mode != "manual":
      self.disarm(reason=f"mode changed to {mode!r} while armed")

  # -------------------------------------------------------------------------------- deadman
  def _heartbeat_fresh(self) -> bool:
    if self._last_heartbeat is None:
      return False
    return (time.monotonic() - self._last_heartbeat) < DEADMAN_TIMEOUT_S

  def sending(self) -> bool:
    """True the instant this process would actually put a packet on the wire THIS tick -
    enabled, armed, and the keyboard dead-man fresh. False does NOT mean disarmed: a stale
    heartbeat alone (Space released) makes this False while ``armed`` stays True - see the
    module docstring item 4. This is what the dashboard badge and ``GET /tx/status``'s
    ``sending`` field both read."""
    return (
      self.enabled
      and self.armed
      and self._client is not None
      and self._client.armed
      and self._heartbeat_fresh()
    )

  # -------------------------------------------------------------------------- control tick
  def on_control_tick(
    self,
    mode: str,
    target_values: dict[str, float],
    kp_values: dict[str, float] | None = None,
    kd_values: dict[str, float] | None = None,
  ) -> None:
    """Call once per SimCore control tick. ``target_values`` must be exactly
    ``SimCore.target`` zipped with ``SimCore.act_names`` - the current manual/script command,
    never a policy action (docs/123 section 4; see the module docstring)."""
    if not self.sending():
      return
    # TxClient.joint_names is the hard allow-list fixed at /tx/config time (self.enabled_motors)
    # - SimCore hands us EVERY actuated joint's current target every tick, filtered down here
    # to exactly what this client was configured to ever know about (anything else would be
    # a ValueError at set_target, which is correct for a caller with a wrong joint name, but
    # SimCore always passes its full act_names set by design, see the module docstring).
    known = set(self._client.joint_names)
    values = {n: v for n, v in target_values.items() if n in known}
    kp = {n: v for n, v in (kp_values or {}).items() if n in known} or None
    kd = {n: v for n, v in (kd_values or {}).items() if n in known} or None
    try:
      self._client.set_target(values, mode=mode, kp=kp, kd=kd)
      msg = self._client.tick()
    except RuntimeError as exc:
      # BLOCKED_MODES safety net - defense in depth on top of check_mode_gate, which should
      # already have disarmed before `mode` could ever reach here as non-manual.
      self.rejected_count += 1
      self.disarm(reason=f"send refused: {exc}")
      return
    if msg is not None:
      self._send_times.append(time.monotonic())

  # -------------------------------------------------------------------------------- status
  def status(self) -> dict:
    now = time.monotonic()
    window_s = 2.0
    while self._send_times and now - self._send_times[0] > window_s:
      self._send_times.popleft()
    rate_hz = round(len(self._send_times) / window_s, 1) if self._send_times else 0.0
    deadman_age = None if self._last_heartbeat is None else round(now - self._last_heartbeat, 3)
    last_sent_target = dict(self._client.last_sent) if self._client is not None else {}
    last_seq = self._client.last_seq if self._client is not None else None
    return dict(
      armed=self.armed,
      sending=self.sending(),
      enable=list(self.enabled_motors),
      enabled=self.enabled,
      host=self.host,
      port=self.port,
      last_seq=last_seq,
      rate_hz=rate_hz,
      deadman_age_s=deadman_age,
      deadman_timeout_s=DEADMAN_TIMEOUT_S,
      rejected_count=self.rejected_count,
      disarm_reason=self.disarm_reason,
      last_sent_target=last_sent_target,
      kp_max=self.kp_max,
      kd_max=self.kd_max,
      ttl_ms=self.ttl_ms,
      arm_token=self.arm_token,
      warnings=list(self._client.warnings) if self._client is not None else [],
    )
