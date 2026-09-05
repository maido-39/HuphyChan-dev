"""HUPHY's 100 Hz UDP JSON telemetry -> canonical ``JointState``/``ImuState``.

HUPHY splits its telemetry into up to three UDP packets per cycle (``telemetry/snapshot.py``
module docstring): FAST (``pos tgt err vel tau`` per motor, every cycle), DIAG (temperature,
CAN health, slow), and IMU.  This module reassembles the fast stream into full canonical
joint vectors and turns the IMU stream into ``ImuState`` - it never touches CAN, never
originates a command, and never guesses a joint it does not recognise.

Units on the HUPHY wire: motor ``pos``/``tgt`` are DEGREES in "cal space" (already sign- and
zero-corrected for the physical joint, per ``leg.py get_observation``), ``vel`` is deg/s and
``tau`` is N*m - but ``vel``/``tau`` are passed straight from the motor driver WITHOUT going
through the same calibration as ``pos`` (``leg.py:370-372``), so the sign fixup this bridge
applies from the joint map must be applied to vel and tau too, not only to pos.  ``-1`` is
HUPHY's "no data" sentinel on every field; it becomes ``null``, and three of the same field
in a row raises a warning (docs/121 section 3).

The mapping table (default: ``joint_map_biped.json``) has exactly 12 rows (2 legs x 6 motors)
plus 4 ankle-joint rows (2 legs x pitch/roll, the FK-derived values HUPHY reports alongside
the crank motors).  A ``(limb, motor)`` pair on the wire that is not one of those rows is a
HARD FAILURE - counted, logged, surfaced in ``Status`` - never a regex match or a silent
default.

Biped structure migration (2026-09-04, docs/121 section 12 / docs/123 section 11): HUPHY's
``biped`` branch prefixes every joint/motor name with the OWNING LIMB's ``Leg.id`` (``robots/
biped.py``: "관절 이름에 팔다리 이름이 붙음" - "right_leg/knee" not "right/knee"), and that
``Leg.id`` comes straight from ``robot.yaml``'s ``limbs`` key. ``joint_map_biped.json`` uses
that vocabulary (``left_leg``/``right_leg``) and is now ``DEFAULT_MAP_PATH``.  Nothing in this
module hardcodes a limb name anywhere - ``JointMap`` reads whatever vocabulary the map FILE
uses, so the wire-format parsing below is unchanged either way.  ``joint_map_huphy.json`` (the
pre-biped fork's bare ``left``/``right`` vocabulary) is kept on disk unchanged and stays
loadable - explicitly, via ``--map`` or ``LEGACY_MAP_PATH`` - because it is still what some
tests and ``joint_map_bench.json`` (its ``bench``-limb variant) reference.

ROM clip task (2026-09-04): each row MAY also carry an optional ``rom_deg: [lo, hi]`` field -
the real hardware's own calibrated ROM (HUPHY ``Motor.limits_deg``), in the same
already-calibrated cal-space degrees ``pos``/``tgt`` arrive in.  ``null`` (both maps ship
with it null on every row, since neither rig is commissioned yet) means "no clip here".
This is defense-in-depth ONLY, layered in FRONT of ``sim_core.py``'s own hard model-range
clip at the qpos-snap point, which stays the actual safety backstop regardless.
"""

from __future__ import annotations

import json
import math
import socket
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

from ..schema import ImuState, JointState

DEFAULT_PORT = 9871
DEFAULT_MAP_PATH = Path(__file__).with_name("joint_map_biped.json")
LEGACY_MAP_PATH = Path(__file__).with_name("joint_map_huphy.json")
"""The pre-biped fork's map: same 12+4 rows, bare ``left``/``right`` limb vocabulary. Kept for
anything that still names it explicitly (``joint_map_bench.json``'s own ``bench``-limb variant
predates biped too, and is unaffected by this DEFAULT_MAP_PATH switch either way)."""

FAST_MOTOR_FIELDS = ("pos", "tgt", "err", "vel", "tau")
ANKLE_JOINT_FIELDS = ("pos", "tgt", "err", "vel")
KNOWN_MOTORS = ("hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_a", "ankle_b")
KNOWN_ANKLE_JOINTS = ("ankle_pitch", "ankle_roll")

