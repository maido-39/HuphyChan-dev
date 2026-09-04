#!/usr/bin/env python3
"""commission_motor.py — assign a CAN id to ONE RobStride motor and (if it is still a
factory unit) take it to the MIT protocol, so `config/robot_v1.0.yaml`'s left_leg ids work.

Why this exists rather than `huphy-commission`: that tool addresses motors **by the ids
written in robot.yaml** (`scripts/commission.py::_joint_or_exit`), so a motor sitting at the
factory id 0x7F is unreachable through it. HUPHY's own `docs/motor_setup.md` says the same
("이 단계에서는 huphy-commission 을 못 씀") and falls back to raw `cansend` — which needs
can-utils + sudo. This does the identical frames through python-can instead, and adds the
Type 7 / Command 7 id assignment the existing `commission_private_to_mit.py` never had.

Frame formats (both verbatim from HUPHY on branch `biped`):
  private, 29-bit ext   arb = TT NN HH DD   (HH = host 0xFD, DD = target id)
                        docs/motor_setup.md quick reference
  MIT, 11-bit std       can_id = motor id, data = FF FF FF FF FF FF <F_CMD> <CMD>
                        motors/robstride/bus.py::_command_frame

Two paths, because the two bench motors are in different states:
  --from private   a factory unit (RS04): Type 0 ping -> Type 7 id -> Type 18+22 zero_sta
                   -> Type 25 protocol=MIT -> **power cycle required**
  --from mit       a unit already commissioned to MIT (the RS03, at id 127): Command 7
                   (0xFA) with F_CMD = new id. Immediate, no power cycle.

NEVER enables torque. Refuses to act when more than one motor answers the ping — two
factory units share id 0x7F, and commanding into that ambiguity is exactly what corrupted
the position feedback on 2026-09-04 (docs/123 §10.x).

  # one motor on the bus at a time
  python3 commission_motor.py --probe
  python3 commission_motor.py --from private --current-id 127 --new-id 4   # RS04 -> knee
  python3 commission_motor.py --from mit     --current-id 127 --new-id 5   # RS03 -> ankle_a
"""
from __future__ import annotations

import argparse
import sys
import time

import can

HOST = 0xFD
CMD_STOP = 0xFD          # MIT Command 2 - harmless, used only to see who answers
CMD_SET_CAN_ID = 0xFA    # MIT Command 7
F_CMD_DEFAULT = 0xFF
SETTLE_S = 0.05


def mit_frame(motor_id: int, command: int, f_cmd: int = F_CMD_DEFAULT) -> can.Message:
  return can.Message(
    arbitration_id=int(motor_id), is_extended_id=False,
    data=bytes([0xFF] * 6 + [int(f_cmd) & 0xFF, int(command) & 0xFF]),
  )


def priv_frame(typ: int, nn: int, target: int, data_hex: str) -> can.Message:
  return can.Message(
    arbitration_id=(typ << 24) | (nn << 16) | (HOST << 8) | int(target),
    is_extended_id=True, data=bytes.fromhex(data_hex),
  )


def collect(bus, wait_s: float) -> list:
  out, t0 = [], time.time()
  while time.time() - t0 < wait_s:
    m = bus.recv(timeout=wait_s)
    if m is None:
      break
    out.append(m)
  return out


