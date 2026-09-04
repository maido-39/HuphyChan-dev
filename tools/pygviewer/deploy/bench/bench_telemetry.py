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
                     ROM clamp (see --rom below), slew <= 20 deg per 100 Hz tick, torque OFF
                     on exit/Ctrl-C.

ROM (--rom, 2026-09-04): the sine target is ALWAYS bounded to q0 +- --rom (RAW multi-turn
degrees, `q0` = the pose read at startup) - this does not change. `robot.motors[id].
limits_deg`, HUPHY's own commissioned hard-stop ROM, is read and printed if present, but is
NOT used to replace or tighten this clip: `limits_deg` is defined in CAL space (HUPHY
config/schema.py: "각도는 전부 cal 공간임 ... 모터가 보고하는 raw 값이 아님" - "all angles
are cal-space ... not the raw value the motor reports"), and this script talks to the motor
directly (`RobStrideBus`/`MitCommand.position_deg`), bypassing HUPHY's Leg/calibration layer
entirely - there is no offset/sign here to convert a cal-space limit into this script's raw
space. Applying it as a raw clip would silently bound the WRONG window rather than the real
one. Once this bench rig goes through `commission sweep` and gets a real offset/zero
reference, route position commands through HUPHY's calibrated Leg/Motor API instead (or add
the same offset_rad/sign conversion `bridge/huphy_udp.py` already does for the main robot)
before ever trusting `limits_deg` as a bound here.

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
  ap.add_argument("--rom", type=float, default=180.0,
                  help="deg; RAW-space swing half-width around the startup pose q0. Always "
                       "in effect - config limits_deg (if set) is CAL-space and only "
                       "printed, never applied here (see module docstring)")
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
  if mcfg.limits_deg is not None:
    print(f"[bench] NOTE: {mcfg.model} has a commissioned limits_deg={mcfg.limits_deg} "
          f"(CAL space, hard-stop) - NOT applied as a clip here: this script commands raw "
          f"multi-turn degrees with no cal-space offset/sign conversion (module docstring). "
          f"--rom={a.rom:g} deg (raw, relative to q0) remains the only ROM bound in effect.",
          flush=True)

  stop = {"flag": False}
  signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("flag", True))
  signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("flag", True))

  dt = 1.0 / a.hz
  t0 = time.perf_counter()
  bus.refresh_states([mid])
  q0 = bus.state(mid).position_deg   # RAW multi-turn deg: the space MitCommand.position_deg lives in
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
        osc = max(-a.rom, min(a.rom, a.sine[0] * math.sin(2 * math.pi * a.sine[1] * t)))
        want = q0 + osc          # centered on the startup pose; --rom limits the swing, not the absolute angle
        tgt = tgt + max(-a.slew, min(a.slew, want - tgt))      # slew clamp
        bus.send_mit({mid: MitCommand(position_deg=tgt, velocity_deg_s=0.0, kp=kp, kd=kd, torque_nm=0.0)})
        bus.collect(expect=1, timeout_s=dt * 0.8)
      else:
        bus.refresh_states([mid])  # sends a zero-force query and collects the reply
      st = bus.state(mid)
      raw = st.position_deg                 # command/error stay in RAW space (firmware convention)
      # wrap ONLY the number we DISPLAY/emit; never feed a wrapped value back into a command.
      pos = ((raw + 180.0) % 360.0) - 180.0
      snap = {
        "t": round(t, 4), "loop_dt": round((time.perf_counter() - tick) * 1e3, 3),
        f"{LIMB}/{JOINT}/pos": pos, f"{LIMB}/{JOINT}/tgt": tgt if active else pos,
        f"{LIMB}/{JOINT}/err": (tgt - raw) if active else 0.0,
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
