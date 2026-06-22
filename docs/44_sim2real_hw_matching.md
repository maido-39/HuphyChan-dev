# 44 · Sim2Real HW 매칭 가이드 — RobStride 바이펫 전용 (액추에이터 파라미터·system ID·transmission)

> [!abstract] 한 줄
> 우리 sim 액추에이터 = **IsaacLab `ImplicitActuatorCfg` 박스 모델**(평탄 effort clip + 하드 velocity clip + PD[Kp,Kd] + armature). 전기·T-N droop 모델 아님. **K-Scale K-Bot도 RobStride엔 똑같은 박스+DR을 씀** → 모델 선택은 옳다. sim2real은 ① 액추에이터 모델 충실도(가장 큰 누락 = 속도의존 T-N) → ② 관절별 system ID(PACE/ktune식: chirp/sine/step + CMA-ES로 armature·마찰·지연 식별) → ③ 잔차에 narrow DR. 가장 시급한 누락은 **friction 항(전무) · 속도의존 토크 clip · action latency(전무) · Kp/Kd가 실배포 PD와 일치하는지**. knee 벨트는 현 serial fold(effort×g, vel÷g, armature×(9g)²)가 옳음. ankle rod는 1:1이면 토크/속도 스케일 불필요, moment-arm(각도)는 **로드 구조하중 사이징·배포 J^T 후처리**에만 필요(학습 sim엔 불필요).
>
> 연구 워크플로 4차원 + adversarial verify 4건 종합. 관련: [[28_reward_actuator_fidelity]](Shin T-N clip·RobStride 스펙) · [[36_all_actuator_tn_envelopes]](T-N 봉투·rotor inertia 미공개) · [[37_ankle_linkage_fidelity]](1:1 rod 직렬링크) · [[38_parallel_ankle_sim2real]](J^T 캠프 A) · [[41_ankle_pitch_pushoff_rs03_underspec]](rod 감속 N≈1.3-1.5) · [[43_ankle_hw_decision]](발목 HW 결정) · [[16_dr_expansion]](DR).
>
> **검증 표기**: ✅ = 1차출처 직접 확인 · ◐ = 공식/표준이론(직접식별 권장) · ⚠ = 추정/placeholder(벤치 ID 필요).

---

## 1. Sim2Real 매칭 전략 개요 — 3단계

**우리 sim 모델의 정체**: `spec.py`가 yaml 각 actuator 그룹을 `ImplicitActuatorCfg`로 빌드 — `effort_limit_sim`(평탄 토크 clip), `velocity_limit_sim`(하드 속도 clip = rpm×2π/60), `stiffness`(Kp), `damping`(PD의 D게인 Kd), `armature`(반사 rotor 관성). **이게 전부.** 전압포락·field-weakening·전류루프 시상수·마찰 — 전부 없음.

### 단계 (A) — 액추에이터 모델 충실도부터
박스 모델의 두 핵심 결함(우리 내부 노트에 이미 기록):
1. **평탄 effort clip이 모든 속도서 peak 토크를 credit**. 실제 RobStride T-N은 전압제한 → 저속 평탄 corner 이후 단조감소([[36_all_actuator_tn_envelopes]]: RS04는 95rpm서 이미 peak, 190rpm서 ~10 N·m). Shin/KAIST-Hound 실험: 평탄 clip을 **속도의존 per-motor MOR clip** `-Vbus ≤ (R/Kt)τ + (1/Kv)ω ≤ Vbus`로 교체 → **+2.0 m/s** sim2real 이득(단일 최대 기여, ablation 6.5→4.5 m/s) ✅. ➡ **이게 우리 박스 모델의 #1 충실도 레버**([[28_reward_actuator_fidelity]] §2 = 동일 계획).
2. **knee 벨트·ankle rod transmission이 명시 모델링 안 됨**(§4).

> [!warning] 우리 목표 = "하중 측정"이라 더 치명적
> 프로젝트 목적이 RL로 동작을 만들어 **HW 설계 하중을 측정**하는 것이므로, 박스가 고속서 토크를 과대 credit하면 측정 하중이 낙관적으로 왜곡. 학습 robustness엔 박스+DR로 충분하나, **측정-grade 하중엔 속도의존 clip(또는 측정 후처리에서 [[36_all_actuator_tn_envelopes]] T-N 곡선으로 down-rate) 필수**.

