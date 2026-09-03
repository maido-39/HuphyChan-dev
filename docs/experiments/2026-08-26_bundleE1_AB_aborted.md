# bundleE1_AB (21:51 시도) — 리부팅으로 중단 (2026-08-26)

> *한 줄*: 수정된 하중률 항의 첫 시험. **iter 32204에서 머신 리부팅으로 죽었다.** 재실행 중.

| | |
|---|---|
| 런 | `logs/rsl_rl/pygmalion_velocity/2026-08-26_21-51-45_bundleE1_AB` |
| 계보 | `ankleAB_c3` `model_31999` → +800 iter 목표 → **32204에서 중단**(목표 32799) |
| 상태 | ❌ **미완주** — 판정에 쓰지 않는다 |
| 변인 | D1 레시피 + `PYG_SOFT_LANDING_MODE=both`(부호 수정 + 가중치 1e-4로 재교정된 `foot_loading_rate`) |

## §왜 죽었나 (재발 방지용 기록)
16384 env 학습 **2개**(E1, V4)와 ROM 영상 렌더를 동시에 돌렸다. 당시 렌더러가 프레임 전체를
메모리에 쌓는 구조였고(2514 프레임 × 1280×720×3 ≈ **7 GB**), 합계가 물리 RAM을 넘겨 스왑으로 밀렸다.
`kswapd0`가 100 %로 209분을 태운 뒤 머신이 재부팅됐다.

**조치**: ① 렌더러가 프레임을 즉시 디스크로 흘리도록 수정(피크 1.4 GB) ② **학습은 한 번에 하나만**.

<!-- SPEC-TABLES:BEGIN (analysis/run_spec_tables.py) -->

## 1b. 이 run의 Reward & Gains (config에서 파싱 — 재현용)

**Reward 항목** (weight·왜·어떻게):

| reward | weight | 왜 | 어떻게 |
|---|--:|---|---|
| foot_clearance | **-2** | 스윙발 지면 이격(발끌림 방지) | 목표 높이 오차×발 수평속도 |
| stance_knee_extension | **-2** | 입각 중 과도한 crouch 억제 | 접촉 중 \|knee\|>25 deg 초과량^2 |
| track_angular_velocity | **+2** | 명령 회전속도 추종 | exp(-err²/std²) |
| track_linear_velocity | **+2** | 명령 전진/측방 속도 추종 | exp(-err²/std²) |
| air_time | **+1** | 체공시간 보상(질질끌기 억제) | 0.05~0.5 s 체공 발 수; \|command\|>0.5에서 활성 |
| dof_pos_limits | **-1** | 관절범위 한계 벌점 | 한계초과 L1 |
| pose | **+1** | 기본 관절자세 정규화(기괴자세 억제) | default-pose L2 |
| self_collisions | **-1** | 자기충돌 벌점 | -접촉수 |
| stand_still_penalty | **-1** | 이동 명령을 무시하고 서는 stall 방지 | 명령 대비 진행률<30%이면 flat cost |
| track_lin_vel_progress | **+1** | 고속 명령에서 정지하는 local optimum 방지 | 명령방향 실제속도 투영값, 명령크기에서 cap |
| upright | **+1** | 몸통 직립 유지(넘어짐 방지) | exp 자세 |
| foot_impact_velocity | **-0.5** | 착지 직전 발 하강속도 감소 | 지면 근처 공중 발의 downward velocity^2 |
| knee_overspeed | **-0.5** | 실측 RS04 무부하 속도를 넘는 보행 억제 | relu(\|knee velocity\|-19.9)^2 |
| foot_swing_height | -0.25 | 스윙발 높이 성형 | 스윙 중 목표 높이 오차 |
| action_rate_l2 | -0.1 | 액션 급변 벌점 | -\|Δa\|² |
| foot_slip | -0.1 | 접지발 미끄러짐 벌점 | -\|v_contact\| |
| body_ang_vel | -0.05 | 몸통 각속도 벌점(흔들림 억제) | -\|ω\|² |
| angular_momentum | -0.02 | 전신 각운동량 벌점(회전 낭비 억제) | -\|L\|² |
| thermal_effort | -0.02 | ★열분배: Σ(τ/rated)² 정규화(관절 균등화) | -Σ(τ/rated)² |
| contact_force_cap | -0.01 | ★충격 cap: 발 GRF 역치초과분 벌점(사뿐착지) | -min(max(F-600,0),800) |
| foot_loading_rate | -0.0001 | - | - |
| soft_landing | -1e-05 | 착지 첫접촉 충격 벌점(약) | -첫접촉 GRF |
| torque_limit | -0 | commanded 토크 한계초과 벌점 | off(0) |

