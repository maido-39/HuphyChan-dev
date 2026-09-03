# 모니터링 로그 — forefoot_cop (실시간 중간검토)

> [!info] run / 가설 / 방법
> **run**: `2026-06-21_12-22-03_forefoot_cop` · warm-start stage-3(model_2499) · Flat-Forefoot-v0(CoP 0.5 + power_cot 0.4).
> **H-A**: 간접 CoP/앞발진행 + power-CoT 보상이 종말기 **앞발 GRF비율↑(toe 적재)** 을 *static-curl 없이* 유도하고 ankle/knee peak τ·CoT↓ 하는가?
> **방법**: `watch_run.sh` 주기형 watcher(~25분)가 스냅샷 → 매번 [[27_training_review_loop]] 체크리스트로 정량/정성 검토 후 **이 노트에 append**. 보수적(DO-NOT-STOP transients).

## 정량 로그 (스냅샷마다 append)
| 시각 | iter | reward | noise_std | error_vel | ep_len | 낙상 | vx | forefoot_cop | 판정 |
|---|---|---|---|---|---|---|---|---|---|
| 12:40 | 124 | 40.5 | 0.29 | 0.47 | 996 | ~1% | 1.24 | 0.0062 | CONTINUE |
| 13:00 | 385 | 42.27 | 0.27 | 0.48 | 1000 | <1% | 1.62 | 0.0075 | CONTINUE |
| 13:25 | 775 | 39.46 | 0.27 | 0.55 | 989 | <1% | 2.00 | 0.0078 | CONTINUE |
| 13:58 | 1230 | 40.45 | 0.28 | 0.53 | 1000 | **0%** | 2.00 | 0.0070 | CONTINUE |
| 14:24 | 1685 | 40.02 | 0.28 | 0.55 | 988 | <1% | 2.00 | 0.0073 | CONTINUE |
| 14:49 | 2010 | 40.89 | 0.27 | 0.55 | 993 | <1% | 2.00 | ~0.007 | CONTINUE |

*iter 1685 — 안정 고원 유지(수렴), 모든 지표 평탄. H-A 여전 음성(forefoot_cop 0.0073). 완주(ETA ~15:25) 대기 → 측정+정식판정+가중↑ 실험.*

## 정성 분석 (유의미 항목)
- **iter 124** — warm-start 초반 0.24 reward가 **40으로 회복** = docs/27 **DO-NOT-STOP #1(warm-start dip)** 정확히 일치. 안 멈춘 게 옳았음. 전 지표 건강(낙상 1%·noise_std 매끈·value_loss 0.012).
- **iter 385** — 안정 수렴, 커리큘럼 vx 1.24→1.62 램핑. reward 42(parent 36 초과 = CoP+power_cot 가산). forefoot_cop 미미하나 초기라 판단 보류.
- **iter 775** — reward 42→**39.5**·error_vel 0.48→**0.55** 소폭 dip = **커리큘럼 vx가 2.0 도달**(명령 최대난이도)한 **DO-NOT-STOP #4(curriculum step)** = 정상. ep_len 989·낙상<1%·noise_std 0.27 안정 → 건강.
  - ★ **H-A 약화 신호**: `forefoot_cop` 0.0062→0.0075→**0.0078 평탄**. vx 2.0 도달·gait 정착 후에도 toe 적재가 안 늘어남(보상의 ~0.02%로 gradient 미약). **다음 스냅샷이 결정점**.
