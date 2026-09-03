# gen21_rough_uneven_p1 (중간 진단 런, iter 1900서 종료·uneven2로 대체)

> **성격**: 정식 앵커 후보가 아니라 **rough 실패진단의 1차 처방 실험**. 계단 제거는 맞았으나 슬로프를 과대(45°)로 남겨 반쯤만 성공 → 슬로프 하향한 [[2026-07-14_gen21_rough_uneven2_p1]]로 대체. 계보/근거는 [[2026-07-14_rough_p1_blind_stairs_diagnosis]].

## §1 가설·변인
- **단일변인**: `ROUGH_TERRAINS_CFG`(계단 40%) → `UNEVEN_TERRAINS_CFG`(계단 0%, PYG_UNEVEN 토글). 나머지(reward/gains/init/warm-start)는 실패한 [[2026-07-13_gen21_rough_p1]]과 동일.
- 가설: rough P1 fell 0.3 정체의 주원인이 "장님 액터 × 계단 40%"라면, 계단 제거만으로 fell이 0.3→<0.1로 떨어져야 함.

<!-- SPEC-TABLES:BEGIN (analysis/run_spec_tables.py) -->

## 1b. 이 run의 Reward & Gains (config에서 파싱 — 재현용)

**Reward 항목** (weight·왜·어떻게):

| reward | weight | 왜 | 어떻게 |
|---|--:|---|---|
| foot_clearance | **-2** | 스윙발 지면 이격(발끌림 방지) | 목표 높이 오차×발 수평속도 |
| track_angular_velocity | **+2** | 명령 회전속도 추종 | exp(-err²/std²) |
| track_linear_velocity | **+2** | 명령 전진/측방 속도 추종 | exp(-err²/std²) |
| air_time | **+1** | 체공시간 보상(질질끌기 억제) | 0.05~0.5 s 체공 발 수; \|command\|>0.5에서 활성 |
| dof_pos_limits | **-1** | 관절범위 한계 벌점 | 한계초과 L1 |
| pose | **+1** | 기본 관절자세 정규화(기괴자세 억제) | default-pose L2 |
| self_collisions | **-1** | 자기충돌 벌점 | -접촉수 |
| stand_still_penalty | **-1** | 이동 명령을 무시하고 서는 stall 방지 | 명령 대비 진행률<30%이면 flat cost |
| track_lin_vel_progress | **+1** | 고속 명령에서 정지하는 local optimum 방지 | 명령방향 실제속도 투영값, 명령크기에서 cap |
| upright | **+1** | 몸통 직립 유지(넘어짐 방지) | exp 자세 |
| knee_overspeed | **-0.5** | 실측 RS04 무부하 속도를 넘는 보행 억제 | relu(\|knee velocity\|-19.9)^2 |
| foot_swing_height | -0.25 | 스윙발 높이 성형 | 스윙 중 목표 높이 오차 |
| action_rate_l2 | -0.1 | 액션 급변 벌점 | -\|Δa\|² |
| foot_slip | -0.1 | 접지발 미끄러짐 벌점 | -\|v_contact\| |
| body_ang_vel | -0.05 | 몸통 각속도 벌점(흔들림 억제) | -\|ω\|² |
| angular_momentum | -0.02 | 전신 각운동량 벌점(회전 낭비 억제) | -\|L\|² |
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
| knee | RS04 | 220 | 6 | 120 |
| ankle_pitch | RS03 | 28.5 | 1.81 | 90 |
| ankle_roll | RS00 | 28.5 | 1.81 | 50 |


**§1b-2. 액추에이터 동역학·한계** (이 런의 `params/env.yaml` 파싱 — `2026-07-14_17-18-44_gen21_rough_uneven_p1`)

| 관절 그룹 | 모터 | Kp [N·m/rad] | Kd [N·m·s/rad] | effort 한계 [N·m] | 무부하 속도 [rad/s] | 로터 관성 armature [kg·m²] | 쿨롱 마찰 [N·m] | 점성 [N·m·s/rad] | T-N 곡선 |
|---|---|--:|--:|--:|--:|--:|--:|--:|---|
| ankle_roll | RS00 | 28.5 | 1.81 | 50 | — | 0.0005 | — | — | 미사용 (effort_limit 상수 클램프) |
| hip_yaw | RS03 | 150 | 6 | 60 | — | 0.005 | — | — | 미사용 (effort_limit 상수 클램프) |
| ankle_pitch | RS03 | 28.5 | 1.81 | 90 | — | 0.005 | — | — | 미사용 (effort_limit 상수 클램프) |
| hip_pitch | RS04 | 150 | 6 | 120 | — | 0.007 | — | — | 미사용 (effort_limit 상수 클램프) |
| knee | RS04 | 220 | 6 | 120 | — | 0.007 | — | — | 미사용 (effort_limit 상수 클램프) |

