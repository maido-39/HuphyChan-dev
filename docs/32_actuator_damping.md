# 액추에이터 관절 댐핑(Kd) — HW 기반 검증 산정 (연구 w2pkt68gl)

> [!abstract] 한 줄
> 무릎 floppy(ζ≈0.32) 문제를 **HW 검증 Kd 범위 + g² 반사 물리**로 해결. 핵심 정정 두 가지: ① "Kd≤5"는 **소형 프레임만**(대형 RS03/04는 Kd≤100), ② 무릎은 **외부 벨트 g² 증폭**으로 직결 한계를 넘어 joint_Kd≈11 달성. 검증 데이터 표는 [[raw/robstride-datasheet]]에 있음(여기선 중복 안 하고 참조).

> 관련: [[30_knee_biomechanics]] · [[28_reward_actuator_fidelity]] · [[21_motor_power_weight]] · [[31_humanoid_hw_comparison]] · 원천 표 [[raw/robstride-datasheet]].

---

## 1. RobStride MIT-mode Kd 범위 (검증, 출력축 기준)

MIT/임피던스 토크법칙 `τ_ref = Kp·(p_set−p) + Kd·(v_set−v) + τ_ff` 의 게인 상한은 **프레임 크기별로 다름**:

| 프레임 | 모델 | Kp 범위 (N·m/rad) | Kd 범위 (N·m·s/rad) |
|---|---|---|---|
| **소형** | RS00 / RS01 / RS02 / RS05 | 0–500 | **0–5** |
| **대형** | RS03 / RS04 / RS06 | 0–5000 | **0–100** |

- 단위: 임피던스 법칙(τ in N·m, p in rad, v in rad/s)에서 직접 유도 → **Kd = N·m·s/rad = N·m/(rad/s)**. (neurobionics TMotorCANControl `set_impedance_gains_real_unit(K, B)` docstring "B: damping in Nm/(rad/s)"로 교차확인.)
- **모든 게인은 내부 기어박스 *이후* 출력축(load end) 기준** — 모터축 아님. 내부 감속비: RS00 = **10:1**, RS03/RS04 = **9:1**. MIT-mode의 p/v/τ가 모두 출력축 값이므로 Kp/Kd도 출력축 게인.
- CAN 인코딩: Kp·Kd 모두 12-bit (소형 0~4096 → 0~500 / 0~5; AK 시리즈와 동일 패킹).

> [!warning] ★ 정정 — "Kd≤5"는 소형 프레임 전용
> 이전 전제 "Kd_max ≈ 5"는 **소형 프레임에만** 해당. 우리 직결 관절 중 RS00(ankle_roll)만 상한 5. **RS04(hip_pitch/roll, knee 모터)·RS03(hip_yaw, ankle_pitch)은 대형 프레임 → 펌웨어 상한 Kd = 100**. 즉 직결 hip/knee도 5에 묶이지 않음.
> ⚠ 실기 이식 주의: RobStride 펌웨어 RS01 fw 0.1.3.4가 "operation control mode의 kp/kd 계수 오류 수정" 이력 → 현재 펌웨어로 스케일 재확인 필요. (Isaac `ImplicitActuator`는 12-bit 레지스터와 무관하게 임의 실수 Kd 수용 → 시뮬상 상한은 실질 제약 아님.)

## 2. 댐핑 반사 물리 (g² 법칙)

감속비 g(출력이 g배 느림) 전동을 통과하면 모터측 회전 임피던스가 관절측으로 **g²로 반사**됨:

```
joint_Kd = motor_Kd × (외부 전동비 g)²
```

(반사 관성 = I_rotor·g², 반사 점성댐핑 = b_motor·g² 와 동일 결과; 에너지 보존 τ_joint=g·τ_motor, ω_joint=ω_motor/g.)

