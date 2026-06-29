# 학습 리포트 — 2026-06-29_05-33-10_humanref_toe_flat

- **task/run**: `2026-06-29_05-33-10_humanref_toe_flat`  ·  **명령**: `(미기록)`
- **의도/변경점**: v5 = **HumanRefToe** = human-ref + base_height + ★ **toe_load_stance**(toe push-off windlass, 사용자 flagged toe). warm-start from v4. toe_load = terminal-stance(반대발 swing+전진+contact age>0.15s)서 passive toe 스프링토크 보상.

## 1. 재현성 (Reproducibility)
- **OBS**: base_lin_vel(3)+base_ang_vel(3)+projected_gravity(3)+velocity_commands(3)+joint_pos(14)+joint_vel(14)+last_action(12)+height_scan(187) = 239 dims; enable_corruption=obs noise
- **Output(action)**: 12 actuated joint position targets (hip pitch/roll/yaw, knee, ankle pitch/roll x2); passive toe excluded
- **사용 파일(백업: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_05-33-10_humanref_toe_flat/repro/`)**:
  - robstride_biped.yaml  <-  pygmalion_locomotion/assets/robot_specs/robstride_biped.yaml
  - robot.xml  <-  pygmalion_locomotion/assets/biped_lower_body_mjcf/robot.xml
  - velocity_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/velocity_env_cfg.py
  - flat_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/flat_env_cfg.py
  - curriculums.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/curriculums.py
  - rsl_rl_ppo_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/agents/rsl_rl_ppo_cfg.py
- **체크포인트**: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_05-33-10_humanref_toe_flat/model_1499.pt`

## 2. 지표 (Metrics)
- **최종 Mean reward**: 65.78 (iter 1499), max 66.00
- **error_vel_xy**: 0.3049
- **error_vel_yaw**: 0.3312

![reward curve](assets/2026-06-29_05-33-10_humanref_toe_flat_reward.png)

## 2b. Reward (이름 · 값 · 무엇 · 왜)
이 run의 **활성 보상 항 전체** — 이름 · 가중치(값) · 최종 기여 · 무엇인지 · 왜 줬는지 (규칙, user 2026-06-29). 의미 누적 추적: [[04_reward_experiments]].

| Reward | 가중치 | 기여(final) | 무엇 | 왜 |
|---|--:|--:|---|---|
| `track_ang_vel_z_exp` | +2 | +1.7981 | 명령 각속도(yaw) 추종 exp | 작업 목표: 방향 전환 추종 |
| `track_lin_vel_xy_exp` | +1 | +0.8996 | 명령 선속도(x,y) 추종 exp | 작업 목표: 원하는 속도로 보행 |
| `gait_reference_tracking` | +1 | +0.7643 | 사람 gait reference 관절각 추종(contact-phase) | ★ 인간형 gait shape(까치발/shuffle 격파) |
| `toe_load_stance` | +0.5 | +0.0942 | terminal stance toe 하중 보상 | ★ push-off windlass(toe 적시 사용) |
| `joint_deviation_hip` | -0.1 | -0.0713 | hip 중립 이탈 penalty | hip 자세 안정(과회전 억제) |
| `flat_orientation_l2` | -1 | -0.0652 | 몸통 수평(중력 proj) penalty | 몸통 똑바로 유지 |
| `action_rate_l2` | -0.01 | -0.0363 | action 변화율 penalty | 급격한 명령 변화 억제 = smooth |
| `dof_acc_l2` | -3e-07 | -0.0282 | 관절 가속도 L2 penalty | 고주파 진동(떨림) 억제 = smooth |
| `foot_landing_vel` | -1 | -0.0211 | 착지 순간 수직속도 penalty | 부드러운 착지(충격 저감) |
| `feet_slide` | -0.1 | -0.0186 | 접지 발 미끄러짐 penalty | 발 고정(slip 방지) |
| `ang_vel_xy_l2` | -0.05 | -0.0159 | roll/pitch 각속도 penalty | 몸통 흔들림 억제 |
| `dof_pos_limits` | -1 | -0.0054 | 관절 한계 근접 penalty | ROM 끝 회피(HW 보호) |
| `foot_impact_force` | -0.005 | -0.0031 | 발 접지력 초과분 penalty | 저충격 착지(HW 파손 보호) |
| `dof_torques_l2` | -1.5e-07 | -0.0025 | 관절 토크 L2 penalty | 에너지/토크 절감(과사용 억제) |
| `base_height` | -1 | -0.0003 | 몸통 높이 목표(0.85) L2 penalty | ★ 다리 신전(까치발) 방지 = 근본 자세제약(gaitfix) |
| `termination_penalty` | -200 | +0.0000 | 조기 종료(낙상) penalty | 넘어짐 회피 |
| `lin_vel_z_l2` | +0 | +0.0000 | 수직 속도 penalty | 상하 bounce 억제(보통 0으로 끔) |
| `feet_air_time` | +0 | +0.0000 | 발 공중(또는 single-stance) 시간 보상 | 보폭/스텝 유도(threshold 미달 시 dead) |

**이번 run 중요/신규 reward + 왜**: ★ **toe_load_stance(+0.5)** = passive toe를 push-off(terminal stance)서 하중 = windlass(사용자 flagged toe). 결과(§5): toe 굽힘 **0.075→0.108 rad↑**(toe 사용 증가) but 최대굽힘 위상 35/79%(push-off 아님) = 타이밍 미해결. base_height 유지(0.859, 까치발 안 돌아옴).

## 2c. 학습 건강도 (TensorBoard: loss·수렴·낙상·보상항)
![tb](assets/2026-06-29_05-33-10_humanref_toe_flat_tensorboard.png)

- **수렴(noise_std)**: 0.24 → **0.21** (정체 ~)
- **mean_reward**: 0.9 → **65.8**, ep_len 최종 **1000**
- **추종 error_vel_xy**: 최종 **0.305** (낮을수록 good), yaw 0.331
- **안정성 낙상률 0%** (base_contact 0.00 / time_out 5.33) (안정 ✅)
- **value loss 최종** 0.006, entropy -4.722, LR 7.6e-05
- **커리큘럼 vx 상한 최종** nan
- 정성 해석: reward **65.8(최고)**·낙상 0%·noise_std 0.24→0.21 수렴 = 건강·안정(단 절뚝). base 0.859(까치발 fix 유지). toe 사용↑이나 절뚝(asym 0.83)·CoT↑ → §5.

## 3. 영상 / 이미지
- 학습 영상 24개: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_05-33-10_humanref_toe_flat/videos/train/` (예: rl-video-step-0.mp4 … rl-video-step-9000.mp4)
- **누적(step-captioned) 영상 — 노트에서 재생** (vault 복사본):
![[2026-06-29_05-33-10_humanref_toe_flat_accumulate.mp4]]
  (원본 참조 `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_05-33-10_humanref_toe_flat/videos/accumulated_progress.mp4`, 77MB)

## 4. 부모 학습 대비 비교
- **부모**: `2026-06-29_03-43-21_humanref_baseh_flat`
- **변경된 설정(velocity_env_cfg diff)**:
  - vs v4(humanref_baseh): **+toe_load_stance(+0.5)**.
- reward 곡선 비교: 위(부모 점선). **정량 비교 vs v4**: toe 굽힘 0.075→**0.108↑**(toe_load 효과), but 절뚝 0.87→0.83(미해결)·CoT 1.54→**1.69↑**(에너지)·타이밍 push-off 아님. = toe 강도만 개선.

## 5. 분석 — toe_load: toe 사용↑ but 타이밍·절뚝 미해결
**정량**: base **0.859**(까치발 fix 유지 ✅) · toe 굽힘 **0.108/0.130 rad**(v4 0.075/0.084↑ = toe_load 효과 ✅) · 단 **toe 최대굽힘 위상 35/79%**(push-off ~50-60% 아님 = windlass 타이밍 미정렬) · ★ **절뚝 asym 0.83**(GRF L4308/R3655N≈8×BW) · ankle_pitch 256%(포화) · CoT 1.69(에너지↑) · score 0.03.
★ **결론**: toe_load는 toe **굽힘 강도**는 키웠으나(windlass 일부), **타이밍(push-off)은 contact-phase 게이트가 실제 cycle과 어긋나 미정렬**. 지배적 잔여문제 = **절뚝**(학습된 것, 로봇 비대칭 아님). → v6(대칭 warm-start) 시도→실패(cross-robot 붕괴) → **v7 = symmetry augmentation**(데이터 미러로 대칭 강제).
**정성**: 까치발 없는 보행 + toe 굽힘, 단 좌우 비대칭(절뚝) 지속.

## 6. 관련 학습 / 연구 링크
- 관련 run: [[experiments/2026-06-29_03-43-21_humanref_baseh_flat]](v4 parent) → [[experiments/2026-06-29_07-02-04_humanref_v6sym_flat]](v6 대칭시도, 실패).
- 활용 연구: [[2026-06-29_human_gait_reference]](human-ref·toe_load) · [[2026-06-29_tiptoe_regression]](base_height).
- ★ 피드백: toe_load=toe 강도↑이나 **절뚝이 핵심 잔여문제** → symmetry augmentation(v7).

## 7. 모터 활용 시각화 (사후 — 토크·속도 RMS/p95/peak·스펙선·포화%·시계열)
*스펙선(rated/peak/velocity-limit)은 이 run의 config(감속비·effort/vel)에서 자동.*

**관절 토크 RMS/p95/MAX vs rated(연속/열)·peak 가로선 + 포화%**
![torque](assets/2026-06-29_05-33-10_humanref_toe_flat_torque.png)

**관절 속도 RMS/p95/MAX(rpm) vs 속도한계 가로선 + 포화%**
![speed](assets/2026-06-29_05-33-10_humanref_toe_flat_speed.png)

**관절 토크 시계열 (시간에 따른 토크 활용, peak/rated 선)**
![torque_ts](assets/2026-06-29_05-33-10_humanref_toe_flat_torque_ts.png)

**관절 속도 시계열 (시간에 따른 속도 활용, limit 선)**
![speed_ts](assets/2026-06-29_05-33-10_humanref_toe_flat_speed_ts.png)

- 정량 해석: base 0.859·**ankle_pitch 256%rated 포화**·ankle_roll 98%. GRF 양발 spike(L4308/R3655N≈8×BW = 절뚝+고충격). toe 사용 0.10-0.13rad(windlass 강도↑). → 절뚝(symmetry)·에너지(power_cot) 해결 후 발목 사이징 재측정해야 유효.

