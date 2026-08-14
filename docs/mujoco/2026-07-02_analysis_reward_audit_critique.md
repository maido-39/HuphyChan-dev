# 분석 기록 — mjlab reward 감사 · IsaacLab 계보 교훈 · 계획 적대적 비평

> 2026-07-02. [계획 v2](2026-07-02_training_plan_v2.md)의 **근거 분석 원본 기록**(소급 작성 — 연구기록 규칙). 방법: workflow `w3lqi6v9i`(run `wf_c0b16e25-e0a`), 3 agents 병렬(Research: isaaclab-lessons + mjlab-reward-audit → Critique: plan-critique, effort=high). raw 발췌 + file:line 근거 포함.

관련: [계획 v2](2026-07-02_training_plan_v2.md) · [gait 분석](2026-07-02_gait_analysis_and_wobble.md) · IsaacLab 원노트: [Siekmann 연구](../reward_research/2026-06-29_gait_emergence_siekmann.md) · [tiptoe 회귀](../reward_research/2026-06-29_tiptoe_regression.md) · [v8](../experiments/2026-06-29_13-00-01_siekmann_v8_flat.md) · [v9](../experiments/2026-06-29_22-48-47_siekmann_pushoff_v9_flat.md)

---

## §1. IsaacLab 계보 교훈 (agent: isaaclab-lessons)

### 1a. Siekmann `periodic_contact` — 작동한 정확한 공식 (이식 스펙)
출처: `pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/rewards.py:413-428`, **weight +1.5**.
```
phi = ((episode_len·step_dt)/period) % 1;  period=1.0s
발별 ph = (phi+off)%1, off ∈ {L:0.0, R:0.5}   ← 공유 clock, 반주기 오프셋
swing = σ(20·(ph−0.6)) · σ(20·(1−ph))          ← stance 60%/swing 40%, sharp=20
rew = $\mathrm{mean}_{feet}[(1-swing)\cdot\exp(-8.0\|v_{foot,xy}\|) + swing\cdot\exp(-0.02\|GRF_{foot}\|)]$
obs += [sin2πφ, cos2πφ]  (239→241, fresh 학습 필요)
```
**v8 실증 효과** (v4/v7 → v8): GRF L/R asym **0.83→0.18** · 접촉 사이클 6/51→**35/35** · GRF peak **8.7→3.1×BW** · human-likeness −0.05→0.14(hip corr +0.91/+0.77) · CoT **2.62→1.22** · falls 0%, noise_std 0.15. **한 항이 절름발이+충격+대칭+hip패턴+에너지 동시 해결** = 최고 지렛대.
- caveat(원노트): 메커니즘은 이식되나 **상수는 형태·timestep별 재튜닝** 대상.

### 1b. base 높이 앵커 교훈 (mjlab 무릎꿇기의 동류)
`base_height_l2`(weight −1.0, target 0.85) 제거 → 다리 신전(base 0.95) → 까치발 = **무앵커 시 퇴행자세**가 실증된 실패군. 원인기여 추정: base_height 제거 ~75%. mjlab 무릎꿇기(base 낮은쪽)는 같은 실패군 — termination(0.7)=가드, reward 앵커=근본. (A0가 termination만으로 0.811 유지 중 → 앵커는 재발 시 투입.)

### 1c. 금지 목록 (v3~v9 실패 실증 — mjlab서 반복 금지)
1. **관절각 레퍼런스 추종(v3-v7)**: phase 불일치로 전패. v7(추종 +2.5)이 오히려 악화(asym 0.83, GRF 8.9×BW, CoT 2.62). → **접촉 스케줄을 입법하라, 관절각 모방 말고**.
2. **toe 직접 보상(v5 `toe_load_stance`)**: 수동 toe($\tau=k\cdot$굽힘)라 정적 curl로 게임됨. DO-NOT-ADD.
3. **무캡 파워 보상**: `ankle_pushoff_work` scale 0.1 무캡 → reward 324 해킹(error_vel 1.56). **캡 있는 v9도** GRF 3.1→**11.5×BW**(5822N)·knee 216Nm 클립·human-likeness 0.14→0.05 = **impact cap(Stage3) 전에 push-off(Stage4) 금지** 순서 위반의 실증.
4. 게이밍 시그니처: **reward↑인데 GRF/human-likeness/CoT↓** → mean_reward만 보지 말고 §7 motor-load + gait 검출기 교차확인.

### 1d. v9 상세 (기록)
mean_reward 84.05·falls 0%로 "건강"했으나 gait 퇴행: ankle_pushoff_work 기여 +0.375(발화), cop_progression +0.105(너무 약함), toe 최대굽힘 phase L77%/R71%(목표 60% 아님), R toe 0.034rad(거의 안 굽힘). 원인: (a) 파워파밍→GRF 스파이크 (b) cop이 Siekmann clock 아닌 접촉시간 proxy에 게이팅 (c) toe sole flush(z≈−0.0598, 상시접촉)→forefoot 신호 약함.