**핵심 실무 nuance (Isaac Lab):**
- Isaac Lab은 `τ = Kp·(q_des−q) + Kd·(q̇_des−q̇) + τ_ff` 에서 **Kp/Kd를 joint-side(출력측)로 직접** 받음. 기어비 γ는 **토크 포화에만** 들어감: `τ_max = γ·τ_motor` — **게인에는 안 들어감**.
- 따라서 **이미 joint-side 숫자를 골랐다면 g²를 다시 곱하지 않음**. g² 공식은 *모터 데이터시트 게인을 관절 프레임으로 변환할 때*(벨트/케이블/추가 기어 관절)만 사용.
- 직결 관절은 g=1 → joint_Kd = motor_Kd (g² 곱 없음).
- **무릎은 외부 벨트가 감쇠를 g²로 증폭** → 직결 관절 한계를 쉽게 초과 가능. 이것이 무릎 회복의 핵심.

## 3. 관절별 Kd 표 (목표 ζ ≈ 0.7)

`ζ = Kd / (2·√(Kp·I_eff))`. 현재 Kd(과소감쇠 진단) → 권장 Kd:

| joint | motor | ext 비 g | I_eff (kg·m²) | Kp | 현재 Kd → ζ | **권장 Kd → ζ** | 비고 |
|---|---|---|---|---|---|---|---|
| hip_pitch | RS04(대형) | 1 (직결) | ~1.5 | 200 | 5 → 0.14 | **24 → 0.69** | I 큼 → Kd 큼, 대형 100 내 OK |
| hip_roll | RS04(대형) | 1 | ~1.5 | 200 | 5 → 0.14 | **24 → 0.69** | 동일 |
| hip_yaw | RS03(대형) | 1 | ~0.15* | 150 | 5 → 0.53 | **6.5 → 0.69** | 대형 100 내 OK |
| **knee** | RS04(대형) | **2.0–2.5 (벨트)** | ~0.3 | 200 | 5 → 0.32 | **11 → 0.71** | motor_Kd≈2.5 × 벨트² 반사 — ★핵심 |
| ankle_pitch | RS03 | 1 | ~0.05 | 80 | 3 → 0.75 | **2.8 → 0.70** (유지급) | 이미 양호 |
| ankle_roll | RS00(소형) | 1 | ~0.02* | 40 | 2 → 1.12 | **1.25 → 0.70** | 과감쇠였음 → 하향(소형 5 내) |

`*` hip_yaw·ankle_roll의 I_eff는 프롬프트 미제공 추정치 → 실제 URDF 관성으로 ζ 재계산 권장(불확실성 §6). hip/knee/ankle_pitch는 제공값 사용.

**무릎 g² 역산** (joint_Kd≈10.8 필요, Kp=200, I=0.3):
- g=2.0 → motor_Kd ≈ 2.7 · g=2.25 → ≈ 2.1 · g=2.5 → ≈ 1.7
- 즉 **motor_Kd를 2~3(소형 상한 5의 40~60%)만 써도 g² 증폭으로 무릎 ζ≈0.7 도달**. 단일 권장값 **motor_Kd≈2.5 → joint_Kd=11(ζ≈0.71)**.

**hip의 Kd=24가 큰 이유**: 유효 관성 1.5 kg·m²가 매우 크기 때문(ζ ∝ 1/√I). 물리적으로 정당하며 대형 프레임 상한(100) 내라 문제없음.

### 설정할 YAML damping

```yaml
hip_pitch_joint:   {stiffness: 200, damping: 24.0}
hip_roll_joint:    {stiffness: 200, damping: 24.0}
hip_yaw_joint:     {stiffness: 150, damping: 6.5}
knee_joint:        {stiffness: 200, damping: 11.0}   # 벨트 1:2~2.5 가정, ζ≈0.71
ankle_pitch_joint: {stiffness: 80,  damping: 2.8}
ankle_roll_joint:  {stiffness: 40,  damping: 1.25}
```

knee damping은 벨트 확정에 따라 **9.5(g=2.0)~13(g=2.5)** 범위 조정(ζ≈0.65~0.8 유지).

## 4. 무릎·hip 토크 수요 (실측, env-0 τ) → 벨트비 선정

- **knee 피크 ~150–200 N·m** → 벨트 **1:2.5(300 N·m, 1.5× 마진)** 선택 ＞ 1:2(240 N·m, 1.2× 마진뿐).
- **hip_pitch**: transient에서 RS04 한계 120 N·m **포화**하나 p95는 40 N·m뿐 → 영향 경미.
- **hip_roll**: 피크 81 N·m → 포화 없음.

