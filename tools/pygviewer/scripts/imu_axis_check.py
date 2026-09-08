#!/usr/bin/env python3
"""물리적으로 축 하나씩 돌려서, 그 회전이 화면의 어느 축으로 나타나는지 잰다.

2026-09-08, 사용자: "projected gravity 는 맞는데 Y 축 회전값이 안맞아."

왜 이 도구가 필요한가. 중력은 자세 3자유도 중 **2개만** 묶는다 - 중력 벡터를 축으로 한
회전(요)은 중력을 전혀 바꾸지 않는다. 그래서 "중력이 맞다"는 것과 "자세가 맞다"는 것은
다른 말이고, 중력 대조만으로는 이 문제를 잡을 수 없다.

사원수 자체는 이미 확인했다: 센서가 함께 보내는 roll/pitch/yaw 와 세 축 모두 0.3도 안에서
일치한다(전선의 반올림 폭). 그러므로 남은 후보는 **어느 좌표계로 그리는가**이고, 그것은
실제로 돌려 보는 것 말고는 가릴 방법이 없다.

재는 방식은 각속도와 자세를 함께 본다. 각속도는 "지금 어느 축을 돌리고 있는가"를 센서
자신의 축으로 말해 주고, 자세 변화는 "그 결과 무엇이 바뀌었는가"를 말해 준다. 둘이 다른
축을 가리키면 그 자리가 틀린 곳이다. 사람 눈으로 화살표를 보는 것보다 이쪽이 정확하다 -
비스듬히 본 3차원 화살표는 어느 축을 도는지 판별하기 어렵고, 이 프로젝트는 이미 그것 때문에
회전 방향을 두 번 잘못 읽었다.

쓰는 법:

    imu_axis_check.py            # 시작하면 안내가 나온다
    imu_axis_check.py --seconds 8

센서를 한 축씩, 다른 축은 되도록 고정한 채 30~60도쯤 천천히 돌린다. 축마다 한 번씩.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8095"
MOVE_DPS = 15.0
"""이보다 빠르면 '돌리는 중'으로 본다. 손으로 천천히 돌려도 넉넉히 넘고, 책상 진동이나
센서 잡음(정지 시 0.0 근처)에는 걸리지 않는다."""

DOMINANT = 2.0
"""우세축으로 인정하는 배수. 나머지 두 축보다 이만큼 커야 '한 축만 돌렸다'고 본다."""


def imu():
  d = json.load(urllib.request.urlopen(BASE + "/status", timeout=5))
  return d["telemetry"]["imu"]


def euler_deg(q):
  """(w,x,y,z) -> roll/pitch/yaw 도. 표준 몸체->월드, ZYX 순서."""
  w, x, y, z = q
  roll = math.degrees(math.atan2(2*(w*x + y*z), 1 - 2*(x*x + y*y)))
  sp = max(-1.0, min(1.0, 2*(w*y - z*x)))
  pitch = math.degrees(math.asin(sp))
  yaw = math.degrees(math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z)))
  return roll, pitch, yaw


def wrap(d):
  """각도 차이를 -180~180 으로. 요가 180도를 넘어갈 때 360도짜리 가짜 변화를 막는다."""
  return (d + 180.0) % 360.0 - 180.0


def watch(seconds: float):
  """한 번의 회전을 지켜보고, 무엇을 돌렸고 무엇이 바뀌었는지 돌려준다."""
  t0 = time.time()
  first = last = None
  gyro_sum = [0.0, 0.0, 0.0]
  n = 0
  while time.time() - t0 < seconds:
    s = imu()
    q = s.get("quat_wxyz")
    g = s.get("gyro_rad_s")
    if q and g:
      e = euler_deg(q)
      if first is None:
        first = e
      last = e
      for i in range(3):
        gyro_sum[i] += math.degrees(g[i])
      n += 1
    time.sleep(0.02)
  if not n or first is None:
    return None
  mean = [v / n for v in gyro_sum]
  return {
    "gyro_mean_dps": mean,
    "d_roll": wrap(last[0] - first[0]),
    "d_pitch": wrap(last[1] - first[1]),
    "d_yaw": wrap(last[2] - first[2]),
    "samples": n,
  }


def verdict(r):
  names = ("X", "Y", "Z")
  gy = r["gyro_mean_dps"]
  order = sorted(range(3), key=lambda i: abs(gy[i]), reverse=True)
  top, second = order[0], order[1]
  turned = names[top]
  if abs(gy[top]) < MOVE_DPS:
    return None, f"거의 안 움직였습니다 (가장 큰 각속도 {gy[top]:+.1f} 도/s). 더 크게 돌려 주세요."
  if abs(gy[top]) < DOMINANT * max(abs(gy[second]), 1e-6):
    return None, (f"여러 축이 함께 돌았습니다 (X{gy[0]:+.1f} Y{gy[1]:+.1f} Z{gy[2]:+.1f} 도/s). "
                  f"한 축만 돌려 주세요.")
  changes = [("roll(X)", r["d_roll"]), ("pitch(Y)", r["d_pitch"]), ("yaw(Z)", r["d_yaw"])]
  changes.sort(key=lambda kv: abs(kv[1]), reverse=True)
  moved, amount = changes[0]
  expect = {"X": "roll(X)", "Y": "pitch(Y)", "Z": "yaw(Z)"}[turned]
  ok = moved == expect
  sign_ok = (amount > 0) == (gy[top] > 0)
  return ok and sign_ok, (
    f"센서 {turned} 축을 {gy[top]:+.1f} 도/s 로 돌렸고,\n"
    f"    가장 크게 바뀐 각도는 {moved} {amount:+.1f} 도"
    f" (roll {r['d_roll']:+.1f} · pitch {r['d_pitch']:+.1f} · yaw {r['d_yaw']:+.1f})\n"
    f"    기대: {expect} 가 같은 부호로 변함 -> "
    + ("맞음" if ok and sign_ok else
       ("축이 다름" if not ok else "축은 맞지만 방향이 반대"))
  )


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--seconds", type=float, default=6.0, help="한 축당 지켜보는 시간")
  a = ap.parse_args(argv)

  try:
    s = imu()
  except Exception as e:
    print(f"뷰어에 연결할 수 없습니다: {e}", file=sys.stderr)
    return 1
  if not s.get("quat_wxyz"):
    print("실물 IMU 자세가 오지 않습니다 (quat_wxyz 없음). 중계기가 떠 있는지 보세요.",
          file=sys.stderr)
    return 1

  print("센서를 한 축씩 천천히 30~60도 돌립니다. 나머지 축은 되도록 고정하세요.\n")
  for axis in ("X", "Y", "Z"):
    input(f"[{axis} 축] 준비되면 Enter 를 누르고, 그 뒤 {a.seconds:.0f}초 동안 {axis} 축으로 돌리세요...")
    r = watch(a.seconds)
    if r is None:
      print("  표본을 못 받았습니다.\n")
      continue
    ok, msg = verdict(r)
    mark = "  " if ok is None else ("OK" if ok else "★ ")
    print(f"{mark}  {msg}\n")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
