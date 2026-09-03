# 학습 리포트 — 2026-07-09_21-09-15 (mjlab rough P2-final, **권위 rough 정책**)

- **task/run**: `2026-07-09_21-09-15_rough_p2_dr` (mjlab MuJoCo-Warp + rsl_rl PPO)
- **의도/변경점**: **2단계 커리큘럼**으로 학습한 최종 rough 정책. Phase1(`2026-07-09_16-21-00_rough_p1_nodr`, DR-off)은 flat P2-final을 **actor-only warm-start**([[rough-terrain-warmstart]])로 이식해 rough 보행 부모스킬을 회복, Phase2(이 런)는 그 위에서 **DR 램프 0$\to$1**(global step 240000$\to$480000)로 재개(`resume=true`, `load_run=..._rough_p1_nodr/model_9999.pt`). ★단일단계 warm-start가 churn(flat vx 81%$\to$26%)했던 실패를 2단계로 교정 → **retired blind-rough 아티팩트(R2)를 대체하는 rough 설계 권위 데이터**.

## 1. 재현성 (Reproducibility)
- **OBS(actor)**: base_ang_vel(3)+projected_gravity(3)+joint_pos(12)+joint_vel(12)+last_action(12)+velocity_commands(3)+height_scan(terrain_scan 1.6$\times$1.0/0.1)+foot_height/air_time/contact (mjlab velocity rough cfg). critic는 base_lin_vel·foot_contact_forces 추가.
- **Output(action)**: 12 관절 위치타겟(hip p/r/y·knee·ankle p/r ×2), action scale 0.25, passive toe 제외
- **config 백업**: `logs/rsl_rl/pygmalion_velocity/2026-07-09_21-09-15_rough_p2_dr/params/{env.yaml, agent.yaml}` (mjlab은 params/에 저장)
- **체크포인트**: `logs/rsl_rl/pygmalion_velocity/2026-07-09_21-09-15_rough_p2_dr/model_19998.pt` (Phase2 19999 iters, 외 model_*.pt) · num_envs=4096
- **지형**: terrain generator 10$\times$20, sub-terrain flat0.2 / pyramid_stairs±0.2 (step 0$\sim$0.1m) / hf_slope±0.1 (0$\sim$1rad) / random_rough0.1 (noise 0.02$\sim$0.1m) / wave0.1, difficulty 0$\to$1 curriculum

## 1b. rough P2-final Reward & Gains (config에서 파싱 — 재현용)

**Reward 항목** (weight·왜·어떻게):

| reward | weight | 왜 | 어떻게 |
|---|--:|---|---|
| track_angular_velocity | **+2** | 명령 회전속도 추종 | exp(-err²/std²), std 0.707 |
| track_linear_velocity | **+2** | 명령 전진/측방 속도 추종 | exp(-err²/std²), std 0.5 |
| foot_clearance | **-2** | 스윙발 지면 이격(발끌림 방지) | target 0.1m, foot_height_scan |
| air_time | **+1** | 체공시간 보상(질질끌기 억제) | thr 0.05\sim0.5s, cmd_thr 0.5 |
| pose | **+1** | variable_posture(정지=엄격 std0.05, 보행=knee std1.2 완화) | default-pose L2, 속도별 std |
| upright | **+1** | 몸통 직립 유지(넘어짐 방지) | exp 자세, std 0.447 |
| dof_pos_limits | **-1** | 관절범위 한계 벌점 | 한계초과 L1 |
| self_collisions | **-1** | 자기충돌 벌점 | -접촉수, force_thr 10 |
| foot_swing_height | -0.25 | 스윙발 높이 성형 | target 0.1m |
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
| knee | RS04 | **220** | 6 | 120 |
| ankle_pitch | RS03 (2-RSU) | 28.5 | 1.81 | 90 |
| ankle_roll | RS00 (2-RSU) | 28.5 | 1.81 | 50 |

- flat P2-final 대비 차이: knee Kp 400$\to$**220**(rough 컴플라이언스 완화), 그 외 hip Kp150/Kd6 under-damped 동일([[bc-kd-controlled-ab]] 확정). thermal_effort의 정규화 rated는 config상 ankle_pitch20/roll5(내부 균등화용); §7 설계 사이징 rated는 2-RSU 값(pitch40/roll10) 적용.