> [!note] 벨트비 바꾸면 다른 파라미터도 함께 갱신 (총비 G = 9×belt)
> 현재 armature 0.0875는 1:3(G=27) 기준. 1:2~2.5로 바꾸면 **armature·effort·velocity 한계 동반 갱신 필수**:
> | belt | 총비 G | armature = 1.2e-4·G² | effort = 120×belt |
> |---|---|---|---|
> | 1:2.0 | 18 | 0.039 | 240 N·m |
> | 1:2.5 | 22.5 | 0.061 | 300 N·m |
> | (1:3.0) | 27 | 0.0875 | 360 N·m (현재) |
> armature는 rotor 반사 I_rotor·G²라 1:3→1:2면 거의 절반(과대 관성 방지). velocity 한계는 belt 작아지면 ↑. I_eff(~0.3)는 다리 링크 질량이 지배적이라 belt 영향 작으나 armature 감소분만큼 ζ 재확인 권장.

## 5. 전기 파라미터 (back-EMF) — 검증 (공식 RobStride GitHub)

| 모델 | Kt (N·m/Arms) | line R (Ω) |
|---|---|---|
| RS04 | 2.1 | 0.16 ±10% |
| RS03 | 2.36 | 0.39 ±10% |
| RS00 | 1.48 | 1.5 ±10% |

(전체 표·L·back-EMF·극수는 [[raw/robstride-datasheet]] 참조 — 중복 안 함.)

> [!warning] rotor inertia 전 모델 **미공개** → armature는 sim 추정치. per-phase R = line/2(wye).
> 위 §3 Kd는 back-EMF 물리모델(`b = Kt²/R`)이 **아니라** 임피던스(ζ) 목표 역산으로 산정. b 추정치(RS04~4465 등)는 phase/line·peak/RMS 규약 불확실로 직접 사용 안 함.

## 6. 불확실성 (정직한 한계)

1. **Kd 단위·출력축 가정**: 소형 프레임/AK는 verified. 대형(RS03/04) 상한 100도 같은 출처지만 펌웨어 스케일링 버그 이력(RS01) → 실기 적용 전 현재 펌웨어로 Kp/Kd 스케일 재확인.
2. **권선저항 R**: line만 공개·rotor inertia 미공개 → back-EMF 댐핑 `b=Kt²/R` 신뢰 불가 → Kd는 ζ 역산으로 산정.
3. **I_eff 추정**: hip_yaw(~0.15)·ankle_roll(~0.02)은 미제공 추정치 → 실제 URDF 관성으로 ζ 재계산 권장.
4. **벨트비 미확정**(2.0 vs 2.5): knee Kd 단일값 11로 두되 확정 후 g²로 미세조정.

**핵심 결론**: 무릎 floppy는 motor_Kd를 5로 올려서가 아니라 **벨트 g²(4~6.25배) 반사로 joint_Kd≈11**을 설정하면 ζ 0.32→0.71 회복. 직결 hip은 관성이 커 joint_Kd를 20대로 올려야 하며, 대형 프레임 한계(100) 내라 문제없음.

## References

검증 출처(하이퍼링크):

- [Seeed Studio — RobStride Motor Control Complete Guide](https://wiki.seeedstudio.com/robstride_control/) — MIT-mode 토크법칙, Kp/Kd 프레임별 범위·12-bit CAN 인코딩.
- [RobStride GitHub — Product_Information (RobStride Product Specification Document 20250626.pdf)](https://github.com/RobStride/Product_Information/blob/main/灵足时代产品规格介绍%20RobStride%20Product%20Specification%20Document%2020250626.pdf) — Kt·line R·L·back-EMF·감속비(공식 전기 스펙).
- [CubeMars / T-Motor — AK Series Module Driver Manual](https://www.cubemars.com/) — MIT 프로토콜 동일(Kp 0–500 / Kd 0–5, 출력축 게인) 교차확인.
- [Isaac Lab — Actuators (core concepts)](https://isaac-sim.github.io/IsaacLab/main/source/overview/core-concepts/actuators.html) — joint-side Kp/Kd PD법칙, γ는 토크 포화에만 진입.
