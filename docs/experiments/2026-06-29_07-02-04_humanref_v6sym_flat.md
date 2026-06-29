# 학습 리포트 — 2026-06-29_07-02-04_humanref_v6sym_flat

- **task/run**: `2026-06-29_07-02-04_humanref_v6sym_flat`  ·  **명령**: `(미기록)`
- **의도/변경점**: v6 = HumanRefToe(v5와 동일 reward)를 ★ **대칭 소스(g1is_dm4340, GRF asym 0.06)서 warm-start** — 절뚝(v4/v5 asym 0.83) 해결 시도. ★ 단 g1is_dm4340 = **옛 로봇(toe collision 없음) + 까치발** 정책 → cross-robot 전이. (결과: §5 실패.)

## 1. 재현성 (Reproducibility)
- **OBS**: base_lin_vel(3)+base_ang_vel(3)+projected_gravity(3)+velocity_commands(3)+joint_pos(14)+joint_vel(14)+last_action(12)+height_scan(187) = 239 dims; enable_corruption=obs noise
- **Output(action)**: 12 actuated joint position targets (hip pitch/roll/yaw, knee, ankle pitch/roll x2); passive toe excluded
- **사용 파일(백업: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_07-02-04_humanref_v6sym_flat/repro/`)**:
  - robstride_biped.yaml  <-  pygmalion_locomotion/assets/robot_specs/robstride_biped.yaml
  - robot.xml  <-  pygmalion_locomotion/assets/biped_lower_body_mjcf/robot.xml
  - velocity_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/velocity_env_cfg.py
  - flat_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/flat_env_cfg.py
  - curriculums.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/curriculums.py
  - rsl_rl_ppo_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/agents/rsl_rl_ppo_cfg.py
- **체크포인트**: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_07-02-04_humanref_v6sym_flat/model_1499.pt`

## 2. 지표 (Metrics)
- **최종 Mean reward**: 59.81 (iter 1499), max 61.87
- **error_vel_xy**: 0.2815
- **error_vel_yaw**: 0.3152

![reward curve](assets/2026-06-29_07-02-04_humanref_v6sym_flat_reward.png)

## 2b. Reward (이름 · 값 · 무엇 · 왜)
이 run의 **활성 보상 항 전체** — 이름 · 가중치(값) · 최종 기여 · 무엇인지 · 왜 줬는지 (규칙, user 2026-06-29). 의미 누적 추적: [[04_reward_experiments]].

| Reward | 가중치 | 기여(final) | 무엇 | 왜 |
|---|--:|--:|---|---|
| `track_ang_vel_z_exp` | +2 | +1.7221 | 명령 각속도(yaw) 추종 exp | 작업 목표: 방향 전환 추종 |
| `track_lin_vel_xy_exp` | +1 | +0.8871 | 명령 선속도(x,y) 추종 exp | 작업 목표: 원하는 속도로 보행 |
| `gait_reference_tracking` | +1 | +0.6166 | 사람 gait reference 관절각 추종(contact-phase) | ★ 인간형 gait shape(까치발/shuffle 격파) |
| `action_rate_l2` | -0.01 | -0.0590 | action 변화율 penalty | 급격한 명령 변화 억제 = smooth |
| `dof_acc_l2` | -3e-07 | -0.0479 | 관절 가속도 L2 penalty | 고주파 진동(떨림) 억제 = smooth |
| `dof_pos_limits` | -1 | -0.0348 | 관절 한계 근접 penalty | ROM 끝 회피(HW 보호) |
| `flat_orientation_l2` | -1 | -0.0238 | 몸통 수평(중력 proj) penalty | 몸통 똑바로 유지 |
| `joint_deviation_hip` | -0.1 | -0.0213 | hip 중립 이탈 penalty | hip 자세 안정(과회전 억제) |
| `ang_vel_xy_l2` | -0.05 | -0.0110 | roll/pitch 각속도 penalty | 몸통 흔들림 억제 |
| `base_height` | -1 | -0.0075 | 몸통 높이 목표(0.85) L2 penalty | ★ 다리 신전(까치발) 방지 = 근본 자세제약(gaitfix) |
| `termination_penalty` | -200 | -0.0065 | 조기 종료(낙상) penalty | 넘어짐 회피 |
| `dof_torques_l2` | -1.5e-07 | -0.0021 | 관절 토크 L2 penalty | 에너지/토크 절감(과사용 억제) |
| `foot_impact_force` | -0.005 | -0.0001 | 발 접지력 초과분 penalty | 저충격 착지(HW 파손 보호) |
| `foot_landing_vel` | -1 | -0.0001 | 착지 순간 수직속도 penalty | 부드러운 착지(충격 저감) |
| `toe_load_stance` | +0.5 | +0.0000 | terminal stance toe 하중 보상 | ★ push-off windlass(toe 적시 사용) |
| `lin_vel_z_l2` | +0 | +0.0000 | 수직 속도 penalty | 상하 bounce 억제(보통 0으로 끔) |
| `feet_air_time` | +0 | +0.0000 | 발 공중(또는 single-stance) 시간 보상 | 보폭/스텝 유도(threshold 미달 시 dead) |
| `feet_slide` | -0.1 | -0.0000 | 접지 발 미끄러짐 penalty | 발 고정(slip 방지) |

**이번 run 중요/신규 reward + 왜**: reward는 v5(HumanRefToe)와 **동일** — 변경은 **warm-start 소스만**(v4 → g1is_dm4340 대칭소스). ★ 결과: toe_load_stance **+0.0000(미발화)**·base_height **-0.0075**(v4 -0.0003보다 큼 = base 0.85서 더 벗어남) = 한발 degenerate gait(§5). reward 변경 없음.

## 2c. 학습 건강도 (TensorBoard: loss·수렴·낙상·보상항)
![tb](assets/2026-06-29_07-02-04_humanref_v6sym_flat_tensorboard.png)

- **수렴(noise_std)**: 0.32 → **0.35** (미수렴·탐색↑ ⚠️ (std 증가))
- **mean_reward**: 0.8 → **59.8**, ep_len 최종 **974**
- **추종 error_vel_xy**: 최종 **0.282** (낮을수록 good), yaw 0.315
- **안정성 낙상률 3%** (base_contact 0.29 / time_out 9.29) (안정 ✅)
- **value loss 최종** 0.011, entropy 0.208, LR 7.6e-05
- **커리큘럼 vx 상한 최종** nan
- 정성 해석: ★ noise_std 0.32→**0.35(미수렴 ⚠)**·낙상 3%. 학습 reward 59.8이나 **measure서 base 0.930·R foot GRF 0(한발 degenerate)** = cross-robot warm-start 붕괴(§5). 실패 run.

## 3. 영상 / 이미지
- 학습 영상 24개: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_07-02-04_humanref_v6sym_flat/videos/train/` (예: rl-video-step-0.mp4 … rl-video-step-9000.mp4)
- **누적(step-captioned) 영상 — 노트에서 재생** (vault 복사본):
![[2026-06-29_07-02-04_humanref_v6sym_flat_accumulate.mp4]]
  (원본 참조 `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_07-02-04_humanref_v6sym_flat/videos/accumulated_progress.mp4`, 73MB)

## 4. 부모 학습 대비 비교
- **부모**: `2026-06-28_19-55-27_g1is_dm4340_flat`
- **변경된 설정(velocity_env_cfg diff)**:
  - vs g1is_dm4340(소스): warm-start 소스만 (reward = HumanRefToe = v5와 동일).
- reward 곡선 비교: 위(부모 점선). **정량 비교**: vs v4(이전 best) base **0.851→0.930**(까치발 복귀)·**한발 붕괴**(R GRF 0). = **cross-robot warm-start 실패**(옛 로봇 까치발 소스).

## 5. 분석 — ★ FAILED (cross-robot warm-start 붕괴)
**정량 (measure)**: base **0.930**(까치발 복귀!) · **R foot GRF = 0**(한발 지지/깽깽이) · GRF asym **1.00**(완전 비대칭, v4 0.87보다 악화) · human-likeness 산출 불가(주기 부족).
★ **원인**: 절뚝 해결하려 **대칭 소스 g1is_dm4340서 warm-start**했으나 — g1is_dm4340 = **옛 로봇(toe collision 없음) + 까치발(base 0.95)** 정책. 현재 로봇(toe collision)으로 **cross-robot/cross-config 전이**하니 정책이 붕괴(한발 + 까치발 복귀). base_height도 못 잡음.
★ **교훈**: **cross-robot/cross-config warm-start 금지** — 같은 로봇·config의 ckpt에서만 warm-start. 절뚝은 warm-start 트릭이 아니라 **symmetry augmentation**(데이터 미러로 대칭 강제)로 풀어야. 
**정성**: 한발로 깽깽이, 까치발 복귀 = degenerate. → **v7 = v4(best) + symmetry augmentation**.

## 6. 관련 학습 / 연구 링크
- 관련 run: [[experiments/2026-06-28_19-55-27_g1is_dm4340_flat]](나쁜 warm-start 소스=옛 로봇 까치발) · [[experiments/2026-06-29_03-43-21_humanref_baseh_flat]](v4, 실제 best). 후속 v7 = v4 + symmetry aug.
- 활용 연구: [[2026-06-29_human_gait_reference]] · [[2026-06-29_tiptoe_regression]].
- ★ 피드백: **cross-robot warm-start 실패** = 교훈(같은 로봇 ckpt만). 절뚝 fix = symmetry augmentation.

## 7. 모터 활용 시각화 (사후 — 토크·속도 RMS/p95/peak·스펙선·포화%·시계열)
*스펙선(rated/peak/velocity-limit)은 이 run의 config(감속비·effort/vel)에서 자동.*

**관절 토크 RMS/p95/MAX vs rated(연속/열)·peak 가로선 + 포화%**
![torque](assets/2026-06-29_07-02-04_humanref_v6sym_flat_torque.png)

**관절 속도 RMS/p95/MAX(rpm) vs 속도한계 가로선 + 포화%**
![speed](assets/2026-06-29_07-02-04_humanref_v6sym_flat_speed.png)

**관절 토크 시계열 (시간에 따른 토크 활용, peak/rated 선)**
![torque_ts](assets/2026-06-29_07-02-04_humanref_v6sym_flat_torque_ts.png)

**관절 속도 시계열 (시간에 따른 속도 활용, limit 선)**
![speed_ts](assets/2026-06-29_07-02-04_humanref_v6sym_flat_speed_ts.png)

- 정량 해석: base 0.930·**한발 degenerate gait**(R GRF 0) = 붕괴 run → 모터 사이징 분석 무의미. 유효 사이징은 정상 gait(v4 계열) 기준. cross-robot warm-start 실패의 기록.

