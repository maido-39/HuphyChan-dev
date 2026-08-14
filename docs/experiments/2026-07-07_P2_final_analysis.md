# 학습 리포트 — 2026-07-07_05-14-13 (mjlab P2-final)

- **task/run**: `2026-07-07_05-14-13` (mjlab MuJoCo-Warp + rsl_rl PPO)
- **의도/변경점**: 2단계 커리큘럼(Phase1 깨끗한 보행 DR-off vx1.5 + Phase2 DR 램프 0→max) 최종 정책의 포괄 재분석. 직립초기·역관절0°·L/R대칭모델·air_time·hip150/6.

## 1. 재현성 (Reproducibility)
- **OBS(actor)**: base_ang_vel(3)+projected_gravity(3)+joint_pos(12)+joint_vel(12)+last_action(12)+velocity_commands(3)+height_scan+gait_clock(2) (mjlab velocity cfg)
- **Output(action)**: 12 관절 위치타겟(hip p/r/y·knee·ankle p/r ×2), passive toe 제외
- **config 백업**: `logs/rsl_rl/pygmalion_velocity/2026-07-07_05-14-13/params/{env.yaml, agent.yaml}` (mjlab은 params/에 저장)
- **체크포인트**: `logs/rsl_rl/pygmalion_velocity/2026-07-07_05-14-13/model_19000.pt` (외 model_*.pt)

## 1b. P2-final Reward & Gains (config에서 파싱 — 재현용)

**Reward 항목** (weight·왜·어떻게):

| reward | weight | 왜 | 어떻게 |
|---|--:|---|---|
| foot_clearance | **-2** | 스윙발 지면 이격(발끌림 방지) | OFF(0): periodic_contact clock이 스윙 스케줄 담당→중복 |
| track_angular_velocity | **+2** | 명령 회전속도 추종 | exp(-err²/std²) |
| track_linear_velocity | **+2** | 명령 전진/측방 속도 추종 | exp(-err²/std²) |
| air_time | **+1** | 체공시간 보상(질질끌기 억제) | off(0) |
| dof_pos_limits | **-1** | 관절범위 한계 벌점 | 한계초과 L1 |
| pose | **+1** | 기본 관절자세 정규화(기괴자세 억제) | default-pose L2 |
| self_collisions | **-1** | 자기충돌 벌점 | -접촉수 |
| upright | **+1** | 몸통 직립 유지(넘어짐 방지) | exp 자세 |
| foot_swing_height | -0.25 | 스윙발 높이 성형 | OFF(0): clock이 스윙 담당→중복 제거 |
| action_rate_l2 | -0.1 | 액션 급변 벌점 | -|Δa|² |
| foot_slip | -0.1 | 접지발 미끄러짐 벌점 | -|v_contact| |
| body_ang_vel | -0.05 | 몸통 각속도 벌점(흔들림 억제) | -|ω|² |
| angular_momentum | -0.02 | 전신 각운동량 벌점(회전 낭비 억제) | -|L|² |
| thermal_effort | -0.02 | ★열분배: Σ(τ/rated)² 정규화(관절 균등화) | -Σ(τ/rated)² |
| contact_force_cap | -0.01 | ★충격 cap: 발 GRF 역치초과분 벌점(사뿐착지) | -min(max(F-600,0),800) |
| soft_landing | -1e-05 | 착지 첫접촉 충격 벌점(약) | -첫접촉 GRF |
| torque_limit | -0 | commanded 토크 한계초과 벌점 | off(0) |

**관절별 Kp/Kd** (position-PD, effort=관절측 peak):

| 관절 | 모터 | Kp(stiffness) | Kd(damping) | effort [N·m] |
|---|---|--:|--:|--:|
| hip_pitch | RS04 | 150 | 6 | 120 |
| hip_roll | RS04 | 150 | 6 | 120 |
| hip_yaw | RS03 | 150 | 6 | 60 |
| knee | RS04 | 400 | 8 | 120 |
| ankle_pitch | RS03 | 28.5 | 1.81 | 90 |
| ankle_roll | RS00 | 28.5 | 1.81 | 50 |

## 2. 지표 (Metrics)
- **최종 Mean reward**: 69.63 (iter 19997), max 88.52
- **error_vel_xy**: 1.352 · **error_vel_yaw**: 0.572
- **낙상률(fell_over/low_base 최종)**: 0.000 / 0.208

![[2026-07-07_05-14-13_reward.png]]

