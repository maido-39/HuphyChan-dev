#!/usr/bin/env python3
"""커널 CAN 계층을 거쳤을 때의 속도를 잰다. **아무것도 설치하지 않고** 돈다.

2026-09-09. 바깥 컴퓨터(Proxmox 호스트)에서 장치에 글자를 직접 써 넣으니 **초당 11,205개**가
나왔습니다. 가상머신 안에서 커널 CAN 계층을 거쳐 잰 값은 **초당 230.5개**였습니다. 48배 차이인데,
**두 가지가 한꺼번에 달라서** 어느 쪽 때문인지 아직 모릅니다:

  (가) 바깥 컴퓨터냐 가상머신이냐
  (나) 장치에 글자를 직접 쓰느냐, 커널 CAN 계층을 거치느냐

이 파일은 **바깥 컴퓨터에서 (나)만 바꿔** 재서 그 둘을 가릅니다. 어댑터를 옮길 필요가 없습니다.

  * 여기서도 230 근처가 나오면 → 범인은 **커널 CAN 계층(문자열 방식 처리)**. 가상머신은 무죄이고,
    펌웨어를 바꾸는 것이 정확한 해법입니다(새 펌웨어는 이 계층을 통째로 안 씁니다).
  * 여기서 11,000 근처가 나오면 → 범인은 **가상머신 통과**. 제어를 실물 기판으로 옮기는 것이
    해법입니다.

설치가 필요 없는 이유
---------------------
* 통신선을 세우는 일은 커널이 합니다. ``ldattach`` (util-linux, 보통 이미 있음) 로 붙입니다.
* 프레임을 보내는 일은 파이썬에 기본으로 들어 있는 ``socket`` 으로 합니다. 따로 받을 것이 없습니다.

안전
----
모터가 쓰지 않는 번호(0x123)로만 보냅니다. 번호가 달라 모터는 무시하고, 확인응답만 해 줍니다.
모터에 힘이 들어가는 일은 없습니다. 끝나면 통신선을 내리고 붙였던 것을 떼어냅니다.
"""

from __future__ import annotations

import glob
import os
import socket
import struct
import subprocess
import sys
import time

SLCAN_LDISC = 17
"""문자열 방식(slcan)을 다루는 커널 처리기의 번호. 리눅스 ``tty.h`` 의 ``N_SLCAN``."""

CAN_ID = 0x123
DATA = b"\xde\xad\xbe\xef\x00\x11\x22\x33"


def sh(*args, **kw):
  return subprocess.run(args, capture_output=True, text=True, **kw)


def main() -> int:
  if os.geteuid() != 0:
    print("root 로 실행해야 합니다 (통신선을 세우는 일이라)", file=sys.stderr)
    return 1

  dev = next((p for p in sorted(glob.glob("/dev/serial/by-id/*")) if "anable" in p),
             (sorted(glob.glob("/dev/ttyACM*")) or [None])[0])
  if not dev:
    print("어댑터를 못 찾았습니다", file=sys.stderr)
    return 1
  real = os.path.realpath(dev)
  print(f"장치: {real}")

  if sh("which", "ldattach").returncode != 0:
    print("ldattach 가 없습니다 (보통 util-linux 에 들어 있습니다).\n"
          "  대신 can-utils 의 slcand 를 쓸 수 있으면 그걸 쓰세요.", file=sys.stderr)
    return 1

  # 1) 어댑터에 속도를 알려주고 채널을 연다 (문자열 방식 명령)
  sh("stty", "-F", real, "raw", "-echo")
  with open(real, "wb", buffering=0) as f:
    f.write(b"C\r"); time.sleep(0.15)
    f.write(b"S8\r"); time.sleep(0.15)   # S8 = 초당 100만 비트
    f.write(b"O\r"); time.sleep(0.25)

  # 2) 커널 처리기를 붙인다 -> can0 이 생긴다
  r = sh("ldattach", str(SLCAN_LDISC), real)
  if r.returncode != 0:
    print(f"ldattach 실패: {r.stderr.strip()}", file=sys.stderr)
    return 1
  time.sleep(0.6)

  made = None
  for name in ("can0", "can1", "slcan0"):
    if sh("ip", "link", "show", name).returncode == 0:
      made = name
      break
  if made is None:
    print("통신선이 안 생겼습니다. `ip link show` 로 확인하세요", file=sys.stderr)
    sh("pkill", "-f", f"ldattach {SLCAN_LDISC}")
    return 1
  print(f"통신선: {made}")

  try:
    sh("ip", "link", "set", made, "up")
    sh("ip", "link", "set", made, "txqueuelen", "1000")

    s = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    s.bind((made,))
    frame = struct.pack("=IB3x8s", CAN_ID, len(DATA), DATA)

    n = 0
    t0 = time.time()
    while time.time() - t0 < 3.0:
      try:
        s.send(frame)
        n += 1
      except OSError:
        pass                      # 보낼 자리가 없으면 잠깐 밀린 것 - 세지 않는다
    el = time.time() - t0
    rate = n / el
    s.close()

    print(f"\n[3] 커널 CAN 계층을 거쳐: 초당 {rate:9.1f}개  ({n}개 / {el:.1f}초)")
    print("=" * 62)
    print(f"  [1] 바깥 컴퓨터, 장치에 글자 직접   초당 11,205  (이미 잼)")
    print(f"  [3] 바깥 컴퓨터, 커널 CAN 계층      초당 {rate:9.1f}  (이번)")
    print(f"  [4] 가상머신,   커널 CAN 계층      초당     230.5  (이미 잼)")
    print("=" * 62)
    if rate < 1000:
      print("\n→ 바깥 컴퓨터에서도 느립니다. 범인은 **커널의 문자열 방식 처리**이고,")
      print("  가상머신은 무죄입니다. 펌웨어를 바꾸면 이 계층을 통째로 안 쓰게 됩니다.")
    else:
      print("\n→ 바깥 컴퓨터에서는 빠릅니다. 범인은 **가상머신 통과**입니다.")
      print("  펌웨어보다 제어를 실물 기판으로 옮기는 것이 먼저입니다.")
  finally:
    sh("ip", "link", "set", made, "down")
    sh("pkill", "-f", f"ldattach {SLCAN_LDISC}")
    time.sleep(0.3)
    try:
      with open(real, "wb", buffering=0) as f:
        f.write(b"C\r")           # 채널 닫기
    except OSError:
      pass
    print("\n정리 완료 (통신선 내림, 붙였던 처리기 떼어냄, 채널 닫음)")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