---

## §2. mjlab reward 함수 감사 (agent: mjlab-reward-audit)

### 2a. 전체 인벤토리 — Pygmalion flat 유효 weight
base: `velocity_env_cfg.py:275-371`, 오버라이드: `config/pygmalion/env_cfgs.py:116-160` (flat은 rough의 reward를 그대로 상속).

| term | 유효 weight | 함수 (file:line) |
|---|--:|---|
| track_linear_velocity | +2.0 | \exp(-err/0.25), rewards.py:27 |
| track_angular_velocity | +2.0 | \exp(-err/0.5), :47 |
| upright | +1.0 | \exp(-tilt²/0.2), :67 (base_link) |
| pose (variable_posture) | +1.0 | \exp(-\mathrmmean(err²/std²)), :438 |
| body_ang_vel | −0.05 | \Sigmaω_xy², :237 |
| angular_momentum | −0.02 | ‖L‖², :249 |
| dof_pos_limits | −1.0 | soft-limit 초과 선형, envs/mdp:81 |
| action_rate_l2 | −0.1 | Σ(Δa²), envs/mdp:58 |
| **air_time** | **0.0 꺼짐** | :262 (아래 2d) |
| foot_clearance | −2.0 | Σ\|h−0.1\|·‖v_xy‖, :294 |
| foot_swing_height | −0.25 | (peak/0.1−1)² 착지시, :324 |
| foot_slip | −0.1 | 접촉 중 v_xy², :379 |
| **soft_landing** | **−1e-5 ≈꺼짐** | :409 (아래 2b) |
| self_collisions | −1.0 | substep force>10N, :162 |
| **torque_limit** | **−0.0 꺼짐** (주석 −0.5) | :184 (아래 2c) |

★ **에너지/토크/관절속도 페널티 전무** — joint_torques_l2·joint_vel_l2·joint_acc_l2·electrical_power_cost·flat_orientation_l2는 `envs/mdp/rewards.py`에 존재하나 **미배선**. 유일 smoothness = action_rate −0.1.

### 2b. soft_landing 정확 형태 (:409-435) — Q2(GRF)의 직접 원인
`cost = Σ_feet ‖순접촉력‖ · 1[first_contact]`, |cmd|≤0.05 시 0. **raw Newton**(착지스텝만, 임펄스 아님, substep peak 놓칠 수 있음 — history 없는 센서). 스케일 산술: GRF 500-2500N × 착지 ~1/35step → **weight −0.1은 착지당 −50~−250 = tracking(+2/step) 25~1000× 압도 → 보행 말살**. 적정 −1e-4~−5e-4(비평: −5e-4→−2e-3 스윕). 현 −1e-5 = 착지당 −0.005~−0.025 = 무의미(★GRF가 안 줄어든 이유).

### 2c. torque_limit 정확 형태 (:184-234)
`excess = clamp(|f_cmd|/e_max − 0.7, min=0)` 합, **선형·정규화·pre-clip**(f_cmd = kp(ctrl−q)−kd·q̇, 포화 후에도 gradient 살리려 의도적). 정격토크 명령 시 0.3 기여, 2×정격 시 1.3. 현 gains서 −0.5는 −0.15~−0.5/step로 적정. ★ 단 **pre-clip이라 고Kp와 결합 시 폭발**(§3-2).

### 2d. air_time 정확 형태 (:262-291) — Q1(보폭) 불가 판정
`Σ_feet 1[0.05<air_time<0.5]` **매 스텝 이진 카운트**(착지보상 아님), |cmd|≤0.5 시 0. **속도의존 보폭 생성 불가**(0.6이나 3.0m/s나 동일 보상, 0.5s서 포화). → custom: 센서가 `last_air_time [B,P]`(contact_sensor.py:211) 노출 → **착지 시 target(‖v_cmd‖)까지의 air time 보상** ~20줄(feet_swing_height 클래스 패턴 :324-376).

### 2e. Siekmann 이식 배관 (mjlab에 phase-clock 부재 확인)
gait clock obs/periodic reward 전무(grep 확인; builtin "clock" 센서는 sim time). 필요물 전부 존재: (a) clock obs = `sin/cos 2π(episode_len·step_dt)/period` callable → actor+critic terms(velocity_env_cfg.py:76-135) (b) 발 접촉력 = `feet_ground_contact` 센서(env_cfgs.py:61-73), critic이 이미 소비 (c) reward = 클래스형 term(feet_swing_height/upright 패턴), 발속도는 feet_slip처럼 `site_lin_vel_w`. **~100줄 + obs 2줄이면 됨.**

