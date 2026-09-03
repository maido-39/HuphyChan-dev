# 학습 리포트 — 2026-07-02_00-54-07 (mjlab A0a-actionscale)

- **task/run**: `2026-07-02_00-54-07` (mjlab MuJoCo-Warp + rsl_rl PPO)  ·  **wandb**: `knvyae27`
- **의도/변경점**: action_scale 0.25 첫 시도. 무릎꿇기 계보.

## 1. 재현성 (Reproducibility)
- **OBS(actor)**: base_ang_vel(3)+projected_gravity(3)+joint_pos(12)+joint_vel(12)+last_action(12)+velocity_commands(3)+height_scan+gait_clock(2) (mjlab velocity cfg)
- **Output(action)**: 12 관절 위치타겟(hip p/r/y·knee·ankle p/r ×2), passive toe 제외
- **config 백업**: `logs/rsl_rl/pygmalion_velocity/2026-07-02_00-54-07/params/{env.yaml, agent.yaml}` (mjlab은 params/에 저장)
- **체크포인트**: `logs/rsl_rl/pygmalion_velocity/2026-07-02_00-54-07/model_31000.pt` (외 model_*.pt)

## 1b. A0a-actionscale Reward & Gains (config에서 파싱 — 재현용)

**Reward 항목** (weight·왜·어떻게):

| reward | weight | 왜 | 어떻게 |
|---|--:|---|---|
| foot_clearance | **-2** | 스윙발 지면 이격(발끌림 방지) | OFF(0): periodic_contact clock이 스윙 스케줄 담당→중복 |
| track_angular_velocity | **+2** | 명령 회전속도 추종 | exp(-err²/std²) |
| track_linear_velocity | **+2** | 명령 전진/측방 속도 추종 | exp(-err²/std²) |
| dof_pos_limits | **-1** | 관절범위 한계 벌점 | 한계초과 L1 |
| pose | **+1** | 기본 관절자세 정규화(기괴자세 억제) | default-pose L2 |
| self_collisions | **-1** | 자기충돌 벌점 | -접촉수 |
| upright | **+1** | 몸통 직립 유지(넘어짐 방지) | exp 자세 |
| foot_swing_height | -0.25 | 스윙발 높이 성형 | OFF(0): clock이 스윙 담당→중복 제거 |
| action_rate_l2 | -0.1 | 액션 급변 벌점 | -|Δa|² |
| foot_slip | -0.1 | 접지발 미끄러짐 벌점 | -|v_contact| |
| body_ang_vel | -0.05 | 몸통 각속도 벌점(흔들림 억제) | -|ω|² |
| angular_momentum | -0.02 | 전신 각운동량 벌점(회전 낭비 억제) | -|L|² |
| soft_landing | -1e-05 | 착지 첫접촉 충격 벌점(약) | -첫접촉 GRF |
| air_time | +0 | 체공시간 보상(질질끌기 억제) | off(0) |
| torque_limit | -0 | commanded 토크 한계초과 벌점 | off(0) |

**관절별 Kp/Kd** (position-PD, effort=관절측 peak):

| 관절 | 모터 | Kp(stiffness) | Kd(damping) | effort [N·m] |
|---|---|--:|--:|--:|
| hip_pitch | RS04 | 27.6 | 1.76 | 120 |
| hip_roll | RS04 | 27.6 | 1.76 | 120 |
| hip_yaw | RS03 | 19.7 | 1.26 | 60 |
| knee | RS04 | 27.6 | 1.76 | 120 |
| ankle_pitch | RS03 | 19.7 | 1.26 | 60 |
| ankle_roll | RS00 | 1.97 | 0.126 | 14 |

<!-- SPEC-TABLES:BEGIN (analysis/run_spec_tables.py) -->

**§1b-2. 액추에이터 동역학·한계** (이 런의 `params/env.yaml` 파싱 — `2026-07-02_00-54-07`)