# Motor health task (2026-09-04): HUPHY's own DIAG fields (telemetry/snapshot.py
# DIAG_MOTOR_FIELDS - temp/age/ack/miss) - split into their own, slower UDP packet on real
# HUPHY (module docstring), but a simple single-packet sender (today's bench_telemetry.py)
# may fold them into the SAME payload as the FAST fields. Both shapes work unchanged here:
# they are handled in the SAME per-field dispatch loop as FAST_MOTOR_FIELDS below, so a
# diag-only packet (real HUPHY) or a combined one (bench) both set `touched=True` and
# refresh whichever of temp/age/ack/miss it carries in the SAME persistent per-joint buffer
# FAST already accumulates into - see the class docstring.
DIAG_MOTOR_FIELDS = (
  "temp", "age", "ack", "miss", "stuck", "fault_le", "fault_be", "temp_valid", "cutoff",
  # +-180 fold guard (docs/125 round 3): wrap_blocked says this joint is refusing commands,
  # wrap_margin says how many degrees are left before the fold.
  "wrap_blocked", "wrap_margin",
  # Which robot-side program is driving (scenario.py). Same value on every joint it drives.
  "prog",
)
"""Fault visibility (2026-09-05, docs/121/docs/124) added `stuck`/`fault_le`/`fault_be` to the
original temp/age/ack/miss set - handled the SAME way (never travel-sign/offset corrected,
since none of these is a joint ANGLE; a negative value is treated as "no data" the same as any
other DIAG field, though none of these three is ever legitimately negative in practice).
Unlike temp/age/ack/miss (which come from HUPHY's own Telemetry, split into the slower DIAG
packet), these three are sent by huphy_remote_motion.py's OWN small supplementary UDP sender
(RemoteMotion._send_fault_telemetry) - a SEPARATE datagram to the same destination, since
HUPHY's Telemetry class (never edited, hard project constraint) has no extension point for a
field it does not know about. Both shapes land in the SAME per-field dispatch loop below
either way, so it makes no difference to this bridge which sender a given tick's payload
came from."""


class JointMap:
  """The explicit limb/motor -> sim-joint table.  No fallback: an unlisted pair raises."""

  def __init__(self, path: str | Path = DEFAULT_MAP_PATH):
    self.path = Path(path)
    raw = json.loads(self.path.read_text())
    self.side_mapping_verified = bool(raw.get("side_mapping_verified"))
    self.motors = {(m["limb"], m["motor"]): m for m in raw["motors"]}
    if len(self.motors) != 12:
      raise ValueError(f"{self.path}: expected 12 motor rows (2 legs x 6 motors), found {len(self.motors)}")
    self.ankle_joints = {(a["limb"], a["joint"]): a for a in raw["ankle_joints"]}

  def sim_joint(self, limb: str, motor: str) -> dict:
    row = self.motors.get((limb, motor))
    if row is None:
      raise KeyError(
        f"(limb={limb!r}, motor={motor!r}) is not one of the 12 rows in {self.path} - "
        "hard failure, not a guess (docs/121 section 3)"
      )
    return row

  def ankle_joint(self, limb: str, joint: str) -> dict:
    row = self.ankle_joints.get((limb, joint))
    if row is None:
      raise KeyError(f"(limb={limb!r}, joint={joint!r}) is not in {self.path}'s ankle_joints table")
    return row


def huphy_deg_to_sim_rad(deg: float, sign: int, offset_rad: float, travel_sign: float) -> float:
  """The one conversion this whole bridge exists to get right: HUPHY physical degrees, in
  its own "cal space" convention, into the sim's canonical, travel-signed radians.

  ``sign``/``offset_rad`` come from the joint map (hardware-side calibration); ``travel_sign``
  comes from the MODEL CONTRACT (docs/reward_research/2026-09-03_stiff_knee_root_cause.md) -
  it is never guessed here, only looked up.  Verified: a physical +30 deg knee flexion on
  both legs (map default sign=1, offset=0) converts to sim L_knee +0.5236 / R_knee -0.5236
  rad, matching the contract's travel_sign (+1 / -1) - see test_bridge_huphy.py.
  """
  return travel_sign * float(sign) * math.radians(deg) + float(offset_rad)


def huphy_deg_s_to_sim_rad_s(deg_s: float, sign: int, travel_sign: float) -> float:
  """Same sign convention as position, no offset - a rate has no zero-point to correct."""
  return travel_sign * float(sign) * math.radians(deg_s)


def huphy_torque_to_sim(nm: float, sign: int, travel_sign: float) -> float:
  """Torque already arrives in N*m; only the sign convention needs correcting."""
  return travel_sign * float(sign) * float(nm)


