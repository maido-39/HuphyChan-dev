#!/usr/bin/env python3
"""어댑터로 얼마나 빨리 보낼 수 있는지 잰다. **아무것도 설치하지 않고** 돈다.

2026-09-09. Proxmox 호스트는 이름 풀이(DNS)가 죽어 있어 `apt install` 이 안 됩니다. 그래서
`can-utils` 도 `slcand` 도 쓰지 않고, **파이썬 기본 기능만으로** 어댑터에 직접 글자를
보냅니다.

이 어댑터는 지금 **문자열 방식(slcan)** 펌웨어라, CAN 프레임 하나가 22글자 ASCII 로 바뀌어
시리얼 장치로 오갑니다. 그러니 그 장치에 그 글자를 그대로 써 넣으면 같은 일이 됩니다.

두 가지를 잽니다
----------------
**1) CAN 채널을 닫은 채** — 어댑터에 글자만 보내고 어댑터는 받아서 버립니다.
   **CAN 선에는 프레임이 하나도 안 나갑니다.** 모터는 아무 영향도 받지 않습니다.
   순수하게 "컴퓨터에서 어댑터까지 글자가 얼마나 빨리 가는가"만 잽니다.

**2) CAN 채널을 연 채** — 실제로 CAN 선에 프레임이 나갑니다. 모터가 쓰지 않는 번호(0x123)로만
   보내므로 모터는 무시하지만, 확인응답은 해 줍니다(그래야 선에 오류가 안 납니다).
   따라서 **모터에 전원이 들어와 있어야** 합니다.

왜 이렇게 재는가
----------------
가상머신 안에서 잰 값은 **초당 230.5개**였습니다(그때는 `slcand` 와 커널 CAN 계층을 거쳤음).
같은 코드를 호스트와 가상머신 양쪽에서 돌려야 **가상머신 통과가 얼마나 먹는지** 갈립니다.
그래서 이 파일은 양쪽에서 똑같이 돕니다.

    python3 host_usb_test.py                    # 장치를 알아서 찾음
    python3 host_usb_test.py --device /dev/ttyACM0
    python3 host_usb_test.py --closed-only      # CAN 선을 아예 안 건드림
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
import time

FRAME = b"t1238DEADBEEF00112233\r"
"""문자열 방식의 CAN 프레임 하나. `t` + 번호 3글자 + 길이 1글자 + 데이터 16글자 + 줄바꿈
= 22글자. 지금 실제로 쓰는 것과 같은 크기다(데이터 8바이트)."""


def find_device(explicit=None) -> str | None:
  if explicit:
    return explicit
  for p in sorted(glob.glob("/dev/serial/by-id/*")):
    if "CANable" in p or "canable" in p:
      return p
  cands = sorted(glob.glob("/dev/ttyACM*"))
  return cands[0] if cands else None


def measure(dev: str, seconds: float, open_channel: bool) -> tuple[float, int]:
  f = open(dev, "wb", buffering=0)
  try:
    if open_channel:
      f.write(b"C\r"); time.sleep(0.15)      # 혹시 열려 있으면 닫고
      f.write(b"S8\r"); time.sleep(0.15)     # S8 = 초당 100만 비트
      f.write(b"O\r"); time.sleep(0.25)      # 채널 열기
    n = 0
    t0 = time.time()
    while time.time() - t0 < seconds:
      f.write(FRAME)
      n += 1
    el = time.time() - t0
    return n / el, n
  finally:
    try:
      if open_channel:
        f.write(b"C\r")                      # 반드시 닫는다
    finally:
      f.close()


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--device", default=None)
  ap.add_argument("--seconds", type=float, default=3.0)
  ap.add_argument("--closed-only", action="store_true",
                  help="CAN 선을 전혀 건드리지 않는 시험만 한다")
  a = ap.parse_args(argv)

  dev = find_device(a.device)
  if dev is None:
    print("어댑터를 못 찾았습니다. 이렇게 확인하세요:\n"
          "  ls -l /dev/serial/by-id/\n  ls -l /dev/ttyACM*", file=sys.stderr)
    return 1
  real = os.path.realpath(dev)
  print(f"장치: {dev}")
  if real != dev:
    print(f"      -> {real}")

  # 줄 끝 글자를 건드리지 않도록 날 것 모드로. 없으면 그냥 넘어간다.
  subprocess.run(["stty", "-F", real, "raw", "-echo"], check=False,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

  print(f"\n[1] CAN 채널 닫은 채 — 선에는 아무것도 안 나갑니다")
  rate, n = measure(dev, a.seconds, open_channel=False)
  print(f"    초당 {rate:8.1f}개  ({n}개 / {a.seconds:.0f}초)  = 초당 {rate*len(FRAME):7.0f} 글자")
  closed = rate

  opened = None
  if not a.closed_only:
    print(f"\n[2] CAN 채널 연 채 — 모터가 안 쓰는 번호(0x123)로 실제 전송")
    print(f"    (모터에 전원이 있어야 합니다. 번호가 달라 모터는 무시합니다.)")
    opened, n2 = measure(dev, a.seconds, open_channel=True)
    print(f"    초당 {opened:8.1f}개  ({n2}개 / {a.seconds:.0f}초)")

  print("\n" + "="*62)
  print(f"비교 기준 — 가상머신 안에서 커널 CAN 계층을 거쳐 잰 값: 초당 230.5개")
  print(f"이번 [1] 닫은 채:   초당 {closed:8.1f}개")
  if opened is not None:
    print(f"이번 [2] 연 채:     초당 {opened:8.1f}개")
  print("="*62)
  print("""
읽는 법
  * [1] 이 230 근처면 -> 막는 곳은 USB 로 글자를 보내는 길 자체
  * [1] 이 훨씬 크면  -> USB 는 여유가 있고, 막는 곳은 그 위의 소프트웨어 계층
  * 호스트와 가상머신에서 [1] 이 크게 다르면 -> 가상머신 통과가 범인
""")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