<!-- SPEC-TABLES:BEGIN (analysis/run_spec_tables.py) -->

**§1b-2. 액추에이터 동역학·한계** (이 런의 `params/env.yaml` 파싱 — `2026-07-09_16-21-00_rough_p1_nodr`)

| 관절 그룹 | 모터 | Kp [N·m/rad] | Kd [N·m·s/rad] | effort 한계 [N·m] | 무부하 속도 [rad/s] | 로터 관성 armature [kg·m²] | 쿨롱 마찰 [N·m] | 점성 [N·m·s/rad] | T-N 곡선 |
|---|---|--:|--:|--:|--:|--:|--:|--:|---|
| ankle_roll | RS00 | 28.5 | 1.81 | 50 | — | 0.0005 | — | — | 미사용 (effort_limit 상수 클램프) |
| hip_yaw | RS03 | 150 | 6 | 60 | — | 0.005 | — | — | 미사용 (effort_limit 상수 클램프) |
| ankle_pitch | RS03 | 28.5 | 1.81 | 90 | — | 0.005 | — | — | 미사용 (effort_limit 상수 클램프) |
| hip_pitch, hip_roll | RS04 | 150 | 6 | 120 | — | 0.007 | — | — | 미사용 (effort_limit 상수 클램프) |
| knee | RS04 | 220 | 6 | 120 | — | 0.007 | — | — | 미사용 (effort_limit 상수 클램프) |

토크는 `effort_limit`과 (있으면) 실측 T-N 곡선의 속도의존 상한 중 **작은 값**으로 클램프된다. armature/쿨롱/점성은 모터 실측값(`PYG_MOTOR_MEAS=1`)이면 실측, 아니면 카탈로그 추정치다.

**§1b-3. ROM 한계·액션 창** (모델 XML range · soft 한계 = 중심±0.5·range×0.9 (mjlab `Entity` 규약) · 액션 clip = env.yaml `actions.joint_pos.clip` · 창 = clip 폭 · default = 액션 0 자세)

**soft 한계와 액션 clip은 같은 공식이다** — `Entity.soft_joint_pos_limits`와 `pygmalion_constants.safe_target_clip()`이 둘 다 *중심 ± 0.5·range·factor*를 쓴다(각 경계에 factor를 곱하는 것이 아니다: 비대칭 관절에서 두 식이 갈린다 — knee `[0,120]`은 `[6,114]`이지 `[0,108]`이 아니다). 그래서 `PYG_SAFE_TARGET_CLIP=1`인 런에서는 두 열이 정확히 일치하고, 정책이 통과하는 클램프와 시뮬레이터가 강제하는 클램프가 하나의 계약이 된다.

모델 출처: 이 시기 `pygmalion_constants._XML_NAME` 기본 분기 — `PYG_V2`/`PYG_HIP_CANT*`/`PYG_ROLLOFF30` 미설정 시 `pygmalion.xml`. 노트의 hip_roll 하드스톱 진술(외전 −45° / 내전 +25°)과 이 파일의 range가 일치 — `pygmalion.xml`

| 관절 | XML range [°] | soft 한계 [°] | 액션 clip [°] | 사용가능 창 [°] | default [°] | 구동 |
|---|---|---|---|--:|--:|---|
| L/R_hip_pitch_joint | [-125, 30] | [-117.2, 22.3] | n/a (구 설정: clip 없음) | 139.5 | 0 | 액션 |
| L/R_hip_roll_joint | [-45, 25] | [-41.5, 21.5] | n/a (구 설정: clip 없음) | 63 | 0 | 액션 |
| L/R_hip_yaw_joint | [-50, 50] | [-45, 45] | n/a (구 설정: clip 없음) | 90 | 0 | 액션 |
| L/R_knee_joint | [-140, 0] | [-133, -7] | n/a (구 설정: clip 없음) | 126 | 0 | 액션 |
| L/R_ankle_pitch_joint | [-50, 40] | [-45.5, 35.5] | n/a (구 설정: clip 없음) | 81 | 0 | 액션 |
| L/R_ankle_roll_joint | [-20, 20] | [-18, 18] | n/a (구 설정: clip 없음) | 36 | 0 | 액션 |
| L/R_toe_joint | [-50, 0] | [-47.5, -2.5] | — (수동) | — | 0 | 수동 |