### 2f. base 높이 reward 부재 확인
mjlab 전체에 base_height류 reward 없음(envs/mdp 전 함수 나열 확인). 현 앵커 = low_base termination(0.7, env_cfgs.py:165-168)뿐. 필요 시 `root_link_pos_w[:,2]` 5줄 custom.

---

## §3. 적대적 비평 (agent: plan-critique) — 초안 결함과 수정

### 3-1. ★ Kp=800 기각 (초안 오류)
- **포화 산술 오류**: max PD 토크는 Kp·0.25·err가 아니라 `Kp(0.25a+q_def−q)−Kd·q̇`, 오차는 관절범위(≥1.5rad)로 바운드. e_sat=120/800=**0.15rad(8.6°)** → 스윙 오차 0.3~0.8rad서 **bang-bang 지배**(선형 ζ=1 설계 무의미). "full action 무클립" 기준조차 Kp≤480.
- **Kd=84 자기제동 포화**: 댐핑토크가 |q̇|>120/84=**1.43rad/s**서 클립 초과 — hip 스윙 3~6, knee 6~10rad/s → **스윙 내내 자기 다리 브레이크**(에너지·보폭 목표 파괴).
- **knee Kd 내부모순**: knee f_eff 1.5Hz ⇒ I=0.297 ⇒ ζ=1엔 Kd=**31.4**(73 아님; 73은 I=1.66 함의 = 측정과 모순). hip 84는 검산 일치.
- **반례**: mjlab G1이 **동일한 armature-기준 공식**(NATURAL_FREQ 10Hz·ζ2)인데 잘 걸음(우리 메모리: G1-vanilla가 custom reward 이김) → armature-기준 자체가 치명 아님, RL이 50Hz 외루프 보상. 실배포 참조: H1(47kg) Kp150-300/Kd2-6, G1 RL Kp100-150/Kd2-4. Kp800/Kd84는 전 배포 스택의 3-5×/15-40×.
- **armature 출처 의혹 → 확인됨**: `pygmalion_constants.py:35-74` 주석 = **kbot MJCF 복사본**(K-Scale kbot도 RobStride 계열이라 준-신뢰하나 미검산) — "316× 불일치" 수치도 이를 상속. RS 로터관성×기어² 검산 필요.
- **수정**: Day-0 오프라인 1관절 chirp(Kp{200,400,800}, 스윙 3~6rad/s 포화듀티<30% 기준) 후 채택. Kp 300~480 예상, ζ0.7~1(측정 I 기준), implicit 적분 확인.

### 3-2. torque_limit × 고Kp 지뢰
pre-clip f_cmd 벌점이라 Kp800서 f_cmd 250~400Nm → excess 1.4/관절 → **−2~−5/step**(tracking +1~2 압도) → **정지가 최적해**. 수정: `min(|f_cmd|, clip)` 벌점화 또는 **A1 gains 동결 후 A1 정책 offline replay로 weight 산정**. A0-시대 토크통계로 B2 weight 정하지 말 것.

### 3-3. 순서/교란
- A1은 A0 대비 단일변수(둘 다 low_base+0.25 포함) — 단 **동일 iter 비교**만 유효.
- **A0 완주 대기 금지**: gains가 근본원인이므로 A0 최종정책은 버릴 것 — iter 1500서 특성화·snapshot·kill.
- **low_base termination이 무릎꿇기 지표를 가림**: 0.71m에 붙어 사는 cheat 가능 → 렌더가 아니라 **base높이 분포(mode≥0.79) + low_base rate≈0**으로 판정.
- B1(충격억제)↔B2(토크벌점)는 같은 관절·같은 이벤트로 결합 — B1 후 재측정하고 B2 weight 결정, 애매하면 A1+B2 단독 ablation.
- B1b(Siekmann)=B3(보폭 clock) 같은 메커니즘 — **한 번에 설계**(속도-스케줄 clock 내장).

### 3-4. 누락 지표 (전 런 리포트에 추가)
CoT(=Σ|τq̇|dt/mgd) · GRF 첫접촉 peak ×BW(목표<3.5)/P99/RMS·asym(<0.2) · **action 포화율(|a|>0.9)** · 명령-실제 q 갭 · |vx err| 게이트 · **motor-util §7을 매 phase 게이트마다**(C까지 미루면 RS03 열파탄 정책에 몇 주 낭비 위험) · 보폭-속도는 vx{0.3,0.6,1.0,1.5} 스윕서 보폭·케이던스 각각 단조증가(r>0.7).