### 단계 (B) — System Identification (관절별)
두 표준 레시피(둘 다 chirp/sine/step 가진 + 최적화 fit, 단 출처·세부 다름):
- **PACE** (ETH Zürich RSL, ★주 플랫폼은 ANYmal *quadruped* — "canonical RobStride method"는 과장, RobStride 휴머노이드 전용이 아님) ✅. 관절별 폐루프 모델 Eq.6: `I_a·q̈ + d·q̇ = sat(P_τ(q̂−q+q_bias) − D_τ·q̇ + τ_comp) + τ_f`. 식별 벡터 **p=[I_a(armature), d(점성), τ_f(쿨롱), q_bias] 관절별 + 전역 지연 T_d** ∈ ℝ^(4n+1). PD 게인은 비식별(non-uniqueness). 여기파 = 멀티관절 **chirp 0.1→10 Hz**, CMA-ES로 **시간평균 위치 MSE** `(1/k)Σ‖q_real−q_sim‖²` 최소화. ★ PACE는 **dynamics randomization 거부**("end-to-end로 식별하므로 DR 안 씀") — 단 task/terrain/push/ground-friction DR은 여전히 함.
- **K-Bot / ktune** (kscalelabs — RobStride 휴머노이드 *진짜* 사례) ✅. ktune = HW와 sim에 **동일 sine/step/chirp + pendulum** 궤적 구동, compare 모드. ★정정: ktune 자체는 자동 fit 아님 — 데이터 로깅+플롯 후 **사용자 수동 튜닝**(또는 Rhoban식 CMA-ES/Optuna 래핑). K-Bot ksim 파이프라인은 CMA-ES로 관절별 stiffness·damping·armature·static/viscous friction 식별, ★목적함수는 **스펙트럴(DFT) MSE**(위치+속도) — *시간평균 위치 MSE가 아님*(그건 PACE). 정책 50Hz / physics 100Hz.

**우리 권장 절충**(DeXtreme식 "DR 유지" vs PACE "DR 거부" 사이): **측정 가능한 건 tight ID**(질량/관성=CAD, 기어비=정확, armature+마찰=벤치) **+ 불확실한 잔차에만 narrow DR**. "PACE가 DR 거부"를 "DR 다 끄기"로 읽지 말 것 — terrain/push/contact-friction DR은 유지.

### 단계 (C) — 잔차 DR
ksim이 박스 모델로 sim2real을 얻는 방식 = `kp_scale, kd_scale, torque_limit_scale, torque_noise, torque_bias` 관절별 randomize (출처: **`ksim/actuators.py`의 `PositionActuators`** — verifier 정정, randomization.py 아님) ✅. IsaacLab에선 EventCfg로 stiffness·damping·effort_limit randomize + 토크 노이즈/바이어스.

```
sim2real 충실도 순서 (우리 박스 모델 기준, 레버 큰 순):
  ① 속도의존 T-N clip (현 평탄 clip → DCMotorCfg/MOR)   ← #1, 가장 큼
  ② action latency 버퍼 + DR                            ← 현재 0 (전무), 둘째 레버
  ③ Kp/Kd가 실배포 onboard PD와 일치 + 제어레이트(50Hz) 일치
  ④ 관절 friction (static/Coulomb/viscous) ID + DR     ← 현재 전무
  ⑤ armature 벤치 ID (rotor inertia 미공개)
  ⑥ backlash deadband (rod/belt) DR
```

---

## 2. 맞춰야 할 파라미터 전체 목록

> "damping/armature/frictionloss 외에 뭘 맞추나"의 답. 핵심 누락은 **friction 3항(전무) · 속도의존 토크 · latency(전무)**.

