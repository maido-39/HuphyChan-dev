#!/usr/bin/env python3
"""같은 명령을 화면 속 모형과 실물 모터에 동시에 주고, 둘의 응답을 주파수별로 비교한다.

2026-09-09, 사용자 지시: "Sim 과 Real 에 동일한 Kp/Kd 값을 주고, Sine Sweep 입력을 넣어서
응답을 비교해 보라." 관찰된 것은 상식과 반대였다 - **링크가 달린 Sim 쪽이 오버슛이 나고,
실물이 목표를 못 따라간다.** 링크의 관성이 붙은 쪽이 더 굼떠야 정상이다.

무엇을 재는가
-------------
한 관절에 사인파 목표를 주되 주파수를 낮은 쪽에서 높은 쪽으로 계단식으로 올린다. 각 계단마다

* **따라간 정도** = 실제로 움직인 폭 ÷ 시킨 폭. 1이면 시킨 만큼 갔고, 0.5면 절반만 갔다.
* **늦은 정도** = 목표보다 몇 도(위상) 늦게 따라오는가.
* **넘어간 정도** = 시킨 폭보다 더 갔는가 (1보다 크면 오버슛).

이 세 가지를 Sim 과 Real 에 대해 같은 명령·같은 시각으로 재서 나란히 놓는다.

왜 계단식 사인인가
------------------
한 번에 쓸고 지나가는(chirp) 방식은 각 주파수에 머무는 시간이 짧아서, 아직 정상상태에 들지
않은 과도 응답을 그 주파수의 답으로 착각하기 쉽다. 계단마다 몇 주기씩 머물고 **앞쪽 주기는
버린 뒤** 재면 그 착각이 없다. 측정 dwell 규칙(문서화된 프로젝트 규칙)과도 같은 이유다.

기록
----
서버 쪽 기록기가 제어 주기마다 한 줄씩 남기고, 그 줄에 **시킨 값·Sim 값·Real 값이 함께**
들어간다(2026-09-09 추가). 두 스트림을 나중에 시각으로 맞붙이면 안 되는 이유는, 재려는 지연이
제어 주기의 일부라서 맞붙이는 오차와 같은 크기이기 때문이다.

안전
----
* 실물로 나가는 실행은 **현재 위치 기준 ±진폭**이 관절 허용 범위 안에 들어올 때만 시작한다.
* 온도를 매 계단마다 보고, 정해진 값을 넘으면 즉시 멈춘다.
* 고장이 보고되면 즉시 멈춘다.
* ``--dry-run`` 은 실물로 아무것도 보내지 않고 Sim 만 돌린다. 먼저 이걸로 확인한다.

    sine_sweep_ab.py --dry-run --joint L_knee_joint
    sine_sweep_ab.py --joint L_knee_joint --amp-deg 8 --match-gains
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

FREQS_HZ = (0.2, 0.4, 0.8, 1.2, 1.6, 2.4, 3.2)
"""계단으로 머무를 주파수들. 0.2 Hz 는 거의 정적이라 '따라가는 정도'의 기준선이 되고,
3.2 Hz 는 이 이득에서 확실히 못 따라오는 쪽이다. 사이를 대략 2배씩 벌려 로그 축에 고르게 찍힌다."""

CYCLES_PER_STEP = 6
"""한 계단에 머무는 주기 수. 앞 2주기는 버리고 뒤 4주기로 잰다."""

DISCARD_CYCLES = 2

TEMP_STOP_C = 50.0
"""이 온도에 닿으면 멈춘다 (사용자 지시: 50도에서 힘을 끊는다)."""

SETTLE_S = 0.6


def _req(method, path, body=None, timeout=20):
  data = json.dumps(body).encode() if body is not None else None
  req = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
  try:
    return json.load(urllib.request.urlopen(req, timeout=timeout)), None
  except urllib.error.HTTPError as e:
    try:
      return None, json.loads(e.read().decode()).get("detail", "")
    except Exception:
      return None, str(e)


def post(path, body=None, timeout=20):
  return _req("POST", path, body, timeout)


def get(path):
  return json.load(urllib.request.urlopen(BASE + path, timeout=5))


def deg(rad):
  return math.degrees(rad)


def build_script(joint, centre_rad, amp_rad, freqs, rate_hz=50.0):
  """계단식 사인 목표를 뷰어의 목표 재생기가 읽는 형식으로 만든다.

  각 계단은 **정수 개의 주기**로 끝나므로 계단 경계에서 목표가 튀지 않는다. 튀면 그 자체가
  넓은 주파수 성분을 가진 입력이라, 바로 다음 계단의 응답을 오염시킨다.
  """
  rows, t = [], 0.0
  dt = 1.0 / rate_hz
  marks = []
  for f in freqs:
    dur = CYCLES_PER_STEP / f
    t0 = t
    n = int(round(dur * rate_hz))
    for k in range(n):
      tt = k * dt
      q = centre_rad + amp_rad * math.sin(2.0 * math.pi * f * tt)
      rows.append([round(t + tt, 6), round(q, 8)])
    t = t0 + n * dt
    marks.append({"f_hz": f, "t0": t0, "t1": t})
  # 마지막에 가운데로 돌려놓고 잠시 멈춘다 - 끝나자마자 목표가 사라지면 마지막 값에서
  # 홀드되는데, 그 값이 사인의 꼭대기면 관절이 거기 매달린 채 끝난다.
  for k in range(int(SETTLE_S * rate_hz)):
    rows.append([round(t + k * dt, 6), round(centre_rad, 8)])
  return {"joint_names": [joint], "rows": [[r[0], r[1]] for r in rows]}, marks, t + SETTLE_S


def analyse(path, joint, marks, amp_rad):
  """기록에서 계단마다 따라간 정도·늦은 정도를 뽑는다."""
  import gzip
  rows = []
  op = gzip.open if str(path).endswith(".gz") else open
  with op(path, "rt") as f:
    for line in f:
      line = line.strip()
      if not line:
        continue
      try:
        d = json.loads(line)
      except Exception:
        continue
      if d.get("type") != "JointState" or joint not in (d.get("joint_names") or []):
        continue
      i = d["joint_names"].index(joint)
      rows.append({
        "t": d["t_ns"] / 1e9,
        "tgt": (d.get("target") or [None])[i],
        "sim": (d.get("q") or [None])[i],
        "real": (d.get("q_real") or [None])[i] if d.get("q_real") else None,
        "age": (d.get("q_real_age_s") or [None])[i] if d.get("q_real_age_s") else None,
      })
  if not rows:
    return []
  t0 = rows[0]["t"]
  for r in rows:
    r["t"] -= t0
  # 재생 시작 시각을 목표가 실제로 흔들리기 시작한 곳으로 잡는다
  out = []
  for m in marks:
    f = m["f_hz"]
    skip = DISCARD_CYCLES / f
    seg = [r for r in rows if m["t0"] + skip <= r["t"] < m["t1"]]
    if len(seg) < 8:
      continue
    row = {"f_hz": f, "n": len(seg)}
    for who in ("sim", "real"):
      vals = [r[who] for r in seg if r[who] is not None]
      tgts = [r["tgt"] for r in seg if r[who] is not None]
      ts = [r["t"] for r in seg if r[who] is not None]
      if len(vals) < 8:
        row[who] = None
        continue
      # 진폭은 정현 성분의 크기로 잰다(최대-최소는 잡음 하나에 끌려간다).
      w = 2 * math.pi * f
      def proj(sig):
        mean = sum(sig) / len(sig)
        c = sum((v - mean) * math.cos(w * t) for v, t in zip(sig, ts)) * 2 / len(sig)
        s = sum((v - mean) * math.sin(w * t) for v, t in zip(sig, ts)) * 2 / len(sig)
        return c, s
      cy, sy = proj(vals)
      ct, st = proj(tgts)
      amp_y = math.hypot(cy, sy)
      amp_t = math.hypot(ct, st)
      ph = math.degrees(math.atan2(sy, cy) - math.atan2(st, ct))
      while ph > 180:
        ph -= 360
      while ph < -180:
        ph += 360
      row[who] = {
        "gain": amp_y / amp_t if amp_t > 1e-9 else float("nan"),
        "phase_deg": ph,
        "amp_deg": deg(amp_y),
        "peak_deg": deg(max(vals) - min(vals)) / 2,
      }
    ages = [r["age"] for r in seg if r.get("age") is not None]
    row["real_age_ms"] = 1000 * sum(ages) / len(ages) if ages else None
    out.append(row)
  return out


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--joint", default="L_knee_joint")
  ap.add_argument("--amp-deg", type=float, default=8.0)
  ap.add_argument("--dry-run", action="store_true", help="실물로 보내지 않고 Sim 만")
  ap.add_argument("--match-gains", action="store_true",
                  help="Sim 의 이득을 실물에 실제로 도착하는 값으로 낮춘다 (동일 조건 비교)")
  ap.add_argument("--kp", type=float, default=None, help="양쪽에 쓸 kp (생략하면 현재값)")
  ap.add_argument("--kd", type=float, default=None)
  ap.add_argument("--base-height", type=float, default=None,
                  help="화면 속 로봇을 이 높이에 매단다. 발이 바닥에 닿으면 무릎이 체중을 "
                       "받아 실측 23 Nm 가 걸리는데, 벤치의 실물 모터는 축에 아무것도 안 달린 "
                       "맨 모터다 - 그대로 비교하면 하중 걸린 쪽과 무부하를 견주게 된다. "
                       "1.35 m 면 발이 떠서 무릎 토크가 4.8 Nm(정강이 무게)로 떨어진다.")
  ap.add_argument("--out", default=None)
  a = ap.parse_args(argv)

  try:
    get("/status")
  except Exception as e:
    print(f"뷰어에 연결할 수 없습니다: {e}", file=sys.stderr)
    return 1

  j = a.joint
  amp = math.radians(a.amp_deg)

  if a.base_height is not None:
    post("/base", {"mode": "fixed", "height": a.base_height})
    time.sleep(1.0)
    z = get("/status")["base"]["pos"][2]
    print(f"화면 속 로봇을 {z:.2f} m 에 매달았습니다")

  # ---------------------------------------------------------------- 어디서 시작하는가
  health = get("/health")["joints"]
  if j not in health:
    print(f"{j} 이라는 관절이 없습니다", file=sys.stderr)
    return 1
  real_q = health[j]["q"]
  if not a.dry_run and real_q is None:
    print(f"{j} 의 실측값이 없습니다 - 로봇 통신을 확인하세요", file=sys.stderr)
    return 1
  centre = real_q if not a.dry_run else get("/snapshot")["q"][
    get("/contract")["contract"]["joint_names"].index(j)]

  clip = get("/contract")["contract"].get("clip", {}).get(j)
  if clip:
    lo, hi = clip[0], clip[1]
    if centre - amp < lo or centre + amp > hi:
      print(f"거부: 지금 위치 {deg(centre):.1f}도에서 ±{a.amp_deg}도를 흔들면 허용 범위 "
            f"[{deg(lo):.1f}, {deg(hi):.1f}]도를 벗어납니다", file=sys.stderr)
      return 1

  print(f"관절 {j} · 가운데 {deg(centre):.1f}도 · 진폭 ±{a.amp_deg}도 · "
        f"{'실물 없음(dry-run)' if a.dry_run else '실물로 전송'}")

  # ---------------------------------------------------------------- 이득을 맞춘다
  tx = get("/tx/status")
  kp_cap, kd_cap = tx["kp_max"], tx["kd_max"]
  g = get("/gains")["gains"][j]
  print(f"지금 이득: Sim kp={g['kp']} kd={g['kd']} · 전송 상한 kp<={kp_cap} kd<={kd_cap}"
        f"  → 실물에 도착하는 값 kp={min(g['kp'], kp_cap)} kd={min(g['kd'], kd_cap)}")
  if a.match_gains or a.kp is not None:
    kp = a.kp if a.kp is not None else min(g["kp"], kp_cap)
    kd = a.kd if a.kd is not None else min(g["kd"], kd_cap)
    r, e = post("/gains", {"overrides": {j: {"kp": kp, "kd": kd}}})
    if not r:
      print(f"이득을 못 바꿨습니다: {e}", file=sys.stderr)
      return 1
    print(f"양쪽 동일 이득으로 맞춤: kp={kp} kd={kd}")

  script, marks, dur = build_script(j, centre, amp, FREQS_HZ)
  spath = "/tmp/claude-1000/sine_sweep.json"
  import pathlib
  pathlib.Path(spath).parent.mkdir(parents=True, exist_ok=True)
  pathlib.Path(spath).write_text(json.dumps(script))
  print(f"계단 {len(marks)}개 · 전체 {dur:.1f}초 · {FREQS_HZ[0]}~{FREQS_HZ[-1]} Hz")

  post("/mode", {"mode": "manual"})
  time.sleep(0.3)

  armed = False
  if not a.dry_run:
    post("/sync_from_real")
    time.sleep(0.35)
    r, e = post("/tx/arm")
    if not r:
      print(f"무장 거부: {e}", file=sys.stderr)
      return 1
    armed = True
    print("무장됨 - 실물로 나갑니다")

  rec, _ = post("/record/start", {})
  out_path = rec["path"] if rec else None
  r, e = post("/script/run", {"path": spath})
  if not r:
    print(f"재생 실패: {e}", file=sys.stderr)
    if armed:
      post("/tx/disarm")
    post("/record/stop")
    return 1

  t0 = time.time()
  stop = None
  while time.time() - t0 < dur + 1.0:
    if armed:
      post("/tx/heartbeat")
    h = get("/health")["joints"][j]
    if h.get("temp_c") and h["temp_c"] >= TEMP_STOP_C:
      stop = f"온도 {h['temp_c']}도 - 멈춤"
      break
    if h.get("fault_reason"):
      stop = f"고장 보고: {h['fault_reason']}"
      break
    time.sleep(0.05)
  if armed:
    post("/tx/disarm")
  post("/script/stop")
  info, _ = post("/record/stop")
  path = (info or {}).get("path") or out_path
  if stop:
    print(f"!! {stop}")

  print(f"\n기록: {path}")
  table = analyse(path, j, marks, amp)
  if not table:
    print("기록에서 이 관절의 줄을 못 찾았습니다", file=sys.stderr)
    return 1

  print(f"\n{'주파수':>7s} | {'Sim 따라감':>10s} {'Sim 늦음':>9s} | "
        f"{'Real 따라감':>11s} {'Real 늦음':>10s} | {'실측 나이':>9s}")
  print("-" * 74)
  for r in table:
    s, rl = r.get("sim"), r.get("real")
    ss = f"{s['gain']:10.3f} {s['phase_deg']:8.1f}도" if s else f"{'-':>10s} {'-':>9s}"
    rr = f"{rl['gain']:11.3f} {rl['phase_deg']:9.1f}도" if rl else f"{'-':>11s} {'-':>10s}"
    age = f"{r['real_age_ms']:7.1f}ms" if r.get("real_age_ms") is not None else f"{'-':>9s}"
    print(f"{r['f_hz']:6.2f}Hz | {ss} | {rr} | {age}")

  print("\n따라감 1.0 = 시킨 만큼 움직임 · 1.0 초과 = 오버슛 · 늦음은 목표 대비 위상")
  if a.out:
    import pathlib
    pathlib.Path(a.out).write_text(json.dumps(
      {"joint": j, "centre_rad": centre, "amp_rad": amp, "record": str(path),
       "base_height": a.base_height, "dry_run": a.dry_run,
       "kp": (a.kp if a.kp is not None else None), "kd": (a.kd if a.kd is not None else None),
       "gains_applied": get("/gains")["gains"][j],
       "tx_caps": {"kp_max": kp_cap, "kd_max": kd_cap},
       "table": table}, indent=1, ensure_ascii=False))
    print(f"표를 저장했습니다: {a.out}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
