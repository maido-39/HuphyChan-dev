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

## 2b. Reward (이름 · 값 · 무엇 · 왜)
활성 보상 항과 **최종 기여**는 아래. 각 항의 **의미 · 가중치 · 왜**는 → [[04_reward_experiments]] ("현재 활성 Reward 전체" 표) 참조 (재도출 금지, 링크로 추적).

| Reward | 가중치 | 기여(final) | 무엇 | 왜 |
|---|--:|--:|---|---|
| `track_ang_vel_z_exp` | +1 | +0.4967 | 명령 각속도(yaw) 추종 exp | 작업 목표: 방향 전환 추종 |
| `track_lin_vel_xy_exp` | +1 | +0.4828 | 명령 선속도(x,y) 추종 exp | 작업 목표: 원하는 속도로 보행 |
| `upright` | +0.5 | +0.3571 | 몸통 직립 자세 보상 | 몸통 똑바로(앞으로 안 숙임) |
| `knee_straight` | -5 | -0.2494 | 무릎 과신전(straight) penalty | 무릎 굽힘 유지(충격 흡수) |
| `foot_impact_force` | -0.005 | -0.1585 | 발 접지력 초과분 penalty | 저충격 착지(HW 파손 보호) |
| `power_cot` | +0.4 | +0.1107 | 속도정규화 기계적 일률(CoT) 보상 | 에너지 효율(stand-still 회피) |
| `feet_air_time` | +0.75 | +0.0992 | 발 공중(또는 single-stance) 시간 보상 | 보폭/스텝 유도(threshold 미달 시 dead) |
| `foot_landing_vel` | -1 | -0.0779 | 착지 순간 수직속도 penalty | 부드러운 착지(충격 저감) |
| `termination_penalty` | -200 | -0.0764 | 조기 종료(낙상) penalty | 넘어짐 회피 |
| `feet_lateral_sep` | -3 | -0.0548 | 양발 측방 분리 penalty | 다리 교차(8자) 방지 |
| `torque_soft_limit` | -0.0025 | -0.0465 | effort 85% 초과 토크 penalty | 모터 가용범위 유지(sim2real/HW) |
| `joint_deviation_hip` | -0.1 | -0.0412 | hip 중립 이탈 penalty | hip 자세 안정(과회전 억제) |
| `torque_soft_limit_ankle` | -0.01 | -0.0345 | ankle_roll 토크 한계 penalty | 포화 ankle_roll offload(열보호) |
| `dof_acc_l2` | -1e-07 | -0.0280 | 관절 가속도 L2 penalty | 고주파 진동(떨림) 억제 = smooth |
| `feet_distance` | -3 | -0.0197 | 양발 간격(min/max) penalty | 발 교차(scissoring) 방지 |
| `foot_roll_flat` | -0.5 | -0.0163 | 발-body roll 평탄 penalty | 발 좌우 평탄(균형 하중) |
| `ang_vel_xy_l2` | -0.05 | -0.0146 | roll/pitch 각속도 penalty | 몸통 흔들림 억제 |
| `no_flight` | -0.5 | -0.0140 | 양발 동시 공중(flight) penalty | 비행 억제(저충격 하중측정) |
| `action_rate_l2` | -0.005 | -0.0138 | action 변화율 penalty | 급격한 명령 변화 억제 = smooth |
| `flat_orientation_l2` | -1 | -0.0136 | 몸통 수평(중력 proj) penalty | 몸통 똑바로 유지 |
| `dof_torques_l2` | -2e-06 | -0.0121 | 관절 토크 L2 penalty | 에너지/토크 절감(과사용 억제) |
| `ankle_pushoff` | +0.5 | +0.0112 | ankle push-off 일(work) 보상 | toe-off 추진력 |
| `feet_slide` | -0.1 | -0.0110 | 접지 발 미끄러짐 penalty | 발 고정(slip 방지) |
| `lin_vel_z_l2` | -0.2 | -0.0076 | 수직 속도 penalty | 상하 bounce 억제(보통 0으로 끔) |
| `forefoot_cop` | +0.5 | +0.0044 | 앞발 CoP 하중 보상 | forefoot rollover 유도 |
| `dof_pos_limits` | -1 | -0.0028 | 관절 한계 근접 penalty | ROM 끝 회피(HW 보호) |
| `base_height` | -1 | -0.0016 | 몸통 높이 목표(0.85) L2 penalty | ★ 다리 신전(까치발) 방지 = 근본 자세제약(gaitfix) |
| `undesired_contacts` | -1 | -0.0001 | 원치 않는 link 접촉 penalty | 무릎/몸통 지면 충돌 회피 |

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

