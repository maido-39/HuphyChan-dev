"""docs/123 plan A item 4: a stand-in for the robot side that needs no ``huphy`` install and
no hardware - so the WHOLE round trip (``tx_client.py`` -> UDP :9872 -> here -> a 1st-order PD
motor model -> HUPHY-format UDP telemetry :9870 -> ``huphy_udp.py``'s existing receiver) can
be exercised on this machine before anything ships to the remote robot host (docs/123 section
4: "로컬에서는 더미 수신기로 스키마·데드맨 검증").

What it is NOT: a physically calibrated simulator.  The per-joint inertia/damping are CLI
knobs with sane-looking defaults, not measured values - the point is to prove the WIRE and
the SAFETY STATE MACHINE (parsing, arm/seq/contract gating, enable filtering, deadman/return)
round-trip correctly, not to predict how a real RS03 responds.

Everything a real robot-side receiver needs is reused, not reimplemented, from files that are
independently unit-tested:

  * ``schema.from_jsonl``            parses/validates the incoming ``JointTarget``
  * ``bridge.remote_target``          arm/seq/contract gating + deadman/hold/return
  * ``bridge.tx_map.JointTargetMapper``  sim-rad -> HUPHY cal-deg, same table/travel_sign
                                       used for the OUTGOING telemetry as for a real
                                       command, so a wrong sign shows up as an obviously
                                       wrong number on the SAME plot the real robot's
                                       telemetry would land on (``huphy_udp.py``'s receive
                                       path, unchanged, is what reads this back out).

No ``huphy`` import anywhere in this file - contrast with ``huphy_remote_motion.py``, which
needs it for everything past the pure conversion step.
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
import threading
import time
from dataclasses import dataclass

from .. import CACHE_DIR, VARIANTS
from ..contract import load_contract
from ..schema import from_jsonl
from .remote_target import (
  DEFAULT_DEADMAN_S,
  DEFAULT_HOLD_S,
  DEFAULT_RETURN_S,
  DeadmanFilter,
  LatestOnly,
)
from .tx_map import JointTargetMapper, clamp_gain, sim_rad_s_to_cal_deg_s, sim_rad_to_cal_deg

logger = logging.getLogger(__name__)

LISTEN_PORT = 9872
TELEMETRY_PORT = 9870
PHYSICS_HZ = 100.0
DEFAULT_INERTIA = 0.02  # kg*m^2, arbitrary but not silly for a single actuated link + rotor
DEFAULT_DAMPING = 0.05  # N*m*s/rad
DEFAULT_KP = 5.0
DEFAULT_KD = 0.5


@dataclass
class MotorModel:
  """One joint's 1st-order-in-velocity PD response: ``I*qdd = kp*(target-q) - kd*qd -
  b*qd``.  Semi-implicit (symplectic) Euler - stable at the step sizes this runs at without
  needing an actual integrator library, and it is the same scheme ``mjlab``'s own physics
  step effectively is for a single decoupled DOF, which is the point of comparison here."""

  q: float
  qd: float = 0.0
  inertia: float = DEFAULT_INERTIA
  damping: float = DEFAULT_DAMPING

  def step(self, target: float, kp: float, kd: float, dt: float) -> float:
    """Advances one physics tick; returns the torque it applied this tick (N*m)."""
    tau = kp * (target - self.q) - kd * self.qd - self.damping * self.qd
    qdd = tau / self.inertia
    self.qd += qdd * dt
    self.q += self.qd * dt
    return tau


class DummyRx:
  """Owns the two sockets and the two threads (receive, physics+telemetry).  Mirrors
  ``huphy_udp.HuphyUdpReceiver``'s start/stop shape so the two feel the same to operate."""

  def __init__(
    self,
    *,
    contract,
    listen_host: str = "0.0.0.0",
    listen_port: int = LISTEN_PORT,
    telemetry_host: str = "127.0.0.1",
    telemetry_port: int = TELEMETRY_PORT,
    arm_token: str,
    enable: set[str] | None = None,
    kp_max: float = DEFAULT_KP,
    kd_max: float = DEFAULT_KD,
    deadman_s: float = DEFAULT_DEADMAN_S,
    hold_s: float = DEFAULT_HOLD_S,
    return_s: float = DEFAULT_RETURN_S,
    hz: float = PHYSICS_HZ,
    inertia: float = DEFAULT_INERTIA,
    damping: float = DEFAULT_DAMPING,
  ) -> None:
    self.contract = contract
    self.mapper = JointTargetMapper(contract)
    self.listen_host = listen_host
    self.listen_port = listen_port
    self.telemetry_host = telemetry_host
    self.telemetry_port = telemetry_port
    self.kp_max = kp_max
    self.kd_max = kd_max
    self.hz = hz
    self.period_s = 1.0 / hz

    known = self.mapper.known_sim_joints() & set(contract.action_joint_names)
    if enable is not None:
      unknown_enable = enable - known
      if unknown_enable:
        raise ValueError(f"--enable names not known: {sorted(unknown_enable)} (known: {sorted(known)})")
    self.enabled_joints = enable if enable is not None else set(known)

    default_q = {n: contract.default_q(n) for n in known}
    self.latest = LatestOnly(expected_arm_token=arm_token, expected_contract_hash=contract.contract_sha)
    self.deadman = DeadmanFilter(
      default_q=default_q, deadman_s=deadman_s, hold_s=hold_s, return_s=return_s,
      enable=self.enabled_joints,
    )
    self.motors: dict[str, MotorModel] = {
      n: MotorModel(q=default_q[n], inertia=inertia, damping=damping) for n in known
    }
    self._last_kp: dict[str, float] = {n: kp_max for n in known}
    self._last_kd: dict[str, float] = {n: kd_max for n in known}
    self._last_cmd: dict[str, float] = dict(default_q)  # what the "motor firmware" is holding

    self._rx_sock: socket.socket | None = None
    self._tx_sock: socket.socket | None = None
    self._rx_thread: threading.Thread | None = None
    self._physics_thread: threading.Thread | None = None
    self._running = False
    self.last_phase: str | None = None
    self.ticks = 0

  # -------------------------------------------------------------------------- lifecycle
  def start(self) -> None:
    self._rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self._rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self._rx_sock.bind((self.listen_host, self.listen_port))
    self._rx_sock.settimeout(0.5)
    self._tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self._running = True
    self._rx_thread = threading.Thread(target=self._recv_loop, name="dummy-rx-recv", daemon=True)
    self._physics_thread = threading.Thread(target=self._physics_loop, name="dummy-rx-physics", daemon=True)
    self._rx_thread.start()
    self._physics_thread.start()

  def stop(self) -> None:
    self._running = False
    for t in (self._rx_thread, self._physics_thread):
      if t is not None:
        t.join(timeout=2.0)
    self._rx_thread = self._physics_thread = None
    if self._rx_sock is not None:
      self._rx_sock.close()
      self._rx_sock = None
    if self._tx_sock is not None:
      self._tx_sock.close()
      self._tx_sock = None

  def __enter__(self) -> "DummyRx":
    self.start()
    return self

  def __exit__(self, *exc) -> None:
    self.stop()

  # --------------------------------------------------------------------------- receive
  def _recv_loop(self) -> None:
    while self._running:
      try:
        data, _addr = self._rx_sock.recvfrom(4096)
      except socket.timeout:
        continue
      except OSError:
        break
      try:
        msg = from_jsonl(data.decode("utf-8"))
      except (ValueError, UnicodeDecodeError) as e:
        self.latest.stats.parse_errors += 1
        logger.warning("dummy_rx: bad packet: %s", e)
        continue
      if msg.type != "JointTarget":
        self.latest.stats.parse_errors += 1
        logger.warning("dummy_rx: unexpected message type %r on :%d", msg.type, self.listen_port)
        continue
      unknown = sorted(set(msg.joint_names) - self.mapper.known_sim_joints())
      if unknown:
        self.latest.stats.parse_errors += 1
        logger.warning("dummy_rx: rejecting message with unknown joint(s) %s", unknown)
        continue
      accepted = self.latest.put(msg)
      if not accepted:
        logger.debug("dummy_rx: rejected seq=%s (stats=%s)", msg.seq, self.latest.stats)

  # --------------------------------------------------------------------------- physics
  def _physics_loop(self) -> None:
    next_tick = time.monotonic()
    while self._running:
      msg, age = self.latest.get()
      state = self.deadman.update(msg, age)
      if state.phase != self.last_phase:
        logger.info("dummy_rx: phase %s -> %s (enabled=%s)", self.last_phase, state.phase,
                    sorted(self.enabled_joints))
        self.last_phase = state.phase

      live_kp = dict(zip(msg.joint_names, msg.kp)) if (msg is not None and state.phase == "live" and msg.kp) else {}
      live_kd = dict(zip(msg.joint_names, msg.kd)) if (msg is not None and state.phase == "live" and msg.kd) else {}

      by_limb: dict[str, dict[str, float]] = {}
      for name, motor in self.motors.items():
        if name in state.target:
          target = state.target[name]
          self._last_cmd[name] = target
          if name in live_kp:
            self._last_kp[name], warns_kp = clamp_gain(live_kp[name], self.kp_max, name=f"kp[{name}]")
            for w in warns_kp:
              logger.warning("dummy_rx: %s", w)
          if name in live_kd:
            self._last_kd[name], warns_kd = clamp_gain(live_kd[name], self.kd_max, name=f"kd[{name}]")
            for w in warns_kd:
              logger.warning("dummy_rx: %s", w)
        else:
          # not enabled / not commanded this tick - "motor firmware" holds its last target,
          # exactly like a real MIT-mode motor that received no new frame this cycle.
          target = self._last_cmd[name]
        tau = motor.step(target, self._last_kp[name], self._last_kd[name], self.period_s)

        limb, motor_name, row = self.mapper.motor_row(name)
        ts = self.mapper.travel_sign[name]
        pos_deg = sim_rad_to_cal_deg(motor.q, row["sign"], row["offset_rad"], ts)
        tgt_deg = sim_rad_to_cal_deg(target, row["sign"], row["offset_rad"], ts)
        vel_deg_s = sim_rad_s_to_cal_deg_s(motor.qd, row["sign"], ts)
        tau_hw = ts * row["sign"] * tau
        by_limb.setdefault(limb, {})[motor_name] = dict(
          pos=pos_deg, tgt=tgt_deg, err=tgt_deg - pos_deg, vel=vel_deg_s, tau=tau_hw,
        )
      self.ticks += 1
      self._send_telemetry(by_limb)

      next_tick += self.period_s
      sleep_s = next_tick - time.monotonic()
      if sleep_s > 0:
        time.sleep(sleep_s)
      else:
        next_tick = time.monotonic()  # fell behind - do not try to catch up (same policy as HUPHY's own loop)

  def _send_telemetry(self, by_limb: dict[str, dict[str, dict[str, float]]]) -> None:
    if self._tx_sock is None:
      return
    for limb, motors in by_limb.items():
      pkt: dict[str, float] = {"t": round(self.ticks * self.period_s, 3), "loop_dt": round(self.period_s * 1000.0, 3)}
      for motor_name, fields in motors.items():
        for field, value in fields.items():
          pkt[f"{limb}/{motor_name}/{field}"] = round(value, 2)
      try:
        self._tx_sock.sendto(json.dumps(pkt).encode("utf-8"), (self.telemetry_host, self.telemetry_port))
      except OSError as e:
        logger.warning("dummy_rx: telemetry send failed: %s", e)