| # | 파라미터 | 의미 | 우리 config 위치 | 측정/공식 | 상태 |
|---|---|---|---|---|---|
| 1 | **Kp (stiffness)** | PD P게인 (PhysX) | yaml `stiffness`→`ImplicitActuatorCfg.stiffness` | 실배포 onboard 위치루프 Kp와 **동일 값** 필수. 미지 시 `Kp=I·ωₙ²` | ⚠ 현 값(200/150/200/80/40)은 ZETA~0.7 추정, 실측 PD 아님 |
| 2 | **Kd (damping)** | PD D게인 (PhysX) — **점성마찰 아님** | yaml `damping`→`.damping` | 실배포 속도루프 Kd. `Kd=2·I·ωₙ`(임계). ⚠ #5 점성마찰과 **이중계상 금지** | ◐ HW-grounded ZETA~0.7 |
| 3 | **effort_limit (peak τ)** | 평탄 토크 clip | yaml `effort_limit`→`effort_limit_sim` (implicit은 `_sim`만 유효) | 벤치 peak=Kt·I_peak. RS00 14·RS03 60·RS04 120 | ✅ 데이터시트 일치([[36_all_actuator_tn_envelopes]]) |
| 4 | **velocity_limit (속도)** | 하드 속도 clip | yaml `velocity_limit_rpm`×RPM2RAD→`velocity_limit_sim` | 무부하 rpm. ⚠ **평탄 clip이 고속 토크 과대 credit** — MOR로 교체 권장 | ✅ 무부하 ceiling 일치 / ◐ T-N droop 미반영 |
| 5 | **friction (static/Coulomb/viscous)** | τ_f = τ_static·sgn + τ_c·sgn(ω) + b·ω | **현재 전무**. IsaacLab actuator의 `friction`/`dynamic_friction`/`viscous_friction` 필드를 spec.py에서 설정 | 무부하 전류 sweep: τ=Kt·I, fit τ=Kc·sgn(ω)+Kv·ω → 절편=Coulomb, 기울기=viscous(b). 또는 free-swing 감쇠(점성=지수, Coulomb=선형) | ⚠ **벤치 ID 필요** (가장 큰 누락) |
| 6 | **armature (반사 rotor 관성)** | joint-space 관성에 직접 가산 | yaml `armature`→`.armature` | `I_a = I_rotor·(N_int·N_ext)²`. knee=`1.2e-4·(9g)²` | ⚠ rotor inertia **미공개**([[36_all_actuator_tn_envelopes]]) → 추정값, 벤치/free-swing ID |
| 7 | **joint limits (range/eff/vel)** | ROM·토크·속도 한계 | MJCF `<joint range>` + actuatorfrcrange | CAD ROM·데이터시트 | ✅ MJCF에 존재 |
| 8 | **link mass/inertia/COM** | 링크 동역학 | MJCF `<inertial>` (`import_inertia_tensor:true`로 권위) + yaml `physics.overrides` | CAD(Fusion) 관성텐서+COM 추출, 저울 검증(총 51.8kg) | ◐ CAD 기반(신뢰 tier) |
| 9 | **contact friction/restitution** | 발-지면 마찰 | PhysX material(USD prim) + env DR | tilt test, DR randomize | ◐ env DR 존재(static 0.30-1.25) |
| 10 | **control delay / latency** | 명령→엔코더 지연 | **현재 전무** — env action/obs delay 버퍼 (actuator 필드 아님) | 벤치 명령→엔코더 lag. PACE 전역 T_d. Booster 0-20ms, BRUCE 0-40ms | ⚠ **완전 누락**(grep 0건) — 둘째 레버 |
| 11 | **actuator 시상수** | 전류루프 1차 지연 | implicit PD엔 없음(즉시) | step 응답 rise time. 느리면 latency로 흡수 | ◐ latency로 처리 |
| 12 | **backlash/compliance** | 벨트·rod 유격·탄성 | ImplicitActuator에 직접 없음 → DR deadband + Kp 감산 | backlash: 출력 엔코더 히스테리시스(~0.5-2°). compliance: Kp 낮춤+시리즈 스프링 | ⚠ DR 필요(rod/belt) |

> [!note] ImplicitActuator 특화 함정 (verifier 강조)
> - **이중계상**: yaml `damping`(Kd)이 현재 제어 댐핑 + 물리 손실을 *둘 다* 대신함. #5 viscous_friction(b)을 벤치로 추가하면 **Kd를 순수 제어 D게인(=2·I·ωₙ)으로 재유도** — 안 그러면 over-damped.
> - **MJCF passthrough 불신**: MJCF `<joint frictionloss/damping>`이 MJCF→USD→PhysX에서 살아남는지 **버전 의존·미검증**(importer가 drive target 있으면 zero化 가능). ★ 우리 파이프라인에선 **yaml/spec.py가 권위** — MJCF knee armature(0.0875) vs yaml(0.0097), MJCF toe(0.0005) vs yaml(0.008)이 **불일치하나 yaml이 이김**, MJCF actuatorfrcrange(knee ±360)도 inert. ➡ friction은 MJCF 의존 말고 **spec.py에서 actuator 필드 직접 설정**.
> - **제어레이트도 맞춰야**: 게인 값만이 아니라 decimation/50Hz 루프 + T_d 지연도 sim=real 일치 필요.