액션 스케일 0.25 rad/단위, 오프셋 = default (`use_default_offset`). clip이 없는 구 설정에서는 정책 목표각을 시뮬레이터의 soft 한계가 사후에 잡는다 — 창은 soft 한계 폭으로 읽는다.

**§1b-4. 이 런의 스택 플래그 (`PYG_*`)**

> 이 런은 실행 환경 스냅샷을 남기지 않았고 노트 본문에도 `PYG_*` 언급이 없다 — **원본 설정 소실**. 리워드 가중치·게인·ROM은 위 §1b~§1b-3(런 config 파싱)이 정본이다.

**P2 (`2026-07-09_21-09-15_rough_p2_dr`)**: 액추에이터 게인·한계·액션 clip이 위 P1 표와 **동일** (env.yaml 대조). 달라지는 것은 도메인 랜덤화·push 등 학습 조건뿐이다.

<!-- SPEC-TABLES:END -->

## 2. 지표 (Metrics)
- **최종 Mean reward**: $\approx$30 (마지막 10 iters 평균, iter 19998=27.65) · **max 62.65**(mid-run, DR 램프 물기 전 55 부근 정점 → full-DR에서 30대 안착)
- **error_vel_xy**: 1.18 (마지막) / 최근 1.2$\sim$1.5 · **error_vel_yaw**: 0.47$\sim$0.54
- **ep_len**: 610$\sim$680 (rough+full-DR; flat 993 대비 축소는 지형 낙상·이탈 반영)
- **낙상률(fell_over/low_base 최종)**: 0.04 / 2.9 (rough full-DR — R2 구cfg 0.09/1.48 대비 low_base 미세 증가는 wide-DR·계단 조합)

*(전용 reward/tensorboard PNG는 이 런 미생성 — 아래 수치는 로그 파싱값. 궤적: reward 0.4→55(정점 iter~14k)→30(full-DR 수렴), ep_len 램프 전 구간 600+ 유지.)*

## 2b. Reward 기여 (이름 · 값 · 기여 · 무엇 · 왜)  — iter 19998
| Reward | 가중치 | 기여(final) | 무엇/왜 |
|---|--:|--:|---|
| `track_angular_velocity` | +2 | +0.7689 | 명령 회전속도 추종 |
| `upright` | +1 | +0.5794 | 몸통 직립 유지(넘어짐 방지) |
| `air_time` | +1 | +0.3585 | 체공시간 보상(질질끌기 억제) |
| `track_linear_velocity` | +2 | +0.3219 | 명령 전진/측방 속도 추종 |
| `pose` | +1 | +0.2646 | variable_posture(정지엄격·보행완화) |
| `action_rate_l2` | -0.1 | -0.4304 | 액션 급변 벌점 |
| `contact_force_cap` | -0.01 | -0.1920 | ★충격 cap: 발 GRF 역치초과분 벌점(사뿐착지) |
| `angular_momentum` | -0.02 | -0.1027 | 전신 각운동량 벌점(회전 낭비 억제) |
| `foot_clearance` | -2 | -0.0888 | 스윙발 지면 이격(발끌림 방지) |
| `thermal_effort` | -0.02 | -0.0766 | ★열분배: Σ(τ/rated)² 정규화(관절 균등화) |
| `dof_pos_limits` | -1 | -0.0118 | 관절범위 한계 벌점 |
| `foot_slip` | -0.1 | -0.0106 | 접지발 미끄러짐 벌점 |
| `foot_swing_height` | -0.25 | -0.0095 | 스윙발 높이 성형 |
| `self_collisions` | -1 | -0.0076 | 자기충돌 벌점 |
| `body_ang_vel` | -0.05 | -0.0042 | 몸통 각속도 벌점(흔들림 억제) |
| `soft_landing` | -1e-05 | -0.0003 | 착지 첫접촉 충격 벌점(약) |
| `torque_limit` | -0 | +0.0000 | commanded 토크 한계초과 벌점 |