def responders(bus, *, mit_ids=range(1, 128), private=True, quiet=False) -> dict:
  """Who is on this bus? Returns {'private': [...], 'mit': [ids]}.

  The private ping is the only one a factory unit answers; the MIT sweep is how an
  already-commissioned unit shows up. Both are read-only.
  """
  found = {"private": [], "mit": []}
  if private:
    bus.send(priv_frame(0x00, 0x0000, 0x7F, "0000000000000000"))
    for m in collect(bus, 0.25):
      found["private"].append(m)
      if not quiet:
        print(f"  private RX  arb {m.arbitration_id:08X}  data {m.data.hex()}")
  for mid in mit_ids:
    bus.send(mit_frame(mid, CMD_STOP))
    for m in collect(bus, 0.02):
      if m.data and m.data[0] == mid and mid not in found["mit"]:
        found["mit"].append(mid)
        if not quiet:
          print(f"  MIT RX      id {mid}  data {m.data.hex()}")
  return found


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--channel", default="can0")
  ap.add_argument("--interface", default="socketcan", help="socketcan (can0) or slcan (/dev/ttyACM0)")
  ap.add_argument("--probe", action="store_true", help="only report who answers; change nothing")
  ap.add_argument("--from", dest="src", choices=["private", "mit"], help="the motor's CURRENT protocol")
  ap.add_argument("--current-id", type=int, default=127)
  ap.add_argument("--new-id", type=int)
  ap.add_argument("--skip-zero", action="store_true", help="private path: do not write zero_sta")
  ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
  a = ap.parse_args()

  bus = can.interface.Bus(channel=a.channel, interface=a.interface)  # bitrate via CAN_BITRATE
  try:
    print(f"[commission] {a.channel} ({a.interface})")
    print("[commission] who is on the bus:")
    found = responders(bus, mit_ids=list(range(1, 13)) + [127])
    n_priv, n_mit = len(found["private"]), len(found["mit"])
    print(f"[commission] private responses {n_priv}, MIT ids {found['mit'] or '-'}")
    if a.probe:
      return 0

    if a.src is None or a.new_id is None:
      print("need --from {private,mit} and --new-id (or use --probe)", file=sys.stderr)
      return 2
    if not 1 <= a.new_id <= 0x7F:
      print("--new-id must be 1..127", file=sys.stderr)
      return 2

    # One motor at a time. Two factory units both answer at 0x7F and the replies are
    # indistinguishable - HUPHY's own set_can_id refuses for the same reason.
    total = n_priv + n_mit
    if total > 1:
      print(f"REFUSING: {total} responders on this bus ({n_priv} private, MIT {found['mit']}).\n"
            f"  Commission ONE motor at a time - disconnect the other and re-run.", file=sys.stderr)
      return 3
    if total == 0:
      print("no motor answered - check power/wiring/bitrate; nothing written.", file=sys.stderr)
      return 1

    if not a.yes:
      ans = input(f"Assign id {a.current_id} -> {a.new_id} via the {a.src} protocol"
                  f"{'' if a.src == 'mit' else ' (+ zero_sta, flash, protocol->MIT)'}. Type 'yes': ")
      if ans.strip().lower() != "yes":
        print("aborted, nothing written")
        return 2

    if a.src == "mit":
      # Command 7. Immediate; no power cycle. Mirrors commissioning.set_can_id().
      bus.send(mit_frame(a.current_id, CMD_SET_CAN_ID, f_cmd=a.new_id))
      time.sleep(SETTLE_S)
      bus.send(mit_frame(a.new_id, CMD_STOP))
      ok = any(m.data and m.data[0] == a.new_id for m in collect(bus, 0.2))
      print(f"[commission] MIT id {a.current_id} -> {a.new_id}: "
            f"{'confirmed' if ok else 'NO REPLY at the new id - check both ids before retrying'}")
      return 0 if ok else 4

    # private path, exactly the order docs/motor_setup.md gives (protocol LAST)
    steps = [(0x07, a.new_id, "0000000000000000", f"Type7  id -> {a.new_id}")]
    if not a.skip_zero:
      steps += [(0x12, 0, "2970000001000000", "Type18 zero_sta = 1"),
                (0x16, 0, "0102030405060708", "Type22 flash save")]
    steps += [(0x19, 0, "0102030405060200", "Type25 protocol -> MIT")]
    target = a.current_id
    for typ, nn, data_hex, label in steps:
      bus.send(priv_frame(typ, nn, target, data_hex))
      rx = collect(bus, 0.4)
      print(f"  {label:<28} {'RX ' + rx[0].data.hex() if rx else '(no response)'}")
      if typ == 0x07:
        target = a.new_id      # id applies immediately; everything after goes to the new id
      time.sleep(SETTLE_S)
    print(f"\n[commission] DONE. POWER-CYCLE the motor now, then verify:\n"
          f"  python3 commission_motor.py --channel {a.channel} --interface {a.interface} --probe\n"
          f"  (expect: MIT ids [{a.new_id}])")
    return 0
  finally:
    bus.shutdown()


if __name__ == "__main__":
  raise SystemExit(main())
