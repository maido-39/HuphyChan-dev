# 44 · 관절 파라미터 생성 파이프라인 (CAD→데이터시트→벤치→검증) — sim2real-faithful joint model

> [!question] 질문 (사용자 2026-06-22, Q5)
> sim2real-faithful 관절 모델에 필요한 **파라미터 전집합**과 각 값을 **우리 로봇에 맞춰 만드는 단계별 워크플로**는? (1) CAD→링크 질량/COM/관성·관절축/범위·전달비/레버암 (2) 데이터시트(RobStride)→Kt·peak/cont 토크·무부하속도·rotor inertia·내부감속비→reflected armature (3) 벤치→Coulomb+viscous 마찰·백래시·저수준 Kp/Kd·지연·실제 T-N (4) 검증→sim vs real step/free-swing 비교 후 DR 범위 설정. 각 단계를 robstride_biped.yaml / MJCF / ImplicitActuatorCfg의 **어디**에 매핑.

> [!abstract] 한 줄
> 관절 1개의 sim2real 모델 = **{링크 관성(CAD) + 전달비/armature(데이터시트×감속비²) + 마찰3종/지연/백래시(벤치) + DR 범위(검증 잔차)}**. 우리 박스모델(ImplicitActuatorCfg)에 **빠진 핵심 = (a) 속도의존 T-N**(→DCMotorCfg `saturation_effort`로 업그레이드, IsaacLab 메인테이너도 권장) (b) **마찰 3종**(frictionloss/damping은 MJCF에 있으나 미식별 추정값) (c) **지연·백래시**(DR로만). [[36]] T-N·[[28]] 충실도·[[37/38]] 전달 연구의 *생성 절차* 통합본.

---

## 0. 관절 1개에 필요한 파라미터 전집합 (체크리스트)

| # | 파라미터 | 단위 | 출처 | sim 위치 | 현재 상태 |
|---|---|---|---|---|---|
| 1 | 링크 질량 | kg | CAD | MJCF `<inertial mass>` | ✅ CAD |
| 2 | COM 위치 | m | CAD | MJCF `<inertial pos>` | ✅ CAD |
| 3 | 관성텐서(대각+quat) | kg·m² | CAD | MJCF `<inertial diaginertia quat>` | ✅ CAD |
| 4 | 관절축 | unit vec | CAD | MJCF `<joint axis>` | ✅ CAD |
| 5 | 관절 ROM | rad | CAD/링크기하 | MJCF `<joint range>` | ✅ (링크 가용범위 검증 필요 [[37]]) |
| 6 | 외부 전달비 N | — | CAD(레버암 r_a/r_m) 또는 벨트 풀리비 | yaml effort×N·vel÷N / armature×N² | ⚠ knee=벨트(스케일근사), ankle_pitch=링크(1:1 가정) |
| 7 | peak 토크 | N·m | 데이터시트 | yaml `effort_limit` | ✅ [[36]] |
| 8 | 연속(thermal) 토크 | N·m | 데이터시트 듀티표 | (sim 미반영 → reward T1/T2 [[28]]) | ⚠ reward로만 |
| 9 | 무부하 속도 | rpm | 데이터시트 | yaml `velocity_limit_rpm` | ✅ [[36]] |
| 10 | T-N corner/곡선 | — | 데이터시트 | (박스모델 미반영 → DCMotorCfg) | ❌ **핵심 gap** |
| 11 | Kt 토크상수 | N·m/Arms | 데이터시트 | (Joule reward만) | ✅ 측정값 [[28]] |
| 12 | rotor inertia J_r | kg·m² | 데이터시트(미공개!) | armature = J_r·(N_int·N_ext)² | ⚠ 추정 [[36]] |
| 13 | 내부 감속비 | — | 데이터시트(RS00=10, RS03/04=9) | armature 계산에 | ✅ [[28]] |
| 14 | armature(reflected) | kg·m² | #12×#13²×#6² | MJCF `<joint armature>` + yaml `armature` | ⚠ 추정(벤치 식별 권장) |
| 15 | Coulomb 마찰 Kc | N·m | 벤치(무부하 전류 절편) | MJCF `frictionloss` | ⚠ 추정 0.1~0.3 |
| 16 | viscous 마찰 Kv | N·m·s/rad | 벤치(무부하 전류 기울기) | MJCF `damping` | ⚠ 추정(ζ로 역산) |
| 17 | 저수준 Kp/Kd | N·m/rad, N·m·s/rad | 실로봇 컨트롤러 | yaml `stiffness`/`damping` | ⚠ HW-grounded(ζ~0.7) 추정 |
| 18 | 제어 지연 | s | 벤치(step 위상지연) | env action delay + DR | DR로 |
| 19 | 백래시 | rad | 벤치(위치 히스테리시스) | (DR deadband) | DR로 [[38]] |