### 3-5. Top-5 리스크
| # | 리스크 | 완화 |
|---|---|---|
| 1 | Kp800/Kd84 자기제동 포화 | Kp≤480(선호 200-400), knee Kd 31, Day-0 chirp |
| 2 | torque_limit pre-clip×고Kp → 정지 | A1 replay로 weight, 또는 clip-clamp |
| 3 | A1 기각 시 B 런 전부 무효 | **A1 정식 accept 전 B 착수 금지**, 이후 constants 동결 |
| 4 | soft_landing 셔플 게이밍 | 1런 타임박스+air_time≥0.2s kill, Siekmann 이식 사전 작성 |
| 5 | HW 판정을 C로 미룸 | §7 매 게이트, **ankle_pitch 정적 63>60은 정책무관 → 지금 서류 확정** |

(게이트별 상세 시퀀스는 [계획 v2 §1](2026-07-02_training_plan_v2.md) — 본 노트가 그 근거 원본.)

---

## §5. Day-0 chirp 게인 테스트 결과 (agent: chirp-gain-test, 계획 v2 Day-0(a) 실행)

**방법**: 1관절 정확-weld 시뮬(★ 단순 "타관절 리셋" 방식은 **무효** — substep 내 타 dof·base가 자유가속해 겉보기 관성 $1/(M^{-1})[ii]$=0.33/0.10만 보임(6.7×/2.9× 과소) → `mj_fullM` 대각 M[ii]=2.214/0.297 기반 정확 weld로 교체, semi-implicit Euler dt 0.002). chirp A=0.4rad, 0.5→2.5Hz/8s, $\tau=\mathrm{clip}(K_p e - K_d \dot q,\ \pm limit)$. 스크립트: `mjlab/analysis/chirp_gain_test.py`(재실행 ~40s CPU).

**결과표** (sat=포화듀티, damp_sat=댐핑토크 단독 클립초과율):

| joint | Kp | Kd | ζ | sat% | rms err° | damp_sat% |
|---|--:|--:|--:|--:|--:|--:|
| hip_pitch | 200 | 42 | 1.0 | 0.0 | 16.2 | 0 |
| hip_pitch | **400** | **30** | **0.5** | **13.1** | **15.8** | — |
| hip_pitch | 400 | 8 | 0.14 | 31.2 | 24.2(공진) | 0 |
| hip_pitch | 800 | 84 | 1.0 | 0.1 | 12.5 | **58.7** |
| hip_pitch | 800 | 12 | 0.06 | 29.8 | 21.6(**공진 기각**: max_err 77°, 명령 1042Nm) | 1.5 |
| knee | 400 | 8 | 0.29 | 0.0 | 3.7 | 0 |
| **knee** | **800** | **12** | **0.39** | **0.0** | **2.6** | 0 |
| knee | 800 | 31 | 1.0 | 0.0 | 5.9 | 15.9 |

**A1 채택 게인**: **hip_pitch 400/30 · hip_roll 400/26 · hip_yaw 400/9 (ζ≈0.5) · knee 800/12 · 발목 현행 유지**(이미 3.9~5.7Hz). hip 대역 0.56→**2.1Hz**(3.8×), knee →**8.3Hz**.

**핵심 판정**:
1. ★ **hip은 물리적 토크한계**: 0.4rad@2.5Hz 완벽추종에 I·A·ω²=218>120 N·m — 어떤 게인도 스윕 상단 못 따라감(토크한계 대역 ~1.85Hz). 게인은 "우아한 지연(고Kd)" vs "폭력적 공진(저Kd)" 선택일 뿐.
2. **hip 저Kd(배포 스타일 2-12) 사용 불가**: ζ0.06-0.14 → 보행대역(1.5-3Hz)에 공진 → 3× 증폭·76° 이탈. (G1류 Kd 2-4는 가벼운 다리라 가능; 우리 hip I=2.2는 불가.)
3. **crit-damping Kd=84는 자기제동**: 댐핑 단독 58.7% 클립 초과(P-D 상쇄로 총명령은 안 터지나 HW서 속도노이즈 증폭 위험) → 비평 §3-1 예측 실증, ζ0.5 절충 채택.
4. caveat: 단관절 weld = 관절간 결합·착지하중·자세의존(무릎 굽힘 시 hip 관성↓)·qd_ref 피드포워드 무시 — 최종 판정은 A1 학습 게이트서.
- workflow `w3lqi6v9i`(run `wf_c0b16e25-e0a`), 2-phase: Research(2 agents 병렬: 계보 노트 정독 / mjlab 소스 감사) → Critique(1 agent, effort high, 전 사실 주입 후 계획 공격). 토큰 ~160k/33 tool uses/487s.
- 입력: docs/reward_research/·docs/experiments/ 원노트, mjlab src(velocity_env_cfg.py·rewards.py·env_cfgs.py·pygmalion_constants.py), 확정 진단(gait 분석 노트).
- 전 수치는 agent가 file:line과 함께 보고 — 본 노트에 원문 그대로 보존. 원 출력: 세션 task `w3lqi6v9i` output.