- **iter 1230 (★결정점)** — reward 39.5→**40.45 회복**(iter 775 dip이 #4 커리큘럼 transient였음 확정), 낙상 **0%**·noise_std 0.28·ep_len 1000 = 완전 건강·수렴. `forefoot_cop` 0.0078→**0.0070**(평탄·소폭↓), `power_cot`↑.

## ★ H-A 중간판정 (iter 1230): 음성 (이 설정)
**판정: 간접 CoP 보상(weight 0.5)은 toe를 적재시키지 못함.** vx 2.0·gait 정착·낙상 0%에도 forefoot_cop이 ~0.007로 평탄 = 정책이 *앞발 굴림 없이* 속도추종+에너지효율 gait를 찾음. 원인: forefoot_cop이 총보상의 ~0.018%라 gradient가 지배 항에 묻힘.
**결정**: 이 run은 **건강·수렴이라 완주**(docs/27 REFINE-next = "let it finish") → 깨끗한 baseline + HW 측정 확보. **다음 실험 refine 후보**:
1. **forefoot_cop 가중 0.5→~2.5** (CoP gradient 강화) — 가장 싸고 빠른 다음 rung, 먼저.
2. **Siekmann 주기 foot-force 보상** (phase별 종말기 앞발 force 강제 — 원리적, 우리 GRF 직결, [[26_reading_list]] T1) — 1이 안 되면.
3. **H3 heel-rise** (ankle-pitch 종말기 참조, 능동발목=합법) + Schumacher 'pain'(GRF/관절한계) 병행 검토.

## ★ 완주(iter 2500) + H-A 정식판정 = 음성 (측정 clip/unclip)
| 관절 | forefoot RMS/max | stage-3 RMS/max | 해석 |
|---|---|---|---|
| **toe (L/R)** | 0.8/6.0 · 1.4/14.1 | 0.7/8.6 · 1.9/8.9 | **거의 불변 = toe 미적재 확정** |
| ankle_pitch | 12.6/46.9 | 9.3/43.2 | ↑ (toe 아닌 발목으로) |
| knee | 35.1/198.5 | 58.0/165.6 | RMS↓ (power_cot 효과) |
| ankle_roll | 5.7/14.0 | 7.6/14.0 | RMS↓ |

- **판정**: `forefoot_cop@0.5`는 toe를 적재 못함. power_cot(에너지)가 knee·ankle_roll **연속토크는** 줄였으나(ankle_roll RMS%rated **151→113%** 개선) toe는 아님.
- **진단(핵심)**: forefoot_cop(게이트된 앞발 GRF비율)이 본질적으로 작음(총보상 ~0.02%) → **가중↑만으로 부족할 가능성**(형식 한계). Kuo 캐논: toe는 **push-off 일**의 부산물 → 다음에 push-off-work 보상 검토.
- **다음 실험**: ① forefoot_cop 0.5→4.0 (가중 가설 테스트, 지금) → 부족 시 ② **ankle push-off 일 보상**([[Paperreview/kuo-donelan-dynamic-walking]]) / Siekmann 주기 foot-force.

관련: [[27_training_review_loop]] · [[25_dayplan_2026-06-21]] · [[23_toe_use_methods]] · [[Paperreview/kuo-donelan-dynamic-walking]]


## 1b. forefoot_cop_monitor Reward & Gains (config에서 파싱 — 재현용)

**Reward 항목** (weight·왜·어떻게):

| reward | weight | 왜 | 어떻게 |
|---|--:|---|---|
| termination_penalty | **-200** | - | - |
| feet_distance | **-2** | - | - |
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

**§1b-2. 액추에이터 동역학·한계** (이 런의 `params/env.yaml` 파싱 — `2026-06-21_12-22-03_forefoot_cop`)

| 관절 그룹 | 모터 | Kp [N·m/rad] | Kd [N·m·s/rad] | effort 한계 [N·m] | 무부하 속도 [rad/s] | 로터 관성 armature [kg·m²] | 쿨롱 마찰 [N·m] | 점성 [N·m·s/rad] | T-N 곡선 |
|---|---|--:|--:|--:|--:|--:|--:|--:|---|
| hip_pitch, hip_roll | RS04 | 200 | 5 | 120 | 20.94 | 0.0097 | — | — | 미사용 (IsaacLab implicit actuator) |
| hip_yaw | RS03 | 150 | 5 | 60 | 23.04 | 0.0049 | — | — | 미사용 (IsaacLab implicit actuator) |
| knee | RS04 | 200 | 5 | 360 | 6.98 | 0.0875 | — | — | 미사용 (IsaacLab implicit actuator) |
| ankle_pitch | RS03 | 80 | 3 | 60 | 23.04 | 0.0049 | — | — | 미사용 (IsaacLab implicit actuator) |
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
