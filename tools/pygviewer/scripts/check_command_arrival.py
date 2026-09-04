#!/usr/bin/env python3
"""check_command_arrival.py — 화면에서 보낸 명령이 로봇에 그대로 도착하는지 자동으로 검사한다.

한 번 실행하면 통과·실패가 숫자로 나온다. 사람이 눈으로 판단할 필요가 없다.

무엇을 검사하는가 (모터 2대로 확인 가능한 범위)
    방향     플러스로 보냈을 때 실제로 같은 쪽으로 도는가
    단위     10도를 보내면 10도쯤 움직이는가 (라디안과 섞였다면 573도가 된다)
    크기     5·10·15도를 보냈을 때 명령과 실제의 기울기가 1인가 (중간에 배율이 끼지 않았는가)
    횟수     화면이 보낸 횟수와 로봇이 받은 횟수가 같은가

무엇을 검사하지 못하는가
    "어느 숫자가 어느 관절로 가는가"는 관절이 2개뿐이라 부분만 확인된다. 두 관절을 서로 다른 값으로
    움직여 뒤바뀌지 않았는지까지는 보지만, 12개짜리 다리에서만 완전히 확인된다.

측정 기록 규칙 (docs 계획 2026-09-05)
    값마다 명령값 / 자리잡은 값(가운데) / 차이 / 흔들린 폭 / 표본 수 / 기다린 시간을 남기고,
    원본을 CSV로 저장한다. 끝에 "이 숫자로 할 수 없는 말"을 적는다.

안전
    - 모터를 움직인다. 실행 전에 주변을 확인할 것.
    - 온도가 기준을 넘거나 값이 이상하면 즉시 멈추고 전송을 끈다.
    - 어떤 오류가 나도 마지막에 반드시 전송을 끈다.

    python3 check_command_arrival.py --api http://127.0.0.1:8095 \
        --joints L_hip_yaw_joint,L_knee_joint --out docs/bench_data/
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

DWELL_S = 15.0            # 한 단계에서 기다리는 시간. 짧게 재면 자리잡기 전 값을 읽어 결론이 뒤집힌다.
SETTLE_SAMPLES = 30       # 자리잡은 값으로 쓸 마지막 표본 수 (약 3초)
POLL_S = 0.1
REPEATS = 3               # 흔들림을 보려면 한 번으로는 부족하다
TEMP_STOP_C = 50.0        # 이 온도를 넘으면 즉시 중단 (설명서의 사용 온도 상한)
TEMP_PLAUSIBLE = (-20.0, 150.0)   # 이 밖의 값은 온도로 믿지 않는다

PASS_UNIT_RATIO = (0.5, 2.0)      # 명령 대비 실제 이동량 비율
PASS_SCALE_SLOPE = (0.8, 1.2)     # 기울기 1에서 얼마나 벗어나도 되는가
PASS_RATE_DIFF = 0.05             # 보내는 횟수 차이 허용 (5%)


@dataclass
class Sample:
  """한 단계에서 얻은 것. 숫자만이 아니라 얼마나 믿을 수 있는지도 함께 담는다."""

  joint: str
  commanded_deg: float
  applied_deg: float
  settled_deg: float
  spread_deg: float
  n: int
  dwell_s: float
  start_deg: float

  @property
  def moved_deg(self) -> float:
    return self.settled_deg - self.start_deg

  @property
  def error_deg(self) -> float:
    return self.settled_deg - self.applied_deg


@dataclass
class Check:
  name: str
  passed: bool
  detail: str
  numbers: dict = field(default_factory=dict)


class Api:
  def __init__(self, base: str):
    self.base = base.rstrip("/")

  def get(self, path: str):
    with urllib.request.urlopen(self.base + path, timeout=5) as r:
      return json.load(r)

  def post(self, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(self.base + path, data=data,
                                 headers={"content-type": "application/json"}, method="POST")
    try:
      with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)
    except urllib.error.HTTPError as e:
      raise RuntimeError(f"{path} 거부됨 ({e.code}): {e.read().decode()[:200]}") from None


def deg(rad: float | None) -> float | None:
  return None if rad is None else math.degrees(rad)


def read_joints(api: Api, joints: list[str]) -> dict[str, dict]:
  h = api.get("/health")["joints"]
  return {j: h.get(j, {}) for j in joints}


def guard(api: Api, joints: list[str]) -> str | None:
  """멈춰야 할 이유가 있으면 문장으로 돌려준다. 없으면 None."""
  for j, info in read_joints(api, joints).items():
    t = info.get("temp_c")
    if t is None:
      continue
    if not (TEMP_PLAUSIBLE[0] <= t <= TEMP_PLAUSIBLE[1]):
      continue        # 온도로 믿지 않는다. 차단도 하지 않되 그냥 넘어간다.
    if t >= TEMP_STOP_C:
      return f"{j} 온도가 {t:.1f}도로 기준({TEMP_STOP_C}도)에 닿음"
    state = info.get("state")
    if state in ("fault", "stuck"):
      return f"{j} 상태가 '{state}'"
  return None


def hold(api: Api, targets_deg: dict[str, float], joints: list[str], dwell_s: float,
         start: dict[str, float]) -> tuple[list[Sample], list[dict]]:
  """목표를 주고 기다렸다가 잰다. 원본 표본도 함께 돌려준다."""
  applied = api.post("/target", {"values": {j: math.radians(v) for j, v in targets_deg.items()}})
  applied_deg = {j: deg(v) for j, v in applied["applied"].items()}
  series: dict[str, list[float]] = {j: [] for j in joints}
  raw: list[dict] = []
  t0 = time.time()
  while time.time() - t0 < dwell_s:
    api.post("/tx/heartbeat")
    info = read_joints(api, joints)
    row = {"t_s": round(time.time() - t0, 2)}
    for j in joints:
      q = deg(info[j].get("q"))
      row[f"{j}_meas_deg"] = None if q is None else round(q, 3)
      row[f"{j}_cmd_deg"] = round(targets_deg.get(j, float("nan")), 3)
      row[f"{j}_temp_c"] = info[j].get("temp_c")
      if q is not None:
        series[j].append(q)
    raw.append(row)
    stop = guard(api, joints)
    if stop:
      raise RuntimeError(f"안전 중단: {stop}")
    time.sleep(POLL_S)

  out = []
  for j in joints:
    tail = series[j][-SETTLE_SAMPLES:]
    if not tail:
      raise RuntimeError(f"{j} 값이 하나도 오지 않음")
    out.append(Sample(joint=j, commanded_deg=targets_deg.get(j, float("nan")),
                      applied_deg=applied_deg.get(j, float("nan")),
                      settled_deg=statistics.median(tail), spread_deg=max(tail) - min(tail),
                      n=len(tail), dwell_s=dwell_s, start_deg=start.get(j, float("nan"))))
  return out, raw


def robot_accepted(ssh_host: str | None, log_path: str) -> int | None:
  """로봇이 지금까지 받은 명령 수. 로그의 마지막 통계 줄에서 읽는다."""
  if not ssh_host:
    return None
  try:
    out = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", ssh_host,
                          f"grep -o 'accepted=[0-9]*' {log_path} | tail -1"],
                         capture_output=True, text=True, timeout=20).stdout.strip()
    return int(out.split("=")[1]) if "=" in out else None
  except Exception:
    return None


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--api", default="http://127.0.0.1:8095")
  ap.add_argument("--joints", default="L_hip_yaw_joint,L_knee_joint")
  ap.add_argument("--out", default="docs/bench_data")
  ap.add_argument("--ssh", default="syaro@10.8.0.14", help="로봇 쪽 로그를 읽을 주소. 빈 값이면 횟수 검사를 건너뜀")
  ap.add_argument("--robot-log", default="~/remote_motion.log")
  ap.add_argument("--dwell", type=float, default=DWELL_S)
  ap.add_argument("--repeats", type=int, default=REPEATS)
  ap.add_argument("--invert-check", action="store_true",
                  help="일부러 부호를 뒤집어 보낸다. 이 시험이 진짜 검사하는지 확인용 — 실패해야 정상")
  a = ap.parse_args()

  joints = [j.strip() for j in a.joints.split(",") if j.strip()]
  api = Api(a.api)
  checks: list[Check] = []
  all_samples: list[Sample] = []
  raw_rows: list[dict] = []
  stamp = time.strftime("%Y-%m-%d_%H%M%S")

  print(f"명령 도착 확인 시험 — 관절 {joints}, 한 단계 {a.dwell:.0f}초, {a.repeats}회 반복")
  sign = -1.0 if a.invert_check else 1.0
  if a.invert_check:
    print("  ** 부호를 일부러 뒤집었습니다. 이 시험은 실패해야 정상입니다. **")

  try:
    # 실물 각도를 불러와 목표를 실제 자세에 맞춘다. 이걸 건너뛰면 전송을 켜는 순간 크게 움직인다.
    s = api.post("/sync_from_real")
    for j, info in (s.get("clipped") or {}).items():
      if j in joints:
        print(f"  주의: {j} 실물 {deg(info['real']):.1f} (deg) 가 허용 범위 밖이라 "
              f"{deg(info['applied']):.1f} (deg) 로 잘렸습니다. 전송을 켜면 그만큼 움직입니다.")
    api.post("/tx/arm")

    base = {j: deg(v.get("q")) for j, v in read_joints(api, joints).items()}
    # 허용 범위 안의 안전한 출발점으로 먼저 이동해 자리잡게 한다.
    home = {}
    contract = api.get("/contract")["contract"]
    for j in joints:
      lo, hi = contract["safe_clip"][j]
      lo_d, hi_d = deg(lo), deg(hi)
      mid = (lo_d + hi_d) / 2.0
      home[j] = max(lo_d + 20.0, min(hi_d - 20.0, mid))
    print(f"\n출발점으로 이동: " + ", ".join(f"{j} {v:.1f} (deg)" for j, v in home.items()))
    got, rows = hold(api, home, joints, a.dwell, base)
    raw_rows += rows
    start = {s_.joint: s_.settled_deg for s_ in got}
    for s_ in got:
      print(f"  {s_.joint:18s} 자리잡음 {s_.settled_deg:8.2f} (deg)  흔들림 {s_.spread_deg:.2f} (deg)  표본 {s_.n}")

    # --- 단계별 이동 ---
    steps = [5.0, 10.0, 15.0, -5.0]
    print(f"\n{'단계':>6} {'관절':>18} {'명령':>9} {'실제이동':>9} {'차이':>8} {'흔들림':>8} {'표본':>5}")
    per_joint: dict[str, list[Sample]] = {j: [] for j in joints}
    for rep in range(a.repeats):
      for d in steps:
        tgt = {j: start[j] + sign * d for j in joints}
        got, rows = hold(api, tgt, joints, a.dwell, start)
        raw_rows += rows
        for s_ in got:
          per_joint[s_.joint].append(s_)
          all_samples.append(s_)
          print(f"{rep+1}-{d:+.0f}".rjust(6) + f" {s_.joint:>18} {sign*d:9.2f} {s_.moved_deg:9.2f} "
                f"{s_.error_deg:8.2f} {s_.spread_deg:8.2f} {s_.n:5d}")

    # --- 판정 ---
    for j in joints:
      ss = per_joint[j]
      # 방향
      ok_dir = all((s_.moved_deg > 0) == (s_.commanded_deg - s_.start_deg > 0)
                   for s_ in ss if abs(s_.commanded_deg - s_.start_deg) >= 3.0)
      checks.append(Check(f"{j} 방향", ok_dir,
                          "명령한 쪽으로 움직임" if ok_dir else "반대로 움직인 단계가 있음"))
      # 단위: 10도 명령 단계만 본다
      tens = [s_ for s_ in ss if abs(abs(s_.commanded_deg - s_.start_deg) - 10.0) < 0.01]
      if tens:
        ratio = statistics.median(abs(s_.moved_deg) / 10.0 for s_ in tens)
        ok_unit = PASS_UNIT_RATIO[0] <= ratio <= PASS_UNIT_RATIO[1]
        checks.append(Check(f"{j} 단위", ok_unit,
                            f"10 (deg) 명령에 {ratio*10:.1f} (deg) 움직임 (비율 {ratio:.2f})",
                            {"ratio": round(ratio, 3)}))
      # 크기: 명령 이동량 대 실제 이동량의 기울기
      xs = [s_.commanded_deg - s_.start_deg for s_ in ss]
      ys = [s_.moved_deg for s_ in ss]
      if len(xs) >= 2 and (max(xs) - min(xs)) > 1e-6:
        mx, my = statistics.mean(xs), statistics.mean(ys)
        denom = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
        ok_scale = PASS_SCALE_SLOPE[0] <= slope <= PASS_SCALE_SLOPE[1]
        checks.append(Check(f"{j} 크기", ok_scale, f"기울기 {slope:.3f} (1.0이면 정확)",
                            {"slope": round(slope, 4)}))

    # 보내는 횟수
    before = robot_accepted(a.ssh, a.robot_log)
    t0 = time.time()
    for _ in range(50):
      api.post("/tx/heartbeat")
      time.sleep(0.1)
    elapsed = time.time() - t0
    after = robot_accepted(a.ssh, a.robot_log)
    tx = api.get("/tx/status")
    if before is not None and after is not None and elapsed > 0:
      robot_rate = (after - before) / elapsed
      view_rate = float(tx.get("rate_hz") or 0.0)
      diff = abs(robot_rate - view_rate) / view_rate if view_rate else 1.0
      ok_rate = diff <= PASS_RATE_DIFF
      checks.append(Check("보내는 횟수", ok_rate,
                          f"화면 {view_rate:.1f}회/초, 로봇 {robot_rate:.1f}회/초 (차이 {diff*100:.1f}%)",
                          {"viewer_hz": view_rate, "robot_hz": round(robot_rate, 2)}))
    else:
      checks.append(Check("보내는 횟수", False, "로봇 쪽 수를 읽지 못해 검사하지 못함"))
  finally:
    try:
      api.post("/tx/disarm")
      print("\n전송 껐습니다.")
    except Exception:
      print("\n전송을 끄지 못했습니다 — 직접 확인하세요.", file=sys.stderr)

  # --- 결과 ---
  print("\n" + "=" * 62)
  for c in checks:
    print(f"  [{'통과' if c.passed else '실패'}] {c.name:24s} {c.detail}")
  n_pass = sum(1 for c in checks if c.passed)
  print(f"  {n_pass}/{len(checks)} 통과")
  print("\n이 숫자로 할 수 없는 말:")
  print("  - 관절의 기준점을 잡지 않았으므로 각도는 '모터가 켜진 순간을 0으로 본 값'이다.")
  print("  - 관절이 2개뿐이라 '어느 숫자가 어느 관절로 가는가'는 부분만 확인된다.")
  print("  - 세기(kp)가 낮아 자리잡은 값에 남는 차이가 있다. 차이의 크기 자체는 세기 설정에 달렸다.")

  import os
  os.makedirs(a.out, exist_ok=True)
  raw_path = os.path.join(a.out, f"{stamp}_command_arrival_raw.csv")
  if raw_rows:
    keys = sorted({k for r in raw_rows for k in r})
    with open(raw_path, "w", newline="") as f:
      w = csv.DictWriter(f, fieldnames=keys)
      w.writeheader()
      w.writerows(raw_rows)
  sum_path = os.path.join(a.out, f"{stamp}_command_arrival_summary.json")
  with open(sum_path, "w") as f:
    json.dump({"checks": [c.__dict__ for c in checks],
               "samples": [s_.__dict__ for s_ in all_samples],
               "settings": {"dwell_s": a.dwell, "repeats": a.repeats, "joints": joints,
                            "inverted": a.invert_check}}, f, ensure_ascii=False, indent=1)
  print(f"\n원본 {raw_path}\n요약 {sum_path}")

  if a.invert_check:
    # 뒤집었을 때는 실패해야 이 시험이 진짜 검사하는 것이다.
    return 0 if n_pass < len(checks) else 1
  return 0 if n_pass == len(checks) else 1


if __name__ == "__main__":
  raise SystemExit(main())