class HuphyBridge:
  """Stateful packet parser: accumulates FAST fields AND DIAG motor-health fields (temp/age/
  ack/miss, 2026-09-04) across packets into a persistent per-joint buffer (HUPHY sends one
  packet per limb, and fast/diag/imu are split further), and emits a full 12-joint
  ``JointState`` whenever a FAST-or-DIAG packet updates anything - a diag-only packet still
  triggers an emission, carrying the LAST KNOWN pos/tgt/vel/tau for a joint alongside its
  freshly-updated temp/age/ack/miss, same accumulation spirit as FAST always had."""

  def __init__(self, contract, jmap: JointMap | None = None):
    self.jmap = jmap or JointMap()
    self.act_names = list(contract.action_joint_names)
    self.travel_sign = {
      n: float(contract.raw["joint_contract"][n]["travel_sign"]) for n in self.act_names
    }
    self._buf = {
      n: dict(
        q=None, target=None, qd=None, tau=None, temp=None, age=None, ack=None, miss=None,
        stuck=None, fault_le=None, fault_be=None, temp_valid=None, cutoff=None, prog=None,
      )
      for n in self.act_names
    }
    self._ankle_buf: dict[str, dict[str, float]] = {}
    self._seq = 0
    self._minus_one_streak: dict[str, int] = {}
    self.warnings: deque[str] = deque(maxlen=20)
    self.packets_parsed = 0
    self._imu_seq = 0
    # ROM clip task (2026-09-04): a joint-map row MAY carry an optional `rom_deg: [lo, hi]`
    # field - the real hardware's OWN calibrated ROM (HUPHY `Motor.limits_deg`, filled in
    # once the leg has been through `commission sweep`), in the same already-calibrated
    # cal-space degrees `pos`/`tgt` arrive in on this wire. `None` (both joint maps ship
    # with `rom_deg: null` on every row today, since neither rig has been commissioned yet)
    # means "no clip here" - defense-in-depth ONLY, layered in FRONT of SimCore's own hard
    # model-range clip at the qpos-snap point (sim_core.py `_update_replay_targets`), which
    # is the actual safety backstop regardless of whether any bridge sets this.
    self.rom_clamp_count: dict[str, int] = {}

  def _clip_rom_deg(self, sim_joint: str, row: dict, value: float) -> float:
    rom = row.get("rom_deg")
    if rom is None:
      return value
    lo, hi = float(rom[0]), float(rom[1])
    clipped = min(max(value, lo), hi)
    if clipped != value:
      n = self.rom_clamp_count.get(sim_joint, 0) + 1
      self.rom_clamp_count[sim_joint] = n
      if n == 1:
        self.warnings.append(f"{sim_joint}: rom_deg {value:.2f} -> {clipped:.2f} deg")
    return clipped

  # ---------------------------------------------------------------------- fast
  def parse_fast(self, payload: dict) -> JointState | None:
    touched = False
    for key, value in payload.items():
      parts = key.split("/")
      if len(parts) != 3:
        continue
      limb, motor, field = parts
      if limb == "imu":
        continue  # handled by parse_imu - not a joint value
      if motor in KNOWN_MOTORS:
        if field == "err":
          continue  # err is target-minus-pos, derivable; not carried on the canonical wire
        if field in DIAG_MOTOR_FIELDS:
          row = self.jmap.sim_joint(limb, motor)  # KeyError propagates: hard failure, not a guess
          sim_joint = row["sim_joint"]
          touched = True
          # Motor health (2026-09-04): temp/age/ack/miss are NEVER travel-sign/offset
          # corrected (they are not joint ANGLES) and never routed through `_sentinel`'s
          # 3-in-a-row WARNING tracking - unlike a missing pos/tgt sample, "age=-1" (never
          # responded) or "ack=-1" (not commanded) are legitimate, common steady states for
          # an idle/unconnected motor, not evidence of a flapping connection worth a warning
          # log line every time. Just the uniform "-1 (or any negative) means null" wire
          # convention (schema.py's rule), silently.
          self._buf[sim_joint][field] = None if value is None or value < 0 else float(value)
          continue
        if field not in FAST_MOTOR_FIELDS:
          continue  # guard/*, can/* etc - genuinely not interpreted here
        row = self.jmap.sim_joint(limb, motor)  # KeyError propagates: hard failure, not a guess
        sim_joint = row["sim_joint"]
        touched = True
        if self._sentinel(f"{limb}/{motor}/{field}", value):
          continue
        ts = self.travel_sign[sim_joint]
        if field == "pos":
          value = self._clip_rom_deg(sim_joint, row, value)
          self._buf[sim_joint]["q"] = huphy_deg_to_sim_rad(value, row["sign"], row["offset_rad"], ts)
        elif field == "tgt":
          value = self._clip_rom_deg(sim_joint, row, value)
          self._buf[sim_joint]["target"] = huphy_deg_to_sim_rad(value, row["sign"], row["offset_rad"], ts)
        elif field == "vel":
          self._buf[sim_joint]["qd"] = huphy_deg_s_to_sim_rad_s(value, row["sign"], ts)
        elif field == "tau":
          self._buf[sim_joint]["tau"] = huphy_torque_to_sim(value, row["sign"], ts)
      elif motor in KNOWN_ANKLE_JOINTS:
        if field != "pos":
          continue  # only the FK-derived angle is carried in ankle_derived
        row = self.jmap.ankle_joint(limb, motor)
        touched = True
        if self._sentinel(f"{limb}/{motor}/{field}", value):
          continue
        side_buf = self._ankle_buf.setdefault(row["side"], {})
        side_buf[row["field"]] = float(row["sign"]) * math.radians(value) + float(row["offset_rad"])
      # anything else (diag: temp/age/ack/miss, guard/*, can/*) is intentionally not
      # interpreted here - it is not a canonical joint value, so there is nothing to convert
    if not touched:
      return None
    self.packets_parsed += 1
    return self._emit_joint_state()

  def _emit_joint_state(self) -> JointState:
    self._seq += 1
    return JointState(
      t_ns=time.monotonic_ns(),
      seq=self._seq,
      src="real",
      contract_hash=None,  # hardware has no notion of a baked sim contract
      joint_names=list(self.act_names),
      q=[self._buf[n]["q"] for n in self.act_names],
      qd=[self._buf[n]["qd"] for n in self.act_names],
      tau_est=[self._buf[n]["tau"] for n in self.act_names],
      target=[self._buf[n]["target"] for n in self.act_names],
      temp_c=[self._buf[n]["temp"] for n in self.act_names],
      motor_age_ms=[self._buf[n]["age"] for n in self.act_names],
      ack=[self._buf[n]["ack"] for n in self.act_names],
      miss=[self._buf[n]["miss"] for n in self.act_names],
      ankle_derived=({s: dict(v) for s, v in self._ankle_buf.items() if v} or None),
      stuck=[self._buf[n]["stuck"] for n in self.act_names],
      fault_le=[self._buf[n]["fault_le"] for n in self.act_names],
      fault_be=[self._buf[n]["fault_be"] for n in self.act_names],
      temp_valid=[self._buf[n]["temp_valid"] for n in self.act_names],
      cutoff=[self._buf[n]["cutoff"] for n in self.act_names],
      prog=[self._buf[n]["prog"] for n in self.act_names],
    )

  # ---------------------------------------------------------------------- imu
  def parse_imu(self, payload: dict) -> ImuState | None:
    """``-1`` is HUPHY's "missing" sentinel only on ``age``/``sensor_dt`` fields
    (``IMU_MISSING_IS_MINUS_ONE`` in ``telemetry/snapshot.py``) - everything else (gyro,
    accel, ``grav_*``) is blanked to 0.0 when unknown, which is indistinguishable from a
    real zero on HUPHY's own wire and not something this bridge can fix.  Applying the -1
    check to ``grav_z`` too would be a real bug: -1.0 is exactly what an upright, standing
    robot reports there, and this bridge nulled out the single most common IMU reading
    before this was caught by ``test_bridge_huphy.py``."""
    touched = False
    gx = gy = gz = ax = ay = az = gvx = gvy = gvz = age_ms = None
    for key, value in payload.items():
      parts = key.split("/")
      if len(parts) != 3 or parts[0] != "imu":
        continue
      _, _name, field = parts
      touched = True
      if field == "age":
        if self._sentinel(key, value):
          continue
        age_ms = value
        continue
      if field == "gx":
        gx = math.radians(value)
      elif field == "gy":
        gy = math.radians(value)
      elif field == "gz":
        gz = math.radians(value)
      elif field == "ax":
        ax = value
      elif field == "ay":
        ay = value
      elif field == "az":
        az = value
      elif field == "grav_x":
        gvx = value
      elif field == "grav_y":
        gvy = value
      elif field == "grav_z":
        gvz = value
    if not touched:
      return None
    self._seq += 1
    return ImuState(
      t_ns=time.monotonic_ns(),
      seq=self._seq,
      src="real",
      contract_hash=None,
      # HUPHY has already reordered its sensor's native (z,y,x,w) quaternion and computed
      # gravity_b from it; re-deriving a quaternion here would risk a second, independent
      # reordering bug, so gravity_b is taken from HUPHY's own grav_* fields directly and
      # quat is left null unless a future need requires it.
      quat_wxyz=None,
      gyro_rad_s=([gx, gy, gz] if None not in (gx, gy, gz) else None),
      acc_m_s2=([ax, ay, az] if None not in (ax, ay, az) else None),
      gravity_b=([gvx, gvy, gvz] if None not in (gvx, gvy, gvz) else None),
      age_s=(age_ms / 1e3 if age_ms not in (None, -1) else None),
    )

  # ---------------------------------------------------------------------- sentinel tracking
  def _sentinel(self, field: str, value) -> bool:
    """True if ``value`` is HUPHY's -1 "no data" sentinel; tracks 3-in-a-row for a warning."""
    is_missing = value == -1
    n = self._minus_one_streak.get(field, 0) + 1 if is_missing else 0
    self._minus_one_streak[field] = n
    if n == 3:
      self.warnings.append(f"{field}: -1 (missing) for 3 packets in a row")
    return is_missing


