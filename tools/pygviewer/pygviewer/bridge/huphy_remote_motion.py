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

from .. import CACHE_DIR, VARIANTS
from ..contract import load_contract
from ..schema import from_jsonl
from .huphy_udp import DEFAULT_MAP_PATH, JointMap
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


def resolve_side(limb_arg: str, jmap: JointMap | None = None) -> str:
  """Resolve ``--limb`` to the key the JOINT MAP uses for that limb.

  The returned value is not merely "left"/"right": every downstream use treats it as the
  map's own limb key (``row["limb"] == side`` in :func:`sim_joints_for_limb`, the lookup in
  :func:`enable_motor_names_to_sim_joints`, and the ``f"{side}/{motor}/{field}"`` telemetry
  keys that must match HUPHY's own wire format). So a map that names a limb something other
  than left/right - ``joint_map_bench.json`` labels the single bench RS03's row
  ``limb: "bench"``, matching ``bench_rs03_slcan.yaml``'s own limb key and the
  ``bench/knee/...`` keys `deploy/bench/bench_telemetry.py` emits - must resolve to THAT
  name, or nothing matches and the receiver silently drives nothing.

  Accepted, in order: the map's own limb keys verbatim (when ``jmap`` is given), then the
  historical aliases - the map vocabulary ``left``/``right`` (docs/123 section 3b's example
  CLI) and HUPHY ``robot.yaml``'s config keys ``left_leg``/``right_leg``
  (``config/robot_v1.0.yaml``) - since both spellings were already in use and picking one
  would make the other fail to match without saying why.
  """
  raw = limb_arg.strip()
  s = raw.lower()
  known = sorted({limb for (limb, _motor) in jmap.motors}) if jmap is not None else []
  if raw in known:
    return raw
  if s in known:
    return s
  if s in ("left", "right"):
    return s
  if s in ("left_leg", "leftleg"):
    return "left"
  if s in ("right_leg", "rightleg"):
    return "right"
  extra = f" or one of this map's limbs {known}" if known else ""
  raise ValueError(f"--limb {limb_arg!r}: expected one of left/right/left_leg/right_leg{extra}")


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
  tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

  print(
    f"huphy_remote_motion --dry-run: side={side} listening on {args.listen}, "
    f"telemetry(assumed-instant-tracking) -> {args.telemetry}, enabled={sorted(enable)}"
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
        print(f"  [{state.phase}] single={single} ankle_pair={ankle_pair}")
      ticks += 1
      time.sleep(max(0.0, period - (time.monotonic() - t0)))
  except KeyboardInterrupt:
    pass
  finally:
    recv.stop()
    tx_sock.close()
    print(f"dry-run: stopped. accepted={latest.stats.accepted} "
          f"rejected_seq={latest.stats.rejected_seq} rejected_arm_token={latest.stats.rejected_arm_token} "
          f"rejected_contract={latest.stats.rejected_contract} parse_errors={recv.parse_errors}")
  return 0


# =========================================================================== real run (huphy)
def run_real(args) -> int:
  """The real thing. Imports huphy HERE, not at module scope, so this file stays importable
  (and its pure helpers testable) on a machine without HUPHY installed."""
  import huphy  # noqa: F401 - surfaces a clear ImportError here if not installed, not later
  from huphy.config import ConfigError, load_robot
  from huphy.control import ControlLoop, Mode
  from huphy import telemetry as tele
  from huphy.motors.base import Gains
  from huphy.robots.leg import ANKLE_POSITION
  # build_robot, not build_leg (2026-09-04): `build_leg` hard-requires all six leg motors
  # (hip_pitch/hip_roll/hip_yaw/knee/ankle_a/ankle_b) and dies with "다리에 필요한 모터가 없음"
  # on the one-motor bench. HUPHY's own `build_robot` dispatches on `limb.kind` ("leg" ->
  # build_leg, "single" -> build_single_joint) and both builders take the SAME keyword
  # signature on purpose, so this is a drop-in that also keeps every existing leg config
  # working unchanged.
  from huphy.scripts.bringup import build_robot
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

  # HUPHY's own limb config key ("left_leg"/"right_leg") vs this bridge's --limb, which also
  # accepts the joint map's plain "left"/"right" (resolve_side handles both; robot.limb()
  # only knows the config-key form, so try that first and fall back to matching by .side).
  try:
    limb_cfg = robot.limb(args.limb)
  except KeyError:
    matches = [lc for lc in robot.limbs.values() if lc.side == side]
    if not matches:
      raise SystemExit(f"no limb in {path} has side={side!r} (--limb {args.limb!r})")
    limb_cfg = matches[0]

  leg = build_robot(
    robot, limb_cfg,
    allow_uncalibrated=args.allow_uncalibrated,
    gains=Gains(kp=args.kp_max, kd=args.kd_max),  # conservative uniform start; per-joint
    # overrides from the live message replace this every tick a joint is actually commanded
    # (see RemoteMotion.__call__) - this is only what an UNCOMMANDED-this-tick motor sits at.
    ankle_output=ANKLE_POSITION,
  )

  try:
    leg.connect()
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
  # motor sits at tau ~= 0 and never moves. Guarded by hasattr so a robot whose bus has no
  # clear_fault (or a test double) is unaffected.
  bus_obj = getattr(leg, "bus", None)
  if bus_obj is not None and hasattr(bus_obj, "clear_fault"):
    bus_obj.clear_fault()
    print("[remote_motion] cleared any latched motor fault before enabling torque", flush=True)

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
  telemetry = tele.Telemetry.from_config(leg, telemetry_cfg)

  motion = RemoteMotion(
    leg=leg, side=side, mapper=mapper, deadman=deadman, latest=latest, gains_cls=Gains,
    kp_max=args.kp_max, kd_max=args.kd_max, default_kp=args.kp_max, default_kd=args.kd_max,
  )

  loop = ControlLoop(leg, hz=args.hz, telemetry=telemetry, mode=Mode.CONTROL)
  recv.start()
  print(
    f"huphy_remote_motion: side={side} {limb_cfg.channel} listening on {args.listen}, "
    f"telemetry -> {telemetry_cfg.host}:{telemetry_cfg.port}, enabled={sorted(enable)}, "
    f"kp_max={args.kp_max} kd_max={args.kd_max}"
  )
  try:
    stats = loop.run(motion, duration_s=args.seconds)
    print(f"\n  {stats.summary()}")
  finally:
    recv.stop()
    leg.disconnect()
    print(f"remote_motion: stopped. accepted={latest.stats.accepted} "
          f"rejected_seq={latest.stats.rejected_seq} rejected_arm_token={latest.stats.rejected_arm_token} "
          f"rejected_contract={latest.stats.rejected_contract} parse_errors={recv.parse_errors} "
          f"warnings(last 20)={list(motion.warnings)[-20:]}")
  return 0


class RemoteMotion:
  """The HUPHY ``Motion`` callable: ``(t, observation) -> Action | None``.  Only exists
  inside ``run_real()``'s huphy-available scope (constructed there and passed to
  ``ControlLoop.run``) - kept as a top-level class rather than a closure so its logic reads
  linearly and so a future test COULD drive it directly against a fake ``leg`` object without
  a real HUPHY install, if one is written (not done here - see docs/123 section 5)."""

  def __init__(self, *, leg, side: str, mapper: JointTargetMapper, deadman: DeadmanFilter,
               latest: LatestOnly, gains_cls, kp_max: float, kd_max: float,
               default_kp: float, default_kd: float):
    self.leg = leg
    self.side = side
    self.mapper = mapper
    self.deadman = deadman
    self.latest = latest
    self.Gains = gains_cls
    self.kp_max = kp_max
    self.kd_max = kd_max
    self.default_kp = default_kp
    self.default_kd = default_kd
    self._ankle_guess = (0.0, 0.0)
    self.warnings: deque[str] = deque(maxlen=200)

  def __call__(self, t: float, observation):
    msg, age = self.latest.get()
    state = self.deadman.update(msg, age)
    if not state.target:
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

    return action


def build_parser() -> argparse.ArgumentParser:
  ap = argparse.ArgumentParser(prog="pygviewer bridge huphy_remote_motion", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--variant", default="LegOnly-AB", choices=list(VARIANTS))
  ap.add_argument("--cache", default=CACHE_DIR)
  ap.add_argument("--map", default=None, help="joint_map_huphy.json override")
  ap.add_argument("--config", default=None, help="HUPHY robot.yaml (real mode only)")
  ap.add_argument("--limb", required=True, help="left/right or HUPHY's left_leg/right_leg")
  ap.add_argument("--listen", default=f"0.0.0.0:{LISTEN_PORT}")
  ap.add_argument("--telemetry", default=None,
                   help="host:port for HUPHY telemetry (real mode overrides robot.yaml; "
                        "dry-run mode requires this)")
  ap.add_argument("--arm-token", required=True)
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
