#!/usr/bin/env python3
"""모터 **한 대만** 있는 MuJoCo 모형을 만들고, 실측에 맞도록 세 값을 찾는다.

2026-09-09. 사용자 지시 3번: "Sim 에서도 그 파라미터를 갖고 mjlab 에서 모터'만'을 만들고,
그 응답과 비교하라." 방법은 사전조사(``docs/reward_research/2026-09-09_motor_sysid_method.md``)
가 정리한 대로, MuJoCo 에 들어 있는 ``mujoco.sysid`` 회색상자 식별을 쓴다.

무엇을 찾는가
-------------
경첩 하나에 토크 액추에이터 하나. 다리도 중력도 없다 — 벤치의 실물이 축에 아무것도 안 달린
맨 모터이므로, 모형도 그래야 같은 것을 비교한다.

======================  ==========================================
``armature``            기어를 지나 반사된 회전자 관성
``frictionloss``        쿨롱 마찰. 방향만 거스르는 일정한 토크
``damping``             점성 마찰. 속도에 비례
======================  ==========================================

왜 이 세 개인가: **빠른 흔들림은 관성이, 느린 흔들림은 마찰이** 지배한다. 다중사인은 두
영역을 한 기록 안에 같이 담으므로 셋을 함께 가를 수 있다.

맞추는 자료와 검증하는 자료를 나눈다
------------------------------------
맞추는 데 쓴 자료로 다시 검증하면 "잘 맞는다"는 말이 아무 뜻이 없다. 사전연구와 같이
**다중사인으로 맞추고, 위치 명령 추종으로 검증한다** — 성격이 다른 움직임이라 과적합이
바로 드러난다.

    fit_motor.py --fit data/sweep_knee_a1.0.csv data/sweep_knee_a1.6.csv \\
                 --validate data/pd_knee_01.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys

import mujoco
import numpy as np
from mujoco import rollout, sysid

DEG = math.pi / 180.0

MOTOR_XML = """\
<mujoco model="one_motor">
  <compiler angle="radian" autolimits="true"/>
  <option integrator="implicitfast" timestep="{dt}">
    <flag contact="disable" gravity="disable"/>
  </option>
  <worldbody>
    <body name="rotor">
      <!-- 관성은 armature 가 전부 담당한다. 몸체 관성을 아주 작게 두는 이유는, 축에
           아무것도 안 달린 맨 모터라 실제로 도는 것이 회전자뿐이기 때문이다. 두 곳에
           관성을 나눠 두면 최적화가 둘을 구별하지 못해 아무 값이나 고른다. -->
      <inertial pos="0 0 0" mass="0.001" diaginertia="1e-6 1e-6 1e-6"/>
      <joint name="j" type="hinge" axis="0 0 1" limited="false"
             armature="{armature}" damping="{damping}" frictionloss="{frictionloss}"/>
      <geom type="cylinder" size="0.04 0.02" mass="0"/>
    </body>
  </worldbody>
  <actuator>
    <motor name="tau" joint="j" gear="{gear}"/>
  </actuator>
  <sensor>
    <jointpos name="pos" joint="j"/>
    <jointvel name="vel" joint="j"/>
  </sensor>