class HuphyUdpReceiver:
  """Owns the UDP socket and a background thread.  Never raises into the caller: a hard
  mapping failure or a malformed packet is counted (``core.real.note_bridge_error``) and the
  next packet is still processed - one bad line from the robot must not take the bridge
  down, the same "send and forget, never block" spirit as HUPHY's own ``UdpSink``."""

  def __init__(
    self,
    core,
    port: int = DEFAULT_PORT,
    host: str = "0.0.0.0",
    jmap_path: str | Path | None = None,
  ):
    self.core = core
    self.bridge = HuphyBridge(core.c, JointMap(jmap_path) if jmap_path else JointMap())
    self.port = port
    self.host = host
    self._sock: socket.socket | None = None
    self._thread: threading.Thread | None = None
    self._running = False
    self.packets = 0
    self.hard_failures = 0
    self.last_error: str | None = None

  def start(self) -> None:
    self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self._sock.bind((self.host, self.port))
    self._sock.settimeout(0.5)
    self._running = True
    self._thread = threading.Thread(target=self._loop, name="pygviewer-huphy-udp", daemon=True)
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
      self.packets += 1
      try:
        payload = json.loads(data.decode("utf-8"))
      except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        self.hard_failures += 1
        self.last_error = f"bad packet: {exc}"
        self.core.real.note_bridge_error(self.last_error)
        continue
      try:
        if any(k.startswith("imu/") for k in payload):
          msg = self.bridge.parse_imu(payload)
          if msg is not None:
            self.core.real.ingest_imu_state(msg)
        else:
          msg = self.bridge.parse_fast(payload)
          if msg is not None:
            self.core.real.ingest_joint_state(msg)
      except KeyError as exc:
        self.hard_failures += 1
        self.last_error = str(exc)
        self.core.real.note_bridge_error(self.last_error)


