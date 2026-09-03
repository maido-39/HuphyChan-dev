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

The mapping table (``joint_map_huphy.json``) has exactly 12 rows (2 legs x 6 motors) plus 4
ankle-joint rows (2 legs x pitch/roll, the FK-derived values HUPHY reports alongside the
crank motors).  A ``(limb, motor)`` pair on the wire that is not one of those rows is a HARD
FAILURE - counted, logged, surfaced in ``Status`` - never a regex match or a silent default.
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
DEFAULT_MAP_PATH = Path(__file__).with_name("joint_map_huphy.json")

FAST_MOTOR_FIELDS = ("pos", "tgt", "err", "vel", "tau")
ANKLE_JOINT_FIELDS = ("pos", "tgt", "err", "vel")
KNOWN_MOTORS = ("hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_a", "ankle_b")
KNOWN_ANKLE_JOINTS = ("ankle_pitch", "ankle_roll")


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
  """Stateful packet parser: accumulates FAST fields across packets into a persistent
  per-joint buffer (HUPHY sends one packet per limb, and fast/diag/imu are split further),
  and emits a full 12-joint ``JointState`` whenever a FAST packet updates anything."""

  def __init__(self, contract, jmap: JointMap | None = None):
    self.jmap = jmap or JointMap()
    self.act_names = list(contract.action_joint_names)
    self.travel_sign = {
      n: float(contract.raw["joint_contract"][n]["travel_sign"]) for n in self.act_names
    }
    self._buf = {n: dict(q=None, target=None, qd=None, tau=None) for n in self.act_names}
    self._ankle_buf: dict[str, dict[str, float]] = {}
    self._seq = 0
    self._minus_one_streak: dict[str, int] = {}
    self.warnings: deque[str] = deque(maxlen=20)
    self.packets_parsed = 0

  # ---------------------------------------------------------------------- fast
  def parse_fast(self, payload: dict) -> JointState | None:
    touched = False
    for key, value in payload.items():
      parts = key.split("/")
      if len(parts) != 3:
        continue
      limb, motor, field = parts
      if motor in KNOWN_MOTORS:
        if field not in FAST_MOTOR_FIELDS or field == "err":
          continue  # err is target-minus-pos, derivable; not carried on the canonical wire
        row = self.jmap.sim_joint(limb, motor)  # KeyError propagates: hard failure, not a guess
        sim_joint = row["sim_joint"]
        touched = True
        if self._sentinel(f"{limb}/{motor}/{field}", value):
          continue
        ts = self.travel_sign[sim_joint]
        if field == "pos":
          self._buf[sim_joint]["q"] = huphy_deg_to_sim_rad(value, row["sign"], row["offset_rad"], ts)
        elif field == "tgt":
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
      ankle_derived=({s: dict(v) for s, v in self._ankle_buf.items() if v} or None),
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
