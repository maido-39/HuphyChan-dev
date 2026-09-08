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
     and ``policy_sim`` does so ONLY when this config opted in via ``allow_policy`` (which
     additionally forces a per-packet ``max_step_deg`` cap). ``policy_shadow`` never does.
     This paragraph read "policy output must never be transmittable" until 2026-09-08; that
     stopped being true when ``allow_policy`` was added for the user's "정책으로 실물 일부
     구동" scenario, and a stale absolute here sends anyone debugging "why does the policy not
     reach the motor" past the one place that actually gates it (:meth:`mode_allowed`).
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

import math
import os
import secrets
import time
from collections import deque

from . import packet_log as packet_log_mod
from .bridge.tx_client import DEFAULT_KD_MAX, DEFAULT_KP_MAX, DEFAULT_TTL_MS, TxClient
from .schema import RobotCommand
from .violations import ViolationLog

DEADMAN_TIMEOUT_S = 0.3
"""Keyboard dead-man (Space, held) timeout - independent of the robot-side age-based dead-man
in ``bridge.remote_target`` (0.2s deadman_s there); this one governs whether THIS PROCESS
keeps calling the client's send path at all, see the module docstring item 4."""

# docs/123 section 3 (user decision, 2026-09-04): the first hardware experiment is one bench
# motor (RS03) at kp<=5. These are the DEFAULT caps offered in the dashboard's TX panel and
# passed straight to TxClient(kp_max=..., kd_max=...), which enforces them on every message.
DEFAULT_KP_CAP = DEFAULT_KP_MAX
DEFAULT_KD_CAP = DEFAULT_KD_MAX

DEFAULT_TX_PORT = 9872
"""Port the robot-side receiver (``bridge.huphy_remote_motion --listen 0.0.0.0:9872``) binds.
Only a DEFAULT for the pre-configure state below - ``configure`` always takes the real one
from the operator."""

POLICY_MODES = ("policy_sim",)
"""Sim modes whose target a policy writes, and which :meth:`TxState.configure` can be asked
to allow through to the motors.

``policy_shadow`` is deliberately NOT here: it exists to watch a policy WITHOUT letting it
drive (``modes.SHADOW_MAY_TRANSMIT``), and a shadow that reaches the motors is a contradiction
in terms. The replay modes are not here either - a recording driving hardware is a separate
decision with its own failure modes, and nobody has asked for it."""


def _env_tx_target() -> tuple[str | None, int]:
  """Where TX *would* send, before anyone has pressed "1. configure".

  2026-09-07 bench.  The dashboard's TX panel used to open with ``127.0.0.1`` typed into its
  host box as a plain HTML default, and nothing ever wrote the live config back into that
  box - so after any rebuild of the panel the form read "127.0.0.1" while this object held
  the real robot (10.8.0.14).  Pressing "1. configure" then re-pointed TX at loopback, where
  nothing listens, and the failure looks exactly like "the robot stopped responding": the
  panel is green, the sequence counter climbs, and no packet ever reaches a motor.

  Seeding host/port from the environment (``PYG_TX_HOST`` / ``PYG_TX_PORT``, set by
  ``tools/dashboard/start_all.sh``) means the box shows the address that is actually wanted
  from the first paint.  This does NOT make TX sendable - ``self._client`` stays ``None``
  until :meth:`configure` runs, which is what every send path checks.
  """
  host = (os.environ.get("PYG_TX_HOST") or "").strip() or None
  raw = (os.environ.get("PYG_TX_PORT") or "").strip()
  try:
    port = int(raw) if raw else DEFAULT_TX_PORT
  except ValueError:
    port = DEFAULT_TX_PORT
  return host, port


def _env_float(name: str, fallback: float) -> float:
  raw = (os.environ.get(name) or "").strip()
  if not raw:
    return fallback
  try:
    return float(raw)
  except ValueError:
    return fallback


def _env_gain_caps() -> tuple[float, float]:
  """Transmit gain caps the panel opens with (``PYG_TX_KP_MAX`` / ``PYG_TX_KD_MAX``).

  2026-09-07 bench.  ``DEFAULT_KP_CAP`` is 5, chosen for the very first single-motor
  experiment.  This bench then MEASURED that 5 sits below the joints' break-away friction -
  a 5 deg command on the knee produced 0.04 deg of motion - and settled on knee 20 /
  hip_yaw 10 under a cap of 30.  A viewer restart silently reverted the cap to 5, and the
  next session read the resulting 0.01 N*m of torque as "the motors are disconnected"
  (docs/127 section 2-3).  A hard-won working value must not be lost to a process restart.
  """
  return _env_float("PYG_TX_KP_MAX", DEFAULT_KP_CAP), _env_float("PYG_TX_KD_MAX", DEFAULT_KD_CAP)


