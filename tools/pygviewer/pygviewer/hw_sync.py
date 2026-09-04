"""UI v2 "sync from hardware" gate (2026-09-04) - the safety fix for a real near-miss.

**What happened, verbatim from the bench (docs/123 section 10.2 has the full writeup):** the
real L_knee was sitting at 27.8 deg while the Joints tab's manual target slider - left over
from whatever it was last dragged to, or simply the sim's own default pose - was showing
66.4 deg. Nothing in this codebase stopped an operator from pressing ARM at that moment: the
very first TX packet would have commanded a 38.6 deg jump, sent at the configured kp/kd, to a
motor that was not expecting one. Two-stage arm (``tx.py``) and the keyboard dead-man both
guard "is TX allowed to run at all" - neither one ever asked "does the target it is about to
send bear any relationship to where the real joint currently is". This module is that missing
question.

**The rule, in one sentence:** ``POST /tx/arm`` refuses (409) until an operator has run
``POST /sync_from_real`` (dashboard: "0. sync from hardware") to pull every TX-enabled joint's
manual target from live telemetry, and that sync has not since been invalidated.

**What counts as "still valid":**

  * every joint in the TX client's ``enable`` list synced successfully (had fresh, finite real
    data at sync time) - a joint sync never saw is named explicitly in the 409, never a bare
    "not ready".
  * for a joint the operator has NOT touched again since syncing (its manual target is still
    exactly the synced value), the LIVE real value must not have drifted more than
    ``arm_drift_limit_rad`` (default 5 deg) away from it. This is deliberately asymmetric: an
    operator dragging the slider to a value far from the synced real position is a conscious,
    intended command and is never blocked here (see :meth:`HwSyncState.check_arm_ready`'s own
    docstring) - what IS blocked is the real joint itself having moved by hand/gravity/drift
    since the sync while the target sat still, because arming then would silently snap it back
    to a now-stale synced position, the same "unexpected jump" this module exists to prevent.

**What invalidates a sync** (docs/123 section 10.2): real telemetry for a synced joint going
stale (no update for more than ``STALE_INVALIDATE_S``), a TX reconfigure (``POST /tx/config``
changes the wire format / enable set the sync was computed against), the sim mode leaving
``"manual"`` (a policy or replay mode can drive the target through a completely different path
that this sync's snapshot says nothing about), or a live model contract swap. Every one of
these calls :meth:`invalidate` (see call sites in ``sim_core.py``/``api.py``) except the
telemetry-staleness case, which is checked lazily on demand by :meth:`refresh_staleness` since
there is no natural "it just went stale" event to push from - see that method's docstring.

Deliberately dependency-free (no mujoco, no FastAPI): every method takes plain dicts/floats so
this is unit-testable without a baked model or an HTTP client, the same reasoning
``pygviewer/tx.py``'s own pure ``TxState`` tests already rely on.
"""

from __future__ import annotations

import math
import secrets
import time

SYNC_STALE_SKIP_S = 0.5
"""``POST /sync_from_real``: a joint whose real data is older than this is skipped with
reason "stale" rather than synced from a number that may no longer describe the robot."""

STALE_INVALIDATE_S = 1.0
"""Once synced, a synced joint whose real telemetry goes quiet for longer than this
invalidates the WHOLE sync (not just that joint) - see :meth:`HwSyncState.refresh_staleness`."""

DEFAULT_ARM_DRIFT_LIMIT_RAD = math.radians(5.0)
"""Default block threshold for "the real joint moved away from an untouched synced target"
(docs/123 section 10.2 user decision, 2026-09-04) - exposed as a module constant, not buried
in a method body, so a caller/test can name it instead of hard-coding ``math.radians(5.0)``
a second time."""


class HwSyncNotReady(RuntimeError):
  """Raised by :meth:`HwSyncState.check_arm_ready` - always a 409 at the API layer
  (``POST /tx/arm``). The message is written to be shown to an operator verbatim."""