def main(argv: list[str] | None = None) -> int:
  ap = argparse.ArgumentParser(prog="pygviewer bridge dummy_rx", description=__doc__)
  ap.add_argument("--variant", default="LegOnly-AB", choices=list(VARIANTS))
  ap.add_argument("--cache", default=CACHE_DIR)
  ap.add_argument("--listen", default=f"0.0.0.0:{LISTEN_PORT}")
  ap.add_argument("--telemetry", default=f"127.0.0.1:{TELEMETRY_PORT}")
  ap.add_argument("--arm-token", required=True)
  ap.add_argument("--enable", default=None, help="comma-separated sim joint names; default = all 12")
  ap.add_argument("--kp-max", type=float, default=DEFAULT_KP)
  ap.add_argument("--kd-max", type=float, default=DEFAULT_KD)
  ap.add_argument("--deadman-s", type=float, default=DEFAULT_DEADMAN_S)
  ap.add_argument("--hold-s", type=float, default=DEFAULT_HOLD_S,
                  help="flat hold at the last live pose after the deadman trips, before slewing to default")
  ap.add_argument("--return-s", type=float, default=DEFAULT_RETURN_S, dest="return_s",
                  help="slew duration from the held pose to default_q, once --hold-s has elapsed")
  ap.add_argument("--hz", type=float, default=PHYSICS_HZ)
  ap.add_argument("--inertia", type=float, default=DEFAULT_INERTIA)
  ap.add_argument("--damping", type=float, default=DEFAULT_DAMPING)
  ap.add_argument("--seconds", type=float, default=None, help="run this long then exit; default = until Ctrl-C")
  ap.add_argument("-v", "--verbose", action="store_true")
  a = ap.parse_args(argv)
  logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(levelname)s %(message)s")

  listen_host, listen_port = a.listen.rsplit(":", 1)
  tele_host, tele_port = a.telemetry.rsplit(":", 1)
  enable = set(a.enable.split(",")) if a.enable else None

  contract = load_contract(a.cache, a.variant)
  rx = DummyRx(
    contract=contract, listen_host=listen_host, listen_port=int(listen_port),
    telemetry_host=tele_host, telemetry_port=int(tele_port), arm_token=a.arm_token,
    enable=enable, kp_max=a.kp_max, kd_max=a.kd_max, deadman_s=a.deadman_s,
    hold_s=a.hold_s, return_s=a.return_s, hz=a.hz, inertia=a.inertia, damping=a.damping,
  )
  rx.start()
  print(
    f"dummy_rx: listening on {a.listen} (JointTarget), telemetry -> {a.telemetry} "
    f"(HUPHY UDP format), {a.variant}, enabled={sorted(rx.enabled_joints)}"
  )
  try:
    if a.seconds is not None:
      time.sleep(a.seconds)
    else:
      while True:
        time.sleep(1.0)
  except KeyboardInterrupt:
    pass
  finally:
    rx.stop()
    print(f"dummy_rx: stopped. {rx.latest.stats}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