---

## 3. Actuator ID — 오픈소스 RobStride 휴머노이드 비교

### 그들이 쓰는 방법
| 그룹 | 모델 | 방법 | 우리와의 관계 |
|---|---|---|---|
| **K-Scale K-Bot** (RS00/02/03/04로 만든 *유일한* 주류 오픈 휴머노이드) | **박스(PD+평탄 clip)** | `kinfer_sim/actuators.py`의 `PositionActuator`(prefix "robstride") = `τ=Kp(tgt−q)+Kd(−q̇)+ff`, clip(±max_torque). 전기/duty 모델은 **Feetech 싸구려 서보 전용**(RobStride 아님) ✅ | ★ **우리 박스 선택을 검증** — T-N/전기모델로 안 바꿔도 됨 |
| **ktune** | real2sim 비교 | sine/step/chirp/pendulum HW↔sim compare, Rhoban 모델 크레딧 | 우리 ID 레시피 |
| **Rhoban** (arXiv 2410.08650) | 확장 마찰 M4 | `τf=Kv·θ̇+Kc+Kl·|τm−τe|+exp(−|θ̇/θ̇s|^α)(Kc^s+Kl^s·|τm−τe|)` = 점성+쿨롱+**부하의존**+Stribeck stiction. pendulum CMA-ES, MAE 1.5-2.9× 개선 ✅ | "damping/armature/frictionloss 외" = **부하의존+Stribeck 추가** |
| Hwangbo actuator-net (ANYmal) | NN 토크예측 | SEA 대상, QDD엔 과잉 | ★ RobStride 생태계 **아무도 안 씀** |
| K-Scale UAN (arXiv 2502.10894) | Unsupervised Actuator Net | 실데이터에서 토크센서 없이 학습 + PD/stall/lag DR | 박스 전이 부족 시 **업그레이드 경로** |

### 공개 RobStride 데이터시트 vs 우리 yaml ✅ (교차검증 [[36_all_actuator_tn_envelopes]])
| 모터 | 데이터시트 peak/무부하 | 기어 | Kt / R | 우리 yaml | 판정 |
|---|---|---|---|---|---|
| **RS04** | 120 N·m / 200 rpm | 9:1 | 2.1 / 0.16Ω | hip 120/200, knee 120/200(g=1) | ✅ **정확 일치** |
| **RS03** | 60 N·m / 무부하 195-200, **정격 100** | 9:1 | 2.36 / 0.39Ω | hip_yaw·ankle_pitch 60/200 | ✅ ceiling 일치 (무부하 200 vs 195는 ±10% 내) |
| **RS00** | 14 N·m / 315 rpm, **정격 100** | 10:1 | **1.48 / 1.5Ω** | ankle_roll 14/315 | ✅ **정확 일치** (Kt=1.48 — ankle_roll ID에 필요) |

> [!warning] "불일치 없음"의 함정
> effort/velocity ceiling은 데이터시트와 일치하나, 그건 **무부하(낙관) 끝**이다. **정격부하 속도는 훨씬 낮음**(RS04 167, RS03 ~100, RS00 100) — 박스가 **고속 토크를 과대 credit**하는 게 우리의 알려진 측정 fidelity gap([[36_all_actuator_tn_envelopes]]·[[28_reward_actuator_fidelity]]). 게다가 **세 모터 전부 전압제한 droop** → 단순 "peak×max속도 박스"는 고속서 틀림. ⚠ 우리 Kp/Kd가 K-Scale 펌웨어 register 게인보다 높은 건 정상(우리는 IsaacLab 물리 PD 게인, 그들은 펌웨어 register — 직접 비교 불가).

**ID 레시피(우리 적용)**: 각 RobStride 관절을 sine+step+chirp+pendulum로 구동 → 위상전류×Kt=토크 측정(RS00 1.48 / RS03 2.36 / RS04 2.1 N·m/Arms) → CMA-ES(또는 수동)로 Kp,Kd,frictionloss,armature를 sim-vs-real 궤적오차 최소화로 fit.