| 관절 그룹 | 모터 | Kp [N·m/rad] | Kd [N·m·s/rad] | effort 한계 [N·m] | 무부하 속도 [rad/s] | 로터 관성 armature [kg·m²] | 쿨롱 마찰 [N·m] | 점성 [N·m·s/rad] | T-N 곡선 |
|---|---|--:|--:|--:|--:|--:|--:|--:|---|
| ankle_roll | RS00 | 1.974 | 0.126 | 14 | — | 0.0005 | — | — | 미사용 (effort_limit 상수 클램프) |
| ankle_pitch | RS03 | 19.739 | 1.257 | 60 | — | 0.005 | — | — | 미사용 (effort_limit 상수 클램프) |
| hip_pitch | RS04 | 27.635 | 1.759 | 120 | — | 0.007 | — | — | 미사용 (effort_limit 상수 클램프) |
| knee | RS04 | 27.635 | 1.759 | 120 | — | 0.007 | — | — | 미사용 (effort_limit 상수 클램프) |

토크는 `effort_limit`과 (있으면) 실측 T-N 곡선의 속도의존 상한 중 **작은 값**으로 클램프된다. armature/쿨롱/점성은 모터 실측값(`PYG_MOTOR_MEAS=1`)이면 실측, 아니면 카탈로그 추정치다.

**§1b-3. ROM 한계·액션 창** (모델 XML range · soft 한계 = 중심±0.5·range×0.9 (mjlab `Entity` 규약) · 액션 clip = env.yaml `actions.joint_pos.clip` · 창 = clip 폭 · default = 액션 0 자세)

**soft 한계와 액션 clip은 같은 공식이다** — `Entity.soft_joint_pos_limits`와 `pygmalion_constants.safe_target_clip()`이 둘 다 *중심 ± 0.5·range·factor*를 쓴다(각 경계에 factor를 곱하는 것이 아니다: 비대칭 관절에서 두 식이 갈린다 — knee `[0,120]`은 `[6,114]`이지 `[0,108]`이 아니다). 그래서 `PYG_SAFE_TARGET_CLIP=1`인 런에서는 두 열이 정확히 일치하고, 정책이 통과하는 클램프와 시뮬레이터가 강제하는 클램프가 하나의 계약이 된다.

모델 출처: 이 시기 `pygmalion_constants._XML_NAME` 기본 분기 — `PYG_V2`/`PYG_HIP_CANT*`/`PYG_ROLLOFF30` 미설정 시 `pygmalion.xml`. 노트의 hip_roll 하드스톱 진술(외전 −45° / 내전 +25°)과 이 파일의 range가 일치 — `pygmalion.xml`

> ⚠ **파일 최신성 주의** — 이 XML은 런 시작(2026-07-02_00-54-07)보다 뒤인 2026-07-06 22:38에 수정되었다. 런 디렉토리에 모델 스냅샷이 없으므로 아래 range는 **현재 파일 기준**이며 런 당시와 다를 수 있다.

| 관절 | XML range [°] | soft 한계 [°] | 액션 clip [°] | 사용가능 창 [°] | default [°] | 구동 |
|---|---|---|---|--:|--:|---|
| L/R_hip_pitch_joint | [-125, 30] | [-117.2, 22.3] | n/a (구 설정: clip 없음) | 139.5 | -18.33 | 액션 |
| L/R_hip_roll_joint | [-45, 25] | [-41.5, 21.5] | n/a (구 설정: clip 없음) | 63 | 0 | 액션 |
| L/R_hip_yaw_joint | [-50, 50] | [-45, 45] | n/a (구 설정: clip 없음) | 90 | 0 | 액션 |
| L/R_knee_joint | [-140, 0] | [-133, -7] | n/a (구 설정: clip 없음) | 126 | -38.39 | 액션 |
| L/R_ankle_pitch_joint | [-50, 40] | [-45.5, 35.5] | n/a (구 설정: clip 없음) | 81 | 20.63 | 액션 |
| L/R_ankle_roll_joint | [-20, 20] | [-18, 18] | n/a (구 설정: clip 없음) | 36 | 0 | 액션 |
| L/R_toe_joint | [-50, 0] | [-47.5, -2.5] | — (수동) | — | 0 | 수동 |