## 2b. Reward 기여 (이름 · 값 · 기여 · 무엇 · 왜)
| Reward | 가중치 | 기여(final) | 무엇/왜 |
|---|--:|--:|---|
| `track_angular_velocity` | +2 | +1.5433 | 명령 회전속도 추종 |
| `upright` | +1 | +0.9808 | 몸통 직립 유지(넘어짐 방지) |
| `track_linear_velocity` | +2 | +0.9257 | 명령 전진/측방 속도 추종 |
| `air_time` | +1 | +0.6297 | 체공시간 보상(질질끌기 억제) |
| `pose` | +1 | +0.5532 | 기본 관절자세 정규화(기괴자세 억제) |
| `action_rate_l2` | -0.1 | -0.4488 | 액션 급변 벌점 |
| `contact_force_cap` | -0.01 | -0.2044 | ★충격 cap: 발 GRF 역치초과분 벌점(사뿐착지) |
| `foot_clearance` | -2 | -0.1331 | 스윙발 지면 이격(발끌림 방지) |
| `angular_momentum` | -0.02 | -0.1258 | 전신 각운동량 벌점(회전 낭비 억제) |
| `thermal_effort` | -0.02 | -0.1156 | ★열분배: Σ(τ/rated)² 정규화(관절 균등화) |
| `dof_pos_limits` | -1 | -0.0211 | 관절범위 한계 벌점 |
| `foot_slip` | -0.1 | -0.0162 | 접지발 미끄러짐 벌점 |
| `foot_swing_height` | -0.25 | -0.0099 | 스윙발 높이 성형 |
| `self_collisions` | -1 | -0.0061 | 자기충돌 벌점 |
| `body_ang_vel` | -0.05 | -0.0037 | 몸통 각속도 벌점(흔들림 억제) |
| `soft_landing` | -1e-05 | -0.0004 | 착지 첫접촉 충격 벌점(약) |
| `torque_limit` | -0 | +0.0000 | commanded 토크 한계초과 벌점 |

## 2c. 학습 건강도 (reward·수렴·추종·낙상)
![[2026-07-07_05-14-13_tensorboard.png]]

- reward 1.1→**69.6**(수렴) · ep_len 최종 993 · 추종 vx 1.352/yaw 0.572 · 낙상 fell 0.00/low_base 0.21

## 5. 분석
in-range(vx±1.5·yaw±1.0) 18000스텝 다양패턴. RMS 전관절 OK, peak hip/knee 106~115%(순간클립)·ankle 2-RSU 커버. ★L/R 비대칭 잔존.

## 7. 모터 활용 시각화 (토크·속도 RMS/p95/max vs 스펙선 + 시계열)
*스펙선(rated 초록/peak·vel-limit 빨강)은 mjlab RobStride 1:1 기준.*

**관절 토크 RMS/p95/MAX vs rated·peak**
![[2026-07-07_05-14-13_torque.png]]

**관절 속도 RMS/p95/MAX(rpm) vs 속도한계**
![[2026-07-07_05-14-13_speed.png]]

**관절 토크 시계열(peak/rated 선)**
![[2026-07-07_05-14-13_torque_ts.png]]

- 정량: knee RMS 42%·ankle_pitch RMS 79%·binding(RMS>rated): 없음

## 6. 관련 학습 / 연구 링크
- 계보/게이트: [[2026-07-02_training_plan_v2]] · 최종설계점: [[2026-07-03_final_design_point]]
- 부호규약: [[2026-07-03_knee_ankle_mechanism_design]] §6b

---

## §R. 부하 선도 (signed + mjlab 한계선)
![[p2_flat_demo_loadviz.mp4]]
- signed 3평면×6관절·데이터 ×1.15·한계선 실정격(빨강=Peak·주황=Nominal·검정 TN).

---

## 0. 학습 구조 + 보행 시연 (2단계 커리큘럼)

**2단계 구조** (사용자 지시):
- **Phase 1** (iter 0–10000, `2026-07-07_01-46-23`): **DR OFF** + G1-like 속도커리큘럼(vx±1.5·vy±1.0·yaw±1.0)으로 **깨끗한 보행 형성**.
- **Phase 2** (iter 10000–20000, resume `2026-07-07_05-14-13`): **DR 램프 `dr_factor` 0→1** (push·friction·encoder·CoM 점진 주입) — 학습된 보행에 강건성 추가. 커맨드 범위 고정.

