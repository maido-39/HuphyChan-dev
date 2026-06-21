# 학습 리포트 — 2026-06-22_02-36-09_gaitfix_collisiontest

- **task/run**: `2026-06-22_02-36-09_gaitfix_collisiontest`  ·  **명령**: `(미기록)`
- **의도/변경점**: ★ **CONFIG-TEST — targeted L-R 물리충돌 검증** (thigh/shin/foot 같은-세그먼트만 충돌: bitmask contype 3·5·9). conaffinity=1(전체충돌)이 spawn 폭발시킨 뒤, *안전한 targeted 방식이 crash 없이 도는지* 확인용. 40iter·warm-start forefoot_cop·launcher 경유(영상+노트 자동). ※ 보상은 *이 시점* 구버전(ankle_pushoff 0.5; v3서 0.1로 재설계).

## 1. 재현성 (Reproducibility)
- **OBS**: base_lin_vel(3)+base_ang_vel(3)+projected_gravity(3)+velocity_commands(3)+joint_pos(14)+joint_vel(14)+last_action(12)+height_scan(187) = 239 dims; enable_corruption=obs noise
- **Output(action)**: 12 actuated joint position targets (hip pitch/roll/yaw, knee, ankle pitch/roll x2); passive toe excluded
- **사용 파일(백업: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-22_02-36-09_gaitfix_collisiontest/repro/`)**:
  - robstride_biped.yaml  <-  pygmalion_locomotion/assets/robot_specs/robstride_biped.yaml
  - robot.xml  <-  pygmalion_locomotion/assets/biped_lower_body_mjcf/robot.xml
  - velocity_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/velocity_env_cfg.py
  - flat_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/flat_env_cfg.py
  - curriculums.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/curriculums.py
  - rsl_rl_ppo_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/agents/rsl_rl_ppo_cfg.py
- **체크포인트**: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-22_02-36-09_gaitfix_collisiontest/model_39.pt`

## 2. 지표 (Metrics)
- **최종 Mean reward**: 14.00 (iter 39), max 14.00
- **error_vel_xy**: 0.6473
- **error_vel_yaw**: 0.5802
- **curriculum_vel_x**: 1.0632

![reward curve](assets/2026-06-22_02-36-09_gaitfix_collisiontest_reward.png)

## 2b. Reward (무엇을 · 왜)
활성 보상 항과 **최종 기여**는 아래. 각 항의 **의미 · 가중치 · 왜**는 → [[04_reward_experiments]] ("현재 활성 Reward 전체" 표) 참조 (재도출 금지, 링크로 추적).

**보상 항목별 기여(최종, 절대값 큰 순)**:
- `track_ang_vel_z_exp`: +0.4967
- `track_lin_vel_xy_exp`: +0.4828
- `upright`: +0.3571
- `knee_straight`: -0.2494
- `foot_impact_force`: -0.1585
- `power_cot`: +0.1107
- `feet_air_time`: +0.0992
- `foot_landing_vel`: -0.0779
- `termination_penalty`: -0.0764
- `feet_lateral_sep`: -0.0548
- `torque_soft_limit`: -0.0465
- `joint_deviation_hip`: -0.0412
- `torque_soft_limit_ankle`: -0.0345
- `dof_acc_l2`: -0.0280
- `feet_distance`: -0.0197
- `foot_roll_flat`: -0.0163
- `ang_vel_xy_l2`: -0.0146
- `no_flight`: -0.0140
- `action_rate_l2`: -0.0138
- `flat_orientation_l2`: -0.0136
- `dof_torques_l2`: -0.0121
- `ankle_pushoff`: +0.0112
- `feet_slide`: -0.0110
- `lin_vel_z_l2`: -0.0076
- `forefoot_cop`: +0.0044
- `dof_pos_limits`: -0.0028
- `base_height`: -0.0016
- `undesired_contacts`: -0.0001

**이번 run 중요/신규 reward + 왜**: 보상 *변경 없음*(이전 gait-fix 보상 그대로). 이 run의 변경점은 **USD 충돌**(robot.xml conaffinity bitmask). `knee_straight` 기여 −0.249(큼)·`foot_impact` −0.159 = warm-start 직선무릎/충격을 강하게 교정 중(초기 불안정 정상).

## 2c. 학습 건강도 (TensorBoard: loss·수렴·낙상·보상항)
![tb](assets/2026-06-22_02-36-09_gaitfix_collisiontest_tensorboard.png)

- **수렴(noise_std)**: 0.28 → **0.31** (미수렴·탐색↑ ⚠️ (std 증가))
- **mean_reward**: 0.1 → **14.0**, ep_len 최종 **819**
- **추종 error_vel_xy**: 최종 **0.647** (낮을수록 good), yaw 0.580
- **안정성 낙상률 38%** (base_contact 0.88 / time_out 1.42) (낙상多 ❌)
- **value loss 최종** 0.050, entropy 1.523, LR 2.6e-04
- **커리큘럼 vx 상한 최종** 1.06
- 정성 해석: ★ **핵심 = iter 39/40 완주 → targeted 충돌이 crash 안 시킴 확인**(conaffinity=1 spawn폭발과 대조 = 검증 성공). 단 **낙상 38%**(높음)는 *충돌+신규 보상이 새로 들어와 warm-start 정책이 재적응 중*(40iter는 너무 짧음). reward 14·error_vel 0.65도 미수렴. → **gaitfix_v3(1000iter)서 수렴**시켜 본 평가.

## 3. 영상 / 이미지
- 학습 영상 1개: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-22_02-36-09_gaitfix_collisiontest/videos/train/` (예: rl-video-step-0.mp4 … rl-video-step-0.mp4)
- **누적(step-captioned) 영상 — 노트에서 재생** (vault 복사본):
![[2026-06-22_02-36-09_gaitfix_collisiontest_accumulate.mp4]]
  (원본 참조 `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-22_02-36-09_gaitfix_collisiontest/videos/accumulated_progress.mp4`, 4MB)

## 5. 분석 (정성/정량) — config-test (검증 전용)
**결과: ✅ targeted L-R 충돌 = 안전**(crash 없음·iter 39/40 완주). conaffinity=1(전체 geom 충돌) spawn 폭발과 대조 → 같은-세그먼트만 충돌하는 bitmask 설계가 옳음 확인. 정면 클로즈업서 다리 비교차.
![collision close-up](assets/gait_diag/col_0.65.png)
표준 모터분석/측정은 **gaitfix_v3(본 학습, 수렴)**서 수행 — 이 run은 충돌 *crash 검증*만 목적(40iter).

## 6. 관련 학습 / 연구 링크
- 관련 run: 본 학습 = `gaitfix_v3`(이 충돌 + 보상재설계(ankle_pushoff↓·forefoot_cop↑) + jitter강화). 선행 = `gaitfix_v1`(conaffinity=1로 crash → 이 targeted 방식으로 교체).
- 코드: 커밋 `d96e5d7`(targeted충돌 bitmask + 보상재설계). 가설 [[37_ankle_linkage_fidelity]](발edge→roll과부하=gait결함).