class TxNotAllowed(RuntimeError):
  """Raised by every TxState method that refuses to act - always a 409 at the API layer."""


class TxState:
  """Owns exactly one (possibly ``None``) :class:`bridge.tx_client.TxClient` and the
  enable/arm/heartbeat state machine wrapped around it."""

  def __init__(self, act_names: list[str], contract=None, violations: ViolationLog | None = None,
               state_fn=None):
    self.act_names = list(act_names)
    self.contract = contract
    # A2 (2026-09-04): the SAME shared record log SimCore hands to RealState, so a send-side
    # safe_clip or a mode-gate refusal lands in the same GET /violations a recv-side ROM
    # violation does - see violations.py's module docstring.
    self.violations = violations
    # Reads the measured real pose at send time, so every logged packet carries the state it
    # was computed against - a command alone cannot be judged after the fact (packet_log.py).
    self.state_fn = state_fn
    # A shared secret this process reports in status(); an operator copies it verbatim into
    # the receiver's own --arm-token (dummy_rx.py / huphy_remote_motion.py both require one;
    # there is deliberately no built-in default, so a stale or forgotten value can never
    # match by accident).
    #
    # Normally made up fresh each start. That is safe but it means **restarting the viewer
    # kills the robot silently**: the receiver keeps checking the OLD token, drops every
    # command as `rejected_arm_token`, and nothing on screen says so - the link, the loop and
    # the telemetry all stay green while the joints simply stop responding (bench, twice on
    # 2026-09-05). Setting PYG_ARM_TOKEN pins it, so the viewer can be restarted without
    # restarting the robot too. Pin it only where the operator controls both ends - it is
    # still a shared secret, so it does not belong in a shell history or a committed file.
    env_token = (os.environ.get("PYG_ARM_TOKEN") or "").strip()
    if env_token:
      self.arm_token = env_token
      self.arm_token_pinned = True
    else:
      self.arm_token = secrets.token_hex(8)
      self.arm_token_pinned = False

    self.host, self.port = _env_tx_target()  # display-only until configure(); see _env_tx_target
    # Packet-level debug log, off unless PYG_TX_LOG names a file (packet_log.py). One log for
    # the life of this process, handed to every TxClient `configure` builds, so a reconfigure
    # does not start a new file mid-incident.
    self.packet_log = packet_log_mod.from_env()
    self.enabled_motors: list[str] = []
    self.kp_max, self.kd_max = _env_gain_caps()
    self.ttl_ms = DEFAULT_TTL_MS
    # Policy output reaching the motors: off unless configure() is explicitly asked for it,
    # and refused there without a per-tick step cap. See configure()'s docstring.
    self.allow_policy = False
    self.max_step_deg: float | None = None

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
    allow_policy: bool = False,
    max_step_deg: float | None = None,
  ) -> None:
    """(Re)build the underlying client.

    ``allow_policy`` lets a policy's own output through to the motors (user decision,
    2026-09-08: "Policy 출력 실제로 모터 제어하는거 시작해줘"). It defaults to False, and with
    it False every path here behaves exactly as it did before this parameter existed.

    ``max_step_deg`` caps how far a transmitted target may move per packet, anchored to the
    PREVIOUS COMMAND (``TxClient._clamp_positions``) - the same anchor the robot's own rate
    limit uses, and for the same reason: anchoring to the measurement instead turns a speed
    limit into a torque cap and makes the command stop advancing whenever the motor lags.

    **``allow_policy`` requires ``max_step_deg``**, and this refuses the combination without
    it. Every other guard in this file is checked once, at arm time: the sync gate, the
    arm-jump ceiling, the mode. An operator's targets then change only as fast as a hand moves
    a slider. A policy rewrites all of them every 20 ms, so a once-at-arm check is no
    protection at all after the first packet, and the per-packet cap is the only thing that
    is. Refusing here rather than warning keeps that from being an option someone forgets.
    """
    if self.armed:
      raise TxNotAllowed("cannot reconfigure while armed - POST /tx/disarm first")
    unknown = sorted(set(enable) - set(self.act_names))
    if unknown:
      raise TxNotAllowed(f"not actuated joints of this model: {unknown}")
    if allow_policy and (max_step_deg is None or float(max_step_deg) <= 0):
      raise TxNotAllowed(
        "allow_policy needs max_step_deg (degrees per packet, > 0): a policy rewrites every "
        "target 50 times a second, so the arm-time checks stop protecting anything after the "
        "first packet and the per-packet step cap is the only guard left"
      )
    self.host, self.port = host, int(port)
    self.enabled_motors = list(enable)
    env_kp, env_kd = _env_gain_caps()
    self.kp_max = float(kp_max) if kp_max is not None else env_kp
    self.kd_max = float(kd_max) if kd_max is not None else env_kd
    self.ttl_ms = int(ttl_ms) if ttl_ms is not None else DEFAULT_TTL_MS
    self.allow_policy = bool(allow_policy)
    self.max_step_deg = float(max_step_deg) if max_step_deg is not None else None
    # Carry the sequence counter across the rebuild (2026-09-05 bench).  `configure` replaces
    # the TxClient, and a fresh one starts at seq 0 - but the ROBOT remembers the highest seq
    # it has accepted and drops anything at or below it (`remote_target.LatestOnly.put`).  So
    # a reconfigure made the robot ignore every command until the new counter climbed back
    # past the old high-water mark, with nothing on screen to say so: joints simply stopped
    # responding while the loop, the link and the telemetry all looked perfect.  Measured on
    # the bench: accepted=843 against rejected_seq=5823, and a whole gain sweep silently did
    # nothing.  A viewer RESTART hits the same wall from the other side, which
    # `LatestOnly` now handles itself.
    resume_seq = 0
    if self._client is not None:
      last = self._client.last_seq
      resume_seq = 0 if last is None else last + 1
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
      on_violation=self._on_client_violation if self.violations is not None else None,
      packet_log=self.packet_log,
      state_fn=self.state_fn,
      start_seq=resume_seq,
      # Per-packet step cap, anchored to the previous COMMAND. None keeps the old behaviour
      # (no slew limit at all) for manual driving, where a hand on a slider is the limit.
      max_delta_rad=(math.radians(self.max_step_deg) if self.max_step_deg else None),
      allow_modes=(frozenset(POLICY_MODES) if self.allow_policy else frozenset()),
    )
    self.enabled = False
    self.armed = False
    self.disarm_reason = None

  # -------------------------------------------------------------------------- recovery
  def send_command(self, op: str, reason: str | None = None) -> dict:
    """Send one recovery action to the robot (schema.RobotCommand).

    2026-09-08, user: "모터 Kill 된 경우에 리셋하는 버튼은?" - there was none. A latched motor
    stops producing torque and refuses commands until the latch is cleared, and the only thing
    that cleared it was the robot bridge's own startup, so recovery meant an ssh session and a
    process restart for a condition the operator can already see on screen.

    Deliberately allowed while DISARMED, and deliberately not gated on the sync or the mode.
    A motor that has cut out is exactly the situation where arming is impossible, so requiring
    an arm first would make this useless precisely when it is needed. What it is NOT allowed
    to do is move anything: the command carries no target, and the robot applies none.

    ``clear_fault`` DISARMS first if armed, and that is the point rather than a convenience.
    A cut-out joint freezes where it died, but nothing upstream notices: the policy keeps
    walking, and both rate limits that stand between it and the motor - this side's
    ``_prev_sent`` slew and the robot's ``clamp_rate`` - are anchored to the PREVIOUS COMMAND,
    which advanced right along with it. So neither one can see the gap that opened, and the
    instant torque comes back the standing command is wherever the policy walked to. Over one
    gait cycle that is the joint's whole swing (measured 2026-09-08: knee 16.1 -> 54.6 deg,
    38.5 deg of travel), delivered as a single step against kp. Disarming forces the operator
    back through :meth:`arm`, which re-seeds the slew ramp from the MEASURED position and
    re-checks the 10 deg arm gate - the two checks that are anchored to the real joint and
    therefore the only two that can still see the divergence.
    """
    if self._client is None:
      raise TxNotAllowed(
        "no TX config yet - POST /tx/config first (the robot's address comes from there)"
      )
    disarmed = False
    if op == "clear_fault" and self.armed:
      self.disarm(reason="clear_fault: re-arm from the joint's real position before commanding it")
      disarmed = True
    msg = RobotCommand(
      t_ns=time.monotonic_ns(),
      seq=0,
      src="sim",
      frame=self._client.frame,
      contract_hash=self._client.contract_hash,
      op=op,
      arm_token=self.arm_token,
      reason=reason,
    )
    self._client.send_raw(msg)
    if self.packet_log is not None:
      self.packet_log.write("cmd", {"op": op, "reason": reason})
    return {"sent": op, "to": f"{self.host}:{self.port}", "reason": reason,
            "disarmed": disarmed}

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
  def check_armable(self, mode: str) -> None:
    """The two checks :meth:`arm` makes BEFORE it mutates any state, split out so a caller
    (``api.py``'s ``POST /tx/arm``, which also has to check the sync-before-arm gate -
    ``hw_sync.py``, docs/123 section 10.2) can check "would arm() succeed on TX's own terms"
    without side effects, so config/mode problems always surface before a "you haven't synced
    yet" message even when the sync check would ALSO fail - the more fundamental setup step
    (0. configure/1. enable, in the dashboard's own numbering) is what an operator needs to
    see first. Raises exactly what :meth:`arm` itself would raise, with the same wording."""
    if not self.enabled or self._client is None:
      raise TxNotAllowed(
        "TX arm refused: the TX panel is not enabled - POST /tx/config then "
        'POST /tx/enable {"on": true} first'
      )
    if not self.mode_allowed(mode):
      allowed = "'manual'" + (f" or {POLICY_MODES}" if self.allow_policy else "")
      raise TxNotAllowed(
        f"TX arm refused: sim mode is {mode!r}, and this TX config allows {allowed}. "
        "'manual' covers the Joints tab and a running POST /script/run sequence; a policy "
        'mode needs POST /tx/config {"allow_policy": true, "max_step_deg": ...} first.'
      )

  def arm(self, mode: str) -> None:
    self.check_armable(mode)
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
    """Record that the operator is holding the key. Accepted while DISARMED too.

    It used to refuse unless armed, which made "is a human present" unmeasurable until after
    arming - and the one-press scenario runner (``scenario_runner.py``, 2026-09-08) needs the
    opposite order: it must confirm the operator is holding the key BEFORE it arms anything,
    because arming is itself one of the steps it performs on their behalf. A chicken-and-egg
    that would otherwise be resolved by the runner faking a heartbeat, which is precisely the
    thing the dead-man exists to prevent.

    Accepting it disarmed loosens nothing: this timestamp only ever GATES sending
    (:meth:`on_control_tick` also requires ``armed`` and ``enabled``), it never causes it."""
    self._last_heartbeat = time.monotonic()

  def mode_allowed(self, mode: str) -> bool:
    """Whether TX may be armed, and stay armed, in this sim mode.

    ``manual`` always - the Joints tab and a running script both run under it. A policy mode
    only when this config opted in (:meth:`configure`), which additionally forces a per-packet
    step cap. One predicate, used by BOTH the arm check and the every-tick gate below, so the
    two can never drift into disagreeing about what is allowed."""
    if mode == "manual":
      return True
    return bool(self.allow_policy) and mode in POLICY_MODES

  def check_mode_gate(self, mode: str) -> None:
    """Call every control tick (``SimCore._on_control_tick``) regardless of what the API
    layer checked - structural enforcement, not a UI-only checkbox."""
    if self.armed and not self.mode_allowed(mode):
      self.disarm(reason=f"mode changed to {mode!r} while armed")

  # -------------------------------------------------------------------------- violations (A2)
  def _on_client_violation(self, info: dict) -> None:
    """``TxClient``'s ``on_violation`` callback (see ``bridge/tx_client.py``'s
    ``_clamp_positions``) - a pre-send ``safe_clip`` clamp, forwarded into the shared log
    under ``side="send"``."""
    self.violations.record(
      side="send", joint=info["joint"], value=info["value"],
      limit_lo=info["limit_lo"], limit_hi=info["limit_hi"], src="send",
    )

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
    and, when ``allow_policy`` was configured, a policy's target in ``policy_sim`` (docs/123
    section 4; see the module docstring)."""
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
      if self.violations is not None:
        # Not a per-joint ROM/torque number (this is a mode-gate refusal, not a clamp) -
        # `joint="*"` covers every joint this client was ever configured to send, `value`
        # stays None (nothing finite to report), the refusal reason is the payload.
        self.violations.record(
          side="send", joint="*", value=None, src="send",
          extra={"reason": str(exc), "mode": mode},
        )
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
    last_sent_gains = dict(self._client.last_sent_gains) if self._client is not None else {}
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
      last_sent_gains=last_sent_gains,
      kp_max=self.kp_max,
      kd_max=self.kd_max,
      ttl_ms=self.ttl_ms,
      # Whether a policy is allowed to drive the motors through this config, and the
      # per-packet step cap that comes with it. Reported so the panel can say it out loud -
      # "a policy can move the hardware right now" is not a state to leave implicit.
      allow_policy=self.allow_policy,
      max_step_deg=self.max_step_deg,
      arm_token=self.arm_token,
      warnings=list(self._client.warnings) if self._client is not None else [],
      # A2: send-side violation count only, so a client watching only /tx/status still sees
      # "something is being clamped/refused" without also polling GET /violations.
      violations_count=(
        self.violations.total_count(side="send") if self.violations is not None else 0
      ),
    )