**적용된 설계 수정**: L/R 관절 range 대칭화(pygmalion.xml) · 무릎 직립 초기자세(HOME) · 역관절(하이퍼익스텐션) 0° 하드스톱 · std_walking[knee] 완화(0.35→1.2, 보행 굽힘 허용) · air_time(gait cycle) · hip 게인 150/6(G1·K-bot 질량스케일).

![[p2_flat_demo_loadviz.mp4]]
*고정 전후좌우 스윕 시연(방향 라벨·부하색). 관련: [게인 이력](../mujoco/2026-07-06_kp_kd_history.md)·[리워드 리서치](../reward_research/2026-07-06_gait_cycle_air_time.md)*

## 8. ★ Gait cycle + L/R 대칭 (18000프레임 다양패턴)

| 지표 | 값 | 판정 |
|---|--|---|
| 정지 무릎 / base | −2.4° / 0.856m | ✅ 직립(굽힘 없음) |
| 보행 무릎굽힘(p5) | L −40° / R −52° | ✅ 굽힘 회복(V4 −12° stiff 대비) |
| 역관절(하이퍼익스텐션) | max +2.6° (soft overshoot) | ✅ 거의 차단 |
| double-support | 11% | ⚠ 낮음(약간 dynamic) |
| DR 강건성 | ep_len 1000 through DR 램프 | ✅✅ push/randomization 흡수 |

**L/R 대칭 (걷는 구간 토크 RMS):**
![[p2_LR_symmetry.png]]

| 관절 | L / R (Nm) | 비대칭 |
|---|--|--|
| hip_pitch | 15.9 / 15.9 | **0%** |
| hip_roll | 24.6 / 24.7 | **0%** |
| hip_yaw | 5.9 / 5.5 | 7% |
| knee | 14.5 / 14.1 | 3% |
| ankle_pitch | 11.9 / 13.1 | 9% |
| ankle_roll | 2.9 / 3.7 | 23% |
| **평균** | | **7%** |
| 접촉 duty | L55 / R61% | 10% |

★ **핵심**: 다양패턴 평균 시 **토크 L/R 비대칭 7%**(hip 0%·knee 3% = 주요 하중은 거의 대칭). "절뚝임"의 실체 = **하중 불균형이 아니라 가벼운 운동학적 비대칭**(R 무릎이 더 굽고 R발이 더 오래 접지) + ankle_roll(저부하) 23%. **HW 부하 설계 관점엔 양호**(좌우 균형). 미관/자연스러움 개선 원하면 mirror augmentation 후속.

## 9. q–속도–토크 선도 (한계선 포함, in-range vx±1.5)
![[cmp_q_torque_scatter.png]]
![[cmp_torque_speed_scatter.png]]
![[torque_speed_P2-final.png]]
*rated(주황)·peak(빨강)·joint-range(보라)·vel-limit·mirror TN. 데이터 ×1.15. RMS(열) 전관절 OK(32~79%), peak만 hip/knee 106~115%(순간 클립)·ankle는 2-RSU 2모터 분담으로 커버(단일모터 스펙 초과는 accounting 아티팩트).*

## 10. DR 커버리지 + 밀도 contour
![[dr_coverage.png]]
![[contour_speed_torque.png]]
![[contour_q_torque.png]]
![[contour_q_speed.png]]
*in-DR vs OOD, 50%/99%/99.9% 밀도 contour. vx±1.5·yaw±1.0 in-range 측정이라 OOD 거의 없음.*

## 11. 반력 wrench (3D)
![[wrench_arrows_p2_long.png]]
*관절별 6-DoF 반력 화살표(힘·모멘트). ankle_roll축 radial(수직 GRF)·knee 압축 방향 = [모터 소싱 노트](../mujoco/2026-07-05_ankle_roll_small_motor_sourcing.md) FEA 하중케이스 입력.*

## 12. 종합 판정
- ✅ **목표 달성**: 직립 자세·무릎 보행굽힘·역관절 차단·gait cycle·DR 강건성(ep_len 1000)·L/R 하중 대칭(7%).
- ⚠ **잔존**: 운동학적 L/R 비대칭(무릎 flex·접촉 duty), double-support 11%(약간 dynamic) — 하중 무관, 미관 개선 후보(mirror aug).
- HW: RMS 전관절 정격 이내, peak hip/knee 순간 클립(RS04 106~115%)·ankle 2-RSU 커버 = [설계점](../mujoco/2026-07-03_final_design_point.md) 스토리 재확인. GRF P99 1.28×BW.