## 2c. 학습 건강도 (reward·수렴·추종·낙상)
- reward 0.4→**55(정점)→30(full-DR 수렴)** · ep_len 최종 610$\sim$680 · 추종 vx 1.18$\sim$1.35/yaw 0.47$\sim$0.54 · 낙상 fell 0.04/low_base 2.9
- ★2단계 효과: Phase1(DR-off, warm-start)이 rough 부모스킬을 살려두고, Phase2 DR 램프에서 reward가 55→30으로 **자연 하강(붕괴 아님)** — full-DR 강건화의 정상적 대가. 단일단계 warm-start의 churn(vx 26%로 붕괴)과 대조.

**★2c-2. 정상상태 달성속도 재측정 (2026-07-11, 15s dwell 0.25격자 `p2r_fc` — 위 학습지표와 상반)**: uniform rough서 달성속도를 처음 직접 계산한 결과 — **vx +1.5→−0.36(−24%, 역주행)·+1.25→51%·+1.0→57%·+0.5→75%**, **후진 전구간 ≈0**(−1.5→+0.07), yaw 50~95%. 구 p2r_wc_long(12s) 재계산도 동일(+1.5→41%, −1.5→−10%) = 측정 아티팩트 아닌 정책 실태. 위 2c의 "추종 vx 1.18~1.35"는 **학습 중 reward 지표**(커리큘럼 지형분포=쉬운 타일 위주)이고, uniform rough 정상상태와 다르다. ⇒ **본 리포트의 부하값 = 저속(실효 ≤0.9 m/s) 험지보행 부하**로 읽어야 하며, 험지 고속을 실제 내는 미래 정책에선 부하 상승 여지. 험지 재학습(flat25b P2 계보) 게이트 = 달성속도. 상세: [[65_design_value_uncertainty]] §6c. push delta(+8~26% P99)는 §6b.

## 3b. 보행 시연 — 고정 전후좌우 스윕 + 실부하 색상 (rough, 최종 정책)
전진·후진·좌우 스트레이프·회전·정지 고정 스케줄, rough 지형. 상단 라벨=명령, 관절구=토크 포화색.

**★측정 v2 시연 (권위 데이터 p2r_v2_fc의 실측 환경 — 텔레포트 프로토콜, tile 99.8%, vx 격자 195s 실시간)**
![[p2r_v2_fc_demo_loadviz.mp4]]

**worst-case 스윕(144s) ⚠구 데이터(지형혼합) — 참고용**
![[p2r_final_wc_loadviz.mp4]]

**장기 dwell(12s 명령유지, 432s — 권위 측정 소스)**
![[p2r_wc_long_loadviz.mp4]]

**peak provenance 클립(순시 최대하중 발생 장면 — peak=클립 아티팩트 증빙)** ([[63_peak_provenance_clips]])
![[p2r_final_wc_peak_clips.mp4]]

## 5. 분석
rough P2-final(Phase2 20k, full-DR 수렴): 직립정지(base 평균 0.860m·p5 0.813)·knee flex 보행·rough 지형(계단/슬로프/파형) 강건. **in-range 하중**(worst 12s-dwell, 21600 steps/432s):
- **RMS 전관절 rated 이내**(열여유 OK): knee 39%·hip_roll 62%·hip_pitch 36%·ankle_pitch 19%. binding(RMS>rated) **없음**.
- **P99(=순시/반복 정격 앵커)**: knee 55.1(rated 138%·peak 46%)·hip_roll 61.0(153%·51%)·hip_pitch 46.6(117%·39%)·hip_yaw 20.2(101%·34%)·ankle_pitch 22.2(56%·25%)·ankle_roll 13.2(132%·26%). → knee/hip_roll이 P99에서 rated 초과지만 peak선 내부 = 링크레버+2-RSU로 커버.
- **★peak(120/60/90)는 전부 액추에이터 클립 아티팩트**([[65_design_value_uncertainty]] §4: rough knee peak=120·22 events/8 clusters) → **정적 사이징 금지, P99×SF에 앵커**.
- **knee $\omega$ 수요 정상화**: 이 새 worst 캠페인 knee P99 8.0·P99.9 11.2 rad/s(max 26.96=클립) — retired blind-rough 아티팩트의 28.9 rad/s 대비 **10.4 rad/s급으로 정규화**([[rough-terrain-warmstart]]). RS04 무부하 19.9 rad/s([[reference-robstride-motor-specs]]) 대비 실현 가능 영역.
- **GRF P99 1.40$\times$BW**(peak 4.86$\times$BW=충격요건만). ankle 2-RSU(effort 90/50)는 P99 22/13 대비 여유.

