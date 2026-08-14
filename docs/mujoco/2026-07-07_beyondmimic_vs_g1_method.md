# BeyondMimic vs G1 — Kp/Kd 도출·적용 방법 비교 (코드 기준)

> 2026-07-07. 실제 코드 확인: BeyondMimic = [HybridRobotics/whole_body_tracking](https://github.com/HybridRobotics/whole_body_tracking) robots/g1.py, G1 = [unitree_rl_gym](../../refs/unitree_rl_gym/) + [g1 mjcf](../../refs/unitree_mujoco/). 관련: [우리 유도](2026-07-07_kpkd_beyondmimic_derivation.md)·[G1 ζ분석](2026-07-07_g1_gains_beyondmimic.md).

## 1. BeyondMimic — 물리 공식 도출 (armature 기준)
whole_body_tracking/robots/g1.py 실제 코드:
```
STIFFNESS = ARMATURE * NATURAL_FREQ**2
DAMPING   = 2.0 * DAMPING_RATIO * ARMATURE * NATURAL_FREQ
NATURAL_FREQ = 10 Hz (=62.83 rad/s),  DAMPING_RATIO = 2.0
ARMATURE_7520_14 = 0.01018  등 (모터별 반사관성)
```
- $K_p = I_{arm}(2\pi f_n)^2,\quad K_d = 2\zeta I_{arm}(2\pi f_n)$, **$I$=모터 armature**, $f_n$=10Hz, $\zeta$=2(over-damped).
- 적용: **`ImplicitActuatorCfg`**(Isaac Lab 엔진 내부 PD = MuJoCo `<position>` actuator kp/kd와 동형).
- ★자인: *"armature만 쓰면 link 관성을 무시해 관성이 과소평가되므로 $\zeta$=2로 보정, $f_n$은 낮게"* — armature 한계를 알고 over-damp로 완충.

## 2. G1(unitree) — 수동 튜닝 + 소프트웨어 PD
- 게인은 **하드코딩 dict**(공식 유도 아님): hip 100/2, knee 150/4, ankle 40/2 (`g1_config.py:42-53`).
- 적용: **torque actuator**(`<motor ctrlrange=±88/139/50>`) + **파이썬 소프트웨어 PD**:
  `torques = p_gains*(target - dof_pos) - d_gains*dof_vel` (`legged_robot.py:323`).
- MuJoCo XML엔 **PD 게인 없음** — passive `<joint damping=0.05 armature=0.01>`만. 엔진은 토크만 받음.

## 3. 구조적 차이 (핵심)
| | BeyondMimic | G1(unitree) |
|---|---|---|
| 게인 출처 | **물리공식**(armature·f_n·ζ) | **수동튜닝** 고정값 |
| I | 모터 armature | (없음, 경험) |
| ζ 목표 | 2 (over, on armature) | 없음 |
| 적용 위치 | **actuator**(엔진 내부 PD) | **컨트롤러**(SW PD on torque) |
| MJCF에 게인? | 있음(position) | 없음(torque+SW PD) |
| 우리(mjlab)와 동형? | ✅ (BuiltinPositionActuator=엔진PD) | ❌ (우린 torque+SW PD 안 씀) |

→ **우리 mjlab은 BeyondMimic식**(엔진 내부 PD, actuator에 stiffness/damping). G1식(torque+SW PD)이 아님.

## 4. 우리 로봇에 BeyondMimic-literal 적용하면? (armature, $f_n$10, $\zeta$2)
| 관절 | Kp | Kd | 실제 ζ_link |
|---|--:|--:|--:|
| hip_pitch | 27.6 | 1.76 | **0.11** under |
| knee | 27.6 | 1.76 | 0.30 under |
| ankle_pitch | 19.7 | 1.26 | 1.41 ok |
| ankle_roll | 2.0 | 0.13 | 0.82 |

★ **BeyondMimic-literal = 우리 A0a**(발목 Kp 19.7 동일) = 예전에 *"너무 물렁"*(wobble·0.56Hz)이라 **버린 값**. armature만 쓰면 51.5kg 이족엔 강성 부족. 또한 Kp도 낮아(28) ζ_link는 여전히 0.11(under) — over-damp(ζ2)도 링크 진동을 못 막음(Kp가 낮아 소프트해서 폭주만 안 할 뿐).

## 5. 결론 — 두 갈래, 우리 선택
- **(A) BeyondMimic-literal**(soft): Kp≈28/Kd≈3.5. 컴플라이언트·저권한. RL+저 $f_n$으로 안정. → 우리 A0a서 실패(물렁).
- **(B) 우리 현행 방향**(stiff Kp): Kp 150(G1 참조스케일, A0a보다 5×) — but Kd를 G1비율로 복사(6) → **ζ_link 0.16 = stiff인데 under-damped = 최악조합**(진동 성향).
- **(C) 권고(=PYG_BEYONDMIMIC 토글)**: **stiff Kp 유지 + Kd를 link-critical로**($K_d=2\sqrt{K_p I_{link}}$, $\zeta$≈1): hip 150/**37**, knee 220/**17**, hip_yaw 150/**14**. = BeyondMimic의 "critical" 정신을 **armature 대신 실제 link 관성**에 적용(BeyondMimic이 armature로 근사한 그 관성을 우리는 mass matrix로 정확히 씀).

★ 즉 우리 A/B 실험(PYG_BEYONDMIMIC)은 (C) = **"stiff Kp + 물리적 link-critical Kd"**. 순정 BeyondMimic(A, soft)이 아님. 원하면 (A)도 별도 런 가능하나, A0a서 이미 물렁으로 판명.

## 6. 왜 BeyondMimic은 armature로 충분한가 / 우리는 왜 다른가
- BeyondMimic 로봇들(G1 35kg 등)은 **가벼워** link/armature 비가 작고, **저 $f_n$·soft Kp**라 armature 근사로도 동작. 
- 우리는 **stiff Kp(150)를 택했고 51.5kg**이라 link 관성이 커서(hip 2.34) armature 근사가 크게 틀림 → **link 관성으로 Kd 계산이 필수**. (G1도 link 기준 ζ0.11 under지만 가벼워 버팀 — [G1 노트](2026-07-07_g1_gains_beyondmimic.md).)
