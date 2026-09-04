"""UI v2 TX (viewer -> hardware) control-plane STUB, added 2026-09-04.

**This is a stub.** `bridge/tx_client.py` (the actual 50 Hz UDP sender, arm token and
pre-clamp another coder is building per ``docs/123_pygviewer_tx_design.md`` option A) does
not exist in this tree yet (checked: ``git log -- tools/pygviewer/pygviewer/bridge`` has no
such commit). Nothing in this module puts a single byte on a wire. What it DOES do is give
the dashboard's TX section a real, testable safety state machine to drive today, built so the
transmit call is the only thing that needs to change once ``tx_client.py`` lands - the arm /
dead-man / per-motor-enable / mode-gate contract below should not have to.

Design item 2 (user, 2026-09-04 10:40, via docs/121 section 10): **policy output must never
be transmittable.** That is enforced HERE, not only in the API layer or the UI:

  * :meth:`TxState.arm` refuses (raises :class:`TxNotAllowed`) unless the caller's mode is
    exactly ``"manual"`` - which is what BOTH the Joints tab's live sliders and a running
    ``POST /script/run`` sequence use (``SimCore.run_script`` sets ``self.mode = "manual"``),
    and is never what ``policy_sim``/``policy_shadow``/``real_replay``/``file_replay`` use.
  * :meth:`TxState.check_mode_gate`, called from ``SimCore._on_control_tick`` every control
    tick (50 Hz) regardless of what the API layer did or didn't check, auto-disarms the
    instant the mode is no longer ``"manual"`` - the same "structural, not just a UI
    checkbox" pattern this codebase already uses for ``modes.SHADOW_MAY_TRANSMIT``.
  * :meth:`TxState.send` refuses unless :meth:`TxState.active` is true, which requires BOTH
    ``armed`` and a heartbeat received within ``DEADMAN_TIMEOUT_S`` - the keyboard dead-man
    (the dashboard calls ``POST /tx/heartbeat`` on every tick a key is held, and simply stops
    calling it the instant the key is released; nothing here waits for an explicit "stop").
  * ``send`` also silently drops any joint not in ``enabled_motors`` - a fresh
    :class:`TxState` enables nothing, so a client must opt every motor in explicitly.
"""

from __future__ import annotations

import time

DEADMAN_TIMEOUT_S = 0.3
# docs/123 section 3 (user decision, 2026-09-04): the first hardware experiment is one bench
# motor (RS03) at kp<=5. These are DISPLAY-ONLY caps for the dashboard's TX panel - nothing
# in this stub enforces them on a value (there is no transmit path yet to enforce them on).
DEFAULT_KP_CAP = 5.0
DEFAULT_KD_CAP = 0.5


class TxNotAllowed(RuntimeError):
  """Raised by every TxState method that refuses to act - always a 409 at the API layer."""


class TxState:
  def __init__(self, act_names: list[str]):
    self.act_names = list(act_names)
    self.armed = False
    self.host: str | None = None
    self.port: int | None = None
    self.enabled_motors: set[str] = set()
    self.kp_cap = DEFAULT_KP_CAP
    self.kd_cap = DEFAULT_KD_CAP
    self.disarm_reason: str | None = None
    self.last_sent_target: dict[str, float] = {}
    self.last_sent_t: float | None = None
    self._last_heartbeat: float | None = None

  def arm(self, mode: str, host: str, port: int) -> None:
    if mode != "manual":
      raise TxNotAllowed(
        f"TX arm refused: sim mode is {mode!r}. Only 'manual' (the Joints tab, or a "
        "running POST /script/run sequence) may arm TX - policy output must never be "
        "transmittable (docs/121 section 10 TX item)."
      )
    self.armed = True
    self.host, self.port = host, int(port)
    self.disarm_reason = None
    self._last_heartbeat = time.monotonic()

  def disarm(self, reason: str = "operator") -> None:
    self.armed = False
    self.disarm_reason = reason

  def heartbeat(self) -> None:
    if not self.armed:
      raise TxNotAllowed("cannot heartbeat: not armed")
    self._last_heartbeat = time.monotonic()

  def set_motor(self, name: str, enabled: bool) -> None:
    if name not in self.act_names:
      raise KeyError(f"{name!r} is not an actuated joint")
    if enabled:
      self.enabled_motors.add(name)
    else:
      self.enabled_motors.discard(name)

  def check_mode_gate(self, mode: str) -> None:
    """Call every control tick (``SimCore._on_control_tick``) regardless of what the API
    layer checked - structural enforcement, not a UI-only checkbox."""
    if self.armed and mode != "manual":
      self.disarm(reason=f"mode changed to {mode!r} while armed")

  def active(self) -> bool:
    """Armed AND the keyboard dead-man's heartbeat is still fresh."""
    if not self.armed or self._last_heartbeat is None:
      return False
    return (time.monotonic() - self._last_heartbeat) < DEADMAN_TIMEOUT_S

  def send(self, values: dict[str, float]) -> dict[str, float]:
    """STUB (module docstring): records the intended per-motor targets - for the dashboard's
    'sent target' plot series and ``GET /tx/status`` - and returns them, but transmits
    nothing anywhere. Only joints in ``enabled_motors`` are kept; everything else is
    silently dropped (a motor must be opted in explicitly, never on by default)."""
    if not self.active():
      raise TxNotAllowed("cannot send: not armed, or the keyboard dead-man timed out")
    sent = {n: float(v) for n, v in values.items() if n in self.enabled_motors}
    self.last_sent_target = sent
    self.last_sent_t = time.monotonic()
    return sent

  def status(self) -> dict:
    age = None if self._last_heartbeat is None else round(time.monotonic() - self._last_heartbeat, 3)
    return dict(
      armed=self.armed,
      active=self.active(),
      host=self.host,
      port=self.port,
      enabled_motors=sorted(self.enabled_motors),
      heartbeat_age_s=age,
      deadman_timeout_s=DEADMAN_TIMEOUT_S,
      disarm_reason=self.disarm_reason,
      last_sent_target=dict(self.last_sent_target),
      kp_cap=self.kp_cap,
      kd_cap=self.kd_cap,
      stub=True,
      note="no bridge/tx_client.py exists yet (docs/123) - this records intended targets "
      "only, nothing is transmitted to hardware",
    )
