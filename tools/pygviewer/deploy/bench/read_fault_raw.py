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
        # In MIT (11-bit) frames data[0] is the motor id, so the manual's byte numbering (which
        # is written for the 29-bit frame, where the id lives in the arbitration field) shifts
        # by one. Reading d[0:4] as the fault word would take the motor id for a fault bit -
        # id 4 would read as "undervoltage" (bit 2) and id 3 as bits 0+1. That is exactly the
        # kind of confidently-wrong readout this whole exercise exists to stamp out, so the
        # shifted window is the only one printed, in both byte orders.
        fault_le = int.from_bytes(d[1:5], "little")   # correct: vendor sends low byte first
        fault_be = int.from_bytes(d[1:5], "big")      # what HUPHY currently does
        warn_le = int.from_bytes(d[5:9], "little") if len(d) >= 9 else None
        print(f"    fault (little-endian, correct) : 0x{fault_le:08X} [{named(fault_le, FAULT_BITS)}]")
        print(f"    fault (big-endian, HUPHY today): 0x{fault_be:08X} [{named(fault_be, FAULT_BITS)}]")
        if warn_le is not None:
          print(f"    warning (little-endian)        : 0x{warn_le:08X} [{named(warn_le, WARN_BITS)}]")
        else:
          print(f"    warning                        : not in this reply ({len(d)} bytes)")
      time.sleep(0.05)
    return 0
  finally:
    bus.shutdown()


if __name__ == "__main__":
  raise SystemExit(main())