## 7. 모터 활용 시각화 (토크·속도 RMS/p95/max vs 스펙선 + 시계열)
*스펙선(rated 초록/peak·vel-limit 빨강)은 mjlab RobStride 1:1 기준. 사이징 rated=2-RSU(ankle_pitch40/roll10).*

**관절 토크 RMS/p95/MAX vs rated·peak**
![[rough_torque.png]]

**관절 속도 RMS/p95/MAX(rpm) vs 속도한계**
![[rough_speed.png]]

**관절 토크 시계열(peak/rated 선)**
![[rough_torque_ts.png]]

**관절 속도 시계열**
![[rough_speed_ts.png]]

| 관절 | RMS | %rated | p95 | max(=클립) | P99 | %peak(P99) | binding |
|---|--:|--:|--:|--:|--:|--:|:--:|
| hip_pitch | 14.2 | 36% | 28.8 | 120* | 46.6 | 39% | |
| hip_roll | 24.7 | 62% | 46.7 | 120* | 61.0 | 51% | |
| hip_yaw | 6.4 | 32% | 13.0 | 60* | 20.2 | 34% | |
| knee | 15.7 | 39% | 31.9 | 120* | 55.1 | 46% | |
| ankle_pitch | 7.6 | 19% | 16.2 | 90* | 22.2 | 25% | |
| ankle_roll | 3.9 | 39% | 9.1 | 25.5 | 13.2 | 26% | |

- 정량: **binding(RMS>rated) 없음** — 전 관절 열여유. max(*)는 클립 상한(정적사이징 금지). 속도 p99(rpm): knee 76.6·ankle_pitch 59.5·hip_yaw 34.0 — 전 관절 한계 내(속도 binding 없음).

## 8. q-속도-토크 선도 (한계선)
*측정: `p2r_wc_long` 롤아웃 21600 frames · vx$\pm$1.5/vy$\pm$1.0/yaw$\pm$1.0 worst 스윕, 12s dwell.*

**관절각 $q$ – 토크 $\tau$** (수평선 = rated/peak)
![[q_torque_roughP2final.png]]
- knee: flex 구간(음의 $q$)에서 토크 상승하는 전형적 지지상 분포. rated선(40) P99 초과는 접촉/계단 과도에 국한, peak선(120)은 클립.

**관절각 $q$ – 속도 $\dot q$** (수평선 = 속도한계)
![[q_speed_roughP2final.png]]
- 속도는 전 관절 한계 내(knee P99 76.6 rpm) — 스윙 flex 구간에서만 커지는 진자형 분포, 속도 binding 없음.

**토크 $\tau$ – 속도 $\dot\omega$ (T–N 4상한)**
![[torque_speed_roughP2final.png]]
- 고토크는 저속(지지상)·고속은 저토크(스윙)로 분리 → T–N 동시요구 없음. 클립점(120)은 저속 순간 스파이크뿐.

**flat 대비 산점(교차검증)**
![[cmp_q_torque_scatter.png]]
![[cmp_torque_speed_scatter.png]]
- rough가 flat 대비 꼬리(계단·과도)가 두껍지만 밀도 코어(RMS 대역)는 동일 대역 — 설계점 불변 확인.

## 8b. 레짐별 작동점 (명령 레짐 색분할, fc/fcp 신데이터, 2026-07-12 소급)
*측정: `p2r_fc`(clean) + `p2r_fcp`(push 주입) 롤아웃, 명령 레짐(forward/backward/lateral/turn/combo/stand) 색분할. 색=명령 레짐; T–N의 빨간 점선=실모터 무부하속도; push_tn=clean(회색) vs push(빨강).*

**T–N (토크–속도, 레짐 색분할)**
![[regime_tn_p2rr.png]]

**$q$–$\tau$ (관절각–토크, 레짐 색분할)**
![[regime_qt_p2rr.png]]

**$q$–$\dot q$ (관절각–속도, 레짐 색분할)**
![[regime_qw_p2rr.png]]

**조인트프레임 wrench $F_r$–$M_t$ (레짐 색분할)**
![[regime_wrench_p2rr.png]]

**T–N: clean vs push 주입 외피 비교**
![[push_tn_p2rr.png]]

