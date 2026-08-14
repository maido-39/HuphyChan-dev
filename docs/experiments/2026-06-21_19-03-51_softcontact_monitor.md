# 모니터링 로그 — softcontact (충격↓ HW 생존)

> [!info] run / 가설 / 동기
> run `2026-06-21_19-03-51_softcontact` · warm-start pushoff3 model_500 · 16384env.
> **동기(측정 기반)**: forefoot_cop·pushoff3 측정서 **충격 = 링크 reaction wrench 5~6.7kN (체중 13배)** = 3D프린트+Al HW 파손한계(1.5kN)의 **4배**. push-off는 toe 적재도 못 늘림(5.7/19.7%). → 충격을 직접 줄여야 HW 생존.
> **H-A(가설)**: `foot_landing_vel`(w-2.0, height<0.12서 발 하강속도 벌점 = 충격의 *원인*) + `foot_impact_force`(w-0.01, contact force>650 soft-cap) → **구조하중 peak이 <1.5kN로 하락**, 보행·추종 유지. ([[Paperreview/kuo-donelan-dynamic-walking]] collision, [[29_natural_gait_reward_hw]])

## 정량 로그
| 시각 | iter | reward | noise_std | error_vel | ep_len | 낙상 | landing_vel | impact_force | 판정 |
|---|---|---|---|---|---|---|---|---|---|
| (config-test) | 40 | 15.5 | — | 0.82 | — | — | -0.21 | -0.45 | 회복·항 작동 |

## 정성 + 디버깅
- config-test(40iter): reward 음수→+15 회복, 새 항 작동(landing_vel -0.21·impact_force -0.45), 크래시 없음. error_vel 0.7-0.8(push-off 0.5보다↑ = 페널티 trade-off, 수렴 추적 필요).
- ★ **핵심 발견**: HW 파손력 6.7kN은 **링크 reaction wrench(구조하중)** — contact sensor(지면력)는 그보다 작아 force 벌점만으론 약함 → **착지 속도(원인) 벌점이 주 레버**.

## 진짜 판정 = 재측정
완주 후 `measure.py` → **구조하중 peak**(forefoot_cop 5.5kN/pushoff3 6.7kN 대비)이 <1.5kN로 떨어졌나 + toe 적재·추종. **안 떨어지면**: 가중치↑ 또는 **PD 컴플라이언스**(발목 강성↓+댐핑 = 기계적 흡수)로 전환.

## 다음 추적 (보수적 중단)
reward 회복 지속 + error_vel 수렴(<0.6 목표) + 낙상<5%. landing 페널티가 보행을 망가뜨리면(error_vel↑·낙상↑) 가중치 하향. [[27_training_review_loop]] · [[24_training_health_analysis]]

관련: [[2026-06-21_16-30-58_forefoot_pushoff2]] · [[29_natural_gait_reward_hw]] · [[30_knee_biomechanics]]


## 1b. softcontact_monitor Reward & Gains (config에서 파싱 — 재현용)

**Reward 항목** (weight·왜·어떻게):

| reward | weight | 왜 | 어떻게 |
|---|--:|---|---|
| termination_penalty | **-200** | - | - |
| feet_distance | **-2** | - | - |
| foot_landing_vel | **-2** | - | - |
| base_height | **-1** | - | - |
| dof_pos_limits | **-1** | 관절범위 한계 벌점 | 한계초과 L1 |
| flat_orientation_l2 | **-1** | 몸통 수평 유지 | -|proj_g_xy|² |
| track_ang_vel_z_exp | **+1** | 명령 회전속도 추종 | exp(-err²) |
| track_lin_vel_xy_exp | **+1** | 명령 전진/측방 속도 추종 | exp(-err²) |
| feet_air_time | **+0.75** | 체공시간 보상(성큼걸음) | +air_time |
| ankle_pushoff | **+0.5** | - | - |
| forefoot_cop | **+0.5** | - | - |
| no_flight | **-0.5** | - | - |
| upright | **+0.5** | 몸통 직립 유지(넘어짐 방지) | exp 자세 |
| power_cot | +0.4 | - | - |
| lin_vel_z_l2 | -0.2 | 수직속도 벌점(상하 튐 억제) | -vz² |
| feet_slide | -0.1 | 접지발 미끄러짐 벌점 | -|v_contact| |
| joint_deviation_hip | -0.1 | - | - |
| ang_vel_xy_l2 | -0.05 | 롤/피치 각속도 벌점 | -|ωxy|² |
| foot_impact_force | -0.01 | - | - |
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