→ ✅ CAD 1차계열(1–5,13) 확정 · ⚠ 데이터시트 추정(12,14) · ❌ 벤치 미식별(15,16,18,19) · ❌ T-N 박스근사(10).

---

## 1. CAD 단계 — 링크 관성·관절·전달

**Export**: Fusion 360 → URDF/MJCF exporter 또는 STEP→onshape-to-robot. **단위 = SI(kg, m); MuJoCo `<compiler angle="radian">`**. **프레임 = 각 링크 좌표계의 `<inertial>`**(MuJoCo는 부모상대 body frame; quat로 주축회전 표현 — 우리 MJCF가 이 형식 사용 확인).
- **import_inertia_tensor: true** (yaml convert) → MJCF `<inertial>` 그대로 사용. ✅ 이미 설정.
- **전달비/레버암**: CAD에서 모터측 레버암 r_m·발측 r_a 측정 → N=r_a/r_m([[37/41]]). knee는 풀리 잇수비. **★ sim엔 N이 명시 안 됨** — effort×N·vel÷N·armature×N²로 *수동 반영*(knee_rs04_sweep 주석이 정확히 이 패턴).

## 2. 데이터시트 단계 — 모터→reflected armature

RobStride 공식 PDF([[36]] 교차검증): RS00 5/14·315rpm·10:1·Kt1.48 / RS03 20/60·200·9:1·Kt2.36 / RS04 40/120·200·9:1·Kt2.1.
- **effort_limit = peak 토크**(직결) 또는 ×N_ext(외부감속). **velocity_limit_rpm = 무부하**(÷N_ext).
- **★ reflected armature = J_rotor × (N_internal × N_external)²** (검증식: 임의 기어가 부하관성을 비²로 모터축에 반영; MuJoCo armature = 관절공간 관성행렬에 더하는 σI). 우리 knee 주석 `1.2e-4×(9g)²` = **이 공식 그대로**(J_rotor 1.2e-4 × (내부9 × 외부g)²). ⚠ **J_rotor가 전 RobStride 미공개**([[36]] §3) → armature는 *추정* → **벤치 식별 권장**.

## 3. 벤치 단계 — 마찰·백래시·Kp/Kd·지연·실 T-N

★ **여기가 추정→실측 전환점.** 우리 ⚠/❌ 항목 대부분이 여기서 확정.