**관절별 Kp/Kd** (position-PD, effort=관절측 peak):

| 관절 | 모터 | Kp(stiffness) | Kd(damping) | effort [N·m] |
|---|---|--:|--:|--:|
| hip_pitch | RS04 | 150 | 6 | 120 |
| hip_roll | RS04 | 150 | 6 | 120 |
| hip_yaw | RS03 | 150 | 6 | 60 |
| knee | RS04 | 220 | 6 | 120 |
| crank_A | RS03 | 22.3 | 1.41 | 60 |
| crank_B | RS03 | 22.3 | 1.41 | 60 |


**§1b-2. 액추에이터 동역학·한계** (이 런의 `params/env.yaml` 파싱 — `2026-08-26_21-51-45_bundleE1_AB`)

| 관절 그룹 | 모터 | Kp [N·m/rad] | Kd [N·m·s/rad] | effort 한계 [N·m] | 무부하 속도 [rad/s] | 로터 관성 armature [kg·m²] | 쿨롱 마찰 [N·m] | 점성 [N·m·s/rad] | T-N 곡선 |
|---|---|--:|--:|--:|--:|--:|--:|--:|---|
| crank_A, crank_B | RS03 | 22.266 | 1.414 | 60 (stall 59.7) | 20.94 | 0.01527 | 0.285 | 0.0223 | 실측 37점 (`PYG_TN=1`) |
| hip_yaw | RS03 | 150 | 6 | 60 (stall 59.7) | 20.94 | 0.01527 | 0.285 | 0.0223 | 실측 37점 (`PYG_TN=1`) |
| hip_pitch | RS04 | 150 | 6 | 120 (stall 120.1) | 20.94 | 0.01633 | 0.269 | 0.0095 | 실측 22점 (`PYG_TN=1`) |
| knee | RS04 | 220 | 6 | 120 (stall 120.1) | 20.94 | 0.01633 | 0.269 | 0.0095 | 실측 22점 (`PYG_TN=1`) |
| ankle_pitch / ankle_roll | (수동, 크랭크가 구동) | — | — | — | — | — | — | — | 폐루프 `equality/connect` 등식구속 |

토크는 `effort_limit`과 (있으면) 실측 T-N 곡선의 속도의존 상한 중 **작은 값**으로 클램프된다. armature/쿨롱/점성은 모터 실측값(`PYG_MOTOR_MEAS=1`)이면 실측, 아니면 카탈로그 추정치다.

**§1b-3. ROM 한계·액션 창** (모델 XML range · soft 한계 = 중심±0.5·range×0.9 (mjlab `Entity` 규약) · 액션 clip = env.yaml `actions.joint_pos.clip` · 창 = clip 폭 · default = 액션 0 자세)

**soft 한계와 액션 clip은 같은 공식이다** — `Entity.soft_joint_pos_limits`와 `pygmalion_constants.safe_target_clip()`이 둘 다 *중심 ± 0.5·range·factor*를 쓴다(각 경계에 factor를 곱하는 것이 아니다: 비대칭 관절에서 두 식이 갈린다 — knee `[0,120]`은 `[6,114]`이지 `[0,108]`이 아니다). 그래서 `PYG_SAFE_TARGET_CLIP=1`인 런에서는 두 열이 정확히 일치하고, 정책이 통과하는 클램프와 시뮬레이터가 강제하는 클램프가 하나의 계약이 된다.

모델 출처: v3/v4 printed 폐루프 **계열** — 두 XML의 관절 range는 완전히 동일하므로 아래 ROM 표는 확정이다. 다만 이 런이 v3(35.35 kg)인지 v4(31.316 kg)인지는 런에 기록이 없어 **질량은 미해석** — `pygmalion_v3_printed_loop.xml`