토크는 `effort_limit`과 (있으면) 실측 T-N 곡선의 속도의존 상한 중 **작은 값**으로 클램프된다. armature/쿨롱/점성은 모터 실측값(`PYG_MOTOR_MEAS=1`)이면 실측, 아니면 카탈로그 추정치다.

**§1b-3. ROM 한계·액션 창** (모델 XML range · soft 한계 = 중심±0.5·range×0.9 (mjlab `Entity` 규약) · 액션 clip = env.yaml `actions.joint_pos.clip` · 창 = clip 폭 · default = 액션 0 자세)

**soft 한계와 액션 clip은 같은 공식이다** — `Entity.soft_joint_pos_limits`와 `pygmalion_constants.safe_target_clip()`이 둘 다 *중심 ± 0.5·range·factor*를 쓴다(각 경계에 factor를 곱하는 것이 아니다: 비대칭 관절에서 두 식이 갈린다 — knee `[0,120]`은 `[6,114]`이지 `[0,108]`이 아니다). 그래서 `PYG_SAFE_TARGET_CLIP=1`인 런에서는 두 열이 정확히 일치하고, 정책이 통과하는 클램프와 시뮬레이터가 강제하는 클램프가 하나의 계약이 된다.

모델 출처: 이 시기 `pygmalion_constants._XML_NAME` 기본 분기 — `PYG_V2`/`PYG_HIP_CANT*`/`PYG_ROLLOFF30` 미설정 시 `pygmalion.xml`. 노트의 hip_roll 하드스톱 진술(외전 −45° / 내전 +25°)과 이 파일의 range가 일치 — `pygmalion.xml`

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

출처: 이 노트의 실행 명령/본문에서 추출 (런처 매니페스트 미기록 — 값 없는 항목은 노트가 이름만 언급)

| 플래그 | 값 |
|---|---|
| `PYG_FRESH_STEPS` | 1 |
| `PYG_INIT_BENT` | 1 |
| `PYG_NO_DR` | 1 |
| `PYG_UNEVEN` | 1 |

§1b의 리워드 가중치 표가 정본이다 — 플래그는 그 가중치가 어떻게 조립됐는지의 기록이다.

<!-- SPEC-TABLES:END -->

## §2 설정
- run: `logs/rsl_rl/pygmalion_velocity/2026-07-14_17-18-44_gen21_rough_uneven_p1`
- actor-only warm-start(flat 앵커 gen21_bent_p2 model_31998) + `PYG_UNEVEN=1 PYG_NO_DR=1 PYG_INIT_BENT=1 PYG_FRESH_STEPS=1`, 4096 env, DR-off P1.
- ★UNEVEN cfg 초판: flat 0.2 + hf_slope 0.15+0.15 (**slope_range (0.0, 1.0)=최대 45°**) + random_rough 0.25 + wave 0.25.

## §12 결과·판정
- **fell 추세(200 iter avg)**: 0.60→0.52→0.50→0.41→0.39→0.37→0.38→0.35→0.32 (iter 0→1800). **감소는 명확**(계단 런은 iter 1000부터 0.3 정체였음 = 계단이 주범임을 부분확증) BUT ~0.33에서 둔화.
- **잔여 병목 = 슬로프 45°**: fell 종착 0.33 ≈ 슬로프 비율 0.30 일치 → 슬로프 지형이 거의 전부 실패. slope_range는 rise/run 기울기(1.0=45°)이며 장님 이족보행엔 불가.
- reward: iter 800–1200 −180~−260 급락(급슬로프 페널티 폭발) 후 iter 1600 +56 회복 — 불안정.
- **판정**: ⚠️ **부분 성공·중간 폐기**. 계단 제거 방향은 옳음이 입증됨. 처방 완성 위해 slope_range 0.3(~17°)로 낮춰 iter 1900서 종료 후 재launch([[2026-07-14_gen21_rough_uneven2_p1]], fell iter 600서 ~0.00 수렴 = 진단 완전확증).

## 교훈
- "걸을 수 없는 지형"은 계단만이 아니라 **급슬로프(45°)도 포함** — 장님(height=critic-only) 정책엔 둘 다 구조적 불가. rough=uneven ground의 "walkable" 경계를 지형별로 봐야 함(slope ≤~0.3, 계단 0).
- 변인 격리 검증 3단(계단40%→계단0%슬로프45%→계단0%슬로프17%)이 **각 요인의 기여를 분해**해 줌 = 한 번에 다 바꾸지 않은 것이 진단에 유효.
