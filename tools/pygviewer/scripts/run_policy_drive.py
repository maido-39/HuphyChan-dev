#!/usr/bin/env python3
"""'정책으로 실물 일부 구동' 시나리오를 순서대로 실행한다.

2026-09-08. 손으로 하면 순서 하나만 틀려도 실패하는데, 실패 모습이 매번 달라서 원인을
찾기 어렵다. 실제로 겪은 것만 적으면:

* **base 를 먼저 풀면 무장하기 전에 넘어진다.** 무장은 정책 목표가 실물과 10도 안으로
  들어오는 순간을 기다리므로 시간이 걸리는데, 그 사이 로봇은 이미 걷고 있다. 한 번은 2 m
  를 걷고 쓰러진 뒤에야 무장이 됐다. 그래서 **base 를 붙잡은 채 무장하고, 그다음 푼다.**
* **초기화를 건너뛰면 base 를 푸는 순간 주저앉는다.** 이전 시행에서 넘어진 자세가 그대로
  남아 있기 때문이다.
* **무장 전에 전송 설정을 못 바꾼다.** `configure` 는 무장 중이면 거부한다(전송 도중 보내는
  관절 목록이 바뀌면 안 되므로). 그래서 설정은 반드시 무장 해제 상태에서 먼저 한다.
* **좌표 맞춤은 manual 에서 해야 한다.** 정책 모드에서는 정책이 매 틱 목표를 덮어써서
  맞춤이 의미가 없다.

각 단계는 결과를 확인하고 진행하며, 실물로 나가는 단계 전에는 무엇이 나갈지 먼저 잰다.

    run_policy_drive.py --seconds 8
    run_policy_drive.py --dry-run          # 실물로 아무것도 안 보내고 시뮬만
    run_policy_drive.py --obs-imu real     # 자세계 관측을 실물에서 (자세계가 로봇에 붙은 뒤)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8095"
JOINTS = ["L_hip_yaw_joint", "L_knee_joint"]

FALL_HEIGHT_M = 0.5
"""이 아래로 내려가면 시뮬이 넘어진 것으로 보고 즉시 전송을 끊는다. 서 있을 때가 0.88 m
근처이므로 넉넉히 아래이고, 넘어지는 중간을 잡기에는 충분히 높다."""

ARM_TRIES = 120
"""무장 재시도 횟수. 정책 목표는 걸음 주기를 따라 오르내리므로, 실물과 10도 안으로 들어오는
순간이 주기마다 돌아온다. 관문을 우회하는 것이 아니라 열리기를 기다리는 것이다."""


def post(path, body=None, timeout=20):
  data = json.dumps(body).encode() if body is not None else b""
  req = urllib.request.Request(BASE + path, data=data, method="POST",
                               headers={"Content-Type": "application/json"})
  try:
    return json.load(urllib.request.urlopen(req, timeout=timeout)), None
  except urllib.error.HTTPError as e:
    try:
      return None, json.loads(e.read().decode()).get("detail", "")
    except Exception:
      return None, str(e)


def get(path):
  return json.load(urllib.request.urlopen(BASE + path, timeout=5))


def pose_deg():
  h = get("/health")["joints"]
  return {n: math.degrees(h[n]["q"]) for n in JOINTS}


def step(n, msg):
  print(f"{n}) {msg}")


def park_targets():
  """정책이 지금 이 자세에서 그 두 관절에 원하는 각도.

  무장이 거부되는 가장 흔한 이유가 이것이다: 실물은 앞 시행이 남긴 자리에 있고 정책은
  자기 자리를 원하는데, 그 차이가 10도 관문을 넘으면 열리지 않는다. 실제로 겪은 예 -
  실물 무릎 53.0도, 정책 27.9도, 이동 25.2도로 거부.

  base 를 붙잡은 채 정책을 잠깐 돌려 그 값을 읽어 온다. 걷는 중의 목표는 주기를 따라
  오르내리므로 '지금 값'이 의미가 없지만, 붙잡아 두면 정책은 선 자세를 유지하려 하므로
  값이 안정적이고, 그 자리가 곧 걸음이 시작되는 자리다.
  """
  snap = get("/snapshot").get("policy")
  if not snap or not snap.get("target"):
    return None
  names = get("/contract")["contract"]["action_joint_names"]
  tgt = snap["target"]
  return {n: tgt[names.index(n)] for n in JOINTS}


def drive_to(targets, timeout_s=6.0, tol_deg=2.0):
  """수동으로 실물을 그 각도까지 옮긴다. 도착했으면 True."""
  post("/mode", {"mode": "manual"})
  time.sleep(0.3)
  post("/sync_from_real")
  time.sleep(0.35)
  r, e = post("/tx/arm")
  if not r:
    print(f"   수동 무장 거부: {e}", file=sys.stderr)
    return False
  for _ in range(30):
    post("/tx/heartbeat")
    time.sleep(0.02)
  post("/target", {"values": targets})
  t0 = time.time()
  while time.time() - t0 < timeout_s:
    post("/tx/heartbeat")
    now = pose_deg()
    if all(abs(now[n] - math.degrees(v)) < tol_deg for n, v in targets.items()):
      post("/tx/disarm")
      return True
    time.sleep(0.03)
  post("/tx/disarm")
  now = pose_deg()
  return all(abs(now[n] - math.degrees(v)) < tol_deg * 3 for n, v in targets.items())


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--policy", default="LegOnly-AB__2026-09-03_19-49-49_legonly_ab_v2_p2__model_5200")
  ap.add_argument("--host", default="10.8.0.14")
  ap.add_argument("--port", type=int, default=9872)
  ap.add_argument("--vx", type=float, default=0.5, help="앞으로 가는 속도 명령 m/s")
  ap.add_argument("--seconds", type=float, default=8.0)
  ap.add_argument("--max-step-deg", type=float, default=4.0,
                  help="패킷당 이동 상한. 50 Hz 이므로 4.0 이면 초당 200도")
  ap.add_argument("--kp-max", type=float, default=30.0)
  ap.add_argument("--obs-imu", choices=["sim", "real"], default="sim",
                  help="자세계 관측을 어디서. real 은 자세계가 로봇에 실제로 붙어 있을 때만 "
                       "의미가 있다 - 책상에 놓인 센서를 넣으면 정책이 남의 자세를 보고 넘어진다")
  ap.add_argument("--dry-run", action="store_true", help="실물로 전송하지 않고 시뮬만 돌린다")
  a = ap.parse_args(argv)

  try:
    get("/status")
  except Exception as e:
    print(f"뷰어에 연결할 수 없습니다: {e}", file=sys.stderr)
    return 1

  step(0, "전송 무장 해제 (설정은 무장 중에 못 바꾼다)")
  post("/tx/disarm")

  step(1, f"자세계 관측을 {a.obs_imu} 으로")
  r, _ = post("/obs_source", {"sources": {"base_ang_vel": a.obs_imu,
                                          "projected_gravity": a.obs_imu,
                                          "motor_pos_history": "sim"}})
  print(f"   마스크 {r['mask'] if r else '?'}  (R=실물, S=시뮬)")

  step(2, f"정책 불러오기: {a.policy}")
  r, e = post("/policy/load", {"name": a.policy})
  if not r:
    print(f"   실패: {e}", file=sys.stderr)
    return 1

  if not a.dry_run:
    step(3, f"전송 설정 (정책 허용, 패킷당 {a.max_step_deg}도 = {a.max_step_deg*50:.0f} 도/s)")
    r, e = post("/tx/config", {"host": a.host, "port": a.port, "enable": JOINTS,
                               "kp_max": a.kp_max, "kd_max": 1.5, "ttl_ms": 250,
                               "allow_policy": True, "max_step_deg": a.max_step_deg})
    if not r:
      print(f"   거부: {e}", file=sys.stderr)
      return 1
    post("/tx/enable", {"on": True})

  step(4, "manual 로 두고 선 자세로 초기화, 실물에서 좌표 맞춤")
  post("/mode", {"mode": "manual"})
  post("/reset", {"keyframe": "knees_bent"})
  time.sleep(0.5)
  if not a.dry_run:
    post("/sync_from_real")
    time.sleep(0.35)

  step(5, "base 를 붙잡은 채로 정책 시작 (푸는 것은 무장한 뒤)")
  post("/base", {"mode": "fixed"})
  post("/policy/cmd", {"vx": a.vx, "vy": 0.0, "wz": 0.0})
  post("/mode", {"mode": "policy_sim"})
  time.sleep(0.5)

  if not a.dry_run:
    step(6, "실물을 정책이 서 있으라는 자리로 먼저 옮긴다 (수동)")
    park = park_targets()
    if park is None:
      print("   정책 목표를 못 읽었습니다", file=sys.stderr)
      return 1
    print("   목표 " + " · ".join(f"{n.replace('_joint','')} {math.degrees(v):.1f}도"
                                  for n, v in park.items()))
    if not drive_to(park):
      print("   옮기지 못했습니다", file=sys.stderr)
      return 1
    print("   현재 " + " · ".join(f"{n.replace('_joint','')} {v:.1f}도"
                                  for n, v in pose_deg().items()))

    step(7, "무장 - 정책 목표가 실물과 10도 안으로 들어오는 순간을 기다린다")
    post("/mode", {"mode": "policy_sim"})
    time.sleep(0.4)
    armed = False
    for i in range(ARM_TRIES):
      r, e = post("/tx/arm")
      if r:
        armed = True
        break
      time.sleep(0.04)
    if not armed:
      print(f"   무장 실패: {e}", file=sys.stderr)
      return 1
    print(f"   성공 (재시도 {i+1}회)")

  step(8, "base 를 풀어 걷게 한다")
  post("/base", {"mode": "free"})

  eff = get("/snapshot")["policy"]["source_mask_effective"]
  print(f"\n관측 실제 소스 {eff} · {'실물 전송 없음(dry-run)' if a.dry_run else '정책 출력이 실물로 나가는 중'}"
        f" · {a.seconds:.0f}초\n")
  t0 = time.time()
  rows, stop = [], None
  while time.time() - t0 < a.seconds:
    if not a.dry_run:
      post("/tx/heartbeat")
    st = get("/status")
    h = get("/health")["joints"]
    z, x = st["base"]["pos"][2], st["base"]["pos"][0]
    rows.append((time.time() - t0, math.degrees(h[JOINTS[0]]["q"]), math.degrees(h[JOINTS[1]]["q"]), z, x))
    if z < FALL_HEIGHT_M:
      stop = f"시뮬이 넘어짐 ({time.time()-t0:.1f}초)"
      break
    if any(h[n]["fault_reason"] for n in JOINTS):
      stop = "모터가 고장을 보고함"
      break
    time.sleep(0.05)
  post("/tx/disarm")

  if stop:
    print(f"!! {stop} - 전송을 끊었습니다\n")
  every = max(1, len(rows) // 12)
  for t, hy, kn, z, x in rows[::every]:
    print(f"   {t:4.1f}s  hip_yaw {hy:6.2f}  knee {kn:6.2f}   높이 {z:.2f} m  전진 {x:+.2f} m")
  if rows:
    hy = [r[1] for r in rows]
    kn = [r[2] for r in rows]
    print(f"\n실물이 움직인 폭  hip_yaw {max(hy)-min(hy):.2f} 도 · knee {max(kn)-min(kn):.2f} 도")
  h = get("/health")["joints"]
  print(f"온도 {[h[n]['temp_c'] for n in JOINTS]} · 고장 {[h[n]['fault_reason'] for n in JOINTS]}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