---

## 4. Transmission 모델링 — knee 벨트 + ankle rod

### 판정 요약
| 관절 | 실 HW | 우리 sim | "direct+scaled" 유효성 |
|---|---|---|---|
| **knee** | RS04 + **벨트** 감속 g | 직결 hinge + effort×g/vel÷g/armature×(9g)² | ✅ **벨트=고정비라 serial fold가 교과서적 정확** (강체 이상화) |
| **ankle_pitch** | RS03 + **rod/4절**(Agibot-X2식, 1:1) | 직결 hinge (N=1) | ◐ **모터 토크/속도 사이징엔 유효**(1:1) / ❌ rod 구조하중 사이징엔 moment-arm(각도) 필요 |

### (1) serial fold vs 명시 closed-loop
**고정비 감속(기어든 벨트든)의 업계 표준 = serial fold**: 출력 관절에서 학습, 비 g를 `effort_limit=g·τ_motor`, `velocity=ω_motor/g`, **`armature=I_rotor·(N_int·N_ext)²`**로 접음. IsaacLab 공식 문서가 `τ_j,max=γ·τ_motor,max` + "armature는 joint-space 관성에 직접 가산" 명시 ✅.

★ **우리 knee가 이미 정확히 이걸 함**: `armature=1.2e-4·(9g)²` — **9=RS04 내부 9:1, g=외부 벨트비, 총 반사비=(9g)²**(verifier: 내부 9를 빠뜨리고 g²만 쓰면 틀림 — 반드시 **총비 (9g)²**). 현재 g=1.0(직결, 벨트 미체결)이나 g-스케일 기계는 벨트비 선택 시 작동.

**명시 closed-loop**(MuJoCo equality constraint)은 (a) 비가 비상수(rod/4절), (b) ROM 내 특이점, (c) 모터공간 에너지 정확 필요, (d) 커플된 수동 DOF일 때만 필요. BRUCE는 closed-chain이 +3.4%/step뿐이나 상수비 벨트엔 불필요 ✅.

### (2) 정책이 보는 공간 + J^T (캠프 A 권장)
**정책은 joint-space(pitch/roll hinge)만 관측/출력**, joint↔actuator 변환은 **배포 SDK**가 처리(학습 sim 아님). Booster Gym/T1: "virtual series joints … transposed Jacobian + PD로 변환"(온보드) ✅. Unitree G1 PR-mode 동일. 우리 IsaacLab 발목 정책은 그대로 두고 **J^T는 배포·하중측정 후처리 단계**로 분리([[38_parallel_ankle_sim2real]] 캠프 A). 캠프 B(정책=모터공간+학습 sim closed-chain, BRUCE/G1 AB)는 충실도 최고이나 단일 DOF rod·벨트엔 과잉.

### (3) 벨트 특이사항
벨트는 운동학적 고정비(fold 정확)이나 강체 반사관성이 못 잡는 둘:
- **compliance**(시리즈 탄성) → Kp 낮춤+randomize, 또는 시리즈 스프링.
- **backlash**(치/장력 유격) → 위치 deadband(Walk-These-Ways: 정책이 overshoot 학습) ✅.
둘 다 **explicit 기하 아닌 DR로 처리**. 효율손실 ~5-10% → knee frictionloss 추가 + effort 약간 down. 반사관성에 출력 풀리 관성 비-trivial이면 `armature=(1.2e-4+I_pulley)·(9g)²`.

### (4) rod 특이사항 — 각도의존 moment-arm
4절/rod는 **비상수 전달비** — moment arm r_a(θ)가 ROM 따라 변함. 처리:
- **(i) 작동점 선형화**: 중립서 상수비 사용. 1:1·중간 ROM서 유효(우리: [[37_ankle_linkage_fidelity]]·[[41_ankle_pitch_pushoff_rs03_underspec]]가 90° ROM서 ±10-15% = 모터 사이징 마진 내).
- **(ii) 풀 기하**: r_a(θ) 다항 fit (BRUCE식). **rod-FORCE/rod-end 하중 한계**(push-off=최대토크 AND 최대 plantarflex=r_a 최악) + ROM 도달성/특이점 확인에 **필수**.

