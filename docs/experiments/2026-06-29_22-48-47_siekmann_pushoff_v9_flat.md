# 학습 리포트 — 2026-06-29_22-48-47_siekmann_pushoff_v9_flat

- **task/run**: `2026-06-29_22-48-47_siekmann_pushoff_v9_flat`  ·  **명령**: `(미기록)`
- **의도/변경점**: **[작성 필요]**

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

## 2. 지표 (Metrics)
- **최종 Mean reward**: 84.05 (iter 1499), max 84.62
- **error_vel_xy**: 0.2991
- **error_vel_yaw**: 0.2237

![reward curve](assets/2026-06-29_22-48-47_siekmann_pushoff_v9_flat_reward.png)

## 2b. Reward (이름 · 값 · 무엇 · 왜)
이 run의 **활성 보상 항 전체** — 이름 · 가중치(값) · 최종 기여 · 무엇인지 · 왜 줬는지 (규칙, user 2026-06-29). 의미 누적 추적: [[04_reward_experiments]].

| Reward | 가중치 | 기여(final) | 무엇 | 왜 |
|---|--:|--:|---|---|
| `track_ang_vel_z_exp` | +2 | +1.8834 | 명령 각속도(yaw) 추종 exp | 작업 목표: 방향 전환 추종 |
| `periodic_contact` | +1.5 | +1.2268 | Siekmann 주기 contact-schedule: stance엔 발 정지·swing엔 발 이지(공유 clock) | ★ heel→toe-off 리듬 legislate = 까치발·절뚝·충격 동시해결(reference-free) |
| `track_lin_vel_xy_exp` | +1 | +0.9025 | 명령 선속도(x,y) 추종 exp | 작업 목표: 원하는 속도로 보행 |
| `ankle_pushoff_work` | +0.5 | +0.3752 | [작성 필요] | [작성 필요] |
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

**이번 run 중요/신규 reward + 왜**: **[작성 필요]** — 추가·변경한 항과 그 이유 (어떤 측정/[[Paperreview/...]]·docs 연구가 근거인지). 예: `torque_soft_limit_ankle` 추가 → 포화 발목 offload(docs/17·22).

## 2c. 학습 건강도 (TensorBoard: loss·수렴·낙상·보상항)
![tb](assets/2026-06-29_22-48-47_siekmann_pushoff_v9_flat_tensorboard.png)

- **수렴(noise_std)**: 0.15 → **0.11** (수렴 ✅)
- **mean_reward**: 0.9 → **84.0**, ep_len 최종 **1000**
- **추종 error_vel_xy**: 최종 **0.299** (낮을수록 good), yaw 0.224
- **안정성 낙상률 0%** (base_contact 0.00 / time_out 11.12) (안정 ✅)
- **value loss 최종** 0.003, entropy -11.800, LR 1.1e-04
- **커리큘럼 vx 상한 최종** nan
- 정성 해석 **[작성 필요]**: noise_std 추세(↓수렴/↑탐색)·value loss·낙상률·error_vel로 *학습이 잘 됐나* + *다음 튜닝*(예: 미수렴이면 iter↑/지형커리큘럼/명령범위↓).

## 3. 영상 / 이미지
- 학습 영상 24개: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_22-48-47_siekmann_pushoff_v9_flat/videos/train/` (예: rl-video-step-0.mp4 … rl-video-step-9000.mp4)
- **누적(step-captioned) 영상 — 노트에서 재생** (vault 복사본):
![[2026-06-29_22-48-47_siekmann_pushoff_v9_flat_accumulate.mp4]]
  (원본 참조 `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-29_22-48-47_siekmann_pushoff_v9_flat/videos/accumulated_progress.mp4`, 82MB)

## 4. 부모 학습 대비 비교
- **부모**: `2026-06-29_13-00-01_siekmann_v8_flat`
- **변경된 설정(velocity_env_cfg diff)**:
  - (부모 repro 백업 없음 → 수동 기재 **[작성 필요]**)
- reward 곡선 비교: 위 그래프(부모 점선). **정량 비교 [작성 필요]**: 무엇이 좋아졌나/나빠졌나.

## 5. 분석 (정성/정량)  **[작성 필요]**
- 정량 (★표준 모터분석 `bash scripts/analyze_run.sh <tag> <clip.npz> [unclip.npz]`): **토크 활용률(% 정격/peak)** + **최대회전 속도(% 속도한계)·토크-속도 작동점** + **연결부 구조하중(|F|/|M|)** + gait(추종·CoT)·toe 사용도·진동(>5Hz)·낙상.
- 정성: 보행 자연스러움·실패모드·의도한 변경의 효과.

## 6. 관련 학습 / 연구 링크  **[작성 필요]**
- 관련 run: [[experiments/<run>]] — *어떤 관계, 무엇을 바꿨고 왜*.
- 활용 연구: [[Paperreview/<slug>]] / docs/16·17·18 — *어떤 결정에 썼는지*.

## 7. 모터 활용 시각화 (사후 — 토크·속도 RMS/p95/peak·스펙선·포화%·시계열)
*스펙선(rated/peak/velocity-limit)은 이 run의 config(감속비·effort/vel)에서 자동.*

**관절 토크 RMS/p95/MAX vs rated(연속/열)·peak 가로선 + 포화%**
![torque](assets/2026-06-29_22-48-47_siekmann_pushoff_v9_flat_torque.png)

**관절 속도 RMS/p95/MAX(rpm) vs 속도한계 가로선 + 포화%**
![speed](assets/2026-06-29_22-48-47_siekmann_pushoff_v9_flat_speed.png)

**관절 토크 시계열 (시간에 따른 토크 활용, peak/rated 선)**
![torque_ts](assets/2026-06-29_22-48-47_siekmann_pushoff_v9_flat_torque_ts.png)

**관절 속도 시계열 (시간에 따른 속도 활용, limit 선)**
![speed_ts](assets/2026-06-29_22-48-47_siekmann_pushoff_v9_flat_speed_ts.png)

- 정량 해석 **[작성 필요]**: 포화 top 관절(토크/속도 %) — ★ **RMS%rated(연속/열) · p95%peak(지속) · max%peak(순시) 따로** 판정 + 시계열 피크 타이밍·L/R 비대칭 → 어느 모터 키우고/감속비 바꿀지(HW 사이징).