def main(argv: list[str] | None = None) -> int:
  """Standalone launcher: ``run.py bridge huphy --variant ... [--port 9871]``.  Runs the
  receiver against a live SimCore (headless, no viser/API) until Ctrl-C."""
  import argparse

  from .. import CACHE_DIR, VARIANTS
  from ..contract import load_contract
  from ..sim_core import SimCore

  ap = argparse.ArgumentParser(prog="pygviewer bridge huphy")
  ap.add_argument("--variant", default="LegOnly-AB", choices=list(VARIANTS))
  ap.add_argument("--cache", default=CACHE_DIR)
  ap.add_argument("--port", type=int, default=DEFAULT_PORT)
  ap.add_argument("--host", default="0.0.0.0")
  ap.add_argument("--map", default=None)
  a = ap.parse_args(argv)

  c = load_contract(a.cache, a.variant)
  core = SimCore(c, realtime=True)
  core.start()
  recv = HuphyUdpReceiver(core, port=a.port, host=a.host, jmap_path=a.map)
  recv.start()
  print(f"HUPHY UDP bridge listening on {a.host}:{a.port} for {a.variant}, feeding SimCore")
  try:
    while True:
      time.sleep(1.0)
  except KeyboardInterrupt:
    pass
  finally:
    recv.stop()
    core.stop()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
