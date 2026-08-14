# 학습 리포트 — 2026-07-02_10-15-49 (mjlab A0-lowbase-term)

- **task/run**: `2026-07-02_10-15-49` (mjlab MuJoCo-Warp + rsl_rl PPO)  ·  **wandb**: `vay00asx`
- **의도/변경점**: ★ low_base<0.7 조기종료 도입(무릎꿇기 근본해결).

## 1. 재현성 (Reproducibility)
- **OBS(actor)**: base_ang_vel(3)+projected_gravity(3)+joint_pos(12)+joint_vel(12)+last_action(12)+velocity_commands(3)+height_scan+gait_clock(2) (mjlab velocity cfg)
- **Output(action)**: 12 관절 위치타겟(hip p/r/y·knee·ankle p/r ×2), passive toe 제외
- **config 백업**: `logs/rsl_rl/pygmalion_velocity/2026-07-02_10-15-49/params/{env.yaml, agent.yaml}` (mjlab은 params/에 저장)
- **체크포인트**: `logs/rsl_rl/pygmalion_velocity/2026-07-02_10-15-49/model_8000.pt` (외 model_*.pt)

## 1b. A0-lowbase-term Reward & Gains (config에서 파싱 — 재현용)

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

## 2. 지표 (Metrics)
- **최종 Mean reward**: 56.42 (iter 8662), max 61.49
- **error_vel_xy**: 1.872 · **error_vel_yaw**: 0.396
- **낙상률(fell_over/low_base 최종)**: 0.000 / 0.292

![[2026-07-02_10-15-49_reward.png]]

## 2b. Reward 기여 (이름 · 값 · 기여 · 무엇 · 왜)
| Reward | 가중치 | 기여(final) | 무엇/왜 |
|---|--:|--:|---|
| `track_angular_velocity` | +2 | +1.6935 | 명령 회전속도 추종 |
| `action_rate_l2` | -0.1 | -1.0063 | 액션 급변 벌점 |
| `upright` | +1 | +0.9851 | 몸통 직립 유지(넘어짐 방지) |
| `track_linear_velocity` | +2 | +0.7239 | 명령 전진/측방 속도 추종 |
| `pose` | +1 | +0.6823 | 기본 관절자세 정규화(기괴자세 억제) |
| `angular_momentum` | -0.02 | -0.1028 | 전신 각운동량 벌점(회전 낭비 억제) |
| `foot_clearance` | -2 | -0.0795 | 스윙발 지면 이격(발끌림 방지) |
| `foot_swing_height` | -0.25 | -0.0137 | 스윙발 높이 성형 |
| `foot_slip` | -0.1 | -0.0135 | 접지발 미끄러짐 벌점 |
| `dof_pos_limits` | -1 | -0.0051 | 관절범위 한계 벌점 |
| `self_collisions` | -1 | -0.0045 | 자기충돌 벌점 |
| `body_ang_vel` | -0.05 | -0.0024 | 몸통 각속도 벌점(흔들림 억제) |
| `soft_landing` | -1e-05 | -0.0004 | 착지 첫접촉 충격 벌점(약) |
| `air_time` | +0 | +0.0000 | 체공시간 보상(질질끌기 억제) |
| `torque_limit` | -0 | +0.0000 | commanded 토크 한계초과 벌점 |

## 2c. 학습 건강도 (reward·수렴·추종·낙상)
![[2026-07-02_10-15-49_tensorboard.png]]

- reward 0.0→**56.4**(수렴) · ep_len 최종 990 · 추종 vx 1.872/yaw 0.396 · 낙상 fell 0.00/low_base 0.29

## 3. 학습 진행 영상 (ACCUMULATION)
![[accum_A0-lowbase-term.mp4]]
*(iter 캡션付. 원본: `logs/rsl_rl/pygmalion_velocity/2026-07-02_10-15-49/videos/accumulated_progress.mp4`)*

## 5. 분석
기립 확보(236→0.5)·base 0.817·knee/ankle_roll 해결·ankle_pitch RMS 110% 잔존. A1 baseline·comparator.

## 7. 모터 활용 시각화 (토크·속도 RMS/p95/max vs 스펙선 + 시계열)
*스펙선(rated 초록/peak·vel-limit 빨강)은 mjlab RobStride 1:1 기준.*

**관절 토크 RMS/p95/MAX vs rated·peak**
![[2026-07-02_10-15-49_torque.png]]

**관절 속도 RMS/p95/MAX(rpm) vs 속도한계**
![[2026-07-02_10-15-49_speed.png]]

**관절 토크 시계열(peak/rated 선)**
![[2026-07-02_10-15-49_torque_ts.png]]

- 정량: knee RMS 58%·ankle_pitch RMS 127%·binding(RMS>rated): ankle_pitch

## 6. 관련 학습 / 연구 링크
- 계보/게이트: [[2026-07-02_training_plan_v2]] · 최종설계점: [[2026-07-03_final_design_point]]
- 부호규약: [[2026-07-03_knee_ankle_mechanism_design]] §6b

---

## §R. 부하 선도 (signed + mjlab 한계선)
![[regime_mjlab_A1b.png]]
- signed 3평면×6관절·데이터 ×1.15·한계선 실정격(빨강=Peak·주황=Nominal·검정 TN).