class HwSyncState:
  """One instance per ``SimCore`` process (``SimCore.hw_sync``). Owns nothing about telemetry
  or the TX client itself - ``api.py`` hands it plain snapshots (joint ages, current targets,
  live real values) computed the same thread-safe way every other endpoint already reads
  them (``core.snapshot()`` / ``core.real.snapshot_joints()``)."""

  def __init__(self, arm_drift_limit_rad: float = DEFAULT_ARM_DRIFT_LIMIT_RAD):
    self.arm_drift_limit_rad = float(arm_drift_limit_rad)
    self.valid = False
    self.reason: str | None = "no sync yet - POST /sync_from_real first"
    self.synced: dict[str, float] = {}  # joint -> value applied at sync time (post-clip)
    self.sync_time_mono: float | None = None
    self.sync_time_wall: float | None = None
    self.sync_token: str | None = None
    self._contract_sha: str | None = None
    self._last_mode: str | None = None

  # -------------------------------------------------------------------------------- sync
  def record_sync(self, synced: dict[str, float], contract_sha: str) -> str:
    """Called once by ``POST /sync_from_real`` after it has computed the per-joint
    synced/clipped/skipped split - this method only records the outcome and (re)validates.
    An empty ``synced`` dict (every joint skipped) is still a "successful sync attempt" as far
    as this state machine is concerned; whether that is good enough to arm is
    :meth:`check_arm_ready`'s question (it will name whichever enabled joints are missing)."""
    self.synced = dict(synced)
    self.sync_time_mono = time.monotonic()
    self.sync_time_wall = time.time()
    self.sync_token = secrets.token_hex(6)
    self._contract_sha = contract_sha
    self.valid = True
    self.reason = None
    return self.sync_token

  def invalidate(self, reason: str) -> None:
    """No-op if already invalid, so a more specific "never synced at all" reason is never
    overwritten by a later, less informative event (e.g. a mode change while idling before
    the very first sync of the session)."""
    if self.valid:
      self.valid = False
      self.reason = reason

  def note_mode(self, mode: str) -> None:
    """Call every time the current mode is known (``sim_core.py``'s ``_apply_cmd`` op
    ``"mode"``, and structurally every control tick from ``_on_control_tick``).

    Only a TRANSITION away from ``"manual"`` invalidates - not merely "the current mode is
    not manual". This distinction is load-bearing (2026-09-04 live bench fix): syncing is
    allowed in ANY mode (an operator may reasonably sync before ever switching to manual), so
    a sync performed while idle must not be invalidated on the very next tick just because
    the mode "is not manual" - nothing left it, it was never manual to begin with. What DOES
    need to invalidate is a policy/replay mode taking over AFTER a manual sync, since that
    drives the target through a path this sync's snapshot never saw. Tracking the previous
    mode (``_last_mode``) is what lets "left manual" and "was never in manual" be told apart.
    """
    left_manual = self._last_mode == "manual" and mode != "manual"
    self._last_mode = mode
    if left_manual:
      self.invalidate(
        f"left manual mode (now {mode!r}) while synced - re-sync required: switch back to "
        "manual, press '0. sync from hardware', then arm"
      )

  def refresh_staleness(self, joint_ages_s: dict[str, float | None], contract_sha: str) -> None:
    """Pull-based invalidation for the two conditions with no natural call site to push an
    event from: (a) real telemetry for a synced joint has gone quiet, (b) the model contract
    changed under this process. Call before reading anything sync-related for a client
    (``GET /tx/status``, ``POST /tx/arm``) so staleness is never more than one request stale
    itself."""
    if not self.valid:
      return
    if contract_sha != self._contract_sha:
      self.invalidate(f"model contract changed since sync ({self._contract_sha} -> {contract_sha})")
      return
    for j in self.synced:
      age = joint_ages_s.get(j)
      if age is None or age > STALE_INVALIDATE_S:
        age_txt = "no data since" if age is None else f"{age:.2f}s old"
        self.invalidate(
          f"real telemetry for {j!r} went stale ({age_txt}, limit {STALE_INVALIDATE_S:.1f}s) "
          "- re-sync before arming"
        )
        return

  # -------------------------------------------------------------------------------- arm gate
  def check_arm_ready(
    self,
    enable: list[str],
    target_now: dict[str, float],
    real_now: dict[str, float | None],
  ) -> None:
    """Raise :class:`HwSyncNotReady` unless arming is allowed right now.

    ``target_now``/``real_now`` are the CURRENT values (not the synced snapshot) - this is
    what lets an operator move a slider after syncing without ever being blocked for it: a
    joint whose current target no longer equals its synced value is read as "the operator
    already made a deliberate decision about this joint since sync" and is skipped from the
    drift check entirely, matching the design brief verbatim ("차이 자체는 허용하되... 무장은
    막지 않음"). The drift check only ever fires for a joint the operator has NOT touched -
    there, a large real-vs-synced gap can only mean the REAL joint moved on its own.
    """
    if not self.valid:
      base_reason = self.reason or "sync is not valid"
      raise HwSyncNotReady(
        f"{base_reason} - press '0. sync from hardware' before arming. TX-enabled joint(s) "
        f"needing a synced value: {list(enable)}"
      )
    missing = [j for j in enable if j not in self.synced]
    if missing:
      raise HwSyncNotReady(
        f"TX-enabled joint(s) with no synced real data, cannot arm: {missing} - press "
        "'0. sync from hardware' with real data flowing for them, or remove them from the "
        "TX enable list via POST /tx/config"
      )
    moved_real: list[tuple[str, float, float]] = []
    for j in enable:
      synced_v = self.synced[j]
      tgt = target_now.get(j, synced_v)
      if abs(tgt - synced_v) > 1e-9:
        continue  # operator moved this joint's target since sync - a deliberate command, never blocked
      real_v = real_now.get(j)
      if real_v is None or not math.isfinite(real_v):
        continue  # nothing live to compare against; sustained silence is refresh_staleness's job
      if abs(real_v - synced_v) > self.arm_drift_limit_rad:
        moved_real.append((j, synced_v, real_v))
    if moved_real:
      details = ", ".join(
        f"{j} moved {math.degrees(abs(rv - sv)):.1f} deg since sync "
        f"({math.degrees(sv):.1f} -> {math.degrees(rv):.1f} deg)"
        for j, sv, rv in moved_real
      )
      raise HwSyncNotReady(
        f"real hardware moved without a matching operator command since sync: {details} - "
        "press '0. sync from hardware' again before arming"
      )

  # -------------------------------------------------------------------------------- status
  def status(self, target_now: dict[str, float], real_now: dict[str, float | None]) -> dict:
    """``GET /tx/status``'s ``sync`` sub-object. ``target_drift_*`` is the largest
    |current target - synced value| across every synced joint, shown for ANY reason it moved
    (operator command or otherwise) - purely informational, never blocking (see
    :meth:`check_arm_ready`'s docstring for why blocking is asymmetric)."""
    drift_rad = 0.0
    drift_joint = None
    for j, sv in self.synced.items():
      tgt = target_now.get(j)
      if tgt is None:
        continue
      d = abs(tgt - sv)
      if d > drift_rad:
        drift_rad, drift_joint = d, j
    return dict(
      valid=self.valid,
      reason=self.reason,
      synced_joints=sorted(self.synced),
      sync_token=self.sync_token,
      sync_time_wall=self.sync_time_wall,
      target_drift_rad=round(drift_rad, 6),
      target_drift_deg=round(math.degrees(drift_rad), 3),
      target_drift_joint=drift_joint,
      arm_drift_limit_rad=self.arm_drift_limit_rad,
      arm_drift_limit_deg=round(math.degrees(self.arm_drift_limit_rad), 3),
    )