### (a) 마찰 — 무부하 정속 전류 스윕 (IsaacLab Disc #3456 + 서보마찰 논문 2410.08650)
- **절차**: 무부하서 여러 정속 ω로 회전, 정상상태 모터 전류 I 기록 → τ = Kt·I.
- **모델**: `τ_fric = Kc·sign(ω) + Kv·ω` (Coulomb+viscous). τ-vs-ω 직선 fit → **절편 b = Kc(Coulomb)**, **기울기 k = Kv(viscous)**.
- **매핑**: MJCF `frictionloss = Kc` (N·m, 정적), MJCF `damping = Kv` (N·m·s/rad, 점성). ⚠ **주의(Disc #3456)**: IsaacLab의 `damping`은 *PD D게인*이지 점성마찰 아님 → 점성마찰은 별도 actuator `friction`/`viscous`로, 또는 **MJCF damping에 넣고 USD로 변환**(우리는 MJCF→USD라 MJCF damping이 점성마찰로 들어감, yaml damping은 PD Kd — *2개가 다른 채널*임을 유의).
- 고충실: Stribeck(저속 마찰 증가)·load-dependent 추가(논문은 CMA-ES로 5~11파라미터 fit, 표준 Coulomb-viscous 대비 1.5~2.9× 오차감소) — 우리는 1차로 Kc/Kv면 충분.

### (b) 백래시 — 위치 히스테리시스
모터 천천히 +방향/−방향 위치명령, 출력축 엔코더 응답 deadband 폭 측정 → 백래시 각(±0.5~2° 추정 [[38]]). sim 직접모델 없음 → **DR deadband 주입**.

### (c) 저수준 Kp/Kd — 실로봇 컨트롤러서 그대로
배포 PD 게인을 sim `stiffness`/`damping`에 동일 입력(sim-real PD 일치 필수, G1 PR↔AB 교훈 [[38]]). 우리 현재 = ζ~0.7 HW-grounded 추정(yaml 주석) → **실 게인으로 교체**. 동급 공개값: Booster T1 Hip/Knee Kp200·Kd5, Ankle Kp50·Kd1(envs/T1.yaml), decimation 10=50Hz.

### (d) 지연 — step 위상
step 명령→응답 위상지연으로 통신+컨트롤 지연 측정(Booster 0–20ms, BRUCE 0–40ms [[38]]). env action delay buffer + DR.

### (e) 실 T-N — 고속 토크 측정
부하 토크센서로 ω별 최대 τ → corner·roll-off 확인([[36]]: 세 모터 전부 전압제한 봉투 = 고속 토크급감). **박스모델은 이걸 못 잡음.**

## 4. 검증 + DR — sim vs real, 잔차를 DR로 덮기

- **step 응답**: 동일 위치 step을 sim·real에 → 상승시간·오버슈트·정상오차 비교 → 불일치면 Kp/Kd·armature·마찰 보정.
- **free-swing(중력 진자)**: 모터 off, 링크 낙하 진동 → 감쇠율로 **점성마찰+armature** 검증(서보논문 "lift&drop"이 정확히 이 테스트).
- **DR 범위 = 검증 잔차 + 제조공차**: Booster 실측 범위 = Kp/Kd ×[0.95,1.05], dof_friction +[0,2], geom friction +[0.1,2], base_mass ×[0.8,1.2], push 0–10N. 우리 추가 권장([[38]] 학계 gap): 전달비/레버암 ±5–10%, 백래시 deadband, 로드 컴플라이언스.

---

## ★ 우리 robstride_biped.yaml / MJCF 적용 (관절별 매핑 요약)

| 값 | 어디로 | 비고 |
|---|---|---|
| 질량/COM/관성 | MJCF `<inertial>` | CAD, import_inertia_tensor:true ✅ |
| 관절축/ROM | MJCF `<joint axis/range>` | CAD ✅ (ROM 링크가용성 검증 [[37]]) |
| peak τ | yaml `effort_limit` (=`effort_limit_sim`) | 데이터시트×N_ext ✅ |
| 무부하 rpm | yaml `velocity_limit_rpm` (=`velocity_limit_sim`) | ÷N_ext ✅ |
| **T-N corner** | **DCMotorCfg `saturation_effort`(=peak), `effort_limit`(=연속), `velocity_limit`(=무부하)** | ❌ 현 ImplicitActuator엔 없음 — **업그레이드 필요** |
| reflected armature | MJCF `<joint armature>` + yaml `armature` | J_r×(N_int·N_ext)², ⚠ 벤치 식별 |
| Coulomb 마찰 | MJCF `frictionloss` | 벤치 무부하 절편, ❌ 추정 |
| viscous 마찰 | MJCF `damping` (PD Kd와 별개 채널) | 벤치 무부하 기울기, ❌ 추정 |
| PD Kp/Kd | yaml `stiffness`/`damping` | 실 컨트롤러, ⚠ ζ추정 |
| 지연/백래시 | env action delay + DR | ❌ DR로만 |

**★ IsaacLab DCMotor 속도의존 T-N 식**(actuator_pd.py):
`max_effort = clip(saturation_effort·(1 − ω/velocity_limit), 0, effort_limit)` (ω<0 대칭) → `τ = clip(τ_PD, min_effort, max_effort)`. 즉 **saturation_effort=peak(자속한계), effort_limit=연속, velocity_limit=무부하** 3값으로 4분면 DC 토크-속도 직선 근사. **이것이 박스모델의 sim2real 1순위 업그레이드**(Shin clip [[28]]의 IsaacLab 네이티브판; 메인테이너도 "ImplicitActuator 직접쓰지 말고 DCMotor" 권고 Disc #2666).

## 신뢰도
- **high**: CAD 1차계열(질량/관성/축, our MJCF)·데이터시트 T-N([[36]] 공식PDF)·reflected armature 공식(J_r·N², 다출처)·IsaacLab 필드 의미+DCMotor 식(공식 API/소스)·MJCF 단위(armature kg·m²/damping N·m·s/frictionloss N·m, 공식 docs)·마찰 무부하식 τ=kω+b(Disc#3456+서보논문)·Booster/G1 게인·DR(공개 yaml).
- **medium**: rotor inertia(전 RobStride 미공개 → armature 추정, 벤치 식별 필요)·백래시/지연 수치(추정).
- **추정/캐비엇**: 우리 yaml의 armature·frictionloss·damping·Kp/Kd는 *전부 추정*(ζ~0.7 grounded)이나 벤치 미식별 → step/free-swing 검증 전까지 DR로 덮어야.

## References
- IsaacLab actuators (Implicit vs DCMotor, armature=관절관성 가산, saturation_effort): https://isaac-sim.github.io/IsaacLab/main/source/api/lab/isaaclab.actuators.html · https://isaac-sim.github.io/IsaacLab/main/source/overview/core-concepts/actuators.html
- DCMotor 권고 + effort_limit 의미(Disc #2666): https://github.com/isaac-sim/IsaacLab/discussions/2666
- 마찰 무부하 식별 τ=kω+b → frictionloss/viscous(Disc #3456): https://github.com/isaac-sim/IsaacLab/discussions/3456
- 서보 마찰모델(벤치 프로토콜·Coulomb+viscous+Stribeck+load, CMA-ES fit): https://arxiv.org/html/2410.08650v1
- MuJoCo 관절 속성 단위(armature kg·m²·damping N·m·s·frictionloss N·m): https://mujoco.readthedocs.io/en/stable/XMLreference.html · DC모터 모델 https://mujoco.readthedocs.io/en/latest/_static/dcmotor.pdf
- reflected inertia I_a=I_r·N²: https://www.motioncontroltips.com/how-do-gearmotors-impact-reflected-mass-inertia-from-the-load/
- K-Bot/K-Scale(RobStride QDD 6–10:1, SysID-calibrated MJCF/URDF, CAD→URDF): https://docs.kscale.dev/robots/k-bot/mechanical/ · https://github.com/kscalelabs/ksim · https://github.com/kscalelabs/kos-sim
- Booster Gym T1(Kp/Kd·decimation·DR yaml): https://github.com/BoosterRobotics/booster_gym (envs/T1.yaml)

관련: [[36_all_actuator_tn_envelopes]](T-N 생성)·[[28_reward_actuator_fidelity]](박스모델 충실도+Shin clip)·[[37_ankle_linkage_fidelity]](레버암/전달비)·[[38_parallel_ankle_sim2real]](J^T·DR·백래시)·[[41_ankle_pitch_pushoff_rs03_underspec]](N 감속).