> [!important] ★ position 정책엔 r_a(θ)가 학습 sim에 불필요 — 이게 핵심 nuance
> 우리 정책은 joint-space position 정책 + 직결 hinge → **정책은 rod를 결코 안 봄**(ankle_pitch hinge만). 1:1(근상수비)이면 직결 fold가 **정책 전이엔 충분**. r_a(θ)는 오직 **HW 설계 후처리** 2가지에만: ① rod 힘 `F_rod=τ_pitch/r_a(θ)`를 push-off(ROM끝)서 사이징([[37_ankle_linkage_fidelity]] ÷레버암), ② ROM 도달성·특이점 체크. **둘 다 yaml 변경 아님.**
>
> ⚠ **단, hinge의 기어비 = 배포 rod 비와 같아야** T-N이 전이됨. 현 ankle_pitch는 N=1(60/200). [[41_ankle_pitch_pushoff_rs03_underspec]]가 push-off **under-spec** 판정(약한 gait서 이미 −60 클립) → **rod 감속 N≈1.3-1.5 채택 시 yaml을 effort×N, vel÷N, armature×N²로 함께 갱신 + ZETA~0.7 유지 위해 Kd/Kp 재튜닝 + T-N 봉투 재검증**(verifier: N 재fold 후 ZETA 재확인 누락 주의).

---

## 5. Joint 파라미터 생성 파이프라인 (단일 관절 = 4 소스 ~19 파라미터)

```
(1) CAD ─────────────► (2) 데이터시트 ───► (3) 벤치 ──────────► (4) 검증→DR
    질량/관성/COM          peak τ, 무부하         friction, Kp/Kd        step·free-swing
    + transmission 비       반사 armature         지연, 실 T-N           → DR 범위
        │                       │                     │                      │
        ▼                       ▼                     ▼                      ▼
   MJCF <inertial>/<joint>   yaml effort/vel/      spec.py actuator       env EventCfg
   yaml import_inertia       armature             friction 필드 + Kp/Kd   DR scales + latency
```

**(1) CAD → 관성+운동학+비.** Fusion→URDF/MJCF, SI 단위, rad. 링크별 `<inertial mass/diaginertia/quat>`, `<joint axis/range>`. 우리 `import_inertia_tensor:true`가 MJCF `<inertial>`을 권위로 사용 ✅. 비 N = CAD 레버암(knee 풀리 치비 / ankle r_a/r_m) → **N은 명시 sim 필드 아님**, effort×N·vel÷N·armature×N²로 수동 적용.

**(2) 데이터시트 → 반사 armature.** effort_limit=peak(×N_ext), velocity=무부하(÷N_ext), `armature=I_rotor·(N_int·N_ext)²`. ⚠ **J_rotor 전 모델 미공개**([[36_all_actuator_tn_envelopes]] §3) → 현 armature(0.0097/0.0049/0.0015)는 **추정** → 벤치 ID.

