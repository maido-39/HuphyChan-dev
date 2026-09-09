#!/usr/bin/env python3
"""모터에 다중사인 **순수 토크**를 넣고 응답을 기록한다. **로봇 위에서 돌린다.**

2026-09-09. 사용자 지시로 찾은 사전연구의 방법을 그대로 따른다 — 근거와 인용은
``docs/reward_research/2026-09-09_motor_sysid_method.md`` 에 있다. 요지만 옮기면:

* 빠른 흔들림은 **회전자 관성**을, 느린 흔들림은 **마찰**을 드러낸다. 사인 하나로는 한쪽만
  보이므로 여러 주파수를 더해 한 번에 넣는다. 배수를 3.4, 7.4 같이 어중간하게 잡는 이유는
  주기가 겹쳐 서로 지워지지 않게 하려는 것이다.
* **위치 되먹임을 끄고(kp=0, kd=0) 순수 토크로 보낸다.** 모터 내부 PD 가 켜져 있으면 우리가
  보려는 물리를 그 PD 가 가려 버린다.

    tau(t) = 진폭 × ( sin(2π f t) + 0.6 sin(2π·3.4f·t) + 0.3 sin(2π·7.4f·t) )

왜 화면에서 안 하고 로봇 위에서 하는가
--------------------------------------
화면은 초당 50번 보낸다. 기준주파수 4 Hz 면 7.4배 성분이 29.6 Hz 인데 초당 50번 지령의
이론 한계는 25 Hz 다 — 넣을 수가 없다. 게다가 명령이 실물에 닿기까지 80 밀리초가 걸리는 것을
같은 날 실측했고(``docs/experiments/2026-09-09_sim_vs_real_sine_sweep.md``), 그 지연이
관성과 뒤섞이면 둘을 가를 수 없다. 그래서 사전연구와 같이 모터 바로 옆에서 넣는다.

★ 안전 — 이 실험이 지금까지와 다른 점
-------------------------------------
**순수 토크에는 위치 되먹임이 없다.** 모터는 시킨 토크만 내고 자기가 어디 있는지 신경쓰지
않는다. 그리고 이 벤치 설정은 ``enforce_limits: false`` 다(보정 전이라 관절 한계값이 전부
비어 있음). 즉 **로봇 쪽에 위치를 막아 줄 장치가 하나도 없다.**

다중사인은 설계상 평균이 0이지만, 마찰의 좌우 비대칭이나 미세한 치우침이 있으면 위치가
서서히 흘러간다. 그래서 막는 일은 **전부 이 파일이** 한다:

1. 시작 위치에서 ``--bound-deg`` 를 벗어나면 그 자리에서 즉시 **위치 유지로 전환**하고 중단.
2. 온도가 ``--temp-stop`` 에 닿으면 중단(모터를 끊는 값 50도보다 낮게 잡는다).
3. 한 번에 ``--seconds`` 를 넘기지 않는다.
4. 어떤 이유로 끝나든 **반드시** 부드러운 위치 유지 → 토크 0 → 토크 끄기 순으로 내려온다.
5. 응답이 끊기면(모터가 답을 안 하면) 그 자리에서 멈춘다 — 안 보이는 채로 토크를 넣지 않는다.

진폭은 작은 값부터 올린다. 사전연구가 쓴 2~3 Nm 는 그쪽 모터(RS02, 17 Nm)의 값이고, 우리
무릎은 RS04(120 Nm) 라 같은 숫자가 같은 뜻이 아니다.

이 스크립트가 도는 동안에는 **로봇 프로그램(huphy_remote_motion)을 멈춰야 한다** — 통신
버스는 한 프로그램만 쓸 수 있다. 멈추면 화면과의 연결이 끊기고 토크가 빠진다(안전한 쪽).

    # 로봇 위에서
    python3 motor_sysid_excite.py --motor knee --amp 0.3 --base-hz 4.0 --seconds 4 --dry-run
    python3 motor_sysid_excite.py --motor knee --amp 0.3 --base-hz 4.0 --seconds 4
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time

HARM = ((1.0, 1.0), (3.4, 0.6), (7.4, 0.3))
"""(주파수 배수, 진폭 배수). 사전연구의 식 그대로.

