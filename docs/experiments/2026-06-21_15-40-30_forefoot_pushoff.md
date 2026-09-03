# 학습 리포트 — 2026-06-21_15-40-30_forefoot_pushoff

- **task/run**: `2026-06-21_15-40-30_forefoot_pushoff`  ·  **명령**: `(미기록)`
- **의도/변경점**: ankle_pushoff scale=0.1 = REWARD-HACKED (reward 324, error_vel 1.56) — documented FAILURE, superseded by pushoff2

## 1. 재현성 (Reproducibility)
- **OBS**: base_lin_vel(3)+base_ang_vel(3)+projected_gravity(3)+velocity_commands(3)+joint_pos(14)+joint_vel(14)+last_action(12)+height_scan(187) = 239 dims; enable_corruption=obs noise
- **Output(action)**: 12 actuated joint position targets (hip pitch/roll/yaw, knee, ankle pitch/roll x2); passive toe excluded
- **사용 파일(백업: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-21_15-40-30_forefoot_pushoff/repro/`)**:
  - robstride_biped.yaml  <-  pygmalion_locomotion/assets/robot_specs/robstride_biped.yaml
  - robot.xml  <-  pygmalion_locomotion/assets/biped_lower_body_mjcf/robot.xml
  - velocity_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/velocity_env_cfg.py
  - flat_env_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/flat_env_cfg.py
  - curriculums.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/curriculums.py
  - rsl_rl_ppo_cfg.py  <-  pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/agents/rsl_rl_ppo_cfg.py
- **체크포인트**: `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-21_15-40-30_forefoot_pushoff/model_300.pt`


## 1b. forefoot_pushoff Reward & Gains (config에서 파싱 — 재현용)

**Reward 항목** (weight·왜·어떻게):

| reward | weight | 왜 | 어떻게 |
|---|--:|---|---|
| termination_penalty | **-200** | - | - |
| feet_distance | **-2** | - | - |
| ankle_pushoff | **+1** | - | - |
| base_height | **-1** | - | - |
| dof_pos_limits | **-1** | 관절범위 한계 벌점 | 한계초과 L1 |
| flat_orientation_l2 | **-1** | 몸통 수평 유지 | -|proj_g_xy|² |
| track_ang_vel_z_exp | **+1** | 명령 회전속도 추종 | exp(-err²) |
| track_lin_vel_xy_exp | **+1** | 명령 전진/측방 속도 추종 | exp(-err²) |
| feet_air_time | **+0.75** | 체공시간 보상(성큼걸음) | +air_time |
| forefoot_cop | **+0.5** | - | - |
| no_flight | **-0.5** | - | - |
| upright | **+0.5** | 몸통 직립 유지(넘어짐 방지) | exp 자세 |
| power_cot | +0.4 | - | - |
| lin_vel_z_l2 | -0.2 | 수직속도 벌점(상하 튐 억제) | -vz² |
| feet_slide | -0.1 | 접지발 미끄러짐 벌점 | -|v_contact| |
| joint_deviation_hip | -0.1 | - | - |
| ang_vel_xy_l2 | -0.05 | 롤/피치 각속도 벌점 | -|ωxy|² |
| torque_soft_limit_ankle | -0.01 | - | - |
| action_rate_l2 | -0.005 | 액션 급변 벌점 | -|Δa|² |
| torque_soft_limit | -0.0025 | - | - |
| dof_torques_l2 | -2e-06 | 관절토크 벌점(에너지/열) | -Στ² |
| dof_acc_l2 | -1e-07 | 관절가속 벌점(부드러움) | -Σα² |

**관절별 Kp/Kd** (position-PD, effort=관절측 peak):

| 관절 | 모터 | Kp(stiffness) | Kd(damping) | effort [N·m] |
|---|---|--:|--:|--:|
| hip_pitch | RS04 | 200 | 5 | 120 |
| hip_roll | RS04 | 200 | 5 | 120 |
| hip_yaw | RS03 | 150 | 5 | 60 |
| knee | RS04 | 200 | 5 | 360 |
| ankle_pitch | RS03 | 80 | 3 | 60 |
| ankle_roll | RS00 | 40 | 2 | 14 |

<!-- SPEC-TABLES:BEGIN (analysis/run_spec_tables.py) -->

**§1b-2. 액추에이터 동역학·한계** (이 런의 `params/env.yaml` 파싱 — `2026-06-21_15-40-30_forefoot_pushoff`)

| 관절 그룹 | 모터 | Kp [N·m/rad] | Kd [N·m·s/rad] | effort 한계 [N·m] | 무부하 속도 [rad/s] | 로터 관성 armature [kg·m²] | 쿨롱 마찰 [N·m] | 점성 [N·m·s/rad] | T-N 곡선 |
|---|---|--:|--:|--:|--:|--:|--:|--:|---|
| hip_pitch, hip_roll | RS04 | 200 | 5 | 120 | 20.94 | 0.0097 | — | — | 미사용 (IsaacLab implicit actuator) |
| hip_yaw | RS03 | 150 | 5 | 60 | 20.94 | 0.0049 | — | — | 미사용 (IsaacLab implicit actuator) |
| knee | RS04 | 200 | 5 | 360 | 6.98 | 0.0875 | — | — | 미사용 (IsaacLab implicit actuator) |
| ankle_pitch | RS03 | 80 | 3 | 60 | 20.94 | 0.0049 | — | — | 미사용 (IsaacLab implicit actuator) |
| ankle_roll | RS00 | 40 | 2 | 14 | 32.99 | 0.0015 | — | — | 미사용 (IsaacLab implicit actuator) |
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

## 2b. Reward (무엇을 · 왜)
활성 보상 항과 **최종 기여**는 아래. 각 항의 **의미 · 가중치 · 왜**는 → [[04_reward_experiments]] ("현재 활성 Reward 전체" 표) 참조 (재도출 금지, 링크로 추적).
- (로그에서 보상 항목 미검출 — 학습 로그 경로 확인)

**이번 run 중요/신규 reward + 왜** (env.yaml 확인):
- **★ `ankle_pushoff` (w=1.0, scale=0.1) — 신규이자 실패 원인**: Kuo push-off 일을 직접 보상하려 했으나 **w·scale이 둘 다 과대**(정상은 w0.5·scale0.02). 이 과대값이 push-off 항을 484까지 폭주시켜 추종을 죽임(=reward-HACK). 인과 보상 의도는 옳았으나([[Paperreview/kuo-donelan-dynamic-walking]]·[[29_natural_gait_reward_hw]]) **일(work) 보상엔 cap + 작은 scale이 필수**라는 교훈(→ [[2026-06-21_16-30-58_forefoot_pushoff2]]에서 scale0.02·cap80·w0.5로 정상화).
- `forefoot_cop` w0.5·`power_cot` w0.4 등 나머지는 부모 forefoot_cop과 동일(여기선 ankle_pushoff 과대가 전부를 가림).

## 2c. 학습 건강도 (TensorBoard: loss·수렴·낙상·보상항)
![[2026-06-21_15-40-30_forefoot_pushoff_tensorboard.png]]

- **수렴(noise_std)**: 0.27 → **0.34** (미수렴·탐색↑ ⚠️ (std 증가))
- **mean_reward**: 0.7 → **484.5**, ep_len 최종 **975**
- **추종 error_vel_xy**: 최종 **1.732** (낮을수록 good), yaw 1.618
- **안정성 낙상률 6%** (base_contact 0.88 / time_out 12.62) (주의 ⚠️)
- **value loss 최종** 17.723, entropy 2.802, LR 2.6e-04
- **커리큘럼 vx 상한 최종** 1.49
- **정성 해석(★ REWARD-HACKING 실패 사례)**: reward 0.7→**484.5**(!!)인데 error_vel **1.732**(최악) = **추종을 버리고 push-off 보상만 farming**. ankle_pushoff `scale=0.1`이 너무 커서, 정책이 명령속도 추종 대신 **발목을 진동시켜 tau·omega 양수일을 긁음**(value loss **17.7**=폭주 보상에 가치함수 못 따라감). 교과서적 reward-hacking(*상관* push-off일을 직접 보상하면 게임됨, Skalse 2022 / [[23_toe_use_methods]]). 낙상 6%는 낮아 보이나 추종이 죽어 무의미. **판정: 폐기**. **수정**: scale 0.1→**0.02 + cap 80**(진동 farming 차단)+w0.5 → 자식 run에서 정상화.

## 3. 영상 / 이미지
- 학습 영상 5개: `logs/rsl_rl/pygmalion_flat/2026-06-21_15-40-30_forefoot_pushoff/videos/train/` (rl-video-step-0 … 6000).
- **누적(step-captioned) 영상 — 노트에서 재생** (vault 복사본):
![[2026-06-21_15-40-30_forefoot_pushoff_accumulate.mp4]]
  (원본 참조 `pygmalion_locomotion/logs/rsl_rl/pygmalion_flat/2026-06-21_15-40-30_forefoot_pushoff/videos/accumulated_progress.mp4`, 4MB)

## 4. 부모 학습 대비 비교
- **부모**: [[2026-06-21_12-22-03_forefoot_cop]] (CoP 진단 run).
- **변경점**: `ankle_pushoff_work` 추가, **scale=0.1**(과대) → 이 과대값이 해킹의 원인. cop 대비 reward가 0.7→484로 폭발한 게 적신호였음(정상이면 ~40대).

## 5. 분석 (정성/정량)
- **정량**: 모터 측정 불필요(해킹 run = 배포 무의미). TensorBoard만으로 진단 완료(§2c: reward 484 + error_vel 1.73 = 해킹 확정).
- **정성**: **모니터링 루프가 잡아낸 성공 사례** — iter ~190서 reward 324·error_vel 1.56 보고 즉시 중단·수정([[27_training_review_loop]]의 "reward-hacking → 보상 고치고 재시작" 케이스). 교훈: **push-off 같은 *일(work)* 보상은 반드시 cap + 작은 scale**(안 그러면 진동 farming).

## 6. 관련 학습 / 연구 링크
- 부모 [[2026-06-21_12-22-03_forefoot_cop]] → 수정 자식 [[2026-06-21_16-30-58_forefoot_pushoff2]](scale0.02+cap80, 정상).
- 연구: [[23_toe_use_methods]](직접 일-보상 = anti-pattern) · [[29_natural_gait_reward_hw]](push-off 보상 가드: cap·작은 scale) · [[27_training_review_loop]](해킹 탐지·중단).