액션 스케일 0.25 rad/단위, 오프셋 = default (`use_default_offset`). clip이 없는 구 설정에서는 정책 목표각을 시뮬레이터의 soft 한계가 사후에 잡는다 — 창은 soft 한계 폭으로 읽는다.

**§1b-4. 이 런의 스택 플래그 (`PYG_*`)**

> 이 런은 실행 환경 스냅샷을 남기지 않았고 노트 본문에도 `PYG_*` 언급이 없다 — **원본 설정 소실**. 리워드 가중치·게인·ROM은 위 §1b~§1b-3(런 config 파싱)이 정본이다.

<!-- SPEC-TABLES:END -->

## 2. 지표 (Metrics)
- **최종 Mean reward**: 49.46 (iter 31516), max 51.72
- **error_vel_xy**: 3.269 · **error_vel_yaw**: 0.371
- **낙상률(fell_over/low_base 최종)**: 0.000 / 0.000

![[2026-07-02_00-54-07_reward.png]]

## 2b. Reward 기여 (이름 · 값 · 기여 · 무엇 · 왜)
| Reward | 가중치 | 기여(final) | 무엇/왜 |
|---|--:|--:|---|
| `track_angular_velocity` | +2 | +1.7070 | 명령 회전속도 추종 |
| `upright` | +1 | +0.9572 | 몸통 직립 유지(넘어짐 방지) |
| `action_rate_l2` | -0.1 | -0.7485 | 액션 급변 벌점 |
| `track_linear_velocity` | +2 | +0.3508 | 명령 전진/측방 속도 추종 |
| `pose` | +1 | +0.2000 | 기본 관절자세 정규화(기괴자세 억제) |
| `angular_momentum` | -0.02 | -0.0500 | 전신 각운동량 벌점(회전 낭비 억제) |
| `foot_swing_height` | -0.25 | -0.0299 | 스윙발 높이 성형 |
| `foot_clearance` | -2 | -0.0287 | 스윙발 지면 이격(발끌림 방지) |
| `dof_pos_limits` | -1 | -0.0210 | 관절범위 한계 벌점 |
| `foot_slip` | -0.1 | -0.0055 | 접지발 미끄러짐 벌점 |
| `body_ang_vel` | -0.05 | -0.0030 | 몸통 각속도 벌점(흔들림 억제) |
| `self_collisions` | -1 | -0.0015 | 자기충돌 벌점 |
| `soft_landing` | -1e-05 | -0.0002 | 착지 첫접촉 충격 벌점(약) |
| `air_time` | +0 | +0.0000 | 체공시간 보상(질질끌기 억제) |
| `torque_limit` | -0 | +0.0000 | commanded 토크 한계초과 벌점 |

## 2c. 학습 건강도 (reward·수렴·추종·낙상)
![[2026-07-02_00-54-07_tensorboard.png]]

- reward -0.5→**49.5**(수렴) · ep_len 최종 1000 · 추종 vx 3.269/yaw 0.371 · 낙상 fell 0.00/low_base 0.00

## 3. 학습 진행 영상 (ACCUMULATION)
![[accum_A0a-actionscale.mp4]]
*(iter 캡션付. 원본: `logs/rsl_rl/pygmalion_velocity/2026-07-02_00-54-07/videos/accumulated_progress.mp4`)*

## 5. 분석
무릎꿇기 지속(low_base 236) → 종료조건 필요, A0-lowbase로 이어짐.

## 6. 관련 학습 / 연구 링크
- 계보/게이트: [[2026-07-02_training_plan_v2]] · 최종설계점: [[2026-07-03_final_design_point]]
- 부호규약: [[2026-07-03_knee_ankle_mechanism_design]] §6b