- **combo 레짐이 전 관절 꼬리를 지배**: knee 토크 상단($+100$ N·m대, peak 클립 근접)·hip_pitch $\pm 50$ 초과·wrench의 $F_r>1000$ N / $M_t>150$ N·m 원거리 점이 거의 전부 combo(분홍). 단일축 명령(forward/lateral)의 코어는 rated선 안쪽 — 구조·순시 설계점은 combo 과도가 결정.
- **hip_roll은 lateral/combo에서 음토크 꼬리** $-50$ N·m 이하(rated 40 초과)가 거의 0속도에서 발생 — 지지상 정적 외전 모멘트로, T–N 동시요구가 아니라 토크 단독 스트레스. ankle_pitch도 deep dorsiflexion($q\approx+0.5\sim0.7$ rad)에서 $-40$ N·m 꼬리(combo/backward)로 rated선에 닿음.
- **속도 여유는 유지되나 할인 필요**: 전 관절이 실측 무부하속도(빨간 점선, knee $\pm 20$ rad/s)의 안쪽(knee 최대 $\sim\pm 13$ rad/s)이지만, 이 정책은 uniform rough에서 전진 명령을 정상상태 41–57%만 달성하므로 관측 속도 수요는 과소평가일 수 있음 — 추종이 정상화되면 스윙 속도 요구가 상향될 여지.
- **push 외피 이동은 미미**: clean(회색)과 push(빨강)의 T–N 외피가 전 관절에서 거의 겹침(knee 상단·ankle_pitch 하단 꼬리도 동급) — rough 접촉 과도가 이미 외피를 지배해 $\pm 0.7$ m/s push 주입이 새로운 worst-case를 만들지 않음. §62 프로토콜(push 주입 최악조건)의 rough 앵커로서 clean 측정만으로도 외피 대표성 확보.

## 9. DR 커버리지
- Phase2 DR 램프 0$\to$1(step 240k$\to$480k, `dr_levels`): push ±0.7m/s·±0.52rad·friction 0.3$\sim$1.2·encoder_bias ±0.015·com_offset ±0.025/0.03m. terrain difficulty 0$\to$1 curriculum(계단 0$\sim$0.1m·슬로프 0$\sim$1rad). 명령 vx±1.5/vy±1.0/yaw±1.0(commands_vel 3단계 최종). 측정 스윕(12s dwell)이 이 전 범위를 균일 커버 → in-range 통계 대표성 확보.

## 10. 관절 반력 wrench (per-LINK)
*측정 소스: `p2r_wc_long`(21600 steps, L+R pooled). 상세 조인트프레임 F_r/F_a/M_t·RMS/RMC/p99/peak·동시6벡터: [[wds_p2r_final_wc]].*

**per-link 요약(P99/max, N·N·m, L+R pooled)**

| body | \|F\| P99 [N] | \|F\| max [N] | \|M\| P99 [N·m] | \|M\| max [N·m] |
|---|--:|--:|--:|--:|
| hip_pitch_link | 520 | 1776 | 69.8 | 179.3 |
| hip_roll_link | 535 | 1830 | 70.5 | 186.1 |
| thigh_link | 559 | 1917 | 71.8 | 198.1 |
| shin_link | 632 | 2244 | 83.3 | 260.5 |
| ankle_pitch_link | 681 | 2446 | 108.2 | 441.9 |
| foot_link | 684 | 2455 | 109.7 | 457.9 |

**per-link wrench P99/max 바(regime 대조)**
![[v2_regimes_wrench_rough.png]]

- **GRF**: P99 **1.40$\times$BW**(709N) · peak 4.86$\times$BW(2457N, 충격요건만) · L/R peak 4.14/4.86$\times$BW. BW=505N.
- 반력 지배 방향: 지지상 다리 축 수직(z) 압축이 지배, hip에서 전후(x) 추진·roll 모멘트 부가. 접촉 과도가 **foot→ankle→shin→thigh→hip 순으로 감쇠 전파**(|F| 684→520N, |M| 110→70N·m) — 구조 하중 경로가 기존 worst-case 캠페인과 동일 양상. ankle_pitch/foot 링크가 |M| 최대(108$\sim$110 P99) = 발목/발 구조가 모멘트 병목.

## 11. gait + L/R 대칭 분석
**L/R 대칭** (토크 RMS·GRF·kinematic)

