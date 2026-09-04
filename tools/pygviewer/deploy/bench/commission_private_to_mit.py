#!/usr/bin/env python3
"""commission_private_to_mit.py — take ONE factory-fresh RobStride motor from the private
protocol to MIT so HUPHY can talk to it. Frames are verbatim from HUPHY docs/motor_setup.md
(RobStride user manual, RS02/RS03/RS04 identical):

    Type 0   ping (read-only)                 0000FD<DD>#0000000000000000
    Type 17  read  zero_sta (0x7029)          1100FD<DD>#2970000000000000
    Type 18  write zero_sta = 1 (RAM)         1200FD<DD>#2970000001000000
    Type 22  commit to flash                  1600FD<DD>#0102030405060708
    Type 25  protocol -> MIT (02), needs a    1900FD<DD>#0102030405060200
             POWER CYCLE to take effect

PERMANENT hardware settings (flash + protocol). Run it yourself at the bench with exactly ONE
motor on the bus. Never enables torque. Reversal: once in MIT, `huphy-commission protocol --to
private` (MIT frame FD/F_CMD=00) switches back.

    source /home/syaro/Human-Pygmalion/.venv-huphy/bin/activate
    CAN_BITRATE=1000000 python commission_private_to_mit.py --channel /dev/ttyACM0 --id 127
    # then power-cycle the motor, then:
    CAN_BITRATE=1000000 huphy-commission --config bench_rs03_slcan.yaml --limb bench scan
"""
import argparse
import time

import can

HOST = 0xFD


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--channel", default="/dev/ttyACM0")
  ap.add_argument("--interface", default="slcan")
  ap.add_argument("--id", type=int, default=127, help="current motor CAN id (factory 127)")
  ap.add_argument("--read-only", action="store_true", help="only Type 0 + Type 17 (no writes)")
  ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
  a = ap.parse_args()
  mid = a.id
  if not 1 <= mid <= 127:
    raise SystemExit("id must be 1..127")
  bus = can.interface.Bus(channel=a.channel, interface=a.interface)  # bitrate: CAN_BITRATE env

  def xfer(typ, nn, data_hex, wait=0.2, label=""):
    arb = (typ << 24) | (nn << 16) | (HOST << 8) | mid
    bus.send(can.Message(arbitration_id=arb, is_extended_id=True, data=bytes.fromhex(data_hex)))
    print(f"TX {label:<28} {arb:08X}#{data_hex}")
    t0 = time.time(); rx = []
    while time.time() - t0 < wait:
      m = bus.recv(timeout=wait)
      if m is None:
        break
      rx.append(m)
      print(f"   RX {m.arbitration_id:08X}  type {(m.arbitration_id >> 24) & 0x1F:2d}  data {m.data.hex()}")
    if not rx:
      print("   (no response)")
    return rx

  ping = xfer(0x00, 0x00, "0000000000000000", label="Type0 ping")
  if not ping:
    print("motor did not answer the ping — check power/wiring/id; nothing written.")
    bus.shutdown(); return 1
  xfer(0x11, 0x00, "2970000000000000", label="Type17 read zero_sta")
  if a.read_only:
    bus.shutdown(); return 0
  if not a.yes:
    ans = input(f"WRITE to motor id {mid}: zero_sta=1, flash save, protocol->MIT (permanent). Type 'yes' to continue: ")
    if ans.strip().lower() != "yes":
      print("aborted, nothing written"); bus.shutdown(); return 2
  xfer(0x12, 0x00, "2970000001000000", label="Type18 write zero_sta=1")
  xfer(0x11, 0x00, "2970000000000000", label="Type17 re-read zero_sta")
  xfer(0x16, 0x00, "0102030405060708", wait=0.5, label="Type22 flash save")
  xfer(0x19, 0x00, "0102030405060200", wait=0.5, label="Type25 protocol->MIT")
  print("\nDONE. POWER-CYCLE the motor now. After power-up it answers MIT (11-bit) frames:\n"
        "  CAN_BITRATE=1000000 huphy-commission --config bench_rs03_slcan.yaml --limb bench scan")
  bus.shutdown()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
