# 학습 리포트 — 2026-06-29_22-48-47_siekmann_pushoff_v9_flat

- **task/run**: `2026-06-29_22-48-47_siekmann_pushoff_v9_flat`  ·  **명령**: `bash scripts/run_training.sh Pygmalion-Velocity-Flat-SiekmannPushoff-v0 siekmann_pushoff_v9_flat 1500 8192 --init_checkpoint logs/rsl_rl/pygmalion_flat/2026-06-29_13-00-01_siekmann_v8_flat/model_1499.pt`
- **의도/변경점**: **v9 = Stage4 toe-use stack**. v8(Siekmann periodic_contact) 백본 위에 **`ankle_pushoff_work`(+0.5)** + **`cop_progression`(+1.2)** 추가 (v8에서 warm-start, obs 241 동일). 목표 = toe를 **직접 보상하지 않고**(|τ_toe| 금지) **원인(terminal-stance forefoot CoP + 발목 push-off power)을 보상**해 windlass·toe-off가 emergent하게. 근거: [[2026-06-29_toe_use_reward]] (Hicks 1954·Kuo 2002). **결과 = 부분 회귀**(§5): GRF 악화, toe-timing 미해결.

## 1. 재현성 (Reproducibility)
- **OBS**: base_lin_vel(3)+base_ang_vel(3)+projected_gravity(3)+velocity_commands(3)+joint_pos(14)+joint_vel(14)+last_action(12)+height_scan(187) = 239 dims; enable_corruption=obs noise
- **Output(action)**: 12 actuated joint position targets (hip pitch/roll/yaw, knee, ankle pitch/roll x2); passive toe excluded
- **사용 파일(백업: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_22-48-47_siekmann_pushoff_v9_flat/repro/`)**:
  - robstride_biped.yaml  <-  pygmalion_locomotion/assets/robot_specs/robstride_biped.yaml
  - robot.xml  <-  pygmalion_locomotion/assets/biped_lower_body_mjcf/robot.xml
  - velocity_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/velocity_env_cfg.py
  - flat_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/flat_env_cfg.py
  - curriculums.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/curriculums.py
  - rsl_rl_ppo_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/agents/rsl_rl_ppo_cfg.py
- **체크포인트**: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_22-48-47_siekmann_pushoff_v9_flat/model_1499.pt`


## 1b. siekmann_pushoff_v9_flat Reward & Gains (config에서 파싱 — 재현용)

**Reward 항목** (weight·왜·어떻게):

| reward | weight | 왜 | 어떻게 |
|---|--:|---|---|
| termination_penalty | **-200** | - | - |
| knee_straight | **-5** | - | - |
| track_ang_vel_z_exp | **+2** | 명령 회전속도 추종 | exp(-err²) |
| periodic_contact | **+1.5** | ★Siekmann 위상접촉(대칭 주기보행) | stance:발속도↓ swing:발힘↓ |
| cop_progression | **+1.2** | - | - |
| base_height | **-1** | - | - |
| dof_pos_limits | **-1** | 관절범위 한계 벌점 | 한계초과 L1 |
| flat_orientation_l2 | **-1** | 몸통 수평 유지 | -|proj_g_xy|² |
| foot_landing_vel | **-1** | - | - |
| track_lin_vel_xy_exp | **+1** | 명령 전진/측방 속도 추종 | exp(-err²) |
| ankle_pushoff_work | **+0.5** | - | - |
| feet_slide | -0.1 | 접지발 미끄러짐 벌점 | -|v_contact| |
| joint_deviation_hip | -0.1 | - | - |
| ang_vel_xy_l2 | -0.05 | 롤/피치 각속도 벌점 | -|ωxy|² |
| action_rate_l2 | -0.01 | 액션 급변 벌점 | -|Δa|² |
| foot_impact_force | -0.005 | - | - |
| dof_acc_l2 | -3e-07 | 관절가속 벌점(부드러움) | -Σα² |
| dof_torques_l2 | -1.5e-07 | 관절토크 벌점(에너지/열) | -Στ² |
| feet_air_time | +0 | 체공시간 보상(성큼걸음) | +air_time |
| lin_vel_z_l2 | +0 | 수직속도 벌점(상하 튐 억제) | -vz² |

**관절별 Kp/Kd** (position-PD, effort=관절측 peak):

| 관절 | 모터 | Kp(stiffness) | Kd(damping) | effort [N·m] |
|---|---|--:|--:|--:|
| hip_pitch | RS04 | 200 | 24 | 120 |
| hip_roll | RS04 | 200 | 24 | 120 |
| hip_yaw | RS03 | 150 | 6.5 | 60 |
| knee | RS04 | 200 | 11 | 216 |
| ankle_pitch | RS03 | 80 | 3 | 60 |
| ankle_roll | RS00 | 40 | 3 | 27 |

<!-- SPEC-TABLES:BEGIN (analysis/run_spec_tables.py) -->

**§1b-2. 액추에이터 동역학·한계** (이 런의 `params/env.yaml` 파싱 — `2026-06-29_22-48-47_siekmann_pushoff_v9_flat`)

| 관절 그룹 | 모터 | Kp [N·m/rad] | Kd [N·m·s/rad] | effort 한계 [N·m] | 무부하 속도 [rad/s] | 로터 관성 armature [kg·m²] | 쿨롱 마찰 [N·m] | 점성 [N·m·s/rad] | T-N 곡선 |
|---|---|--:|--:|--:|--:|--:|--:|--:|---|
| hip_pitch, hip_roll | RS04 | 200 | 24 | 120 | 20.94 | 0.0097 | — | — | 미사용 (IsaacLab implicit actuator) |
| hip_yaw | RS03 | 150 | 6.5 | 60 | 20.94 | 0.0049 | — | — | 미사용 (IsaacLab implicit actuator) |
| knee | RS04 | 200 | 11 | 216 | 11.62 | 0.0315 | — | — | 미사용 (IsaacLab implicit actuator) |
| ankle_pitch | RS03 | 80 | 3 | 60 | 20.94 | 0.0049 | — | — | 미사용 (IsaacLab implicit actuator) |
| ankle_roll | RS00 | 40 | 3 | 27 | 10.47 | 0.06 | — | — | 미사용 (IsaacLab implicit actuator) |
| toe | — | 60 | 4 | 60 | 32.99 | 0.008 | — | — | 미사용 (IsaacLab implicit actuator) |

토크는 `effort_limit`과 (있으면) 실측 T-N 곡선의 속도의존 상한 중 **작은 값**으로 클램프된다. armature/쿨롱/점성은 모터 실측값(`PYG_MOTOR_MEAS=1`)이면 실측, 아니면 카탈로그 추정치다.

**§1b-3. ROM 한계·액션 창** (모델 XML range · soft 한계 = 중심±0.5·range×0.9 (mjlab `Entity` 규약) · 액션 clip = env.yaml `actions.joint_pos.clip` · 창 = clip 폭 · default = 액션 0 자세)

**soft 한계와 액션 clip은 같은 공식이다** — `Entity.soft_joint_pos_limits`와 `pygmalion_constants.safe_target_clip()`이 둘 다 *중심 ± 0.5·range·factor*를 쓴다(각 경계에 factor를 곱하는 것이 아니다: 비대칭 관절에서 두 식이 갈린다 — knee `[0,120]`은 `[6,114]`이지 `[0,108]`이 아니다). 그래서 `PYG_SAFE_TARGET_CLIP=1`인 런에서는 두 열이 정확히 일치하고, 정책이 통과하는 클램프와 시뮬레이터가 강제하는 클램프가 하나의 계약이 된다.

모델 출처: 런 디렉토리 `repro/` 스냅샷 (권위) — `robot.xml`

| 관절 | XML range [°] | soft 한계 [°] | 액션 clip [°] | 사용가능 창 [°] | default [°] | 구동 |
|---|---|---|---|--:|--:|---|
| L/R_hip_pitch_joint | [-125, 30] | [-117.2, 22.3] | n/a (구 설정: clip 없음) | 139.5 | -11.46 | 액션 |
| L/R_hip_roll_joint | [-45, 25] | [-41.5, 21.5] | n/a (구 설정: clip 없음) | 63 | 0 | 액션 |
| L_hip_yaw_joint | [-50, 50] | [-45, 45] | n/a (구 설정: clip 없음) | 90 | 0 | 액션 |
| L_knee_joint | [-140, 10] | [-132.5, 2.5] | n/a (구 설정: clip 없음) | 135 | -22.92 | 액션 |
| L/R_ankle_pitch_joint | [-50, 40] | [-45.5, 35.5] | n/a (구 설정: clip 없음) | 81 | 11.46 | 액션 |
| L/R_ankle_roll_joint | [-20, 20] | [-18, 18] | n/a (구 설정: clip 없음) | 36 | 0 | 액션 |
| L_toe_joint | [-50, 0] | [-47.5, -2.5] | n/a (구 설정: clip 없음) | 45 | 0 | 액션 |
| R_hip_yaw_joint | [-40, 40] | [-36, 36] | n/a (구 설정: clip 없음) | 72 | 0 | 액션 |
| R_knee_joint | [-125, 10] | [-118.2, 3.3] | n/a (구 설정: clip 없음) | 121.5 | -22.92 | 액션 |
| R_toe_joint | [-45, 0] | [-42.7, -2.2] | n/a (구 설정: clip 없음) | 40.5 | 0 | 액션 |

액션 스케일 0.5 rad/단위, 오프셋 = default (`use_default_offset`). clip이 없는 구 설정에서는 정책 목표각을 시뮬레이터의 soft 한계가 사후에 잡는다 — 창은 soft 한계 폭으로 읽는다.

**§1b-4. 이 런의 스택 플래그 (`PYG_*`)**

> 이 런은 실행 환경 스냅샷을 남기지 않았고 노트 본문에도 `PYG_*` 언급이 없다 — **원본 설정 소실**. 리워드 가중치·게인·ROM은 위 §1b~§1b-3(런 config 파싱)이 정본이다.

<!-- SPEC-TABLES:END -->

## 2. 지표 (Metrics)
- **최종 Mean reward**: 84.05 (iter 1499), max 84.62
- **error_vel_xy**: 0.2991
- **error_vel_yaw**: 0.2237

![[2026-06-29_22-48-47_siekmann_pushoff_v9_flat_reward.png]]

## 2b. Reward (이름 · 값 · 무엇 · 왜)
이 run의 **활성 보상 항 전체** — 이름 · 가중치(값) · 최종 기여 · 무엇인지 · 왜 줬는지 (규칙, user 2026-06-29). 의미 누적 추적: [[04_reward_experiments]].

| Reward | 가중치 | 기여(final) | 무엇 | 왜 |
|---|--:|--:|---|---|
| `track_ang_vel_z_exp` | +2 | +1.8834 | 명령 각속도(yaw) 추종 exp | 작업 목표: 방향 전환 추종 |
| `periodic_contact` | +1.5 | +1.2268 | Siekmann 주기 contact-schedule: stance엔 발 정지·swing엔 발 이지(공유 clock) | ★ heel→toe-off 리듬 legislate = 까치발·절뚝·충격 동시해결(reference-free) |
| `track_lin_vel_xy_exp` | +1 | +0.9025 | 명령 선속도(x,y) 추종 exp | 작업 목표: 원하는 속도로 보행 |
| `ankle_pushoff_work` | +0.5 | +0.3752 | terminal-stance 발목 plantarflexion power(τ·ω) clamp(0,80W)·gate 보상 | ★ CoP를 앞으로 미는 push-off 엔진(Kuo 2002) → toe-off 추진 + windlass 유발 (원인보상) |
| `joint_deviation_hip` | -0.1 | -0.1135 | hip 중립 이탈 penalty | hip 자세 안정(과회전 억제) |
| `cop_progression` | +1.2 | +0.1052 | CoP heel→toe 진행 보상 | 인간 heel-toe rollover 인코딩 |
| `foot_landing_vel` | -1 | -0.0681 | 착지 순간 수직속도 penalty | 부드러운 착지(충격 저감) |
| `knee_straight` | -5 | -0.0236 | 무릎 과신전(straight) penalty | 무릎 굽힘 유지(충격 흡수) |
| `ang_vel_xy_l2` | -0.05 | -0.0218 | roll/pitch 각속도 penalty | 몸통 흔들림 억제 |
| `flat_orientation_l2` | -1 | -0.0180 | 몸통 수평(중력 proj) penalty | 몸통 똑바로 유지 |
| `dof_acc_l2` | -3e-07 | -0.0134 | 관절 가속도 L2 penalty | 고주파 진동(떨림) 억제 = smooth |
| `foot_impact_force` | -0.005 | -0.0126 | 발 접지력 초과분 penalty | 저충격 착지(HW 파손 보호) |
| `action_rate_l2` | -0.01 | -0.0089 | action 변화율 penalty | 급격한 명령 변화 억제 = smooth |
| `feet_slide` | -0.1 | -0.0050 | 접지 발 미끄러짐 penalty | 발 고정(slip 방지) |
| `dof_torques_l2` | -1.5e-07 | -0.0014 | 관절 토크 L2 penalty | 에너지/토크 절감(과사용 억제) |
| `dof_pos_limits` | -1 | -0.0013 | 관절 한계 근접 penalty | ROM 끝 회피(HW 보호) |
| `base_height` | -1 | -0.0009 | 몸통 높이 목표(0.85) L2 penalty | ★ 다리 신전(까치발) 방지 = 근본 자세제약(gaitfix) |
| `lin_vel_z_l2` | +0 | +0.0000 | 수직 속도 penalty | 상하 bounce 억제(보통 0으로 끔) |
| `feet_air_time` | +0 | +0.0000 | 발 공중(또는 single-stance) 시간 보상 | 보폭/스텝 유도(threshold 미달 시 dead) |
| `termination_penalty` | -200 | +0.0000 | 조기 종료(낙상) penalty | 넘어짐 회피 |

**이번 run 중요/신규 reward + 왜**: **신규 2항 = toe-use stack** ([[2026-06-29_toe_use_reward]] 근거). ① `ankle_pushoff_work`(+0.5): terminal single-support의 발목 plantarflex power = CoP 전진 엔진(Kuo 2002, Adamczyk-Kuo 2013). ② `cop_progression`(+1.2): forefoot 하중분율 `Fz_fore/(Fz_foot+Fz_fore)`가 stance 통해 상승 시 보상(인간 heel→toe rollover). **핵심 설계철학 = passive windlass(Hicks 1954)는 toe 직접보상(|τ_toe|, v5 실패)이 아니라 하중(CoP)·push-off power를 보상해 emergent**. 단 이번엔 impact cap 없이 얹어 power-farming 발생(§5).

## 2c. 학습 건강도 (TensorBoard: loss·수렴·낙상·보상항)
![[2026-06-29_22-48-47_siekmann_pushoff_v9_flat_tensorboard.png]]

- **수렴(noise_std)**: 0.15 → **0.11** (수렴 ✅)
- **mean_reward**: 0.9 → **84.0**, ep_len 최종 **1000**
- **추종 error_vel_xy**: 최종 **0.299** (낮을수록 good), yaw 0.224
- **안정성 낙상률 0%** (base_contact 0.00 / time_out 11.12) (안정 ✅)
- **value loss 최종** 0.003, entropy -11.800, LR 1.1e-04
- **커리큘럼 vx 상한 최종** nan
- 정성 해석: **학습 자체는 건강하게 수렴** — noise_std 0.15→0.11(↓ 수렴), value loss 0.003, 낙상 0%(base_contact 0.00), ep_len 1000 만기, error_vel_xy 0.299. **그러나 mean_reward 84로 높아도 gait 품질(GRF·human-likeness)은 악화**(§5) = 신규 항이 **reward를 farming**(보상↑·실제목표↓). 다음 튜닝: ankle_pushoff에 **impact/GRF cap** + Siekmann clock terminal-stance window(phase 0.45–0.6)로 **gate 재설계**, 그 후 재학습.

## 3. 영상 / 이미지
- 학습 영상 24개: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_22-48-47_siekmann_pushoff_v9_flat/videos/train/` (예: rl-video-step-0.mp4 … rl-video-step-9000.mp4)
- **누적(step-captioned) 영상 — 노트에서 재생** (vault 복사본):
![[2026-06-29_22-48-47_siekmann_pushoff_v9_flat_accumulate.mp4]]
  (원본 참조 `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_22-48-47_siekmann_pushoff_v9_flat/videos/accumulated_progress.mp4`, 82MB)

## 4. 부모 학습 대비 비교
- **부모**: `2026-06-29_13-00-01_siekmann_v8_flat`
- **변경된 설정(velocity_env_cfg diff)**:
  - 부모 v8(Siekmann) 대비 **추가만**: `ankle_pushoff_work`(+0.5), `cop_progression`(+1.2). 그 외 reward/obs/DR/액추에이터 동일 (warm-start이므로 obs 241 불변).
- reward 곡선 비교: 위 그래프(부모 점선). **정량 비교**: mean_reward는 신규 양(+)항으로 ↑(ankle_pushoff +0.375, cop +0.105 기여)지만 **실제 목표는 악화** — GRF peak 3.1×BW→**11.5×BW**, human-likeness 0.14→**0.05**, toe-timing 미개선. 유일한 개선은 GRF L/R asym 0.18→**0.13**(대칭성 소폭↑). = 전형적 reward-gaming 신호.

## 5. 분석 (정성/정량)

**정량 (toe-use 평가):**
| 지표 | v8(부모) | **v9** | 판정 |
|---|--:|--:|---|
| base_height | 0.85 | 0.853 | = 유지(까치발 없음) |
| GRF peak | 3.1×BW | **11.5×BW (5822 N)** | ✗ **크게 악화** |
| GRF L/R asym | 0.18 | 0.13 | ✓ 소폭 개선 |
| human-likeness | 0.14 | **0.05** | ✗ 악화 |
| toe 최대굽힘 위상 | — | L 77% / R 71% (목표 ~60%) | ✗ push-off 시점 아님 |
| toe 굽힘량 | — | L 0.145 / **R 0.034 rad** | ✗ R 거의 안 굽음 |
| CoT | 1.22 | 1.66 (344 W) | ✗ 효율 악화 |

**정성 / 근본원인:**
- ★ **`ankle_pushoff_work`가 power(τ·ω)를 farming** → 정책이 **공격적 push-off**로 보상을 챙김 → GRF 충격 스파이크(11.5×BW). [[2026-06-29_toe_use_reward]]가 경고한 **power-farming 위험이 현실화**.
- **`cop_progression` 기여 0.105로 약함** — contact-time proxy가 Siekmann clock과 미정렬 + toe sole flush(forefoot 신호 약함, 연구노트 §주의)로 gradient 부족 → toe-timing 미교정(R toe 0.034 rad = 거의 정지).
- ★ **순서 위반**: 연구노트의 hard 전제는 "foot-roll(v8) → push-off → CoP"이나, **impact cap(Stage3) 없이** push-off를 얹어 충격을 키움.
- **다음 액션**: (a) `ankle_pushoff_work`에 GRF/impact cap 또는 power 상한, (b) gate를 Siekmann terminal-stance window(phase 0.45–0.6)로 좁힘, (c) `cop_progression`을 clock-gate로 재설계 + toe를 forefoot-distinct하게, (d) GRF soft-limit 강화 후 재학습. **v8을 Stage3(impact cap)으로 먼저 다지고 push-off는 그 위에.**

## 6. 관련 학습 / 연구 링크
- 부모/백본: [[experiments/2026-06-29_13-00-01_siekmann_v8_flat]] — Siekmann periodic_contact 재설계 성공(까치발·절뚝·충격 동시해결). v9는 그 위에 toe-use 2항 추가.
- 활용 연구: [[2026-06-29_toe_use_reward]] (설계 근거: 원인보상·|τ_toe| 금지·power-farming 경고 ← 이번에 현실화) · [[2026-06-29_gait_emergence_siekmann]] · docs/17(toe geometry)·docs/23(cop/forefoot).
- 선행 실패: v5 `toe_load_stance`(직접 toe 보상 → 굽힘 magnitude만↑, timing 그대로) = v9가 피하려던 안티패턴.

## 7. 모터 활용 시각화 (사후 — 토크·속도 RMS/p95/peak·스펙선·포화%·시계열)
*스펙선(rated/peak/velocity-limit)은 이 run의 config(감속비·effort/vel)에서 자동.*

**관절 토크 RMS/p95/MAX vs rated(연속/열)·peak 가로선 + 포화%**
![[2026-06-29_22-48-47_siekmann_pushoff_v9_flat_torque.png]]

**관절 속도 RMS/p95/MAX(rpm) vs 속도한계 가로선 + 포화%**
![[2026-06-29_22-48-47_siekmann_pushoff_v9_flat_speed.png]]

**관절 토크 시계열 (시간에 따른 토크 활용, peak/rated 선)**
![[2026-06-29_22-48-47_siekmann_pushoff_v9_flat_torque_ts.png]]

**관절 속도 시계열 (시간에 따른 속도 활용, limit 선)**
![[2026-06-29_22-48-47_siekmann_pushoff_v9_flat_speed_ts.png]]

- 정량 해석: **knee가 순시 포화** — L/R_knee peak **216 N·m = effort 한계에 clipping**(고정), RMS 34/42 N·m. **hip_pitch/hip_roll도 peak 120 N·m로 한계 고정**. push-off 보상이 무릎·고관절 토크를 한계까지 끌어올림(GRF 5822 N과 동반). 속도: **R_hip_roll peak 20.5 rad/s**(가장 빠름), knee ~11.7 rad/s. **L/R 비대칭**: R측 토크/속도가 전반적으로 높음(R_knee RMS 42 vs L 34) = §5의 절뚝과 일치. **HW 시사**: 무릎·고관절이 순시 토크한계에 물려 clipping → push-off 보상을 cap하지 않으면 무릎 모터 상향 필요. 단 이는 **reward-farming의 결과**이므로 §5 재튜닝(impact cap) 후 재측정이 우선.



---

## §R. 부하 선도 소급 (2026-07-03 룰: signed + 당시 한계선)

![[regime_pushoff_v9.png]]

- 3평면(속도-토크/각도-토크/각도-속도) × 6관절, **signed**(사분면=제동/방향성), contour 실선(굵음=50% 코어·얇음=99%).
- **한계선 산출**: 이 run의 `params/env.yaml`의 `effort_limit_sim`/`velocity_limit_sim`(**관절측 = 감속비 반영값**)을 파싱. ★데이터만 ×1.15(sim→real 마찰·기어효율 보정), 한계선은 실정격 그대로(클립 데이터가 peak선 ~15% 위 = 실기 필요토크). 빨강=±Peak(토크·속도)·주황=±Nominal(rated×기어)·검정=관절측 TN(토크×기어, 속도÷기어). 관절별 모터·기어는 그림 상단 캡션 명기. 전 레짐 표: `docs/mujoco/assets/regimes_limits.csv`.
- 생성: `mjlab/analysis/regime_compare.py` · 비교 총론: [8-레짐 인사이트](../mujoco/2026-07-03_design_insights_all_regimes.md)
