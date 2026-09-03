# 모니터링 로그 — forefoot_pushoff2 (수정된 Kuo push-off)

> [!info] run / 가설 / 수정
> run `2026-06-21_16-30-58_forefoot_pushoff2` · warm-start forefoot model_2499 · **ankle_pushoff_work w0.5·scale0.02·cap80**(이전 w1.0·scale0.1·cap無가 reward-HACK→reward 324) + power_cot0.4 + forefoot_cop(진단). H-A 테스트 #3 (Kuo push-off 일 = 인과 타깃, [[Paperreview/kuo-donelan-dynamic-walking]]·[[29_natural_gait_reward_hw]]).

## 정량 로그
| 시각 | iter | reward | noise_std | error_vel | ep_len | 낙상 | ankle_pushoff | 판정 |
|---|---|---|---|---|---|---|---|---|
| 16:55 | 190 | 43.08 | 0.26 | 0.48 | 1000 | 0% | 0.029 | CONTINUE |
| 17:30 | 580 | 42.39 | 0.27 | 0.52 | 1000 | 0% | 0.042 | CONTINUE |

*iter 580 — 건강(reward 42·error_vel 0.52·낙상 0%). ★ ankle_pushoff 0.029→0.042 증가(forefoot_cop ~6배) = push-off가 cause-reward로 작동, 정책이 더 미는 중. 완주 측정서 toe 적재+발목 전이 확인 예정.*

## 정성 + verify_run.sh (디버깅 루프)
- **수정 성공**: iter 190서 reward 43·error_vel 0.48·낙상 0% = **정상**(해킹 run은 같은 iter서 324/1.56). scale0.02+cap이 해킹 차단.
- **`verify_run.sh` 확인**: env_spacing **15.0** ✅·accumulate ✅·전 reward(ankle_pushoff·power_cot·forefoot_cop·dof_acc·track) ✅ — 이 run에 기능 반영 확정.
- **★ H-A 호전**: `ankle_pushoff` **0.029**(forefoot_cop 0.005의 ~5배) + **증가 중** = push-off가 forefoot_cop보다 강한 신호, 정책이 반응. (forefoot_cop은 평탄했음.)
- **영상 nit**: 로봇 1대(15-20→1 개선)지만 origin_type="env"라 robot이 걸어가며 화면 가장자리로 밀림 → **asset_root 추종으로 중앙고정** 필요(다음 run 수정+verify).

## 다음 추적
ankle_pushoff 지속 증가 + toe 적재(측정서 toe RMS·앞발 GRF) + **발목으로 부하 전이**(연구 예측) 확인. reward 폭주/추종저하 감시(보수적).

관련: [[27_training_review_loop]] · [[29_natural_gait_reward_hw]] · [[2026-06-21_12-22-03_forefoot_cop_monitor]]


## 1b. forefoot_pushoff2_monitor Reward & Gains (config에서 파싱 — 재현용)

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
| ankle_pushoff | **+0.5** | - | - |
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

**§1b-2. 액추에이터 동역학·한계** (이 런의 `params/env.yaml` 파싱 — `2026-06-21_16-30-58_forefoot_pushoff2`)

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
