# 학습 리포트 — 2026-06-29_03-43-21_humanref_baseh_flat

- **task/run**: `2026-06-29_03-43-21_humanref_baseh_flat`  ·  **명령**: `(미기록)`
- **의도/변경점**: ★ **까치발 근본fix 검증** = human-ref + **base_height(-1.0@0.85) 복원**(까치발 근본원인=G1이 gaitfix의 base_height 제거한 회귀, [[2026-06-29_tiptoe_regression]]; `_apply_g1_impact_stable` 전 계통 복원). = gait_reference_tracking + base_height. warm-start from g1is_v2(=v3와 동일 init = 깨끗한 base_height A/B).

## 1. 재현성 (Reproducibility)
- **OBS**: base_lin_vel(3)+base_ang_vel(3)+projected_gravity(3)+velocity_commands(3)+joint_pos(14)+joint_vel(14)+last_action(12)+height_scan(187) = 239 dims; enable_corruption=obs noise
- **Output(action)**: 12 actuated joint position targets (hip pitch/roll/yaw, knee, ankle pitch/roll x2); passive toe excluded
- **사용 파일(백업: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_03-43-21_humanref_baseh_flat/repro/`)**:
  - robstride_biped.yaml  <-  pygmalion_locomotion/assets/robot_specs/robstride_biped.yaml
  - robot.xml  <-  pygmalion_locomotion/assets/biped_lower_body_mjcf/robot.xml
  - velocity_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/velocity_env_cfg.py
  - flat_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/flat_env_cfg.py
  - curriculums.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/curriculums.py
  - rsl_rl_ppo_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/agents/rsl_rl_ppo_cfg.py
- **체크포인트**: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_03-43-21_humanref_baseh_flat/model_1499.pt`

## 2. 지표 (Metrics)
- **최종 Mean reward**: 61.49 (iter 1499), max 63.47
- **error_vel_xy**: 0.2959
- **error_vel_yaw**: 0.3282

![reward curve](assets/2026-06-29_03-43-21_humanref_baseh_flat_reward.png)

## 2b. Reward (이름 · 값 · 무엇 · 왜)
이 run의 **활성 보상 항 전체** — 이름 · 가중치(값) · 최종 기여 · 무엇인지 · 왜 줬는지 (규칙, user 2026-06-29). 의미 누적 추적: [[04_reward_experiments]].

| Reward | 가중치 | 기여(final) | 무엇 | 왜 |
|---|--:|--:|---|---|
| `track_ang_vel_z_exp` | +2 | +1.7419 | 명령 각속도(yaw) 추종 exp | 작업 목표: 방향 전환 추종 |
| `track_lin_vel_xy_exp` | +1 | +0.8835 | 명령 선속도(x,y) 추종 exp | 작업 목표: 원하는 속도로 보행 |
| `gait_reference_tracking` | +1 | +0.7197 | 사람 gait reference 관절각 추종(contact-phase) | ★ 인간형 gait shape(까치발/shuffle 격파) |
| `flat_orientation_l2` | -1 | -0.0584 | 몸통 수평(중력 proj) penalty | 몸통 똑바로 유지 |
| `joint_deviation_hip` | -0.1 | -0.0526 | hip 중립 이탈 penalty | hip 자세 안정(과회전 억제) |
| `action_rate_l2` | -0.01 | -0.0423 | action 변화율 penalty | 급격한 명령 변화 억제 = smooth |
| `dof_acc_l2` | -3e-07 | -0.0335 | 관절 가속도 L2 penalty | 고주파 진동(떨림) 억제 = smooth |
| `foot_landing_vel` | -1 | -0.0270 | 착지 순간 수직속도 penalty | 부드러운 착지(충격 저감) |
| `ang_vel_xy_l2` | -0.05 | -0.0162 | roll/pitch 각속도 penalty | 몸통 흔들림 억제 |
| `feet_slide` | -0.1 | -0.0124 | 접지 발 미끄러짐 penalty | 발 고정(slip 방지) |
| `dof_pos_limits` | -1 | -0.0084 | 관절 한계 근접 penalty | ROM 끝 회피(HW 보호) |
| `foot_impact_force` | -0.005 | -0.0075 | 발 접지력 초과분 penalty | 저충격 착지(HW 파손 보호) |
| `termination_penalty` | -200 | -0.0056 | 조기 종료(낙상) penalty | 넘어짐 회피 |
| `dof_torques_l2` | -1.5e-07 | -0.0026 | 관절 토크 L2 penalty | 에너지/토크 절감(과사용 억제) |
| `base_height` | -1 | -0.0003 | 몸통 높이 목표(0.85) L2 penalty | ★ 다리 신전(까치발) 방지 = 근본 자세제약(gaitfix) |
| `feet_air_time` | +0 | +0.0000 | 발 공중(또는 single-stance) 시간 보상 | 보폭/스텝 유도(threshold 미달 시 dead) |
| `lin_vel_z_l2` | +0 | +0.0000 | 수직 속도 penalty | 상하 bounce 억제(보통 0으로 끔) |

**이번 run 중요/신규 reward + 왜**: ★ **base_height(-1.0 @ 0.85)** = 까치발 근본fix(기여 -0.0003≈0 = base가 정확히 0.85 도달!) — 다리 신전 유인 제거 → 다리 굽힘=평발. gait_reference_tracking(+1.0)과 함께. 결과(§5): base **0.926→0.851**·안정 **57 cycles**·hip corr **+0.6~0.7**(인간형) = 까치발 해소 검증.

## 2c. 학습 건강도 (TensorBoard: loss·수렴·낙상·보상항)
![tb](assets/2026-06-29_03-43-21_humanref_baseh_flat_tensorboard.png)

- **수렴(noise_std)**: 0.20 → **0.24** (미수렴·탐색↑ ⚠️ (std 증가))
- **mean_reward**: 0.8 → **61.5**, ep_len 최종 **980**
- **추종 error_vel_xy**: 최종 **0.296** (낮을수록 good), yaw 0.328
- **안정성 낙상률 3%** (base_contact 0.12 / time_out 4.29) (안정 ✅)
- **value loss 최종** 0.006, entropy -3.388, LR 2.6e-04
- **커리큘럼 vx 상한 최종** nan
- 정성 해석: noise_std 0.20→0.24(거의 수렴)·reward **61.5(최고)**·낙상 3%(v3 5%↓) = **건강+안정**. ★ 까치발 fix 성공(§5): base 0.851·57 cycles·hip 인간형. 남은: 진폭·절뚝·energy(v5+).

## 3. 영상 / 이미지
- 학습 영상 24개: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_03-43-21_humanref_baseh_flat/videos/train/` (예: rl-video-step-0.mp4 … rl-video-step-9000.mp4)
- **누적(step-captioned) 영상 — 노트에서 재생** (vault 복사본):
![[2026-06-29_03-43-21_humanref_baseh_flat_accumulate.mp4]]
  (원본 참조 `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_03-43-21_humanref_baseh_flat/videos/accumulated_progress.mp4`, 73MB)

## 4. 부모 학습 대비 비교
- **부모**: `2026-06-28_23-58-20_g1is_v2_flat`
- **변경된 설정(velocity_env_cfg diff)**:
  - vs g1is_v2: +gait_reference_tracking, **+base_height(-1.0@0.85)**, −swing_height/−foot_flat/−knee_straight.
- reward 곡선 비교: 위(부모 점선). **정량 비교 vs v3**(human-ref, base_height 無): base **0.926→0.851**(까치발 해소), 안정 **10→57 cycles**, hip corr **음(-0.87)→양(+0.6~0.7)**, score -0.08→+0.06. = **base_height가 까치발+불안정 둘 다 해결**.

## 5. 분석 — ★ 까치발 근본fix **검증 성공** (+ 남은 과제)
**까치발 해결**(measure + `gait_humanlikeness`/`gait_toe_timing`):
| 지표 | v3(no base_h) | **v4(+base_h)** | g1is(까치발) | 판정 |
|---|--:|--:|--:|---|
| base_height | 0.926 | ★ **0.851** | 0.95 | ✅ 다리 굽음=까치발 해소(target 0.85) |
| 안정성 cycles | 10 | ★ **57** | — | ✅ 안정화 |
| hip_pitch corr | -0.87(버그) | ★ **+0.6~0.7** | -0.78 | ✅ 사람 패턴 따름 |
| L toe 굽힘 위상 | 0%(swing) | **51%(push-off)** | — | ✅ windlass 시작 |
| ankle_roll RMS | 96% | **79%** | 215% | ✅ |

★ **결론**: gaitfix→G1서 제거됐던 **base_height 복원이 까치발을 근본 해결** — base 0.95→0.851(다리 굽힘), 동시에 **안정화**(10→57 cycles), hip이 **사람 패턴**(+0.6~0.7). v3(reference만)→v4(+base_height)로 base_height 효과 격리 입증. (★ 초기 음의 corr은 human-likeness **툴 버그**(busier 한 발 cycle)였음 — per-leg 검출로 수정.)

**남은 과제**(별개, v5+):
- **진폭** range_ratio 0.29(사람의 ~30%, 보폭 더 필요) → gait_reference weight↑ 검토.
- ★ **절뚝** GRF L863/**R4426N**(asym 0.87) + R toe 시기 어긋남 → symmetry augmentation + toe_load.
- **ankle_pitch 252%**(포화) + CoT 1.54 → energy(power_cot) + 발목.
**정성**: 까치발 사라지고 다리 굽힌 보행, 단 좌우 비대칭(절뚝) 잔존.
→ **v5 = HumanRefToe**(+toe_load windlass) → 이후 symmetry(절뚝)·power_cot(energy).

## 6. 관련 학습 / 연구 링크
- 관련 run: [[experiments/2026-06-29_01-43-55_humanref_v3_flat]](base_height 無, 까치발 지속 = A/B 대조) · [[experiments/2026-06-28_23-58-20_g1is_v2_flat]](parent, warm-start).
- 활용 연구: ★ [[2026-06-29_tiptoe_regression]](까치발=base_height 회귀 근본원인) · [[2026-06-29_human_gait_reference]](human-ref) · [[gait_reference]]·[[51_joint_sign_conventions]].
- ★ 결과 피드백: **base_height 복원 = 까치발 근본fix 확정**(v3 vs v4 A/B). 다음 = 절뚝(symmetry)·toe(toe_load)·energy(power_cot).

## 7. 모터 활용 시각화 (사후 — 토크·속도 RMS/p95/peak·스펙선·포화%·시계열)
*스펙선(rated/peak/velocity-limit)은 이 run의 config(감속비·effort/vel)에서 자동.*

**관절 토크 RMS/p95/MAX vs rated(연속/열)·peak 가로선 + 포화%**
![torque](assets/2026-06-29_03-43-21_humanref_baseh_flat_torque.png)

**관절 속도 RMS/p95/MAX(rpm) vs 속도한계 가로선 + 포화%**
![speed](assets/2026-06-29_03-43-21_humanref_baseh_flat_speed.png)

**관절 토크 시계열 (시간에 따른 토크 활용, peak/rated 선)**
![torque_ts](assets/2026-06-29_03-43-21_humanref_baseh_flat_torque_ts.png)

**관절 속도 시계열 (시간에 따른 속도 활용, limit 선)**
![speed_ts](assets/2026-06-29_03-43-21_humanref_baseh_flat_speed_ts.png)

- 정량 해석: base **0.851**(까치발 해소) + ankle_roll **79%**(v3 96%↓) but **ankle_pitch 252%rated 포화 지속**(reference의 plantar 추종 구동). ★ **L/R GRF 비대칭** L863/R4426N = 절뚝(R foot 과부하). → ankle_pitch 포화·절뚝은 v5+(toe_load/symmetry)로 gait 정상화 후 발목 사이징 재측정. base_height 복원으로 다리신전-기인 발목부하는 개선 경로.

