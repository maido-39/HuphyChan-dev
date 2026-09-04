#!/usr/bin/env python3
"""read_fault_raw.py — ask each motor for its fault word and print the RAW 8 bytes.

Read-only: sends only the fault QUERY frame (RobStride Command 5 with the query flag) and a
harmless stop frame; never enables torque, never commands a position.

Why raw bytes: the RS03/RS04 user manuals (2025-11-12, `Motor_Spec/manuals/`) define the fault
feedback frame's data field as

    Byte0~3  fault value    bit14 stall overload, bit7 encoder uncalibrated, bit3 overvoltage,
                            bit2 undervoltage, bit1 driver chip, bit0 overtemperature (145 C)
    Byte4~7  warning value  bit0 overtemperature warning (135 C)

while HUPHY's own reader takes the fault word from Byte1~4 (it assumes the leading byte is the
motor id, as it is in the STATE frame). Those two readings differ by one byte, so this prints
the bytes verbatim plus both interpretations and lets the hardware settle the question.
"""
from __future__ import annotations

import argparse
import time

import can

CMD_FAULT = 0xFB          # Command 5
CMD_STOP = 0xFD           # Command 2 - harmless, used to see who answers
F_CMD_QUERY = 0x00        # anything but 0xFF means "query"
F_CMD_DEFAULT = 0xFF

FAULT_BITS = {14: "stall overload", 7: "encoder uncalibrated", 3: "overvoltage",
              2: "undervoltage", 1: "driver chip", 0: "overtemperature (145 C)"}
WARN_BITS = {0: "overtemperature warning (135 C)"}


def mit(motor_id: int, command: int, f_cmd: int = F_CMD_DEFAULT) -> can.Message:
  return can.Message(arbitration_id=int(motor_id), is_extended_id=False,
                     data=bytes([0xFF] * 6 + [f_cmd & 0xFF, command & 0xFF]))


def named(value: int, table: dict[int, str]) -> str:
  hits = [name for bit, name in sorted(table.items()) if value >> bit & 1]
  return ", ".join(hits) if hits else "-"


def collect(bus, wait_s: float) -> list:
  out, t0 = [], time.time()
  while time.time() - t0 < wait_s:
    m = bus.recv(timeout=wait_s)
    if m is None:
      break
    out.append(m)
  return out


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--channel", default="can0")
  ap.add_argument("--interface", default="socketcan")
  ap.add_argument("--ids", default="3,4", help="motor ids to ask, comma separated")
  a = ap.parse_args()
  bus = can.interface.Bus(channel=a.channel, interface=a.interface)
  try:
    for mid in [int(x) for x in a.ids.split(",") if x.strip()]:
      print(f"\n=== motor id {mid} ===")
      # drain anything stale first: a fault reply shares its CAN id with a state frame, so a
      # leftover state frame would be read as the fault word.
      collect(bus, 0.05)
      bus.send(mit(mid, CMD_FAULT, f_cmd=F_CMD_QUERY))
      frames = collect(bus, 0.3)
      if not frames:
        print("  no reply")
        continue
      for i, m in enumerate(frames[:3]):
        d = bytes(m.data)
        print(f"  reply[{i}] can_id 0x{m.arbitration_id:X} ext={m.is_extended_id} "
              f"len={len(d)} bytes={' '.join(f'{b:02X}' for b in d)}")
        if len(d) < 8:
          continue
        manual_fault_le = int.from_bytes(d[0:4], "little")
        manual_fault_be = int.from_bytes(d[0:4], "big")
        manual_warn_le = int.from_bytes(d[4:8], "little")
        manual_warn_be = int.from_bytes(d[4:8], "big")
        huphy = int.from_bytes(d[1:5], "big")
        print(f"    manual Byte0~3 fault : LE 0x{manual_fault_le:08X} [{named(manual_fault_le, FAULT_BITS)}]"
              f"  BE 0x{manual_fault_be:08X} [{named(manual_fault_be, FAULT_BITS)}]")
        print(f"    manual Byte4~7 warn  : LE 0x{manual_warn_le:08X} [{named(manual_warn_le, WARN_BITS)}]"
              f"  BE 0x{manual_warn_be:08X} [{named(manual_warn_be, WARN_BITS)}]")
        print(f"    HUPHY  Byte1~4 (BE)  : 0x{huphy:08X} [{named(huphy, FAULT_BITS)}]")
      time.sleep(0.05)
    return 0
  finally:
    bus.shutdown()


if __name__ == "__main__":
  raise SystemExit(main())
