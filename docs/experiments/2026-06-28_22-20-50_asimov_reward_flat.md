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

## 2. 지표 (Metrics)
- **최종 Mean reward**: 50.65 (iter 1499), max 51.86
- **error_vel_xy**: 0.2170
- **error_vel_yaw**: 0.2278

![reward curve](assets/2026-06-28_22-20-50_asimov_reward_flat_reward.png)

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
![tb](assets/2026-06-28_22-20-50_asimov_reward_flat_tensorboard.png)

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
![torque](assets/2026-06-28_22-20-50_asimov_reward_flat_torque.png)

**관절 속도 RMS/p95/MAX(rpm) vs 속도한계 가로선 + 포화%**
![speed](assets/2026-06-28_22-20-50_asimov_reward_flat_speed.png)

**관절 토크 시계열 (시간에 따른 토크 활용, peak/rated 선)**
![torque_ts](assets/2026-06-28_22-20-50_asimov_reward_flat_torque_ts.png)

**관절 속도 시계열 (시간에 따른 속도 활용, limit 선)**
![speed_ts](assets/2026-06-28_22-20-50_asimov_reward_flat_speed_ts.png)

- 정량 해석: ★ **ankle_pitch 243%rated 과부하**(블로그 tight ankle deviation 구동) — g1is_dm4340(191%)보다 심함. **ankle_roll 77%**(g1is 215%보다 낮음 — tight tol이 측방 shuffle 억제). knee/hip 여유. → 블로그 reward는 ankle_roll은 덜 쓰지만 **ankle_pitch를 더 과부하 + peak 충격 2배(1991N)**. = 블로그 air_time/tight-ankle은 우리 목표에 부적합. HW 사이징은 v2(plantigrade·저충격) 후 재측정해야 유효.