| 관절 | XML range [°] | soft 한계 [°] | 액션 clip [°] | 사용가능 창 [°] | default [°] | 구동 |
|---|---|---|---|--:|--:|---|
| L/R_hip_pitch_joint | [-120, 25] | [-112.8, 17.7] | n/a (구 설정: clip 없음) | 130.5 | -10.03 | 액션 |
| L/R_hip_roll_joint | [-85, 25] | [-79.5, 19.5] | n/a (구 설정: clip 없음) | 99 | 0 | 액션 |
| L/R_hip_yaw_joint | [-45, 45] | [-40.5, 40.5] | n/a (구 설정: clip 없음) | 81 | 0 | 액션 |
| L/R_knee_joint | [-120, 0] | [-114, -6] | n/a (구 설정: clip 없음) | 108 | -20.05 | 액션 |
| L_crank_A_joint | [-68.8, 68.8] | [-61.9, 61.9] | n/a (구 설정: clip 없음) | 123.8 | -17.12 | 액션 |
| L_crank_B_joint | [-68.8, 68.8] | [-61.9, 61.9] | n/a (구 설정: clip 없음) | 123.8 | -17.12 | 액션 |
| L_ankle_pitch_joint | [-50, 30] | [-46, 26] | — (수동) | — | 20.6 | 수동 |
| L_ankle_roll_joint | [-20, 20] | [-18, 18] | — (수동) | — | 0.15 | 수동 |
| R_crank_A_joint | [-68.8, 68.8] | [-61.9, 61.9] | n/a (구 설정: clip 없음) | 123.8 | -17.14 | 액션 |
| R_crank_B_joint | [-68.8, 68.8] | [-61.9, 61.9] | n/a (구 설정: clip 없음) | 123.8 | -17.14 | 액션 |
| R_ankle_pitch_joint | [-50, 30] | [-46, 26] | — (수동) | — | 20.63 | 수동 |
| R_ankle_roll_joint | [-20, 20] | [-18, 18] | — (수동) | — | 0.15 | 수동 |
| waist_yaw_joint | [-60, 60] | [-54, 54] | — (수동) | — | 0 | 수동 |
| L/R_shoulder_pitch_joint | [-180, 60] | [-168, 48] | — (수동) | — | 0 | 수동 |
| L/R_shoulder_roll_joint | [-32, 30] | [-28.9, 26.9] | — (수동) | — | 0 | 수동 |

액션 스케일 0.25 rad/단위, 오프셋 = default (`use_default_offset`). clip이 없는 구 설정에서는 정책 목표각을 시뮬레이터의 soft 한계가 사후에 잡는다 — 창은 soft 한계 폭으로 읽는다.

**§1b-4. 이 런의 스택 플래그 (`PYG_*`)**

출처: 이 노트의 실행 명령/본문에서 추출 (런처 매니페스트 미기록 — 값 없는 항목은 노트가 이름만 언급)

| 플래그 | 값 |
|---|---|
| `PYG_SOFT_LANDING_MODE` | both |

§1b의 리워드 가중치 표가 정본이다 — 플래그는 그 가중치가 어떻게 조립됐는지의 기록이다.

<!-- SPEC-TABLES:END -->

## §2 중단 시점 지표 (iter 32204, 참고용)
| | 값 |
|---|---|
| Mean reward | 83.41 |
| `error_vel_xy_mean` | 0.5156 |
| `stance_knee_deg` | 26.07° |
| **`foot_loading_rate` 기여** | **−0.0749** |
| `foot_impact_velocity` | −0.0291 |
| `fell_over` | 0.000 |

★건진 것 하나: **하중률 항이 처음으로 실제로 동작했다**(−0.0749). 이전 세 런(TRT/B2/D1)에서는
부호 버그로 정확히 0.00000이었다([[2026-08-26_human_landing_bundle]] §12). 재교정한 가중치 1e-4도
의도한 대역(무릎항 −0.033과 동급)에 들어왔다.

## §12 판정
**판정 없음** — 미완주. 동일 설정으로 재실행했고(2026-08-27 03:2x, 단독 실행) 그 노트에서 판정한다.

## §R 참조
[[2026-08-26_human_landing_bundle]] §12 · [[2026-08-26_bundleD1_AB]]