배수가 정수가 아닌 이유: 정수배면 주기가 딱 맞아떨어져 특정 위상에서 성분이 서로 지워지고,
그 순간의 응답에서는 지워진 성분에 대해 아무것도 배울 수 없다."""

SETTLE_HOLD_S = 0.7
"""끝낸 뒤 위치 유지로 잡아 주는 시간. 토크를 그냥 0으로 놓으면 관성으로 계속 돌아간다."""

HOLD_KP = 8.0
HOLD_KD = 0.6
"""내려올 때만 쓰는 부드러운 위치 유지 이득. 실험 중에는 절대 켜지 않는다(물리를 가린다)."""


def multisine(t: float, amp: float, f0: float) -> float:
  return amp * sum(a * math.sin(2.0 * math.pi * (m * f0) * t) for m, a in HARM)


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--config", default="/home/syaro/Human-Pygmalion/HUPHY/config/robot_bench.yaml")
  ap.add_argument("--limb", default="left_leg")
  ap.add_argument("--motor", default="knee", help="HUPHY 모터 이름 (knee / hip_yaw / ...)")
  ap.add_argument("--amp", type=float, default=0.3, help="토크 진폭 Nm — 작게 시작할 것")
  ap.add_argument("--base-hz", type=float, default=4.0)
  ap.add_argument("--seconds", type=float, default=4.0)
  ap.add_argument("--rate-hz", type=float, default=1000.0)
  ap.add_argument("--bound-deg", type=float, default=20.0,
                  help="시작 위치에서 이만큼 벗어나면 즉시 중단. 로봇 쪽에 한계가 없으므로 "
                       "이것이 유일한 위치 보호다")
  ap.add_argument("--temp-stop", type=float, default=45.0)
  ap.add_argument("--out", default=None)
  ap.add_argument("--dry-run", action="store_true",
                  help="토크를 0으로 두고 나머지를 전부 그대로 돈다. 통신·기록·중단 경로를 "
                       "모터를 움직이지 않고 확인한다")
  a = ap.parse_args(argv)

  from huphy.config import load_robot
  from huphy.motors.base import Gains
  from huphy.motors.robstride.bus import MitCommand
  from huphy.robots.leg import ANKLE_POSITION
  from huphy.scripts.bringup import build_biped

  robot = load_robot(a.config)
  limb_cfg = next(c for c in robot.limbs.values() if c.name == a.limb)
  biped = build_biped(robot, limbs=[limb_cfg], allow_uncalibrated=True,
                      gains=Gains(kp=0.0, kd=0.0), ankle_output=ANKLE_POSITION)
  leg = biped.part(limb_cfg.name)
  biped.connect()
  bus = leg.bus
  if hasattr(bus, "clear_fault"):
    bus.clear_fault()

  # limb_cfg.motors 는 이름 -> Motor(id=..., model=...) 다. 이름을 번호로 옮기는 곳은
  # 여기 한 군데뿐이어야 한다 - 번호를 손으로 적으면 언젠가 다른 모터에 토크를 넣는다.
  motor_cfg = limb_cfg.motors.get(a.motor)
  if motor_cfg is None:
    print(f"모터 이름 {a.motor!r} 이 설정에 없습니다. 있는 것: {sorted(limb_cfg.motors)}",
          file=sys.stderr)
    return 1
  mid = motor_cfg.id
  print(f"모터 {a.motor} = 번호 {mid} ({motor_cfg.model})")

  def zero_cmd(tau=0.0, kp=0.0, kd=0.0, pos=0.0):
    return {mid: MitCommand(position_deg=pos, velocity_deg_s=0.0, kp=kp, kd=kd, torque_nm=tau)}

  # 상태를 먼저 안다. MIT 모드에는 읽기 전용 명령이 없어서, 아무 힘도 안 내는 명령을 보내고
  # 그 응답으로 위치를 배운다. 위치를 모르는 채로 토크를 넣지 않는다.
  biped.enable()
  for _ in range(20):
    bus.send_mit(zero_cmd())
    bus.collect(expect=1)
    time.sleep(0.005)
  st = bus.state(mid)
  if not st.is_valid:
    print("모터가 응답하지 않습니다 — 아무것도 넣지 않고 그만둡니다", file=sys.stderr)
    biped.disable()
    return 1
  q0, t0_temp = st.position_deg, st.temp_c
  print(f"시작 위치 {q0:.2f}도 · 온도 {t0_temp:.1f}도 · 한계 ±{a.bound_deg}도")
  print(f"신호: 진폭 {a.amp} Nm, 기준 {a.base_hz} Hz, 배수 {[m for m,_ in HARM]}, "
        f"{a.seconds}초, 목표 초당 {a.rate_hz:.0f}회"
        + ("   [건식 — 토크 0]" if a.dry_run else ""))

  rows, stop = [], None
  dt = 1.0 / a.rate_hz
  t_start = time.monotonic()
  next_t = t_start
  try:
    while True:
      now = time.monotonic()
      t = now - t_start
      if t >= a.seconds:
        stop = "정해진 시간 끝"
        break
      tau = 0.0 if a.dry_run else multisine(t, a.amp, a.base_hz)
      bus.send_mit(zero_cmd(tau=tau))
      missing = bus.collect(expect=1)
      st = bus.state(mid)
      # 우리 모터만 본다. `collect` 는 설정에 있는 여섯 개 중 이번에 답하지 않은 것을 전부
      # 돌려주는데, 벤치에는 두 대뿐이고 우리는 한 대에만 명령한다 - 나머지가 답하지 않는 것은
      # 정상이다. 이걸 실패로 읽으면 첫 주기에 무조건 멈춘다(2026-09-09 건식에서 실제로 그랬음).
      if mid in missing:
        stop = "우리 모터가 응답하지 않음 — 보이지 않는 채로 토크를 넣지 않는다"
        break
      if abs(st.position_deg - q0) > a.bound_deg:
        stop = (f"위치가 시작에서 {st.position_deg - q0:+.1f}도 벗어남 "
                f"(한계 ±{a.bound_deg}도)")
        break
      if st.temp_c >= a.temp_stop:
        stop = f"온도 {st.temp_c:.1f}도 도달"
        break
      rows.append((t, tau, st.position_deg, st.velocity_deg_s, st.torque_nm, st.temp_c))
      next_t += dt
      sleep = next_t - time.monotonic()
      if sleep > 0:
        time.sleep(sleep)
      else:
        next_t = time.monotonic()   # 뒤처지면 따라잡지 않는다 (밀린 만큼 몰아 보내면 위험)
  except KeyboardInterrupt:
    stop = "사람이 중단"
  finally:
    # 어떤 이유로 끝나든 같은 순서로 내려온다: 부드럽게 잡고 → 토크 0 → 토크 끄기.
    try:
      st = bus.state(mid)
      hold = st.position_deg if st.is_valid else q0
      t_end = time.monotonic() + SETTLE_HOLD_S
      while time.monotonic() < t_end:
        bus.send_mit(zero_cmd(kp=HOLD_KP, kd=HOLD_KD, pos=hold))
        bus.collect(expect=1)
        time.sleep(0.002)
      for _ in range(10):
        bus.send_mit(zero_cmd())
        bus.collect(expect=1)
        time.sleep(0.002)
    finally:
      biped.disable()
      print("토크 껐습니다")

  print(f"\n끝난 이유: {stop}")
  if not rows:
    print("기록된 줄이 없습니다", file=sys.stderr)
    return 1
  achieved = len(rows) / rows[-1][0] if rows[-1][0] > 0 else 0.0
  qs = [r[2] for r in rows]
  print(f"줄 {len(rows)}개 · 실제 초당 {achieved:.0f}회 (목표 {a.rate_hz:.0f})")
  print(f"위치 {min(qs):.2f} ~ {max(qs):.2f}도 (폭 {max(qs)-min(qs):.2f}도) · "
        f"끝난 자리 {qs[-1]-q0:+.2f}도 표류")
  print(f"온도 {rows[0][5]:.1f} → {rows[-1][5]:.1f}도")

  out = a.out or f"sysid_{a.motor}_amp{a.amp}_f{a.base_hz}_{time.strftime('%Y%m%d_%H%M%S')}.csv"
  with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["t_s", "tau_cmd_nm", "pos_deg", "vel_deg_s", "tau_est_nm", "temp_c"])
    w.writerows(rows)
  print(f"기록: {out}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
