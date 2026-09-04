#!/usr/bin/env python3
"""bench_telemetry.py — stream the bench motor to the viewer in HUPHY's own UDP wire format.

Interim tool until HUPHY's SingleJoint robot (branch bench-single-joint) lands: uses ONLY
HUPHY library classes (load_robot, CanBus, RobStrideBus, MitCommand, UdpSink) and emits the
exact keys HUPHY's ControlLoop telemetry would emit for limb `bench`, joint `knee`:

    {"t": ..., "loop_dt": ..., "bench/knee/pos": deg, "bench/knee/tgt": deg, "bench/knee/err": deg,
     "bench/knee/vel": deg/s, "bench/knee/tau": N*m, "bench/knee/temp": C}

Modes:
    --passive        (default) torque OFF; only reads the motor (spin the rotor by hand)
    --sine A F       torque ON; target = A*sin(2*pi*F*t) [deg], kp/kd from --kp/--kd (default 20/0.5)
                     ROM clamp +-180 deg, slew <= 20 deg per 100 Hz tick, torque OFF on exit/Ctrl-C.

    source /home/syaro/Human-Pygmalion/.venv-huphy/bin/activate
    CAN_BITRATE=1000000 python bench_telemetry.py --config bench_rs03_slcan.yaml --host 192.168.20.177
"""
from __future__ import annotations

import argparse
import math
import signal
import sys
import time

from huphy.config import load_robot
from huphy.motors.canbus import CanBus
from huphy.motors.robstride.bus import MitCommand, RobStrideBus
from huphy.telemetry.udp import UdpSink

LIMB = "bench"
JOINT = "knee"


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--config", default="bench_rs03_slcan.yaml")
  ap.add_argument("--limb", default="bench")
  ap.add_argument("--host", default="192.168.20.177", help="viewer host (HUPHY UdpSink target)")
  ap.add_argument("--port", type=int, default=9870)
  ap.add_argument("--hz", type=float, default=50.0)
  ap.add_argument("--passive", action="store_true", default=True)
  ap.add_argument("--sine", nargs=2, type=float, metavar=("AMP_DEG", "FREQ_HZ"), help="torque ON, sine target")
  ap.add_argument("--kp", type=float, default=20.0)
  ap.add_argument("--kd", type=float, default=0.5)
  ap.add_argument("--seconds", type=float, default=0.0, help="0 = run until Ctrl-C")
  ap.add_argument("--rom", type=float, default=180.0)
  ap.add_argument("--slew", type=float, default=20.0, help="deg per tick")
  a = ap.parse_args()

  robot = load_robot(a.config)
  limb = robot.limbs[a.limb]
  motors = limb.motors_by_id()
  (mid, mcfg), = motors.items()
  bus = RobStrideBus(CanBus(limb.channel, interface=limb.interface), motors)
  bus.connect()
  sink = UdpSink(a.host, a.port)
  sink.open()
  active = a.sine is not None
  kp, kd = min(a.kp, 30.0), min(a.kd, 2.0)
  print(f"[bench] motor id {mid} {mcfg.model} via {limb.channel}/{limb.interface}; telemetry -> {a.host}:{a.port} "
        f"@ {a.hz:.0f} Hz; mode {'SINE ' + str(a.sine) + f' kp={kp} kd={kd}' if active else 'PASSIVE (torque off)'}", flush=True)

  stop = {"flag": False}
  signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("flag", True))
  signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("flag", True))

  dt = 1.0 / a.hz
  t0 = time.perf_counter()
  bus.refresh_states([mid])
  q0 = ((bus.state(mid).position_deg + 180.0) % 360.0) - 180.0
  tgt = q0
  if active:
    bus.clear_fault([mid])   # a latched stall fault from a previous run blocks torque
    bus.enable_torque([mid])
  n = 0
  try:
    while not stop["flag"] and (a.seconds <= 0 or time.perf_counter() - t0 < a.seconds):
      tick = time.perf_counter()
      t = tick - t0
      if active:
        want = q0 + a.sine[0] * math.sin(2 * math.pi * a.sine[1] * t)
        want = max(-a.rom, min(a.rom, want))
        tgt = tgt + max(-a.slew, min(a.slew, want - tgt))      # slew clamp
        bus.send_mit({mid: MitCommand(position_deg=tgt, velocity_deg_s=0.0, kp=kp, kd=kd, torque_nm=0.0)})
        bus.collect(expect=1, timeout_s=dt * 0.8)
      else:
        bus.refresh_states([mid])  # sends a zero-force query and collects the reply
      st = bus.state(mid)
      # HUPHY's cal space wraps to +-180 deg (motors/base.py wrap180); without a calibration file
      # the raw multi-turn angle would leak through (e.g. 344 deg for -16 deg), so wrap here.
      pos = ((st.position_deg + 180.0) % 360.0) - 180.0
      snap = {
        "t": round(t, 4), "loop_dt": round((time.perf_counter() - tick) * 1e3, 3),
        f"{LIMB}/{JOINT}/pos": pos, f"{LIMB}/{JOINT}/tgt": tgt if active else pos,
        f"{LIMB}/{JOINT}/err": (tgt - pos) if active else 0.0,
        f"{LIMB}/{JOINT}/vel": st.velocity_deg_s, f"{LIMB}/{JOINT}/tau": st.torque_nm,
        f"{LIMB}/{JOINT}/temp": st.temp_c,
      }
      sink.send(snap)
      n += 1
      if n % int(a.hz) == 0:
        print(f"[bench] t={t:6.1f}s pos={pos:8.2f} tgt={tgt:8.2f} vel={st.velocity_deg_s:8.2f} tau={st.torque_nm:6.2f} T={st.temp_c:4.1f}", flush=True)
      rest = dt - (time.perf_counter() - tick)
      if rest > 0:
        time.sleep(rest)
  finally:
    if active:
      bus.disable_torque([mid])
      print("[bench] torque OFF", flush=True)
    sink.close()
    bus.disconnect()
  return 0


if __name__ == "__main__":
  sys.exit(main())