**(3) 벤치 = 추정→실측 전환.**
- **friction**: 무부하 정속 전류 sweep, τ=Kt·I, fit τ=Kc·sgn(ω)+Kv·ω → 절편 Kc(Coulomb)→`dynamic_friction`, 기울기 Kv(viscous,b)→`viscous_friction` (IsaacLab Disc #3456: ★`damping`은 PD게인이지 viscous 아님) ✅. 선택: Stribeck/부하의존(Rhoban M4).
- **backlash**: 저속 ± 명령, 출력엔코더 히스테리시스(~0.5-2°)→DR deadband.
- **Kp/Kd**: 배포 PD 게인을 yaml에 **그대로 복사**(sim-real PD 일치 필수). peer: Booster T1 Hip/Knee Kp200/Kd5, Ankle Kp50/Kd1, decimation 10=50Hz ✅. ⚠ 우리 ankle Kd=3 vs Booster Kd=1 — 실 controller와 다르면 전이 위험.
- **latency**: step 위상지연→action delay 버퍼+DR(현재 0).
- **실 T-N**: 로드셀 토크 vs ω → 전압제한 봉투 확인(박스 미반영).

**(4) 검증+DR.** step 응답(rise/overshoot/steady-error) sim↔real → Kp/Kd/armature/friction 보정. free-swing(중력 pendulum, 모터 off) 감쇠율 → viscous+armature 검증. DR 범위 = 잔차+공차. Booster 공개값: Kp/Kd×[0.95,1.05], base_mass×[0.8,1.2], geom friction additive[0.1,2], push 0-10N ✅. 우리 추가([[16_dr_expansion]]·[[38_parallel_ankle_sim2real]]): transmission/레버암 ±5-10%, backlash deadband, **action latency(현 0), Kp/Kd randomize(현 0), joint-friction randomize(현 0)** — 셋 다 우리 env에 grep 0건.

> [!note] 대안 업그레이드 — DCMotorCfg (IsaacLab 네이티브 T-N)
> 평탄 박스를 **`DCMotorCfg`**로 교체하면 코드만으로(IsaacLab 수정 X, maintainer 권장 #2666) 4-quadrant T-N 직선 획득 ✅:
> `max_effort = clip(saturation_effort·(1 − ω/velocity_limit), ..., effort_limit)`, 음의 분기 대칭(ω>vel서 음토크=제동 quadrant — "0 floor 아님"). 매핑: **saturation_effort=peak(120/60/14), effort_limit=연속(40/20/5), velocity_limit=무부하(200/200/315rpm)**.
> ⚠ effort_limit 의미가 바뀜(peak→연속=훨씬 tight steady clip) → 학습 거동 변화 → **재학습 필수**(hot-swap 금지). 단 stall→무부하 직선도 corner 이후 droop을 과대 credit([[36_all_actuator_tn_envelopes]] RS04 95rpm corner) → DCMotor도 근사, MOR보다 거침. 열/연속 한계는 여전히 reward 후처리([[28_reward_actuator_fidelity]] T1/T2)로.

---

## 6. ★ 우선순위 action 체크리스트 (우리 프로젝트 당장)

**측정/벤치 (HW 확보 후):**
1. ☐ **RobStride rotor inertia 벤치 ID** (free-swing 감쇠 fit) — armature 전 그룹이 추정값, ZETA·고주파 안정성 직결. [[36_all_actuator_tn_envelopes]] 미해결 항.
2. ☐ **friction 3항 ID** — 무부하 전류 sweep(τ=Kt·I, Kt: RS00 1.48/RS03 2.36/RS04 2.1) + free-swing → Coulomb·viscous·(선택)Stribeck. **현재 전무**.
3. ☐ **실 Kp/Kd 측정** — 배포 onboard PD 게인 확인, yaml과 일치시킴(현 값은 ZETA~0.7 추정). + 제어레이트 50Hz·decimation 일치.
4. ☐ **command→encoder latency 측정** — action delay 버퍼 값 확보.
5. ☐ **링크별 질량/COM 저울 검증** — CAD 관성텐서 재추출 vs MJCF `<inertial>`(권위).
6. ☐ **CAD에서 ankle rod r_a(θ) + knee 풀리비** 추출 — rod-force 사이징·기어비 확정.

**코드/config 수정 (레버 큰 순):**
7. ☐ **속도의존 T-N clip** (#1 레버): 평탄 effort_limit → `DCMotorCfg`(config만) 또는 Shin MOR custom actuator. 측정-grade 하중에 필수. [[28_reward_actuator_fidelity]] §2.
8. ☐ **action latency 버퍼 + DR** 추가 (현 0, 둘째 레버) — Booster 0-20ms.
9. ☐ **spec.py에 friction 필드 추가** (MJCF passthrough 말고 actuator 직접) + Kd를 순수 D게인으로 재유도(이중계상 방지).
10. ☐ **DR 확장**: Kp/Kd×[0.95,1.05]·joint-friction additive·transmission ±5-10%·backlash deadband (현 모두 0). [[16_dr_expansion]].
11. ☐ **ankle_pitch rod 감속 N≈1.3-1.5** 채택 시: effort×N·vel÷N·armature×N²·Kd/Kp 재튜닝·T-N 재검증. [[41_ankle_pitch_pushoff_rs03_underspec]]·[[43_ankle_hw_decision]].
12. ☐ (선택) RS03 두 그룹 velocity 200→195 데이터시트 정밀화 (±10% 내, 저우선).

**구조 우선 (param ID보다 먼저):**
13. ☐ **ankle_roll RS00 포화는 param ID로 못 고침** — 100% peak-clip·RMS~280%([[36_all_actuator_tn_envelopes]]·[[43_ankle_hw_decision]]). 모터 upsize(DM-J4340) 또는 발폭↑ 결정이 fine sysid보다 **선행**. 바인딩 액추에이터는 충실도로 구제 불가.

---

## 7. 출처 (하이퍼링크)

**액추에이터 모델·system ID:**
- [PACE (arXiv 2509.06342)](https://arxiv.org/html/2509.06342v1) — Eq.6 관절모델, [I_a,d,τ_f,q_bias]+전역지연, chirp, CMA-ES, DR 거부. ✅ (ETH/ANYmal — RobStride 전용 아님)
- [PACE code (leggedrobotics/pace-sim2real)](https://github.com/leggedrobotics/pace-sim2real) — chirp_data, CMA-ES ✅
- [K-Bot ksim (kscalelabs/ksim)](https://github.com/kscalelabs/ksim) + [kinfer-sim actuators](https://github.com/kscalelabs/kinfer-sim/blob/master/kinfer_sim/actuators.py) — RobStride=PD+clip 박스, Feetech=전기모델; DR scale은 `ksim/actuators.py` ✅
- [ktune (kscalelabs/ktune)](https://github.com/kscalelabs/ktune) — sine/step/chirp/pendulum compare ✅
- [Rhoban 확장마찰 (arXiv 2410.08650)](https://arxiv.org/html/2410.08650v1) — M4 Coulomb+viscous+부하의존+Stribeck, pendulum CMA-ES ✅
- [K-Scale UAN (arXiv 2502.10894)](https://arxiv.org/abs/2502.10894) — Unsupervised Actuator Net, 박스 업그레이드 경로 ✅
- [Shin/KAIST Hound (arXiv 2312.17507)](https://arxiv.org/abs/2312.17507) — 속도의존 MOR clip, +2.0 m/s ✅

**IsaacLab:**
- [Actuators API](https://isaac-sim.github.io/IsaacLab/main/source/api/lab/isaaclab.actuators.html) — ImplicitActuatorCfg/DCMotorCfg 필드, armature 가산, effort_limit==_sim ✅
- [Actuator core-concepts](https://isaac-sim.github.io/IsaacLab/main/source/overview/core-concepts/actuators.html) — τ_j,max=γ·τ_motor,max, serial fold ✅
- [Disc #3456](https://github.com/isaac-sim/IsaacLab/discussions/3456) — 무부하 friction ID(절편=Coulomb, 기울기=viscous), damping≠viscous ✅
- [Disc #2666](https://github.com/isaac-sim/IsaacLab/discussions/2666) — DCMotorCfg 권장 ✅

**transmission·기타:**
- [K-Bot mechanical](https://docs.kscale.dev/robots/k-bot/mechanical/) — RS00 10:1·RS02 7.75:1·RS03 9:1·RS04 9:1 ✅
- [BRUCE (arXiv 2507.00273)](https://arxiv.org/html/2507.00273v2) — closed-chain, 비상수비 ρ₄, 다항 moment-arm, 모터공간 액션 ✅
- [Booster Gym/T1 (arXiv 2506.15132)](https://arxiv.org/abs/2506.15132) + [code](https://github.com/BoosterRobotics/booster_gym) — virtual serial + J^T 배포, Kp/Kd·DR 범위 ✅
- [Walk These Ways (arXiv 2212.03238)](https://arxiv.org/pdf/2212.03238) — backlash deadband ✅
- [RobStride 데이터시트 (OpenELAB RS04)](https://openelab.io/blogs/learn/robstride04-qdd-120n-m-integrated-joint-bldc-gear-motor-complete-guide) · [RS03](https://openelab.io/products/robstride03-qdd-60n-m-integrated-joint-motor-module) · [Seeed wiki](https://wiki.seeedstudio.com/robstride_control/) ✅
- ROBOTIS-OP3 sim2real(기어 휴머노이드, 반사관성 fold) [arXiv 2204.03897](https://arxiv.org/pdf/2204.03897) ✅
- 내부: [[28_reward_actuator_fidelity]] · [[36_all_actuator_tn_envelopes]] · [[37_ankle_linkage_fidelity]] · [[38_parallel_ankle_sim2real]] · [[41_ankle_pitch_pushoff_rs03_underspec]] · [[43_ankle_hw_decision]] · [[16_dr_expansion]]