</mujoco>
"""


def load_csv(path):
  """실측 한 벌. 각도는 도, 시간은 초로 기록돼 있다 — 여기서 라디안으로 바꾼다."""
  t, cmd, pos, vel = [], [], [], []
  with open(path) as f:
    for row in csv.DictReader(f):
      t.append(float(row["t_s"]))
      cmd.append(float(row["cmd"]))
      pos.append(float(row["pos_deg"]) * DEG)
      vel.append(float(row["vel_deg_s"]) * DEG)
  return (np.asarray(t), np.asarray(cmd), np.asarray(pos), np.asarray(vel))


def build_spec(dt, armature=0.01, damping=0.01, frictionloss=0.2, gear=1.0):
  return mujoco.MjSpec.from_string(MOTOR_XML.format(
    dt=dt, armature=armature, damping=damping, frictionloss=frictionloss, gear=gear))


def make_sequence(path, name, delay_samples=0):
  """한 기록을 툴박스가 먹는 모양으로 바꾼다.

  각도를 **시작점 기준 상대값**으로 옮긴다. 모터의 절대 각도는 이 실험과 아무 상관이 없고,
  그대로 두면 최적화가 초기 위치를 맞추는 데 힘을 쓴다.
  """
  t, cmd, pos, vel = load_csv(path)
  dt = float(np.median(np.diff(t)))
  pos = pos - pos[0]
  if delay_samples:
    # 명령을 뒤로 미룬다 = 모형이 실물과 같은 시점에 힘을 받는다. 앞쪽은 0 으로 채운다
    # (실제로도 그 시각에는 아직 아무 힘이 안 갔다).
    cmd = np.concatenate([np.zeros(delay_samples), cmd[:-delay_samples]])
  ctrl = cmd.reshape(-1, 1)
  meas = np.column_stack([pos, vel])
  return dict(name=name, t=t, dt=dt, ctrl=ctrl, meas=meas, q0=pos[0], v0=vel[0])


def rollout_model(model, ctrl, q0, v0):
  data = mujoco.MjData(model)
  init = sysid.create_initial_state(model, np.array([q0]), np.array([v0]), data.act)
  state, sensor = rollout.rollout(model, data, init, ctrl[:-1])
  return np.squeeze(sensor, axis=0)


def rollout_pd(model, target_rad, q0, v0, kp, kd):
  """위치 명령을 **모터 펌웨어와 같은 식으로** 되먹여 돌린다.

      tau = kp*(목표각 - 현재각) + kd*(0 - 현재속도)

  미리 계산한 토크 배열을 넣을 수 없는 이유: 되먹임이라 매 순간의 토크가 그 순간의 위치에
  달려 있다. 사전연구도 검증을 이렇게 했다 - "같은 위치 명령을 같은 Kp/Kd 로 설정한 MuJoCo
  액추에이터에 넣었다".

  앞서 이 되먹임을 빼먹고 목표 **각도**를 토크로 넣어, 30~50 뉴턴미터를 계속 때리는 꼴이
  되어 검증 오차가 62만 도로 나왔다(2026-09-09).
  """
  data = mujoco.MjData(model)
  data.qpos[0], data.qvel[0] = q0, v0
  out = np.empty((len(target_rad), 2))
  for i, tgt in enumerate(target_rad):
    out[i] = (data.qpos[0], data.qvel[0])
    data.ctrl[0] = kp * (tgt - data.qpos[0]) + kd * (0.0 - data.qvel[0])
    mujoco.mj_step(model, data)
  return out


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--fit", nargs="+", required=True)
  ap.add_argument("--validate", nargs="*", default=[])
  ap.add_argument("--armature0", type=float, default=0.01633,
                  help="출발값. 기본은 지금 로봇 모형이 쓰는 무릎 값")
  ap.add_argument("--damping0", type=float, default=0.0095)
  ap.add_argument("--friction0", type=float, default=0.2695)
  ap.add_argument("--delay-samples", type=int, default=0,
                  help="시킨 토크를 이만큼 늦춰서 모형에 넣는다. 실측 지연 약 15 ms "
                       "= 200 Hz 에서 3 표본")
  ap.add_argument("--no-scale", action="store_true", help="토크 배율을 고정 1로 둔다")
  ap.add_argument("--val-kp", type=float, default=8.0,
                  help="검증 자료를 받을 때 모터에 실제로 보낸 이득")
  ap.add_argument("--val-kd", type=float, default=0.6)
  ap.add_argument("--out", default="System_ID/fit_result.json")
  a = ap.parse_args(argv)

  seqs = [make_sequence(p, f"seq{i}", a.delay_samples) for i, p in enumerate(a.fit)]
  dt = seqs[0]["dt"]
  print(f"맞추는 자료 {len(seqs)}벌 · 표본 간격 {dt*1000:.2f} ms "
        f"({1/dt:.0f} Hz) · 길이 " + ", ".join(f"{s['t'][-1]:.1f}초" for s in seqs))

  spec = build_spec(dt, a.armature0, a.damping0, a.friction0, 1.0)
  model = spec.compile()
  data = mujoco.MjData(model)

  # MjSpec 의 관절 속성은 이름마다 모양이 다르다 — 직접 확인한 결과:
  #   armature, frictionloss  : 스칼라 (3칸 배열을 넣으면 거부)
  #   damping, stiffness      : 3칸 배열 (스칼라를 넣으면 거부)
  # 공 관절·자유 관절은 축이 셋이라 축마다 값이 필요하지만, 관성과 쿨롱 마찰은 관절 하나에
  # 하나뿐이라 그렇다. 틀린 모양을 넣으면 조용히 통과하지 않고 그 자리에서 거부되므로,
  # 여기서 한 번만 갈라 두면 된다.
  VECTOR_ATTRS = {"damping", "stiffness"}

  def _set(name):
    def apply(spec, p):
      v = float(p.value[0])
      setattr(spec.joint("j"), name,
              np.array([v, 0.0, 0.0]) if name in VECTOR_ATTRS else v)
    return apply

  params = sysid.ParameterDict()
  params.add(sysid.Parameter("armature", nominal=a.armature0, min_value=1e-4,
                             max_value=1.0, modifier=_set("armature")))
  params.add(sysid.Parameter("damping", nominal=a.damping0, min_value=0.0,
                             max_value=2.0, modifier=_set("damping")))
  params.add(sysid.Parameter("frictionloss", nominal=a.friction0, min_value=0.0,
                             max_value=5.0, modifier=_set("frictionloss")))
  # 시킨 토크가 그대로 나오지 않는다. 실측(2026-09-09): 모터가 보고한 토크가 시킨 값의
  # 0.27~0.37배. 이 차이를 파라미터로 두지 않으면 관성과 마찰이 대신 그 몫을 떠안아,
  # 맞추는 자료에는 잘 맞고 다른 자료에는 안 맞는 값이 나온다(실제로 그랬다).
  # 액추에이터의 gear 가 곧 "시킨 값 -> 실제 토크" 배율이다.
  if not a.no_scale:
    params.add(sysid.Parameter(
      "torque_scale", nominal=1.0, min_value=0.05, max_value=8.0,
      modifier=lambda spec, p: setattr(spec.actuator("tau"), "gear",
                                       np.array([float(p.value[0]), 0, 0, 0, 0, 0]))))

  mss = []
  for s in seqs:
    init = sysid.create_initial_state(model, np.array([s["q0"]]), np.array([s["v0"]]), data.act)
    mss.append(sysid.ModelSequences(
      s["name"], spec, "measured", init,
      sysid.TimeSeries(s["t"], s["ctrl"]),
      sysid.TimeSeries.from_names(s["t"], s["meas"], model)))

  keys = list(params.parameters)
  before = {k: float(params[k].value[0]) for k in keys}
  residual_fn = sysid.build_residual_fn(models_sequences=mss)
  r0 = residual_fn(params.as_vector(), params)
  cost0 = float(np.sum(np.square(np.concatenate([np.ravel(x) for x in r0[0]]))))

  print("\n맞추는 중...")
  opt, _ = sysid.optimize(initial_params=params, residual_fn=residual_fn,
                          optimizer="mujoco", verbose=False)
  after = {k: float(opt[k].value[0]) for k in keys}
  r1 = residual_fn(opt.as_vector(), opt)
  cost1 = float(np.sum(np.square(np.concatenate([np.ravel(x) for x in r1[0]]))))

  print(f"\n{'값':16s} {'출발(현 모형)':>14s} {'맞춘 뒤':>12s} {'배수':>8s}")
  print("-" * 54)
  for k in before:
    ratio = after[k] / before[k] if before[k] else float("inf")
    print(f"{k:16s} {before[k]:14.5f} {after[k]:12.5f} {ratio:7.2f}x")
  print(f"\n남은 차이(작을수록 잘 맞음): {cost0:.4f} → {cost1:.4f}")

  # ---------------------------------------------------------------- 검증
  report = {"fit_files": a.fit, "before": before, "after": after,
            "cost_before": cost0, "cost_after": cost1, "validate": {}}
  for vp in a.validate:
    v = make_sequence(vp, "val")  # 검증은 위치 명령이라 지연을 여기서 넣지 않는다
    # 검증 자료의 cmd 는 목표 **각도**(도)다. 시작점 기준으로 옮겨 위치와 같은 기준에 둔다.
    tgt = (v["ctrl"][:, 0] * DEG) - (v["ctrl"][0, 0] * DEG) + v["q0"]
    out = {}
    for label, prm in (("before", before), ("after", after)):
      m = build_spec(v["dt"], prm["armature"], prm["damping"], prm["frictionloss"],
                     prm.get("torque_scale", 1.0)).compile()
      sens = rollout_pd(m, tgt, v["q0"], v["v0"], a.val_kp, a.val_kd)
      n = min(len(sens), len(v["meas"]))
      err = sens[:n, 0] - v["meas"][:n, 0]
      out[label] = dict(rms_deg=float(np.sqrt(np.mean(err**2)) / DEG),
                        max_deg=float(np.max(np.abs(err)) / DEG))
    report["validate"][vp] = out
    print(f"\n검증 (맞추는 데 쓰지 않은 자료: {vp})")
    print(f"  위치 오차   출발 {out['before']['rms_deg']:.3f}도(제곱평균) "
          f"/ {out['before']['max_deg']:.3f}도(최대)")
    print(f"             맞춘뒤 {out['after']['rms_deg']:.3f}도(제곱평균) "
          f"/ {out['after']['max_deg']:.3f}도(최대)")

  # 값만 내면 얼마나 믿을 수 있는지 알 수 없다. 최적점의 기울기에서 구간을 낸다.
  try:
    J = []
    x0 = opt.as_vector()
    base = np.concatenate([np.ravel(z) for z in residual_fn(x0, opt)[0]])
    for i in range(len(x0)):
      h = max(abs(x0[i]) * 1e-4, 1e-8)
      xp = x0.copy(); xp[i] += h
      J.append((np.concatenate([np.ravel(z) for z in residual_fn(xp, opt)[0]]) - base) / h)
    J = np.stack(J, axis=1)
    lo, hi = sysid.calculate_intervals([base], J)
    print(f"\n{'값':16s} {'맞춘 값':>12s} {'95% 구간':>26s}")
    print("-" * 58)
    for i, k in enumerate(keys):
      l = float(np.ravel(lo)[i]); h2 = float(np.ravel(hi)[i])
      print(f"{k:16s} {after[k]:12.5f}   [{l:9.5f}, {h2:9.5f}]")
      report.setdefault("interval", {})[k] = [l, h2]
  except Exception as exc:
    print(f"\n신뢰구간을 내지 못했습니다: {exc}")

  with open(a.out, "w") as f:
    json.dump(report, f, indent=1, ensure_ascii=False)
  print(f"\n결과 저장: {a.out}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
