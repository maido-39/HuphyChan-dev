# 학습 리포트 — 2026-06-28_22-20-50_asimov_reward_flat

- **task/run**: `2026-06-28_22-20-50_asimov_reward_flat`  ·  **명령**: `(미기록)`
- **의도/변경점**: Menlo/Asimov 블로그(teaching-a-humanoid-to-walk) reward를 **그대로** 적용한 대조군 (사용자: "블로그 reward 그대로 + 문제 파악"). G1 vanilla base + 블로그식: feet_air_time→`mdp.feet_air_time` @**+0.5**(actual air-time=flight 보상, 블로그 16kg 다리용) · ang_vel_xy -0.08 · foot_impact_force · **joint_deviation_ankle -0.5**(비대칭 tight ankle tol). 로봇은 g1is와 동일(DM-J4340 ankle, knee1.8:1, primitive collision) **단 toe collision은 옛 USD=없음**(이 run은 v2 toe 추가 *전*). 목적: 블로그 철학을 51.8kg 하중측정 로봇에 적용 시 문제 실측. 근거 [[2026-06-28_menlo_blog_review]]·[[2026-06-28_asimov_reward_asis]].

## 1. 재현성 (Reproducibility)
- **OBS**: base_lin_vel(3)+base_ang_vel(3)+projected_gravity(3)+velocity_commands(3)+joint_pos(14)+joint_vel(14)+last_action(12)+height_scan(187) = 239 dims; enable_corruption=obs noise
- **Output(action)**: 12 actuated joint position targets (hip pitch/roll/yaw, knee, ankle pitch/roll x2); passive toe excluded
- **사용 파일(백업: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-28_22-20-50_asimov_reward_flat/repro/`)**:
  - robstride_biped.yaml  <-  pygmalion_locomotion/assets/robot_specs/robstride_biped.yaml
  - robot.xml  <-  pygmalion_locomotion/assets/biped_lower_body_mjcf/robot.xml
  - velocity_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/velocity_env_cfg.py
  - flat_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/flat_env_cfg.py
  - curriculums.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/curriculums.py
  - rsl_rl_ppo_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/agents/rsl_rl_ppo_cfg.py
- **체크포인트**: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-28_22-20-50_asimov_reward_flat/model_1499.pt`


## 1b. asimov_reward_flat Reward & Gains (config에서 파싱 — 재현용)

**Reward 항목** (weight·왜·어떻게):

| reward | weight | 왜 | 어떻게 |
|---|--:|---|---|
| termination_penalty | **-200** | - | - |
| track_ang_vel_z_exp | **+2** | 명령 회전속도 추종 | exp(-err²) |
| dof_pos_limits | **-1** | 관절범위 한계 벌점 | 한계초과 L1 |
| flat_orientation_l2 | **-1** | 몸통 수평 유지 | -|proj_g_xy|² |
| track_lin_vel_xy_exp | **+1** | 명령 전진/측방 속도 추종 | exp(-err²) |
| feet_air_time | **+0.5** | 체공시간 보상(성큼걸음) | +air_time |
| joint_deviation_ankle | **-0.5** | - | - |
| feet_slide | -0.1 | 접지발 미끄러짐 벌점 | -|v_contact| |
| joint_deviation_hip | -0.1 | - | - |
| ang_vel_xy_l2 | -0.08 | 롤/피치 각속도 벌점 | -|ωxy|² |
| action_rate_l2 | -0.005 | 액션 급변 벌점 | -|Δa|² |
| foot_impact_force | -0.005 | - | - |
| dof_torques_l2 | -1.5e-07 | 관절토크 벌점(에너지/열) | -Στ² |
| dof_acc_l2 | -1.25e-07 | 관절가속 벌점(부드러움) | -Σα² |
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

**§1b-2. 액추에이터 동역학·한계** (이 런의 `params/env.yaml` 파싱 — `2026-06-28_22-20-50_asimov_reward_flat`)

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

> ⚠ **파일 최신성 주의** — 이 XML은 런 시작(2026-06-28_22-20-50)보다 뒤인 2026-06-28 23:13에 수정되었다. 런 디렉토리에 모델 스냅샷이 없으므로 아래 range는 **현재 파일 기준**이며 런 당시와 다를 수 있다.

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
- **최종 Mean reward**: 50.65 (iter 1499), max 51.86
- **error_vel_xy**: 0.2170
- **error_vel_yaw**: 0.2278

![[2026-06-28_22-20-50_asimov_reward_flat_reward.png]]

## 2b. Reward (이름 · 값 · 무엇 · 왜)
활성 보상 항과 **최종 기여**는 아래. 각 항의 **의미 · 가중치 · 왜**는 → [[04_reward_experiments]] ("현재 활성 Reward 전체" 표) 참조 (재도출 금지, 링크로 추적).

| Reward | 가중치 | 기여(final) | 무엇 | 왜 |
|---|--:|--:|---|---|
| `track_ang_vel_z_exp` | +2 | +1.8381 | 명령 각속도(yaw) 추종 exp | 작업 목표: 방향 전환 추종 |
| `track_lin_vel_xy_exp` | +1 | +0.9268 | 명령 선속도(x,y) 추종 exp | 작업 목표: 원하는 속도로 보행 |
| `joint_deviation_ankle` | -0.5 | -0.0853 | ankle 중립 이탈 penalty | 발목 자세 tight 유지(블로그식) |
| `feet_slide` | -0.1 | -0.0325 | 접지 발 미끄러짐 penalty | 발 고정(slip 방지) |
| `action_rate_l2` | -0.005 | -0.0285 | action 변화율 penalty | 급격한 명령 변화 억제 = smooth |
| `joint_deviation_hip` | -0.1 | -0.0200 | hip 중립 이탈 penalty | hip 자세 안정(과회전 억제) |
| `feet_air_time` | +0.5 | -0.0164 | 발 공중(또는 single-stance) 시간 보상 | 보폭/스텝 유도(threshold 미달 시 dead) |
| `ang_vel_xy_l2` | -0.08 | -0.0113 | roll/pitch 각속도 penalty | 몸통 흔들림 억제 |
| `flat_orientation_l2` | -1 | -0.0038 | 몸통 수평(중력 proj) penalty | 몸통 똑바로 유지 |
| `termination_penalty` | -200 | -0.0027 | 조기 종료(낙상) penalty | 넘어짐 회피 |
| `dof_acc_l2` | -1.25e-07 | -0.0024 | 관절 가속도 L2 penalty | 고주파 진동(떨림) 억제 = smooth |
| `foot_impact_force` | -0.005 | -0.0023 | 발 접지력 초과분 penalty | 저충격 착지(HW 파손 보호) |
| `dof_torques_l2` | -1.5e-07 | -0.0017 | 관절 토크 L2 penalty | 에너지/토크 절감(과사용 억제) |
| `lin_vel_z_l2` | +0 | +0.0000 | 수직 속도 penalty | 상하 bounce 억제(보통 0으로 끔) |
| `dof_pos_limits` | -1 | -0.0000 | 관절 한계 근접 penalty | ROM 끝 회피(HW 보호) |

**이번 run 중요/신규 reward + 왜**: 블로그 핵심 = **feet_air_time +0.5**(actual air-time=flight 보상) + **joint_deviation_ankle -0.5**(ankle을 neutral 근처로 tight). 결과: ★ **air_time 기여 -0.0164 = DEAD** — 51.8kg 로봇은 flight 거의 못 만듦(flight 1.3%) → 블로그 시그니처 레버가 무거운 로봇엔 무력(연구 [[2026-06-28_menlo_blog_review]] 예측: air_time=flight=경량 로봇용, 확증). ★ **joint_deviation_ankle -0.0853**(2번째 큰 penalty) = ankle을 neutral로 당기며 추종과 충돌 → §5·§7 ankle_pitch 과부하의 직접 원인.

## 2c. 학습 건강도 (TensorBoard: loss·수렴·낙상·보상항)
![[2026-06-28_22-20-50_asimov_reward_flat_tensorboard.png]]

- **수렴(noise_std)**: 0.99 → **0.26** (수렴 ✅)
- **mean_reward**: -0.3 → **50.6**, ep_len 최종 **982**
- **추종 error_vel_xy**: 최종 **0.217** (낮을수록 good), yaw 0.228
- **안정성 낙상률 1%** (base_contact 0.12 / time_out 9.04) (안정 ✅)
- **value loss 최종** 0.006, entropy -1.651, LR 2.6e-04
- **커리큘럼 vx 상한 최종** nan
- 정성 해석: noise_std 0.99→0.26 **수렴 ✅**, reward 50.6, 낙상 1%, error_vel 0.217 = 학습 건강·추종 양호(g1is_dm4340와 동급). entropy -1.65(g1is -0.26보다 낮음=더 결정적). = **학습 자체는 잘 됨, 그러나 §5: 블로그 reward가 우리 HW엔 충격·발목과부하 유발**(잘 학습됐으나 *우리 목표엔 부적합한 것을* 학습).

## 3. 영상 / 이미지
- 학습 영상 24개: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-28_22-20-50_asimov_reward_flat/videos/train/` (예: rl-video-step-0.mp4 … rl-video-step-9000.mp4)
- **누적(step-captioned) 영상 — 노트에서 재생** (vault 복사본):
![[2026-06-28_22-20-50_asimov_reward_flat_accumulate.mp4]]
  (원본 참조 `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-28_22-20-50_asimov_reward_flat/videos/accumulated_progress.mp4`, 70MB)

## 5. 분석 (정성/정량) — ★ 블로그 reward as-is 문제 실측 (vs g1is_dm4340 대조)

| 지표 | asimov(블로그) | g1is_dm4340(우리 reward) | 판정 |
|---|--:|--:|---|
| GRF peak | ★ **1991N (3.9×BW)** | 1079N (2.1×BW) | ⚠ HW 파손범위(1.5-2.7kN) **진입** |
| flight(양발 off) | 1.3% | 2.7% | air_time +0.5에도 flight 거의 없음(무거움) |
| ankle_pitch RMS | ★ **243%**rated | 191% | ⚠ joint_deviation_ankle이 발목 과부하 |
| ankle_roll RMS | 77% | 215% | ✅ 오히려 낮음(tight tol이 측방 shuffle 억제) |
| base_height | 0.864m | 0.952m | 까치발 덜함 |
| reward / error_vel_xy | 50.6 / 0.217 | 51.9 / 0.228 | 추종은 동급 |

★ **결론 (블로그 reward as-is, 우리 51.8kg 하중측정 로봇)**:
1. ★ **peak 충격 ~2배(1991N=3.9×BW)** → HW 파손범위(1.5-2.7kN) **진입** = 저충격 하중측정 목표 **위반**. flight(1.3%) 탓 아니라 **tight ankle deviation이 발목 컴플라이언스를 줄여 더 딱딱한 착지** → peak GRF↑.
2. ★ **ankle_pitch 243% 과부하** — 블로그 joint_deviation_ankle(-0.5, 16kg 로봇용 tight tol)이 51.8kg 발목을 neutral로 당기며 추종과 싸워 과부하.
3. **air_time +0.5 = DEAD(-0.0164, flight 1.3%)** — 블로그 시그니처 레버가 무거운 로봇엔 무력(연구 예측 확증).
4. ⚠ 단 **까치발은 덜함**(base_h 0.864, ankle_roll 77%) — tight shaping이 shuffle 억제 = 블로그가 전부 나쁜 건 아니나 **충격·발목과부하 대가**가 치명.

**정성(영상)**: 추종·안정은 OK, 발목을 neutral로 당겨 shuffle은 덜하나 착지가 딱딱(고충격). → **블로그 air_time/tight-ankle은 우리 하중측정 로봇엔 부적합**([[2026-06-28_menlo_blog_review]] 'DEPART blog air_time' 확증). **v2**(swing_height+foot_flat, air_time·tight-ankle 없이, +toe collision)가 **까치발 해결 + 저충격** 둘 다 노림.

## 6. 관련 학습 / 연구 링크
- 관련 run: [[experiments/2026-06-28_19-55-27_g1is_dm4340_flat]](대조군, 같은 로봇·우리 reward) — 본 run은 **reward만 블로그로 교체**.
- 활용 연구: [[2026-06-28_menlo_blog_review]](블로그 철학 레퍼런스 검증) · [[2026-06-28_asimov_reward_asis]](as-is 적용 계획) · [[2026-06-28_heeltoe_stride_fix]](v2 대안 = swing_height+foot_flat).
- ★ 결과 피드백: 블로그 **air_time=DEAD** + **tight-ankle=충격·발목과부하** 입증 → v2(swing_height+foot_flat+toe collision)로 진행.

## 7. 모터 활용 시각화 (사후 — 토크·속도 RMS/p95/peak·스펙선·포화%·시계열)
*스펙선(rated/peak/velocity-limit)은 이 run의 config(감속비·effort/vel)에서 자동.*

**관절 토크 RMS/p95/MAX vs rated(연속/열)·peak 가로선 + 포화%**
![[2026-06-28_22-20-50_asimov_reward_flat_torque.png]]

**관절 속도 RMS/p95/MAX(rpm) vs 속도한계 가로선 + 포화%**
![[2026-06-28_22-20-50_asimov_reward_flat_speed.png]]

**관절 토크 시계열 (시간에 따른 토크 활용, peak/rated 선)**
![[2026-06-28_22-20-50_asimov_reward_flat_torque_ts.png]]

**관절 속도 시계열 (시간에 따른 속도 활용, limit 선)**
![[2026-06-28_22-20-50_asimov_reward_flat_speed_ts.png]]

- 정량 해석: ★ **ankle_pitch 243%rated 과부하**(블로그 tight ankle deviation 구동) — g1is_dm4340(191%)보다 심함. **ankle_roll 77%**(g1is 215%보다 낮음 — tight tol이 측방 shuffle 억제). knee/hip 여유. → 블로그 reward는 ankle_roll은 덜 쓰지만 **ankle_pitch를 더 과부하 + peak 충격 2배(1991N)**. = 블로그 air_time/tight-ankle은 우리 목표에 부적합. HW 사이징은 v2(plantigrade·저충격) 후 재측정해야 유효.



---

## §R. 부하 선도 소급 (2026-07-03 룰: signed + 당시 한계선)

![[regime_asimov_reward_flat.png]]

- 3평면(속도-토크/각도-토크/각도-속도) × 6관절, **signed**. contour 실선(굵음=50% 코어·얇음=99%).
- ★데이터만 ×1.15(sim→real 마찰·기어효율 보정), 한계선은 실정격 그대로(클립 데이터가 peak선 ~15% 위 = 실기 필요토크). 빨강=±Peak(토크·속도)·주황=±Nominal(rated×기어)·검정=관절측 TN(토크×기어, 속도÷기어) — 이 run의 `params/env.yaml` 파싱값, 관절별 모터·기어는 그림 캡션 명기.
- 생성: `mjlab/analysis/batch_regime_notes.py` · 총론: [8-레짐 인사이트](../mujoco/2026-07-03_design_insights_all_regimes.md)
