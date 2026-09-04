"""docs/123 plan A item 3 (the "example implementation" in section 3b, made real): the
ROBOT-SIDE script that turns a ``JointTarget`` UDP stream into a HUPHY ``Motion`` -
``Leg.build_commands`` -> HUPHY's own safety guards (NaN/limit/slew) -> ``bus.send_mit`` ->
CAN.  HUPHY itself is never edited - this file only imports it (docs/123 section 3: "HUPHY
코드는 건드리지 않고 별도 스크립트로 동작").

Runs on the robot host, where ``huphy`` and (for real motion) a live CAN bus exist.  Neither
exists on this development machine, so ``huphy`` is imported LAZILY, only inside
``run_real()`` - everything else in this file (argument parsing, the sim-rad -> HUPHY-cal-deg
math, the arm/seq/deadman state machine, and ``--dry-run``) is plain Python + this repo's own
code and is unit-tested here without HUPHY installed.

Two run modes, matching the CLI flag:

  ``run_real()``   the real thing - builds a HUPHY ``Leg`` (via ``bringup.build_leg``, the
                    same helper HUPHY's own scripts use), runs ``ControlLoop(leg, mode=
                    CONTROL)`` with this file's ``Motion``, and lets HUPHY's OWN telemetry
                    (``Telemetry.from_config``) carry pos/vel/tau back out on UDP :9870 -
                    nothing here reimplements that wire, it is HUPHY's existing feature,
                    just pointed at the viewer host via ``--telemetry``.
  ``run_dry()``    "CAN 없이 명령만 로그·UDP 텔레메트리 에코" (docs/123 item 3): no CAN, no
                    ``huphy`` import at all - computes exactly what WOULD be sent (the same
                    sim-rad -> cal-deg conversion, the same arm/deadman gating) and echoes an
                    HONEST "assumes instant, perfect tracking" telemetry packet in HUPHY's
                    wire format, so an operator can verify keys/signs/units end to end on
                    their own PlotJuggler/viewer BEFORE a CAN bus or a motor is ever involved.
                    This is NOT a physics model (``dummy_rx.py`` is, for that) - it is a
                    wiring/sign/unit check.

The ankle pair (``L_crank_A_joint``/``L_crank_B_joint`` -> HUPHY's ``ankle_a``/``ankle_b``
MOTOR targets) needs one extra step that ``tx_map.py`` deliberately does NOT do (it would
force a ``huphy`` import into a module that has to stay importable without HUPHY): HUPHY's
``Leg.build_commands`` only accepts an ankle command as ``ankle_pitch``/``ankle_roll``
(degrees, then its OWN closed-form IK reconstructs ``a1``/``a2`` and runs it through the
guards) - it has no path that accepts a raw motor-level ``ankle_a``/``ankle_b`` target.  So
``run_real()`` FK-converts our crank targets to pitch/roll with the leg's own
``AnkleKinematics.solve_fk`` (the SAME kinematics/mirroring HUPHY already built for this leg)
before handing them to ``build_commands``, which promptly IK's them back to ``a1``/``a2``.
That round trip is numerical (Newton FK, closed-form IK) and is flagged as a HUPHY interface
gap in docs/123 section 5, not worked around here - see that section for the bug-report text.

Biped structure migration (2026-09-04, docs/121 section 12 / docs/123 section 11): HUPHY's
``biped`` branch dropped ``build_robot``/``LimbConfig.kind == "single"`` (both never existed
here upstream at all, in fact - a prior version of this file assumed a "single" kind that
this repo's HUPHY checkout never had).  The only builders now are ``build_leg`` (still hard-
requires all 6 leg motors, ``robots/leg.py`` ``REQUIRED_MOTORS``) and ``build_biped`` (composes
one or more ``Leg``s into a ``Biped``, which fills the ``Robot`` contract ``ControlLoop`` runs
against).  This file now calls ``build_biped`` with ``limbs=[the one LimbConfig --limb
resolved to]`` - deliberately ONE leg, not "every kind:leg limb in robot.yaml" (build_biped's
own default when ``limbs`` is omitted) - because ``Biped.connect()``/``enable()`` are
all-or-nothing across every part it holds (``robots/biped.py``: "하나라도 실패하면 전부 끊고
올림"), and this tool has always driven exactly one side per invocation; building a second,
physically-absent leg here would make every run fail on that leg's CAN bus instead of driving
the one that exists.  A ``Biped`` is still needed (not a bare ``Leg``) because ``ControlLoop``
needs a ``Robot``, and going through the biped layer is what buys the correct action-name
contract below.

``Biped`` also changes the ACTION contract: every joint/motor name gets the owning limb's
``Leg.id`` prefixed with ``/`` (``"left_leg/knee"``, not bare ``"knee"``), and
``Biped.split_action`` HARD-FAILS on an unprefixed name (``robots/biped.py``: "모르는 이름은
에러임").  ``RemoteMotion.__call__`` builds its action dict in bare per-leg names exactly as
before (unchanged - ``Leg.build_commands`` itself still takes bare ``hip_pitch``/.../
``ankle_pitch``/``ankle_roll``, per-leg, since ``Leg`` did not change) and prefixes the WHOLE
dict with ``f"{side}/"`` as the very last step before returning it - the one place in this
file that has to know about the biped naming convention at all.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import socket
import threading
import time
from collections import deque
from typing import Callable

from .. import CACHE_DIR, VARIANTS
from ..contract import load_contract
from ..schema import from_jsonl
from .huphy_udp import DEFAULT_MAP_PATH, JointMap
from .motor_fault import (
  FaultPoller,
  FaultReading,
  StuckDetector,
  ThermalCutoff,
  decode_fault_word,
  describe_cutoff_simple,
  describe_fault_simple,
  describe_stuck_simple,
  query_fault_raw,
)
from .remote_target import (
  DEFAULT_DEADMAN_S,
  DEFAULT_HOLD_S,
  DEFAULT_RETURN_S,
  DeadmanFilter,
  LatestOnly,
)
from .tx_map import JointTargetMapper, clamp_gain

logger = logging.getLogger(__name__)

LISTEN_PORT = 9872
DEFAULT_KP = 5.0
DEFAULT_KD = 0.5
DEFAULT_HZ = 100.0

SINGLE_MOTOR_NAMES = ("hip_pitch", "hip_roll", "hip_yaw", "knee")
ANKLE_MOTOR_NAMES = ("ankle_a", "ankle_b")
MOTOR_ALIASES = {"ankle": ANKLE_MOTOR_NAMES}
"""``--enable ankle`` is shorthand for both crank motors together - HUPHY's ankle command is
atomic (both loads or neither, ``Leg._motor_targets``'s "통째로 버림" rule), so it never makes
sense to enable exactly one of them."""

OBS_POS_SUFFIX = ".pos"
OBS_TAU_SUFFIX = ".torque"
OBS_TEMP_SUFFIX = ".temp"
"""Observation-dict key suffixes, now read off HUPHY's source rather than inferred
(2026-09-05, bench). ``Leg.get_observation`` (``robots/leg.py:364-367``) writes exactly:

    out[f"{motor_name}.pos"]     out[f"{motor_name}.vel"]
    out[f"{motor_name}.torque"]  out[f"{motor_name}.temp"]

The torque suffix was ``.tau`` here until the bench proved the cost of guessing: the stuck
detector needs a torque reading, ``obs.get(".tau")`` always returned ``None``, and the
detector's own fail-safe ("no reading -> report nothing") meant a knee that sat frozen for
170 s under an overvoltage cutout was never once reported as stuck. The wire vocabulary this
bridge uses elsewhere (``FAST_MOTOR_FIELDS``: pos/vel/tau) is NOT the observation vocabulary -
they differ on this one field."""


# =========================================================================== pure helpers
# Nothing below this line imports huphy - these are unit-tested directly (test_remote_motion.py).
def sim_joints_for_limb(jmap: JointMap, side: str) -> list[str]:
  """The 6 sim joint names belonging to one side ("left"/"right") of ``joint_map_huphy.json``."""
  return [row["sim_joint"] for (limb, _motor), row in jmap.motors.items() if limb == side]


def enable_motor_names_to_sim_joints(names: list[str], side: str, jmap: JointMap) -> set[str]:
  """``["hip_pitch", "ankle"]`` -> the matching sim joint names for ``side``.  Unknown motor
  names are a hard failure (``KeyError`` via ``JointMap.sim_joint``), same policy as the rest
  of this bridge - a typo in ``--enable`` must not silently enable nothing."""
  motors: set[str] = set()
  for n in (x.strip() for x in names if x.strip()):
    motors.update(MOTOR_ALIASES.get(n, (n,)))
  return {jmap.sim_joint(side, m)["sim_joint"] for m in motors}


def split_motor_targets_into_action(
  motor_targets: dict[str, float]
) -> tuple[dict[str, float], tuple[float, float] | None]:
  """``{"hip_pitch": deg, ..., "ankle_a": deg, "ankle_b": deg}`` (whatever subset is enabled
  this tick) -> ``(single-joint degrees, (a1_deg, a2_deg) or None)``.

  The ankle pair is returned ONLY when both motors are present - sending one without the
  other would corrupt the pose (HUPHY's own ``Leg._motor_targets`` "통째로 버림" rule: one
  crank moving without the other twists the joint), so an unpaired one is dropped here, at
  the boundary, and the caller is expected to log it rather than send a partial command."""
  single = {k: v for k, v in motor_targets.items() if k in SINGLE_MOTOR_NAMES}
  ankle = None
  if "ankle_a" in motor_targets and "ankle_b" in motor_targets:
    ankle = (motor_targets["ankle_a"], motor_targets["ankle_b"])
  return single, ankle


_LEFT_ALIASES = ("left", "left_leg", "leftleg", "bench")
"""Historical spellings that all mean "the left-side leg". ``bench`` is here because the
single-motor bench rig's own map (``joint_map_bench.json``) has always put its one leg on the
left ((limb='left') for the 5 real joints, (limb='bench') only for the re-patched knee row) -
so an operator typing the old ``--limb bench`` habit against a map that has NO literal
``bench`` row (e.g. the biped default) should still land on that map's left-side leg, not a
hard error over a spelling that used to work."""
_RIGHT_ALIASES = ("right", "right_leg", "rightleg")


def resolve_side(limb_arg: str, jmap: JointMap | None = None) -> str:
  """Resolve ``--limb`` to the key the JOINT MAP uses for that limb.

  The returned value is not merely "left"/"right": every downstream use treats it as the
  map's own limb key (``row["limb"] == side`` in :func:`sim_joints_for_limb`, the lookup in
  :func:`enable_motor_names_to_sim_joints`, the ``f"{side}/{motor}/{field}"`` telemetry keys
  that must match HUPHY's own wire format, AND - biped structure migration, 2026-09-04 - the
  ``f"{side}/"`` prefix :class:`RemoteMotion` puts on every outgoing action key, which must
  equal the actual ``Leg.id`` HUPHY's ``robot.yaml`` gave that limb or ``Biped.split_action``
  hard-fails the whole command).  So resolution must land on whatever THIS map calls that
  limb, whatever vocabulary that happens to be - ``left_leg``/``right_leg`` (the biped
  default, ``joint_map_biped.json``, matching HUPHY's own ``robot.yaml`` ``limbs`` keys),
  ``left``/``right`` (the legacy ``joint_map_huphy.json``), or a one-off name like
  ``joint_map_bench.json``'s ``bench``.

  Resolution order:

    1. an EXACT match against the map's own limb keys (verbatim, then lower-cased) always
       wins - never overridden by an alias guess, so a map's real vocabulary is authoritative.
    2. no ``jmap`` at all (pure-helper unit tests, no map to resolve against) - the historical
       bare ``left``/``right``/``left_leg``/``right_leg`` vocabulary, unchanged from before
       biped existed.
    3. a ``jmap`` IS given but step 1 found nothing verbatim - try the historical aliases
       (``left``/``left_leg``/``leftleg``/``bench`` for the left side, ``right``/``right_leg``/
       ``rightleg`` for the right) and resolve to whichever of THIS map's own limb names
       actually represents that side.  This is what lets an operator keep typing
       ``--limb left`` or ``--limb bench`` against the NEW biped map and land on
       ``left_leg`` without needing to learn the new spelling first.

  A name that matches nothing in any of the three steps is a hard failure - the error lists
  this map's actual limbs, since guessing which one was meant is exactly the silent-failure
  mode this whole bridge refuses to have (a typo'd ``--limb`` must not drive nothing while
  looking like it started).
  """
  raw = limb_arg.strip()
  s = raw.lower()
  known = sorted({limb for (limb, _motor) in jmap.motors}) if jmap is not None else []

  # 1) the map's own vocabulary, verbatim, always wins.
  if raw in known:
    return raw
  if s in known:
    return s

  # 2) no map to resolve against - preserve the pre-biped bare left/right/left_leg/right_leg
  #    behaviour exactly (used by this module's own pure-helper tests).
  if jmap is None:
    if s in ("left", "right"):
      return s
    if s in ("left_leg", "leftleg"):
      return "left"
    if s in ("right_leg", "rightleg"):
      return "right"
    raise ValueError(f"--limb {limb_arg!r}: expected one of left/right/left_leg/right_leg")

  # 3) a map was given, but didn't have this spelling verbatim - fall back to "which side"
  #    and resolve to whatever THIS map calls that side.
  for aliases in (_LEFT_ALIASES, _RIGHT_ALIASES):
    if s in aliases:
      for candidate in aliases:
        if candidate in known:
          return candidate
      break  # matched a side bucket but this map has no limb for it - fall through to error

  raise ValueError(
    f"--limb {limb_arg!r}: not one of this map's limbs and no alias resolves to one "
    f"(available limbs: {known})"
  )


@dataclasses.dataclass
class GainPlan:
  """What kp/kd to send for each HUPHY motor name this tick, already clamped."""

  kp: dict[str, float]
  kd: dict[str, float]
  warnings: list[str]


def plan_gains(
  state_target_sim_joints: list[str],
  mapper: JointTargetMapper,
  side: str,
  msg,
  phase: str,
  *,
  kp_max: float,
  kd_max: float,
  default_kp: float,
  default_kd: float,
) -> GainPlan:
  """Per-motor kp/kd for exactly the sim joints in ``state_target_sim_joints`` (already
  filtered to enabled joints of ``side`` by the caller's ``DeadmanFilter``).  Uses the
  message's own kp/kd ONLY while ``phase == "live"`` (a hold/returning/default tick has no
  live per-joint gain data to use, by construction - falling back to a fixed conservative
  default rather than inventing one from a stale message is deliberate, and matches
  ``dummy_rx.py``'s identical choice)."""
  live_kp: dict[str, float] = {}
  live_kd: dict[str, float] = {}
  if msg is not None and phase == "live":
    if msg.kp:
      live_kp = dict(zip(msg.joint_names, msg.kp))
    if msg.kd:
      live_kd = dict(zip(msg.joint_names, msg.kd))

  kp_out: dict[str, float] = {}
  kd_out: dict[str, float] = {}
  warnings: list[str] = []
  for sim_joint in state_target_sim_joints:
    limb, motor_name, _row = mapper.motor_row(sim_joint)
    if limb != side:
      continue
    kp, w = clamp_gain(live_kp.get(sim_joint, default_kp), kp_max, name=f"kp[{motor_name}]")
    warnings.extend(w)
    kd, w = clamp_gain(live_kd.get(sim_joint, default_kd), kd_max, name=f"kd[{motor_name}]")
    warnings.extend(w)
    kp_out[motor_name] = kp
    kd_out[motor_name] = kd
  return GainPlan(kp=kp_out, kd=kd_out, warnings=warnings)


# =========================================================================== shared receive
class _Receiver:
  """UDP receive thread shared by ``run_dry``/``run_real`` - parses, rejects unknown joints
  hard (never a guess), and hands accepted messages to a ``LatestOnly``.  No huphy import."""

  def __init__(self, host: str, port: int, latest: LatestOnly, known_sim_joints: set[str]):
    self.host = host
    self.port = port
    self.latest = latest
    self.known_sim_joints = known_sim_joints
    self._sock: socket.socket | None = None
    self._thread: threading.Thread | None = None
    self._running = False
    self.parse_errors = 0

  def start(self) -> None:
    self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self._sock.bind((self.host, self.port))
    self._sock.settimeout(0.5)
    self._running = True
    self._thread = threading.Thread(target=self._loop, name="huphy-remote-recv", daemon=True)
    self._thread.start()

  def stop(self) -> None:
    self._running = False
    if self._thread is not None:
      self._thread.join(timeout=2.0)
      self._thread = None
    if self._sock is not None:
      self._sock.close()
      self._sock = None

  def _loop(self) -> None:
    while self._running:
      try:
        data, _addr = self._sock.recvfrom(4096)
      except socket.timeout:
        continue
      except OSError:
        break
      try:
        msg = from_jsonl(data.decode("utf-8"))
      except (ValueError, UnicodeDecodeError) as e:
        self.parse_errors += 1
        logger.warning("remote_motion: bad packet: %s", e)
        continue
      if msg.type != "JointTarget":
        self.parse_errors += 1
        continue
      unknown = sorted(set(msg.joint_names) - self.known_sim_joints)
      if unknown:
        self.parse_errors += 1
        logger.warning("remote_motion: rejecting message with unknown joint(s) %s", unknown)
        continue
      self.latest.put(msg)


class _StatsTicker:
  """Background thread: prints the receive counters (accepted/rejected_seq/
  rejected_arm_token/rejected_contract/parse_errors) every ``interval_s`` seconds, not only at
  process exit.

  2026-09-04: the exit-only summary this bridge had before made a real bench session take
  much longer to debug than it should have - TX was confirmed sending at 50 Hz, telemetry was
  confirmed arriving, and the motor still never moved, and the ONLY thing that would have said
  why (``rejected_arm_token`` climbing every tick, a stale ``--arm-token`` on one side) was
  invisible until Ctrl-C.  A periodic line turns "nothing is happening, why" into "the counter
  told me in five seconds" - same spirit as ``docs/123`` section 10.1's ``clear_fault()`` fix,
  another case where the symptom looked identical to several different root causes and only a
  number printed at the right time told them apart."""

  def __init__(
    self, latest: LatestOnly, recv: _Receiver, *, interval_s: float = 5.0, label: str = "",
    idle_refresh_fn: Callable[[], int] | None = None,
  ):
    self.latest = latest
    self.recv = recv
    self.interval_s = float(interval_s)
    self.label = label
    self.idle_refresh_fn = idle_refresh_fn
    """Optional ``() -> int`` returning the running idle-refresh-tick count (2026-09-04, docs/
    123 section 11b) - ``None`` in ``--dry-run`` (no ``RemoteMotion``/real control loop, the
    concept does not apply there) so the field is omitted rather than printed as a
    misleading always-0."""
    self._thread: threading.Thread | None = None
    self._running = False

  def start(self) -> None:
    if self.interval_s <= 0:
      return  # 0/negative disables the ticker outright - e.g. a short automated test run
    self._running = True
    self._thread = threading.Thread(target=self._loop, name="huphy-remote-stats", daemon=True)
    self._thread.start()

  def stop(self) -> None:
    self._running = False
    if self._thread is not None:
      self._thread.join(timeout=1.0)
      self._thread = None

  def _loop(self) -> None:
    while self._running:
      # Sleep in small slices so `stop()` doesn't have to wait out a whole interval - a short
      # --seconds test run must not be held up by a 5s-granularity join timeout.
      slept = 0.0
      while self._running and slept < self.interval_s:
        time.sleep(min(0.2, self.interval_s - slept))
        slept += 0.2
      if not self._running:
        return
      self.print_once()

  def print_once(self) -> None:
    s = self.latest.stats
    extra = f" idle_refresh={self.idle_refresh_fn()}" if self.idle_refresh_fn is not None else ""
    print(
      f"{self.label}stats: accepted={s.accepted} rejected_seq={s.rejected_seq} "
      f"rejected_arm_token={s.rejected_arm_token} rejected_contract={s.rejected_contract} "
      f"parse_errors={self.recv.parse_errors}{extra}",
      flush=True,
    )


# =========================================================================== dry run (no huphy)
def run_dry(args) -> int:
  """"CAN 없이 명령만 로그·UDP 텔레메트리 에코" - no huphy, no CAN, assumes INSTANT perfect
  tracking (pos == target every tick) purely to exercise wiring/signs/units end to end. Use
  ``dummy_rx.py`` instead for anything that needs to look like a real dynamic response."""
  contract = load_contract(args.cache, args.variant)
  jmap = JointMap(args.map) if args.map else JointMap(DEFAULT_MAP_PATH)
  mapper = JointTargetMapper(contract, jmap)
  side = resolve_side(args.limb, jmap)
  our_sim_joints = sim_joints_for_limb(jmap, side)
  enable = (
    enable_motor_names_to_sim_joints(args.enable.split(","), side, jmap)
    if args.enable else set(our_sim_joints)
  )
  default_q = {sj: contract.default_q(sj) for sj in our_sim_joints}

  listen_host, listen_port = args.listen.rsplit(":", 1)
  tele_host, tele_port = args.telemetry.rsplit(":", 1)

  latest = LatestOnly(expected_arm_token=args.arm_token, expected_contract_hash=contract.contract_sha)
  deadman = DeadmanFilter(
    default_q=default_q, deadman_s=args.deadman_s, hold_s=args.hold_s, return_s=args.return_s,
    enable=enable,
  )
  recv = _Receiver(listen_host, int(listen_port), latest, mapper.known_sim_joints())
  recv.start()
  ticker = _StatsTicker(latest, recv, interval_s=args.stats_interval_s, label="dry-run: ")
  ticker.start()
  tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

  print(
    f"huphy_remote_motion --dry-run: side={side} listening on {args.listen}, "
    f"telemetry(assumed-instant-tracking) -> {args.telemetry}, enabled={sorted(enable)}",
    flush=True,
  )
  period = 1.0 / args.hz
  last_phase = None
  ticks = 0
  try:
    deadline = None if args.seconds is None else time.monotonic() + args.seconds
    while deadline is None or time.monotonic() < deadline:
      t0 = time.monotonic()
      msg, age = latest.get()
      state = deadman.update(msg, age)
      if state.phase != last_phase:
        logger.info("dry-run: phase %s -> %s", last_phase, state.phase)
        last_phase = state.phase

      motor_targets = (
        mapper.to_motor_targets(list(state.target), list(state.target.values())).get(side, {})
        if state.target else {}
      )
      single, ankle_pair = split_motor_targets_into_action(motor_targets)
      if ("ankle_a" in motor_targets) != ("ankle_b" in motor_targets):
        logger.warning("dry-run: only one of ankle_a/ankle_b present this tick - dropped")

      pkt: dict[str, float] = {"t": round(ticks * period, 3), "loop_dt": round(period * 1000.0, 3)}
      for motor_name, deg in motor_targets.items():
        pkt[f"{side}/{motor_name}/pos"] = round(deg, 2)
        pkt[f"{side}/{motor_name}/tgt"] = round(deg, 2)
        pkt[f"{side}/{motor_name}/err"] = 0.0
        pkt[f"{side}/{motor_name}/vel"] = 0.0
        pkt[f"{side}/{motor_name}/tau"] = 0.0
      if len(pkt) > 2:
        try:
          tx_sock.sendto(json.dumps(pkt).encode("utf-8"), (tele_host, int(tele_port)))
        except OSError as e:
          logger.warning("dry-run: telemetry send failed: %s", e)
      if args.verbose:
        print(f"  [{state.phase}] single={single} ankle_pair={ankle_pair}", flush=True)
      ticks += 1
      time.sleep(max(0.0, period - (time.monotonic() - t0)))
  except KeyboardInterrupt:
    pass
  finally:
    recv.stop()
    ticker.stop()
    tx_sock.close()
    print(f"dry-run: stopped. accepted={latest.stats.accepted} "
          f"rejected_seq={latest.stats.rejected_seq} rejected_arm_token={latest.stats.rejected_arm_token} "
          f"rejected_contract={latest.stats.rejected_contract} parse_errors={recv.parse_errors}", flush=True)
  return 0


# =========================================================================== real run (huphy)
def _make_can_fault_query_fn(limb_cfg, leg):
  """Best-effort layer (b) wiring (docs/124 section 1/2): an INDEPENDENT ``python-can`` bus
  handle on this leg's OWN CAN channel, used ONLY to read a fault-query reply's RAW bytes
  ourselves - never through ``bus.read_fault()``'s own decode (this robot's HUPHY checkout
  may or may not have the byte-order bug docs/124 section 1 found fixed yet, and there is no
  way to tell from here which one is checked out). SocketCAN allows multiple simultaneous
  listeners on one interface (the same reason ``candump`` can run alongside real traffic
  without stealing it), so this does not compete with HUPHY's own bus handle for exclusive
  access - it only ADDS one low-rate (``FAULT_POLL_INTERVAL_S``) query frame while idle.

  UNVERIFIED against real hardware: motors are off for this change and hardware verification
  is explicitly reserved for the human operator (project rule), not this session. Every
  failure mode below returns ``None`` rather than raising, so a wrong assumption here
  degrades to layer (a) [freeze detection] only, never crashes a live run. A
  ``fault code reading unavailable`` warning at startup means layer (b) did NOT activate -
  confirm on the bench that it does before relying on it.
  """
  try:
    import can
  except ImportError as e:
    logger.warning("remote_motion: fault code reading unavailable (no python-can): %s", e)
    return None
  try:
    bus = can.interface.Bus(channel=limb_cfg.channel, interface=limb_cfg.interface)
  except Exception as e:
    logger.warning(
      "remote_motion: fault code reading unavailable (could not open %s/%s): %s",
      limb_cfg.channel, limb_cfg.interface, e,
    )
    return None

  # id -> motor name, by OBJECT IDENTITY against leg.config.motors - never a guessed
  # attribute name on HUPHY's own MotorConfig/id type (see this function's own docstring).
  cfg_to_name = {id(cfg): name for name, cfg in leg.config.motors.items()}
  try:
    motors_by_id = limb_cfg.motors_by_id()
  except Exception as e:
    logger.warning("remote_motion: fault code reading unavailable (motors_by_id failed): %s", e)
    return None
  name_by_id = {mid: cfg_to_name.get(id(cfg)) for mid, cfg in motors_by_id.items()}
  name_by_id = {mid: name for mid, name in name_by_id.items() if name is not None}
  if not name_by_id:
    logger.warning("remote_motion: fault code reading unavailable (no motor id/name match)")
    return None

  def send_fn(motor_id: int, data: bytes) -> None:
    bus.send(can.Message(arbitration_id=int(motor_id), is_extended_id=False, data=data))

  def recv_fn(timeout_s: float):
    m = bus.recv(timeout=max(0.0, timeout_s))
    return bytes(m.data) if m is not None else None

  def query_fn() -> dict[str, bytes | None]:
    raw = query_fault_raw(list(name_by_id), send_fn, recv_fn)
    out: dict[str, bytes | None] = {}
    for mid, data in raw.items():
      # byte0 = motor id (this robot's 11-bit wiring, docs/124 section 1); bytes[1:5] = the
      # 4-byte fault word, same slice read_fault_raw.py's own reference tool uses.
      out[name_by_id[mid]] = None if data is None or len(data) < 5 else bytes(data[1:5])
    return out

  logger.info(
    "remote_motion: fault code reading enabled on %s/%s for %s",
    limb_cfg.channel, limb_cfg.interface, sorted(name_by_id.values()),
  )
  return query_fn


def run_real(args) -> int:
  """The real thing. Imports huphy HERE, not at module scope, so this file stays importable
  (and its pure helpers testable) on a machine without HUPHY installed."""
  import huphy  # noqa: F401 - surfaces a clear ImportError here if not installed, not later
  from huphy.config import ConfigError, load_robot
  from huphy.control import ControlLoop, Mode
  from huphy import telemetry as tele
  from huphy.motors.base import Gains
  from huphy.robots.leg import ANKLE_POSITION
  # build_biped, not build_robot (2026-09-04, biped branch): `build_robot`/`LimbConfig.kind ==
  # "single"` never existed in this repo's HUPHY checkout at all - `biped` only ever shipped
  # `build_leg` (still hard-requires all six leg motors, `robots/leg.py` REQUIRED_MOTORS - the
  # single-motor bench works around this by declaring all 6 motor rows in robot_bench.yaml,
  # not by relaxing Leg) and `build_biped` (composes one-or-more Legs into a Biped, the
  # `Robot`-contract object `ControlLoop`/`Telemetry.from_config` actually need). We build
  # exactly ONE leg via `build_biped(..., limbs=[limb_cfg])` rather than biped's own default of
  # "every kind:leg limb in robot.yaml" - see the module docstring's biped-migration note for
  # why (Biped.connect()/enable() are all-or-nothing across every part it holds, and this tool
  # has always driven exactly one side per invocation).
  from huphy.scripts.bringup import build_biped
  from huphy.scripts.commission import CONFIG_NAME, _find_config

  contract = load_contract(args.cache, args.variant)
  jmap = JointMap(args.map) if args.map else JointMap(DEFAULT_MAP_PATH)
  mapper = JointTargetMapper(contract, jmap)
  side = resolve_side(args.limb, jmap)
  our_sim_joints = sim_joints_for_limb(jmap, side)
  enable = (
    enable_motor_names_to_sim_joints(args.enable.split(","), side, jmap)
    if args.enable else set(our_sim_joints)
  )
  default_q = {sj: contract.default_q(sj) for sj in our_sim_joints}

  path = args.config or _find_config()
  if path is None:
    raise SystemExit(f"{CONFIG_NAME} not found - run from inside the HUPHY repo or pass --config")
  try:
    robot = load_robot(path)
  except ConfigError as e:
    raise SystemExit(str(e)) from e

  # `RobotConfig.limb()` is unchanged by biped - still a straight dict lookup on robot.yaml's
  # own `limbs` keys. `side` (resolve_side's result) is usually already that key verbatim (the
  # biped default map's vocabulary IS robot.yaml's vocabulary, by construction), but a legacy
  # map (bare "left"/"right"/"bench") won't match a biped robot.yaml's "left_leg"/"right_leg"
  # key directly - fall back to matching by `LimbConfig.side` ("left"/"right"), inferred from
  # `side`'s own spelling, same as the pre-biped fallback did.
  try:
    limb_cfg = robot.limb(side)
  except KeyError:
    physical_side = "left" if side.lower().startswith("left") or side.lower() == "bench" else (
      "right" if side.lower().startswith("right") else None
    )
    matches = [lc for lc in robot.limbs.values() if lc.side == physical_side]
    if not matches:
      raise SystemExit(
        f"no limb in {path} matches --limb {args.limb!r} (resolved side={side!r}; "
        f"limbs in {path}: {sorted(robot.limbs)})"
      )
    limb_cfg = matches[0]

  biped = build_biped(
    robot, limbs=[limb_cfg],
    allow_uncalibrated=args.allow_uncalibrated,
    gains=Gains(kp=args.kp_max, kd=args.kd_max),  # conservative uniform start; per-joint
    # overrides from the live message replace this every tick a joint is actually commanded
    # (see RemoteMotion.__call__) - this is only what an UNCOMMANDED-this-tick motor sits at.
    ankle_output=ANKLE_POSITION,
  )
  leg = biped.part(limb_cfg.name)  # the one underlying Leg - kinematics/gain-override live here

  try:
    biped.connect()
  except ImportError as e:
    raise SystemExit(str(e)) from e
  except ConnectionError as e:
    raise SystemExit(
      f"{e}\nis the channel up?\n  sudo ip link set {limb_cfg.channel} up type can bitrate 1000000"
    ) from e

  # Clear a latched fault BEFORE ControlLoop._enter() calls robot.enable() (2026-09-04).
  # `deploy/bench/bench_telemetry.py` already had to learn this the hard way: a latched fault
  # from a previous run blocks torque, `enable_torque` then silently does nothing, and the
  # symptom is a command stream that looks perfectly healthy - target exactly `max_delta_deg`
  # ahead of the measured pose (clamp_jump doing its job), telemetry at full rate - while the
  # motor sits at tau ~= 0 and never moves. Iterates every part of `biped` (not just `leg`) so
  # this still clears every leg's bus once a second leg is ever added - guarded by hasattr so a
  # bus with no clear_fault (or a test double) is unaffected.
  for part in biped.parts:
    bus_obj = getattr(part, "bus", None)
    if bus_obj is not None and hasattr(bus_obj, "clear_fault"):
      bus_obj.clear_fault()
      print(f"[remote_motion] cleared any latched motor fault on {part.id} before enabling torque",
            flush=True)

  # Seed each motor's measured position before the control loop starts (2026-09-05, bench).
  #
  # HUPHY refuses to send a command for a motor whose position it does not know:
  # `safety/guards.py::apply` returns `RejectReason.NO_STATE` when `current_deg is None`, and
  # `Leg.build_commands` skips that motor. But in CONTROL mode a position only ever arrives as
  # the REPLY to a command (`ControlLoop.step` calls `refresh()` only in OBSERVE; MIT has no
  # read-only frame). So an empty state table is self-sustaining: no state -> every command is
  # rejected -> nothing is sent -> no reply -> still no state. Measured on the bench: the loop
  # ran a clean 1200 cycles at 100 Hz reporting "0 cycles with no response" - because it sent
  # nothing at all - while the viewer showed every joint dead at 0.0 deg and HUPHY's own
  # telemetry reported ack=-1 ("not commanded") for both live motors.
  #
  # `refresh_states()` is HUPHY's own way out: it sends an all-gains-zero PASSIVE frame, which
  # applies no torque but does make the motor answer with its state. One call before the loop
  # is enough to break the deadlock; after that each command's own reply keeps the table fresh.
  #
  # ...but ONLY once torque is on (2026-09-05, second bench incident). A motor whose driver is
  # off does not answer a MIT command frame at all - it still answers the private "who are you"
  # query, which is why a probe found both motors happily on the bus while this seeding got
  # 0/6. `ControlLoop._enter()` (huphy control/loop.py:363-372) is what calls `robot.enable()`,
  # and that runs INSIDE `loop.run()` - i.e. AFTER this block. So the ordering only worked by
  # luck: it survived while the previous process had been killed hard (leaving torque latched
  # on), and broke the first time a run shut down cleanly, because `_exit()` disables torque on
  # the way out. Then the NO_STATE deadlock above is permanent and the viewer shows every joint
  # dead at 0.0 deg with the loop reporting a perfectly healthy 100 Hz.
  #
  # Enabling here is safe and not a duplicate-with-side-effects: `enable()` only powers the
  # driver, it applies no target (nothing moves until a command carries one), and `_enter()`
  # calling it a second time a few milliseconds later is idempotent.
  biped.enable()
  print("[remote_motion] torque enabled before seeding (motors ignore command frames while off)",
        flush=True)

  for part in biped.parts:
    bus_obj = getattr(part, "bus", None)
    if bus_obj is None or not hasattr(bus_obj, "refresh_states"):
      continue
    missing = bus_obj.refresh_states()
    ids = getattr(bus_obj, "motor_ids", ())
    got = [m for m in ids if m not in (missing or ())]
    print(f"[remote_motion] seeded measured positions on {part.id}: "
          f"{len(got)}/{len(ids)} motors answered (no answer: {sorted(missing or ())})",
          flush=True)

  listen_host, listen_port = args.listen.rsplit(":", 1)
  latest = LatestOnly(expected_arm_token=args.arm_token, expected_contract_hash=contract.contract_sha)
  deadman = DeadmanFilter(
    default_q=default_q, deadman_s=args.deadman_s, hold_s=args.hold_s, return_s=args.return_s,
    enable=enable,
  )
  recv = _Receiver(listen_host, int(listen_port), latest, mapper.known_sim_joints())

  telemetry_cfg = robot.telemetry
  if args.telemetry:
    tele_host, tele_port = args.telemetry.rsplit(":", 1)
    telemetry_cfg = dataclasses.replace(telemetry_cfg, host=tele_host, port=int(tele_port))
  telemetry = tele.Telemetry.from_config(biped, telemetry_cfg)

  # Fault visibility (2026-09-05, docs/121/docs/124) layer (b): best-effort, never fatal - see
  # _make_can_fault_query_fn's own docstring for exactly what is and is not verified here.
  fault_query_fn = _make_can_fault_query_fn(limb_cfg, leg)

  motion = RemoteMotion(
    leg=leg, side=side, action_prefix=limb_cfg.name, mapper=mapper, deadman=deadman,
    latest=latest, gains_cls=Gains,
    kp_max=args.kp_max, kd_max=args.kd_max, default_kp=args.kp_max, default_kd=args.kd_max,
    idle_refresh=args.idle_refresh,
    fault_query_fn=fault_query_fn,
    telemetry_addr=(telemetry_cfg.host, int(telemetry_cfg.port)),
  )
  # constructed after `motion` so the ticker's periodic line can report the running
  # idle-refresh-tick count alongside the receive counters (docs/123 section 11b) - a
  # visibly-nonzero idle_refresh with accepted=0 is exactly "connected but not armed yet",
  # not silence, the same distinction that used to require someone to notice the motor
  # never gets state-locked before Ctrl-C.
  ticker = _StatsTicker(
    latest, recv, interval_s=args.stats_interval_s, label="",
    idle_refresh_fn=lambda: motion.idle_refresh_count,
  )

  loop = ControlLoop(biped, hz=args.hz, telemetry=telemetry, mode=Mode.CONTROL)
  recv.start()
  ticker.start()
  print(
    f"huphy_remote_motion: side={side} (biped limb {limb_cfg.name!r}) {limb_cfg.channel} "
    f"listening on {args.listen}, telemetry -> {telemetry_cfg.host}:{telemetry_cfg.port}, "
    f"enabled={sorted(enable)}, kp_max={args.kp_max} kd_max={args.kd_max}, "
    f"idle_refresh={'on' if args.idle_refresh else 'off'}",
    flush=True,
  )
  try:
    stats = loop.run(motion, duration_s=args.seconds)
    print(f"\n  {stats.summary()}", flush=True)
  finally:
    recv.stop()
    ticker.stop()
    biped.disconnect()
    print(f"remote_motion: stopped. accepted={latest.stats.accepted} "
          f"rejected_seq={latest.stats.rejected_seq} rejected_arm_token={latest.stats.rejected_arm_token} "
          f"rejected_contract={latest.stats.rejected_contract} parse_errors={recv.parse_errors} "
          f"idle_refresh={motion.idle_refresh_count} "
          f"warnings(last 20)={list(motion.warnings)[-20:]}", flush=True)
  return 0


class RemoteMotion:
  """The HUPHY ``Motion`` callable: ``(t, observation) -> Action | None``.  Only exists
  inside ``run_real()``'s huphy-available scope (constructed there and passed to
  ``ControlLoop.run``) - kept as a top-level class rather than a closure so its logic reads
  linearly and so a future test COULD drive it directly against a fake ``leg`` object without
  a real HUPHY install, if one is written (not done here - see docs/123 section 5).

  Biped structure migration (2026-09-04): note the TWO distinct "side" names this class
  carries, which are usually equal in value but mean different things and can genuinely
  diverge (a legacy joint map's ``left``/``right`` against a biped ``robot.yaml``'s
  ``left_leg``/``right_leg``):

    ``side``            the JOINT MAP's own limb key (``resolve_side``'s result) - used to
                         pull this leg's motor targets out of ``mapper.to_motor_targets()``'s
                         ``{limb: {...}}`` dict and to filter ``plan_gains``'s per-joint gains,
                         exactly as before biped existed.
    ``action_prefix``   the ACTUAL biped limb id (``Leg.id`` / ``LimbConfig.name``, e.g.
                         ``"left_leg"``) - the ``/``-prefix ``Biped.split_action`` requires on
                         every action key.  Applied ONLY at the very last step, on the way out.

  Idle refresh (2026-09-04, docs/123 section 11b - a real bench finding, not a bug in this
  file's own logic): HUPHY's ``ControlLoop.step`` only calls ``robot.refresh()`` in
  ``Mode.OBSERVE``; in ``Mode.CONTROL`` (what this script always runs), state is updated
  SOLELY from the response to a command this process just sent (``control/loop.py:257-275`` -
  MIT has no read-only frame, "아무것도 보내지 않으면 아무것도 오지 않음"). Before an operator
  has ever armed anything (``state.phase == "idle"``), returning ``None`` here - the natural
  reading of "there is nothing to command yet" - means literally ZERO frames go out, so every
  enabled joint's telemetry stays frozen at the bus's pre-connect cache (all-zero) forever,
  even though the hardware is fully connected and would answer fine. The fix is NOT to drive
  toward ``default_q`` while idle (that reintroduces the "kp_max toward default_q the instant
  the process connects" swing this bridge deliberately avoided by returning `None` in the
  first place) - it is to send a harmless kp=kd=0 "keep the channel alive" frame instead, at
  the LAST OBSERVED pose (never a synthesized target). See ``_idle_refresh_action``.
  """

  def __init__(self, *, leg, side: str, action_prefix: str, mapper: JointTargetMapper,
               deadman: DeadmanFilter, latest: LatestOnly, gains_cls, kp_max: float,
               kd_max: float, default_kp: float, default_kd: float, idle_refresh: bool = True,
               fault_query_fn: Callable[[], dict[str, bytes | None]] | None = None,
               telemetry_addr: tuple[str, int] | None = None):
    self.leg = leg
    self.side = side
    self.action_prefix = action_prefix
    self.mapper = mapper
    self.deadman = deadman
    self.latest = latest
    self.Gains = gains_cls
    self.kp_max = kp_max
    self.kd_max = kd_max
    self.default_kp = default_kp
    self.default_kd = default_kd
    self.idle_refresh = idle_refresh
    self.idle_refresh_count = 0
    self._ankle_guess = (0.0, 0.0)
    self.warnings: deque[str] = deque(maxlen=200)

    # Fault visibility (2026-09-05, docs/121 section 12c / docs/124) - see
    # bridge/motor_fault.py's module docstring for the two layers this implements.
    self.stuck_detector = StuckDetector()
    self.fault_poller = FaultPoller()
    self.fault_query_fn = fault_query_fn
    """``() -> {motor_name: raw_fault_bytes|None}``, called ONLY while ``FaultPoller`` says
    transmission is idle - ``None`` disables layer (b) entirely (layer (a), ``StuckDetector``,
    is unconditional and needs no CAN access at all, so it is unaffected). ``None`` in every
    unit test and in ``--dry-run``; ``run_real()``'s ``_make_can_fault_query_fn`` builds the
    real one, best-effort (see that function's own docstring)."""
    self.last_fault: dict[str, FaultReading] = {}
    self._stuck_active: dict[str, bool] = {}

    # Overheat cutoff (2026-09-05, docs/121 section 13c): 50 C cuts a joint's torque to zero,
    # 45 C resumes it (ThermalCutoff, bridge/motor_fault.py). Runs alongside layer (a)/(b)
    # above in `_update_fault_visibility` - same reasoning applies (comm can look perfectly
    # fine while a joint is overheating, so this must never depend on the ok/warn/dead verdict
    # either). `_cut_motor_names` is written every tick by `_update_thermal_cutoff` and read by
    # `__call__`'s live-command path to actually withhold torque.
    self.thermal_cutoff = ThermalCutoff()
    self._cut_motor_names: set[str] = set()
    self._temp_unreadable_active: dict[str, bool] = {}
    self.telemetry_addr = telemetry_addr
    self._telemetry_sock = (
      socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if telemetry_addr is not None else None
    )
    """A SEPARATE, small UDP sender for the new numeric fields this task adds (``stuck``/
    ``fault_le``/``fault_be``): HUPHY's own telemetry (``run_real()``'s
    ``tele.Telemetry.from_config``) is a HUPHY class this project never edits (hard
    constraint) and has no extension point for a field it does not know about, so this sends
    its OWN datagram to the SAME destination, in the SAME flat ``{limb}/{motor}/{field}`` wire
    shape ``bench_telemetry.py``/``run_dry()`` already use - the viewer's ``HuphyBridge``
    parses each UDP datagram independently, so this coexists with HUPHY's own stream without
    ever touching it."""

  def __call__(self, t: float, observation):
    msg, age = self.latest.get()
    state = self.deadman.update(msg, age)

    # Fault visibility (2026-09-05): runs EVERY tick, independent of phase/idle - the whole
    # point of the docs/124 incident is that a stuck joint must never look normal just
    # because nothing is currently commanding it.
    self._update_fault_visibility(t, observation, state)

    # "idle" - never armed yet (docs/123 section 11b's class docstring above). `not
    # state.target` is kept as a second, defensive trigger for the same branch: it is
    # normally already unreachable while idle (`DeadmanFilter` itself anchors the idle
    # target to `default_q`), but an empty `--enable` (or a map/side mismatch) would still
    # produce an empty target in a LATER phase too, and that must never fall through to
    # `plan_gains` with an empty `state.target` list either.
    if state.phase == "idle" or not state.target:
      if self.idle_refresh:
        return self._idle_refresh_action(observation)
      return None

    result = self.mapper.to_motor_targets(list(state.target), list(state.target.values()))
    motor_targets = result.get(self.side, {})
    single, ankle_pair = split_motor_targets_into_action(motor_targets)
    if ("ankle_a" in motor_targets) != ("ankle_b" in motor_targets):
      self.warnings.append("only one of ankle_a/ankle_b present this tick - dropped")

    action: dict[str, float] = dict(single)
    if ankle_pair is not None:
      a1_deg, a2_deg = ankle_pair
      try:
        pitch_deg, roll_deg = self.leg.kinematics.solve_fk(
          a1_deg, a2_deg, guess_pitch_deg=self._ankle_guess[0], guess_roll_deg=self._ankle_guess[1],
        )
      except Exception as e:  # AnkleUnreachableError - avoid importing huphy types just to catch
        self.warnings.append(f"ankle FK failed for a1={a1_deg:.2f} a2={a2_deg:.2f}: {e}")
      else:
        self._ankle_guess = (pitch_deg, roll_deg)
        action["ankle_pitch"] = pitch_deg
        action["ankle_roll"] = roll_deg

    if not action:
      return None

    plan = plan_gains(
      list(state.target), self.mapper, self.side, msg, state.phase,
      kp_max=self.kp_max, kd_max=self.kd_max, default_kp=self.default_kp, default_kd=self.default_kd,
    )
    self.warnings.extend(plan.warnings)
    if plan.kp:
      motors = dict(self.leg.config.motors)
      for motor_name, kp in plan.kp.items():
        motors[motor_name] = dataclasses.replace(
          motors[motor_name], gains=self.Gains(kp=kp, kd=plan.kd[motor_name])
        )
      self.leg.config = dataclasses.replace(self.leg.config, motors=motors)

    # Overheat cutoff (2026-09-05, docs/121 section 13c): applied LAST, strictly AFTER the
    # gain plan above, so a cut motor's forced zero-gain can never be clobbered by
    # plan_gains's own kp/kd for that same motor. The motor's key STAYS in `action` (never
    # just omitted) at its LAST OBSERVED pose - never a synthesized target, the exact same
    # reasoning `_idle_refresh_action` already uses ("never drive toward default_q") - so
    # HUPHY's own uncommanded-joint hold behaviour can never apply a real gain against a
    # stale target either; omitting the key is not enough on its own to guarantee zero
    # torque. `_cut_motor_names` only ever contains SINGLE_MOTOR_NAMES (see
    # `_update_thermal_cutoff`'s own docstring for why ankle is not covered).
    for motor_name in self._cut_motor_names:
      obs_pos = (observation or {}).get(f"{self.action_prefix}/{motor_name}{OBS_POS_SUFFIX}")
      action[motor_name] = obs_pos if obs_pos is not None else action.get(motor_name, 0.0)
      motors = dict(self.leg.config.motors)
      motors[motor_name] = dataclasses.replace(motors[motor_name], gains=self.Gains(kp=0.0, kd=0.0))
      self.leg.config = dataclasses.replace(self.leg.config, motors=motors)

    # Biped structure migration (2026-09-04): `action` above is built in bare per-leg names
    # (`Leg.action_features`'s own vocabulary - "hip_pitch"/.../"ankle_pitch"/"ankle_roll",
    # unchanged from before biped existed). `ControlLoop.step` hands this dict to
    # `self.robot.build_commands(action)` where `self.robot` is the `Biped`, not this `Leg` -
    # and `Biped.split_action` HARD-FAILS on any name without its owning limb's `/`-prefix
    # (`robots/biped.py`: "모르는 이름은 에러임"). This (and `_idle_refresh_action` below,
    # the only other `return` in this class) are the only two places that prefix for that -
    # everywhere else (mapper, deadman, gain plan) stays in bare-name / `self.side` (the
    # joint map's own vocabulary) terms, same as pre-biped.
    return {f"{self.action_prefix}/{k}": v for k, v in action.items()}

  # ------------------------------------------------------------ fault visibility (2026-09-05)
  def _update_fault_visibility(self, t: float, observation, state) -> None:
    """Layer (a) (:class:`StuckDetector`, unconditional, no extra CAN traffic) + layer (b)
    (:class:`FaultPoller`-gated raw fault query, only while transmission is idle) - see
    ``bridge/motor_fault.py``'s module docstring. Restricted to the four
    ``SINGLE_MOTOR_NAMES``: the ankle pair's action-space names (``ankle_pitch``/
    ``ankle_roll``) are FK-DERIVED, not raw motor telemetry, and this bridge has no confirmed
    per-crank torque observation in that space - NOT extended to the ankle pair here, a
    stated limitation, not a silent omission (see this task's own report)."""
    obs = observation or {}
    stuck_flags: dict[str, float] = {}
    if state.target:
      motor_targets = self.mapper.to_motor_targets(
        list(state.target), list(state.target.values())
      ).get(self.side, {})
      single, _ = split_motor_targets_into_action(motor_targets)
      for motor_name, target_deg in single.items():
        pos = obs.get(f"{self.action_prefix}/{motor_name}{OBS_POS_SUFFIX}")
        tau = obs.get(f"{self.action_prefix}/{motor_name}{OBS_TAU_SUFFIX}")
        result = self.stuck_detector.update(motor_name, t, target_deg, pos, tau)
        now_stuck = result is not None
        stuck_flags[motor_name] = 1.0 if now_stuck else 0.0
        if now_stuck and not self._stuck_active.get(motor_name, False):
          # Log only on the transition INTO stuck (not every tick while it persists) - the
          # telemetry flag above still stays 1.0 for the whole duration, so the dashboard
          # shows it continuously even though the log/warnings deque gets one line, not a
          # flood at the control loop's own 100 Hz.
          line = describe_stuck_simple(motor_name, result)
          logger.warning("remote_motion: %s", line)
          self.warnings.append(line)
        self._stuck_active[motor_name] = now_stuck

    should_query = self.fault_poller.update(t, state.phase)
    fault_now: dict[str, FaultReading] = {}
    if should_query and self.fault_query_fn is not None:
      try:
        raw = self.fault_query_fn()
      except Exception as e:  # a fault QUERY must never take the control loop down
        self.warnings.append(f"fault query failed: {e}")
        raw = {}
      for motor_name, data in raw.items():
        if data is None:
          continue
        reading = decode_fault_word(data)
        self.last_fault[motor_name] = reading
        fault_now[motor_name] = reading
        line = describe_fault_simple(motor_name, reading)
        logger.warning(
          "remote_motion: %s (little/correct 0x%08X %s, big/HUPHY-order 0x%08X %s)",
          line, reading.little, reading.little_names, reading.big, reading.big_names,
        )
        self.warnings.append(line)

    temp_flags = self._update_thermal_cutoff(observation)
    self._send_fault_telemetry(stuck_flags, fault_now, temp_flags)

  def _enabled_single_motor_names(self) -> set[str]:
    """The subset of :data:`SINGLE_MOTOR_NAMES` currently enabled on this side - the same
    "ankle not covered" restriction as :meth:`_update_fault_visibility` (see that method's
    docstring), reused by the overheat cutoff below."""
    return {
      self.mapper.motor_row(sj)[1] for sj in self._enabled_sim_joints()
    } & set(SINGLE_MOTOR_NAMES)

  def _update_thermal_cutoff(self, observation) -> dict[str, float]:
    """Overheat cutoff (2026-09-05, docs/121 section 13c, user instruction): 50 C cuts a
    joint's torque to zero, 45 C resumes it (:class:`ThermalCutoff`, hysteresis so it does not
    chatter right at the line). Runs every tick, independent of phase - same reasoning as
    :meth:`_update_fault_visibility`: communication can look perfectly healthy while a joint
    is overheating, so this cannot depend on that verdict either.

    Writes :attr:`_cut_motor_names` (consulted by ``__call__``'s live-command path to
    actually withhold torque - this method only DECIDES, it never touches ``action`` or
    ``leg.config`` itself, since idle ticks have no ``action`` to withhold from and already
    send zero gain regardless). Returns the ``{motor}/temp_valid`` and ``{motor}/cutoff``
    telemetry flags for :meth:`_send_fault_telemetry`.

    Restricted to :data:`SINGLE_MOTOR_NAMES` - same ankle limitation as stuck detection
    (cutting one crank motor of an atomic ankle pair without the other would twist the joint,
    ``split_motor_targets_into_action``'s own "통째로 버림" rule).
    """
    obs = observation or {}
    flags: dict[str, float] = {}
    cut_now: set[str] = set()
    for motor_name in self._enabled_single_motor_names():
      temp = obs.get(f"{self.action_prefix}/{motor_name}{OBS_TEMP_SUFFIX}")
      result = self.thermal_cutoff.update(motor_name, temp)
      flags[f"{motor_name}/temp_valid"] = 1.0 if result["valid"] else 0.0
      flags[f"{motor_name}/cutoff"] = 1.0 if result["cut"] else 0.0
      if result["cut"]:
        cut_now.add(motor_name)
      if result["transitioned"]:
        line = describe_cutoff_simple(motor_name, result, resumed=not result["cut"])
        logger.warning("remote_motion: %s", line)
        self.warnings.append(line)
      if result["valid"]:
        self._temp_unreadable_active[motor_name] = False
      elif not self._temp_unreadable_active.get(motor_name, False):
        # Log once per NEW unreadable streak (not every 100 Hz tick) - the telemetry flag
        # above still stays 0.0 for the whole streak, so the dashboard shows "unreadable"
        # continuously (user instruction: "조용히 정규화하지 말 것") even though the
        # log/warnings deque gets one line, not a flood.
        line = f"{motor_name}: 온도를 읽을 수 없음 (값 {temp!r})"
        logger.warning("remote_motion: %s", line)
        self.warnings.append(line)
        self._temp_unreadable_active[motor_name] = True
    self._cut_motor_names = cut_now
    return flags

  def _send_fault_telemetry(
    self, stuck_flags: dict[str, float], fault_now: dict[str, FaultReading],
    temp_flags: dict[str, float] | None = None,
  ) -> None:
    if self._telemetry_sock is None or self.telemetry_addr is None:
      return
    pkt: dict[str, float] = {}
    for motor_name, flag in stuck_flags.items():
      pkt[f"{self.action_prefix}/{motor_name}/stuck"] = flag
    for motor_name, reading in fault_now.items():
      pkt[f"{self.action_prefix}/{motor_name}/fault_le"] = float(reading.little)
      pkt[f"{self.action_prefix}/{motor_name}/fault_be"] = float(reading.big)
    for key, flag in (temp_flags or {}).items():
      pkt[f"{self.action_prefix}/{key}"] = flag  # key already "{motor_name}/temp_valid" etc.
    if not pkt:
      return
    try:
      self._telemetry_sock.sendto(json.dumps(pkt).encode("utf-8"), self.telemetry_addr)
    except OSError as e:
      self.warnings.append(f"fault telemetry send failed: {e}")

  def _enabled_sim_joints(self) -> list[str]:
    """Sim joint names enabled for THIS side. ``self.deadman.enable`` verbatim when it is a
    concrete set (what ``run_real``/``run_dry`` always pass); if it were ``None`` (meaning
    "everything", the same convention ``DeadmanFilter._enabled`` itself uses - not something
    the CLI can currently produce, but this class should not assume its caller always will),
    fall back to every sim joint the mapper knows for this side."""
    universe = (
      self.deadman.enable if self.deadman.enable is not None else self.mapper.known_sim_joints()
    )
    return [sj for sj in universe if self.mapper.motor_row(sj)[0] == self.side]

  def _idle_refresh_action(self, observation) -> dict[str, float] | None:
    """Zero-gain (kp=kd=0) "keep the state channel alive" frame for every ``--enable``d joint
    on this side, positioned at the LAST OBSERVED pose - never ``default_q``, never any other
    synthesized target (see the class docstring's "Idle refresh" section for why). Returns
    ``None`` if nothing is enabled on this side (nothing to refresh, not an error).

    kp=kd=0 through the SAME per-tick gain-override path `plan_gains`'s callers already use
    (`dataclasses.replace(self.leg.config, motors=...)`) - a MIT frame with zero gains and
    zero feedforward torque asks nothing of the motor (HUPHY's own guards/codec see a normal,
    in-range command, not a special "observe" mode - MIT has none), so this can never move a
    joint or fight a human hand on it, armed or not.
    """
    motor_names = {self.mapper.motor_row(sj)[1] for sj in self._enabled_sim_joints()}
    single_names = motor_names & set(SINGLE_MOTOR_NAMES)
    ankle_a_in, ankle_b_in = "ankle_a" in motor_names, "ankle_b" in motor_names
    ankle_enabled = ankle_a_in and ankle_b_in
    if ankle_a_in != ankle_b_in:
      self.warnings.append("idle refresh: only one of ankle_a/ankle_b enabled - dropped")

    joint_names = set(single_names) | ({"ankle_pitch", "ankle_roll"} if ankle_enabled else set())
    if not joint_names:
      return None

    obs = observation or {}
    action = {j: float(obs.get(f"{self.action_prefix}/{j}.pos", 0.0)) for j in joint_names}

    motor_gain_names = single_names | ({"ankle_a", "ankle_b"} if ankle_enabled else set())
    motors = dict(self.leg.config.motors)
    for motor_name in motor_gain_names:
      motors[motor_name] = dataclasses.replace(motors[motor_name], gains=self.Gains(kp=0.0, kd=0.0))
    self.leg.config = dataclasses.replace(self.leg.config, motors=motors)

    self.idle_refresh_count += 1
    return {f"{self.action_prefix}/{k}": v for k, v in action.items()}


def build_parser() -> argparse.ArgumentParser:
  ap = argparse.ArgumentParser(prog="pygviewer bridge huphy_remote_motion", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--variant", default="LegOnly-AB", choices=list(VARIANTS))
  ap.add_argument("--cache", default=CACHE_DIR)
  ap.add_argument("--map", default=None,
                   help="joint map override (default: joint_map_biped.json, biped's left_leg/"
                        "right_leg vocabulary; joint_map_huphy.json's legacy left/right map "
                        "still works if passed explicitly)")
  ap.add_argument("--config", default=None, help="HUPHY robot.yaml (real mode only)")
  ap.add_argument("--limb", required=True,
                   help="which limb to command - the joint map's own vocabulary "
                        "(left_leg/right_leg for the biped default) or a historical alias "
                        "(left/right/left_leg/right_leg/bench); an alias resolves to whichever "
                        "of the map's own limbs represents that side")
  ap.add_argument("--listen", default=f"0.0.0.0:{LISTEN_PORT}")
  ap.add_argument("--telemetry", default=None,
                   help="host:port for HUPHY telemetry (real mode overrides robot.yaml; "
                        "dry-run mode requires this)")
  ap.add_argument("--arm-token", required=True)
  ap.add_argument("--stats-interval-s", type=float, default=5.0,
                   help="print accepted/rejected_*/parse_errors this often while running, not "
                        "only at exit (0 disables the periodic print)")
  ap.add_argument("--enable", default=None, help="comma-separated motor names, e.g. hip_pitch,knee,ankle")
  ap.add_argument("--kp-max", type=float, default=DEFAULT_KP)
  ap.add_argument("--kd-max", type=float, default=DEFAULT_KD)
  ap.add_argument("--deadman-s", type=float, default=DEFAULT_DEADMAN_S)
  ap.add_argument("--hold-s", type=float, default=DEFAULT_HOLD_S,
                   help="flat hold at the last live pose after the deadman trips, before slewing to default")
  ap.add_argument("--return-s", type=float, default=DEFAULT_RETURN_S,
                   help="slew duration from the held pose to default_q, once --hold-s has elapsed")
  ap.add_argument("--hz", type=float, default=DEFAULT_HZ)
  ap.add_argument("--seconds", type=float, default=None, help="run this long then exit; default = until Ctrl-C")
  ap.add_argument("--allow-uncalibrated", action="store_true")
  ap.add_argument(
    "--no-idle-refresh", dest="idle_refresh", action="store_false", default=True,
    help="real mode only (docs/123 section 11b): CONTROL-mode HUPHY only updates a joint's "
         "telemetry from the response to a command THIS process sent, so before anything is "
         "armed, a kp=kd=0 frame is sent for every --enable'd joint just to keep state "
         "flowing - never driving toward default_q. Pass this to go back to sending nothing "
         "(and getting no telemetry) before the first armed target arrives.",
  )
  ap.add_argument("--dry-run", action="store_true",
                   help="no huphy, no CAN - log + echo telemetry assuming instant tracking")
  ap.add_argument("-v", "--verbose", action="store_true")
  return ap


def main(argv: list[str] | None = None) -> int:
  args = build_parser().parse_args(argv)
  logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
  if args.dry_run:
    if not args.telemetry:
      raise SystemExit("--dry-run requires --telemetry host:port (there is no robot.yaml to read a default from)")
    return run_dry(args)
  return run_real(args)


if __name__ == "__main__":
  raise SystemExit(main())