| 지표 | L | R | 비대칭 |
|---|--:|--:|--:|
| hip_pitch 토크 RMS [N·m] | 14.05 | 14.38 | 2% |
| knee 토크 RMS [N·m] | 15.17 | 16.13 | 6% |
| hip_roll 토크 RMS [N·m] | 26.03 | 23.23 | 11% |
| ankle_roll 토크 RMS [N·m] | 3.54 | 4.23 | 16% |
| knee flex max [°] | -143.5 | -107.9 | **25%** |
| GRF peak [×BW] | 4.14 | 4.86 | 15% |

- ★해석: 주요 하중(hip_pitch/knee 토크)은 **2$\sim$6% 대칭** — 하드웨어 하중은 좌우 균형. knee flex kinematic 25% 비대칭(오른다리 덜 굽힘)은 flat P2-final과 동일한 **gait-style 이슈이지 하중 문제 아님**(추후 mirror loss로 다듬을 항목). ankle_roll 16%·hip_roll 11% 비대칭은 절대치가 작아(RMS<5, <27) 사이징 영향 미미.
- **tracking(방향별)**: 전진 vx 추종은 양호(error_vel_xy 1.2$\sim$1.4, flat 1.35와 동급), yaw 0.47$\sim$0.54. **측방(vy) 만성 약세**는 flat 계보부터의 고질(측방 명령 achieved velocity가 낮음) — rough에서도 유지되나 하중/사이징에는 영향 없음.

## 12. 종합 판정
**2단계 rough 커리큘럼 성공** — R2(retired blind-rough) 대체 rough 설계 권위 데이터:
- **Phase 1**(DR-off, flat P2-final actor-only warm-start): rough 부모스킬 회복(단일단계 warm-start churn 교정).
- **Phase 2**(DR 램프 0→1): reward 55→30 자연하강(붕괴 아님)·ep_len 600+ 유지 = **full-DR 강건**.

**달성**: ① 직립 정지(base 0.860m) ② rough(계단/슬로프/파형) 보행 ③ **RMS 전관절 rated 이내(binding 없음, 열여유)** ④ knee $\omega$ 수요 정상화(P99 8.0 rad/s, retired 28.9 대비) ⑤ L/R **하중** 대칭(토크 2$\sim$6%).

**잔여**: kinematic L/R 절뚝(knee 25%)·측방(vy) 추종 약세 — 둘 다 gait-style/추종 이슈이지 하중 문제 아님.

**설계점(동결 BOM 유지, [[64_joint_bearing_design_inputs]]·CI [[65_design_value_uncertainty]])**:
- knee/hip = RS04×6 + 링크레버(P99 초과분 커버). knee P99 **55.1(±13.3%)** / hip_roll P99 **61.0(±4.7%)** / hip_pitch P99 **46.6(±11.2%)** — 순시정격 앵커=**P99 상한CI×1.25**.
- hip_yaw = RS03. ankle = **2-RSU**(pitch effort 90=2×RS03 co-act, roll 50) — P99 22/13 대비 **headroom**.
- GRF 구조 앵커 ≈ **1.40BW×1.3**. peak(4.86BW·클립 ±)는 충격요건만 — **raw peak 사이징 금지**([[65_design_value_uncertainty]] §4·§5).

## 6. 관련 학습 / 연구 링크
- warm-start 레시피: [[rough-terrain-warmstart]] · 설계입력 종합: [[64_joint_bearing_design_inputs]] · CI/안전율: [[65_design_value_uncertainty]]
- peak provenance: [[63_peak_provenance_clips]] · 최신 설계인사이트: [[2026-07-10_design_insights_updated]] · wrench 상세: [[wds_p2r_final_wc]]

---

## §R. 부하 선도 (signed + mjlab 한계선)
포화 요약 · GRF · 토크-속도/각도-토크 산점 · 링크 부재력 (rough worst, 12s-dwell):
![[torque_speed_roughP2final.png]]
![[q_torque_roughP2final.png]]
![[v2_regimes_wrench_rough.png]]
- signed 3평면×6관절·한계선 실정격(빨강=Peak·주황=Nominal·검정 TN). §8 q-v-t 선도와 상보. peak=클립 아티팩트이므로 **P99×SF에 사이징**([[65_design_value_uncertainty]]).
