# 학습 리포트 — 2026-07-11_06-29-27_flat25b_bentinit_p1 (mjlab flat 2.5 **Phase1** · 진행보상 · **bent-knee init** · init-pose A/B의 bent arm)

- **task/run**: `2026-07-11_06-29-27_flat25b_bentinit_p1` (mjlab MuJoCo-Warp + rsl_rl PPO) · wandb `pygmalion`
- **정식 명칭**: **flat-2.5max progress-reward no-domain-rand bent-knee-init (2026-07-11)**
- **의도/변경점**: **init-pose A/B의 bent arm**. straight arm [[2026-07-10_flat25b_prog_p1]]과 **config 완전 동일**(진행보상 FIX·DR-OFF·num_envs 8192·20000 iter)하되 **단일 변수 `PYG_INIT_BENT=1`**만 바꿨다 — 초기자세를 크라우치로: **knee $-0.67$ rad($-38°$) · hip_pitch $-0.32$($-18°$) · ankle_pitch $+0.36$($+21°$) · base 0.83m**(straight는 전관절 0°·base 0.87). 이 토글은 초기자세만이 아니라 **pose-reward 타겟 + 관측/액션 default offset까지 함께 시프트**하므로 "bent가 정책의 HOME"이 된다. env.yaml diff로 단일변수임을 사전 실증(init_state 3관절+base_z만 상이, agent.yaml은 run_name만) — 계획·가설: [[2026-07-11_bentinit_ab_plan]].
- **이 런의 위상(정확히)**: ① **init-pose A/B의 bent arm** — 판정은 [[2026-07-12_bentinit_ab_result]]가 담당(★bent 승: knee P99 $-20\%$·GRF peak $-37\%$·push 강건성·고속추종 우세 → **Gen-2 init = bent 확정**). 본 리포트는 판정 중복 없이 **bent arm 단독의 완전 부하특성**을 기록한다. ② 구 A/B([[55_init_pose_straight_vs_bent]], 1.5박스 저속 레짐 "승자없는 재분배")의 **결론을 반전시킨 당사자** — 2.5박스 고속 레짐에서는 bent가 설계 지배축을 이긴다.

## 1. 재현성 (Reproducibility)
- **OBS(actor, 45dim)**: base_ang_vel(3)+projected_gravity(3)+joint_pos(12)+joint_vel(12)+last_action(12)+velocity_commands(3). critic(60dim)는 base_lin_vel(3)·foot_height/air_time/contact·foot_contact_forces 추가. flat 태스크라 height_scan 없음. ★joint_pos 관측과 액션 default offset이 **bent 자세 기준**으로 시프트됨(`PYG_INIT_BENT=1`) — 평가/측정 시 이 토글을 빼먹으면 관측분포가 어긋나 평가무효([[2026-07-11_bentinit_ab_plan]] 주의사항).
- **Output(action)**: 12 관절 위치타겟(hip p/r/y·knee·ankle p/r ×2), action scale 0.25, use_default_offset(**default=bent pose**), passive toe 제외.
- **config 백업**: `logs/rsl_rl/pygmalion_velocity/2026-07-11_06-29-27_flat25b_bentinit_p1/params/{env.yaml, agent.yaml}` · seed 42. straight arm과의 diff = `init_state`(base 0.87→**0.83**, joint 0→**knee $-0.67$·hip_pitch $-0.32$·ankle_pitch $+0.36$**) 단 하나.
- **체크포인트**: `.../model_19999.pt` (20000 iters 완주, Time elapsed 8:48:53, 111.8k steps/s) · num_envs=8192 · save_interval 100 · onnx export 동봉.
- **지형**: `terrain_type: plane` (순수 평지, terrain_generator=null).
- **커리큘럼(env.yaml)**: 5-stage $v_x$ $\pm0.8\to\pm2.0\to[-2.0,+2.5]$, yaw $\pm0.5\to\pm1.0$ (step 0/96k/192k/288k/384k env-step = iter 0/4k/8k/12k/16k). straight arm과 동일.
- **측정 소스**: `analysis/out/bent_fc.npz` — ★**full-coverage 표준 프로토콜**(`measure_full.py`, PYG_BOX="-2.0,2.5,1.0,1.0"): 축별 **0.25 격자** 스윕 + 2D 복합면 + 11 박스코너 + 24 균일랜덤 = **121 블록 × 15초 체류 = 90750 steps(1815s)**, model_19999, 모델 `bent_fc_model.mjb`. push 내성 변형 `bent_fcp.npz`(동일 스케줄 + 4초마다 in-DR push 주입). ⚠**측정도 `PYG_INIT_BENT=1`로 수행**(학습과 관측/액션 default 일치 — 필수). 15s dwell이라 straight 리포트의 2.1s 스윕(`flat25b_final`)과 직접 비교 금지 — 동일 프로토콜 상대는 `flat25b_fc`([[2026-07-12_bentinit_ab_result]]).

## 1b. flat25b_bentinit Reward & Gains (config에서 파싱 — 재현용)

**Reward 항목** (weight·왜·어떻게) — ★straight arm [[2026-07-10_flat25b_prog_p1]]과 **전 항목·전 weight 동일**(env.yaml diff = init_state뿐). 유일한 실질 변화 = `pose` reward의 default-pose 타겟이 **bent 자세**로 이동:

| reward | weight | 왜 | 어떻게 |
|---|--:|---|---|
| track_linear_velocity | +2 | 명령 전진/측방 속도 추종(정밀도) | \exp(-\lVert e\rVert²/σ²), σ=√(0.75)=0.866 |
| track_lin_vel_progress | +1 | 진행보상(FIX 핵심): 명령방향 속도를 명령크기까지 선형 보상 | \min(v_xy·\hatcmd, \lvertcmd\rvert); 정지명령은 0 |
| track_angular_velocity | +2 | 명령 회전속도 추종 | \exp(-e²/σ²), σ=0.707 |
| upright | +1 | 몸통 직립 유지 | \exp 자세, σ=0.447 (base_link) |
| pose | +1 | variable_posture(정지 σ0.05, 보행 knee σ1.2·hip_roll σ0.15 완화) | ★default-pose L2의 **default가 bent**(knee -0.67 등) |
| air_time | +1 | 체공시간 보상(질질끌기 억제) | thr 0.05\sim0.5s, cmd_thr 0.5 |
| foot_clearance | -2 | 스윙발 지면 이격(발끌림 방지) | target 0.1m, foot_height_scan |
| dof_pos_limits | -1 | 관절범위 한계 벌점 | 한계초과 L1 |
| self_collisions | -1 | 자기충돌 벌점 | -접촉수, force_thr 10 |
| foot_swing_height | -0.25 | 스윙발 높이 성형 | target 0.1m |
| action_rate_l2 | -0.1 | 액션 급변 벌점 | -\lvertΔ a\rvert² |
| foot_slip | -0.1 | 접지발 미끄러짐 벌점 | -\lvert v_contact\rvert |
| body_ang_vel | -0.05 | 몸통 각속도 벌점 | -\lvertω\rvert² |
| angular_momentum | -0.02 | 전신 각운동량 벌점 | -\lvert L\rvert² |
| thermal_effort | -0.02 | 열분배: \sum(τ/rated)² 정규화 | 관절 균등화 |
| contact_force_cap | -0.01 | 충격 cap: 발 GRF 역치초과분 벌점 | -\min(\max(F-600,0),800) |
| soft_landing | -1e-05 | 착지 첫접촉 충격 벌점(약) | -첫접촉 GRF |
| torque_limit | -0 | commanded 토크 한계초과 벌점 | off(0) |

**관절별 Kp/Kd** (position-PD, effort=관절측 clip; env.yaml actuator 파싱 — straight arm과 동일):

| 관절 | 모터 | Kp(stiffness) | Kd(damping) | effort clip [N·m] |
|---|---|--:|--:|--:|
| hip_pitch | RS04 | 150 | 6 | 120 |
| hip_roll | RS04 | 150 | 6 | 120 |
| hip_yaw | RS03 | 150 | 6 | 60 |
| knee | RS04 | **220** | 6 | 120 |
| ankle_pitch | RS03 (2-RSU) | 28.5 | 1.81 | 90 |
| ankle_roll | RS00 (2-RSU) | 28.5 | 1.81 | 50 |

- hip Kp150/Kd6 under-damped 유지. effort clip은 raw 값(120/60/90/50)에 걸림(§7 실측서 hip_pitch/hip_roll/knee가 정확히 120.0, ankle_pitch 90.0, ankle_roll 50.0 도달). §7 사이징 rated는 RobStride 명목값(RS04 40·RS03 20·RS00 5; ankle 2-RSU 공동구동 시 pitch40/roll10) — 실측 TN: [[robstride-datasheet]]·[[48_motor_util_sizing]].
- **PD 법 검증**([analysis/analyze_qtarget.py](../../mujoco-sim/mjlab/analysis/analyze_qtarget.py), $\tau\approx K_p e - K_d\dot q$ 회귀): 복원 gain **Kp 142/149/148/217/28/27, Kd 5.6/5.9/5.9/5.9/1.8/1.8, $R^2$ 0.96$\sim$1.00** — config와 일치(knee 217은 clip 포화로 220보다 약간 낮게 적합, hip_pitch $R^2$ 0.96은 고속블록 clip 포화 몫). ankle_pitch는 $R^2$=1.00 완전 선형.

## 2. 지표 (Metrics)
- **최종 Mean reward**: **102.30** (iter 19999). 궤적: $-0.42\to$54(100)→107(500)→**정점 115.1(iter 2878)**→커리큘럼 확장(4k/8k/12k/16k)마다 계단식 소폭 하강→**최후 100.9$\sim$104.1 평탄**. 붕괴·진동 없음. straight arm(최종 100.7, 정점 106)보다 **전 구간 소폭 높게 유지**.
- **error_vel_xy**: **1.03** (최종; straight 1.02$\sim$1.05와 동급) · **error_vel_yaw**: **0.65** (straight 0.58보다 소폭 악화 — bent도 진행보상의 선속도 우선 트레이드오프 공유).
- **ep_len**: **988$\sim$1000** (거의 max, DR-OFF 평지). straight(983$\sim$1000)와 동급.
- **낙상**: **fell_over 0.000**(전 구간, 최후 50블록 max 0.042) / low_base 0.00$\sim$0.29(최종 0.083) — straight(fell 0.000·low_base 0.04$\sim$0.17)와 동급 안정.

## 2b. Reward 기여 (이름 · 값 · 무엇/왜) — 최종 블록(iter 19999)
| Reward | 가중치 | 기여(final) | 무엇/왜 (괄호=straight arm 대비) |
|---|--:|--:|---|
| `track_linear_velocity` | +2 | **+1.5673** | 명령 선속도 추종 (+1.55와 동급) |
| `track_angular_velocity` | +2 | +1.5073 | 명령 회전속도 추종 (1.57보다 소폭↓ = yaw 트레이드) |
| `upright` | +1 | +0.9854 | 몸통 직립 유지 |
| `track_lin_vel_progress` | +1 | **+0.8959** | ★진행보상 — straight +0.7994보다 **+12%**(고속 명령서 더 잘 밈; §3c 93% vs 86%로 실측 확인) |
| `pose` | +1 | **+0.7398** | ★variable_posture — straight +0.5723보다 **+29%**: bent 타겟은 보행자세와 가까워 유지가 쉬움 |
| `air_time` | +1 | +0.6784 | 체공시간 보상 (동급) |
| `action_rate_l2` | -0.1 | -0.5633 | 액션 급변 벌점 (-0.50과 동급 = jitter 없음) |
| `thermal_effort` | -0.02 | **-0.1818** | ★열분배 — straight -0.1395보다 **30% 더 냄** = bent의 상시 관절토크(크라우치 모멘트팔) 비용 |
| `contact_force_cap` | -0.01 | -0.1605 | 충격 cap (-0.18보다 소폭 완화 = 사뿐착지) |
| `foot_clearance` | -2 | -0.1183 | 스윙발 이격 |
| `angular_momentum` | -0.02 | -0.1126 | 각운동량 벌점 |
| `foot_slip` | -0.1 | -0.0263 | 접지발 미끄러짐 |
| `foot_swing_height` | -0.25 | -0.0127 | 스윙발 높이 성형 |
| `dof_pos_limits` | -1 | -0.0102 | 관절범위 한계 |
| `self_collisions` | -1 | -0.0059 | 자기충돌 |
| `body_ang_vel` | -0.05 | -0.0036 | 몸통 각속도 |
| `soft_landing` | -1e-05 | -0.0004 | 착지 충격(약) |
| `torque_limit` | -0 | +0.0000 | off |

- ★**진단**: bent의 이득 2줄 = **progress +12%·pose +29%**(고속을 더 잘 밀고, 보행자세 유지가 공짜에 가까움), 비용 1줄 = **thermal_effort +30%**(크라우치 상시토크). 낙상·jitter·추종정밀은 straight와 동급 → init 변경이 학습 안정성을 해치지 않고 **레짐 이득만 취했다**는 보상-기여 수준의 신호.

## 2c. 학습 건강도 (reward·수렴·추종·낙상)
- reward $-0.42\to$115(정점)→**100.9$\sim$104.1 평탄**(붕괴 없음; 계단 하강은 커리큘럼 확장 시점과 일치 = 정상) · ep_len 988$\sim$1000 · 추종 vx 1.03/yaw 0.65 · 낙상 **fell 0.000**/low_base $\le$0.29.
- straight arm 대비: reward·progress·pose ↑, yaw 추종 소폭 ↓, 나머지 동급 — **동일 건강도에서 고속추종·부하 레짐만 개선**. 학습지표 progress 0.896 > straight 0.80은 §3c 실측(93% vs 86%)으로 확인됨.

## 3b. 보행 시연 (accumulate video)
학습 진행 누적 영상(step/iter 캡션, 60 clips 중 40 균등 서브샘플). random-cmd 롤아웃이 iter가 오를수록 크라우치 초기자세에서 안정 보행으로 수렴하는 과정.

![[accum_flat25b_bentinit_p1.mp4]]
*(iter 캡션付. 원본: `.../videos/accumulated_progress.mp4` — `analysis/accum_video.py`로 train 인터벌 클립 스티칭.)*

- ★**좌우 동시 A/B 영상**(straight vs bent, 동일 명령 프레임잠금·실시간 25fps·부하색 구체+GRF 벡터)은 [[2026-07-12_bentinit_ab_result]] §6에 — 본 노트에 중복 임베드하지 않음.

## 3c. 추종 (15초 체류 정상상태 — full-coverage 0.25 격자)
`analysis/track_from_npz.py`(qpos_full body-frame 유한차분+yaw회전, settle 15) on `bent_fc.npz`, 전표 `analysis/out/bent_fc_tracking.txt`:

| cmd (순수 v_x) | 달성 | % | 판정 |
|---|--:|--:|:--:|
| **+2.5** | **2.33** | **93%** | ✅ (straight 86% 대비 ★우세, 게이트 ≥1.5 통과) |
| +2.0 | 1.98 | 99% | ✅ |
| +1.75 / +1.5 / +1.25 | 1.76/1.56/1.32 | 100/104/106% | ✅ |
| +1.0 / +0.75 / +0.5 / +0.25 | 1.13/0.95/0.78/0.46 | 113/126/156/185% | ⚠ 저속 **overshoot**(아래) |
| **−2.0** | −1.29 | 64% | ⚠ 후진 약함(straight 76%보다 −12%p) |
| −1.5 \sim −1.0 | −1.08/−0.93/−0.66 | 72/74/66% | 약함 |
| −0.75 \sim −0.25 | | 55/42/0% | 저속 후진 정체 |

| cmd (측방·선회·복합) | 달성% | 해석 |
|---|---|---|
| v_y +0.5/+1.0 | 78/61% | 측방 여전히 약함(왼쪽 우세) |
| v_y −0.5/−0.75/−1.0 | 71/68/**−4%** | −1.0은 방향조차 못 냄(비대칭) |
| yaw ±0.5/±0.75 | 82·13/63·59% | 저·중선회는 절반 이상 |
| yaw ±1.0 | 18/40% | 최대 선회 약함 |
| (2.5,0,±0.5) | 88% | 전진+선회 양호 |
| (2.5,±1.0,0) | 96/88% | 전진+측방 양호 |
| (2.5,0,±1.0) | 39% ⚠ | **낙상 블록**(리셋 5건 집중) |

- ★**bent의 잔여결함 패턴은 straight와 다르다**: straight의 중저속 전진 **stall**(0.7/1.6 → 41/44%, [[2026-07-11_midspeed_stall_overshoot]])이 bent서는 사라지고 대신 **저속 전진 overshoot**(0.25$\sim$1.0 명령을 113$\sim$185%로 과속)로 나타남 — 정지·저속 정밀도는 미해결이나 "걷다가 멈추는" stall보다 양호한 병리. 순수 후진·측방·최대선회 약점은 양팔 공유(사이징 비영향 gait-품질 항목, 측방은 hip_roll pose-std 병목 [[2026-07-11_lateral_hiproll_pose_suppression]]).
- **측정 아티팩트 주의**: (2.25,0,0) 174%·(2.5,−0.5,0) 130%·(1.38,−1,0) 345%는 낙상 리셋의 텔레포트가 유한차분 속도를 오염시킨 가짜 수치(해당 블록 리셋 실측 1$\sim$2건씩) — 추종 판정에서 제외.
- **정지 (0,0,0)**: 달성 (+0.002, −0.000, −0.008) — 완전 정지 성립(크라우치 자세로 정지).

## 5. 분석
flat 2.5 Phase1 + 진행보상 + **bent-knee init**(DR-OFF): 측정 1815s·121블록·15s dwell, L+R pooled. 비교 기준은 동일 프로토콜의 straight arm `flat25b_fc`([[2026-07-12_bentinit_ab_result]] §1):
- **base_height**: 평균 **0.793m**·p5 0.743·min 0.693 — straight fc(0.836m)보다 **4cm 낮은 크라우치 순항**. init 0.83 부근을 보행 중에도 유지(직립 회귀 없음 = pose 타겟 시프트가 실효).
- **RMS(열여유, 단일모터 rated 기준)**: ankle_pitch **112%**(22.4/20 — ★유일 rated 초과, 2-RSU 공동구동 40 기준 **56%**)·knee **83%**(33.3/40)·hip_pitch 74%·ankle_roll 67%·hip_yaw 65%·hip_roll 57%. → ★bent의 열병목 = **ankle_pitch(공동구동 전제 필수) + knee**. straight fc(knee 34.6·hip_pitch 24.1·ankle_pitch 9.3) 대비 **hip_pitch +23%·ankle_pitch 2.4배, knee는 −4%로 동급** — 크라우치가 "상시토크"를 ankle/hip으로 옮기되 knee 열부하는 오히려 유지.
- **P99(순시/반복 앵커)**: **hip_pitch 91.0**(clip 120의 76%)·**knee 90.8**(76%)·ankle_pitch 66.4(clip 90의 74%)·hip_yaw 39.6(66%)·hip_roll 53.7(45%)·ankle_roll 11.7(23%). ★straight fc 대비 **knee 113.9→90.8 = −20%**(클립 95%서 76%로 — 순시 최악관절의 여유 확보가 bent의 핵심 이득), hip_pitch −5%, **ankle_pitch 23.2→66.4 = +186%**(비용), hip_yaw +13%.
- **knee $\omega$ 수요 (sim-to-real 관점 ★완화)**: P99 **11.0 rad/s**·P99.9 **14.6**·max 25.1(리셋 근방 포함). RS04 무부하 실측 19.9 rad/s([[robstride-datasheet]]) 대비 **P99.9 = 73%로 내부**(straight fc는 15.9=80%) — 고속을 더 잘 추종하면서도 knee 속도수요는 오히려 낮다(크라우치 무릎이 스윙 회수 각속도를 줄임). max 25.1(126%)은 0.1% 미만 스파이크.
- **GRF**: pooled P99 **1.37×BW**(693N)·RMS 0.69BW·peak **4.73×BW**(2387N·R발, 충격요건만). straight fc(P99 1.52·peak 7.52BW) 대비 **P99 −10%·peak −37%** = ★크라우치 충격흡수 재현(구 A/B [[55_init_pose_straight_vs_bent]]의 GRF 이득은 유지하면서, 구 A/B의 knee +98% 비용은 고속 레짐서 −20% 이득으로 반전).
- **push 내성**(`bent_fcp`, 4초마다 in-DR push): 리셋 **15→19(1.3×)** — straight의 13→31(2.4×)보다 ★강건. push 시 재분배는 **knee로 집중**: knee P99 90.8→**120.0(clip 도달, +32%)**·RMS 33.3→51.4·sat 0.15→2.62%, 반면 hip_pitch/ankle_pitch P99는 −19/−20%(push로 고속블록이 무너져 추진토크가 줄어든 몫). GRF peak 4.73→9.36BW(push 충격). clip 도달 = 진수요 미지([[65_design_value_uncertainty]] §4) → push-학습 P2 비교가 확정판(이미 완료: [[2026-07-12_bentinit_ab_result]] §8, bent P2 knee 109.3).
- **낙상 분포**: fc 리셋 15건 중 11건이 $v_x\ge2.25$ 블록(특히 (2.5,0,±1.0) 5건) — 고속+최대선회 조합이 취약면. fcp 19건은 push 하 후진($v_x\le-1.25$) 블록으로 이동(8건).

## 7. 모터 활용 시각화 (토크·속도 RMS/p95/max vs 스펙선 + 시계열)
*스펙선: rated 초록(RS04 40·RS03 20·RS00 5, 단일모터)/peak-clip 빨강(120/60/90/50 raw). 사이징 rated는 ankle 2-RSU 공동구동 시 pitch40/roll10로 재해석([[64_joint_bearing_design_inputs]]).*

**관절 토크 RMS/p95/MAX vs rated·peak-clip**
![[bentp1_torque.png]]

**관절 속도 RMS/p95/MAX(rpm) vs 무부하 실속도**
![[bentp1_speed.png]]

**관절 토크 시계열(rated/clip 선, 첫 12s)**
![[bentp1_torque_ts.png]]

| 관절 | RMS | %rated(단일) | p95 | max(=clip) | P99 | %clip(P99) | sat%(≥99%clip) | binding |
|---|--:|--:|--:|--:|--:|--:|--:|:--:|
| hip_pitch | 29.7 | 74% | 62.1 | 120.0* | **91.0** | **76%** | 0.16% | P99 공동최악 |
| hip_roll | 22.8 | 57% | 42.1 | 120.0* | 53.7 | 45% | 0.02% | |
| hip_yaw | 13.1 | 65% | 27.7 | 60.0* | 39.6 | 66% | 0.04% | ★+13% vs straight |
| knee | 33.3 | 83% | 68.7 | 120.0* | **90.8** | **76%** | 0.15% | P99 공동최악·열 2위 |
| ankle_pitch | 22.4 | **112%** (공동구동 56%) | 47.8 | 90.0* | 66.4 | 74% | 0.11% | **RMS binding** |
| ankle_roll | 3.3 | 67% (공동구동 33%) | 7.5 | 50.0* | 11.7 | 23% | 0.02% | |

- 정량: **RMS binding = ankle_pitch(단일 RS03 기준 112%)** — ★**2-RSU 공동구동(pitch40) 전제 시 56%로 여유**. bent는 이 공동구동 전제를 **열적 필수**로 만든다(straight도 push 시 67로 튀므로 어차피 필수였음 — [[2026-07-12_bentinit_ab_result]] §5). 순시(P99)는 hip_pitch·knee가 91.0/90.8로 나란한 공동최악이되 **둘 다 clip의 76%로 여유**(straight fc는 knee 113.9=95%로 아슬) — saturation도 전 관절 $\le$0.16%로 낮음. max(*)는 clip 상한이므로 **정적사이징 금지**([[65_design_value_uncertainty]] §4). 속도(rpm): knee p95 74·P99 105·max 239(=25.1rad/s, 리셋 근방 스파이크), ankle_pitch max 464rpm은 낙상 충격 순간의 아티팩트(P99.9 150rpm) — p95 기준 전 관절 실한계 내.
- 상세 수치·열 모델: `docs/mujoco/assets/actuator_eval_bentp1.csv`(+`torque_hist_bentp1.png`).

## 8. q-속도-토크 선도 (한계선)
*측정: `bent_fc` 롤아웃 90750 frames·전 명령박스($v_x[-2.0,2.5]$/$v_y\pm1.0$/yaw$\pm1.0$)·1815s. ★`actuator_eval.py` 산점은 sim→real **×1.15 마찰보정 포함**(clip 위 점 = 보정분). 산점의 ankle 스펙선은 구 단일모터 기준(60/14) — ankle 실제 clip(90/50)은 §7 바 그래프 기준으로 읽을 것.*

**관절각 $q$ – 토크 $\tau$** (수평선 = rated/peak, 수직선 = 관절범위)
![[q_torque_bentp1.png]]
- knee: **flex 구간이 $-140°\sim-20°$로 straight보다 깊게 이동**(크라우치), 지지상 고토크가 $-60°$ 부근에 집중되고 clip(120) 도달은 희소. hip_pitch는 $-60°\sim-40°$(몸통 앞기울임+크라우치)서 양방향 고토크 — straight의 "양·음 clip 왕복"보다 분포가 온화. ankle_pitch는 $+20°\sim+40°$(배굴)서 음토크 벽 — bent의 ankle 듀티 급증이 각도영역째 보인다.

**관절각 $q$ – 속도 $\dot q$** (수평선 = 무부하 실속도)
![[q_speed_bentp1.png]]
- knee 스윙 회수 속도가 크라우치 각도범위 안에서 해소돼 **실무부하선(190rpm) 초과 표본이 straight보다 감소**(§5 P99.9 73%). 고속 초과점은 리셋 근방 스파이크.

**토크 $\tau$ – 속도 $\dot\omega$ (T–N 4상한)**
![[torque_speed_bentp1.png]]
- 고토크는 저속(지지상)·고속은 저토크(스윙)로 분리 — T–N 동시요구 없음. knee 1상한 고토크 로브가 straight보다 뚜렷하되 clip 접촉은 희소, ankle_pitch 3상한(음토크·배굴)이 bent 고유의 로브.

**q/qtarget 오차 + 토크 P/D 분해** ($\tau\approx K_p e - K_d\dot q$)
![[qtarget_error_bentp1.png]]
![[qtarget_error_bymove_bentp1.png]]
- ★**knee D-term RMS 20.6**(P-term 36.4)로 6관절 중 최대 감쇠토크 — 고속 추종의 대가(straight 23.9보다는 작음 = 스윙속도 감소와 일관). **hip_pitch P-term 31.9**(D 9.7)·err_rms 0.225rad — 오차구동 추진. **ankle_pitch err_rms 0.79rad·p95 1.69rad로 최대 오차**(soft Kp28.5가 오차를 허용하며 토크를 냄 — 2-RSU 컴플라이언스 설계와 부합). PD $R^2$ 0.96$\sim$1.00로 법 검증(§1b).

## 8b. 레짐별 작동점 (명령 레짐 색분할, 2026-07-12 소급)
*색 = 명령 레짐(forward/backward/lateral/turn/combo/stand), T–N의 빨간 점선 = 실모터 무부하속도, push_tn = clean(`bent_fc`, 회색) vs push 주입(`bent_fcp`, 빨강).*

![[regime_tn_bentp1r.png]]
![[regime_qt_bentp1r.png]]
![[regime_qw_bentp1r.png]]
![[regime_wrench_bentp1r.png]]
![[push_tn_bentp1r.png]]

- **knee 고토크 로브($+50\sim120$ N·m, $|\dot q|<5$ rad/s)는 forward+combo가 본체, 상단 가장자리($\sim+100$, $q\approx-1.0$ rad)에 backward가 뚜렷** — 크라우치 지지상 무릎 수요는 전진 계열이 만들고 후진이 피크를 얹는다. 반대로 고속 스윙 회수 링($|\dot q|>5$ rad/s, 저토크)은 combo·backward·turn 색이 지배하고 forward 코어는 저속에 머묾.
- **bent 고유의 ankle_pitch 음토크 벽($-40\sim-85$ N·m, $q\approx+0.3\sim0.7$ rad 배굴)은 forward·combo(최하단엔 turn)** — 전진 push-off/지지가 ankle_pitch 수요의 주범. backward는 부호가 뒤집혀 $+25$ N·m 양토크 아크(속도 $+15$ rad/s까지)를 그린다 — 레짐에 따라 발목 사용 방향 자체가 갈림.
- wrench 극단 꼬리(ankle_pitch $F_r\sim1.6$ kN, ankle_roll $M_t>300$ N·m, knee $F_r>1$ kN)는 거의 전부 **combo(복합명령)** — 구조 P99 앵커는 단일축 명령이 아니라 combo 레짐이 결정.
- push_tn: push 주입(빨강)은 대체로 clean(회색) 포락선 내부지만, **knee 상단 clip($+120$ N·m)에 빨간 포화 밴드**가 새로 생김 — push 회복이 무릎을 effort clip까지 밀어붙인다(§9의 "push-학습 P2 앵커 필요"와 일관).

## 9. DR 커버리지 (Phase1 = DR-OFF)
- **DR-OFF**(`PYG_NO_DR=1`): push/friction/encoder/com randomization **없음** — nominal 도메인만 학습. 본 리포트 in-range 통계는 **명목(무DR) 하중**이다. `bent_fcp`의 push 수치도 "push-학습 안 된 정책이 맞는 push"라 과도추정·클립도달이 섞임(진수요 미지).
- ★**설계 배포 앵커는 push-학습 P2 = `bentp2_fc`**([[2026-07-12_bentinit_ab_result]] §8: knee P99 109.3·hip_pitch 95.0·GRF 1.30BW) — 본 P1 명목값은 **하한 참조**로만 쓰고 over-anchor 금지([[65_design_value_uncertainty]] §5 SF 독트린: 열=RMS×1.15·순시=in-DR P99×1.25·구조=P99 wrench×SF).
- 명령 커버리지: 학습 박스 전범위를 0.25 격자+복합면+랜덤으로 커버(121블록) — 커버리지 자체는 표준 프로토콜 충족.

## 10. 관절 반력 wrench (per-LINK)
*측정 소스: `bent_fc`(90750 steps, L+R pooled, world frame CoM 기준).*

**per-link 요약(P99/max, N·N·m, L+R pooled)**

| body | \|F\| P99 [N] | \|F\| max [N] | \|M\| P99 [N·m] | \|M\| max [N·m] |
|---|--:|--:|--:|--:|
| hip_pitch_link | 493 | 1194 | 102.0 | 340.9 |
| hip_roll_link | 507 | 1233 | 102.3 | 346.8 |
| thigh_link | 530 | 1304 | 103.2 | 354.8 |
| shin_link | 589 | 1477 | 118.8 | 386.2 |
| ankle_pitch_link | 651 | 2386 | 127.2 | 1957.4 |
| foot_link | 654 | 2387 | 126.7 | 1958.4 |

**베어링-로드 로즈(조인트프레임 반경력 방향분포 + 설계수치)**
![[bearing_load_bentp1.png]]

- 지지상 다리축 압축 지배, foot→hip으로 감쇠 전파(\|F\| P99 654→493N). ★straight arm 리포트(2.1s 스윕) 수치 대비 **P99가 전 링크 20$\sim$35% 낮음** — 프로토콜 차이(15s 정상상태)와 bent의 GRF 완충이 겹친 결과이며, 동일 프로토콜 조인트프레임 비교([[2026-07-12_bentinit_ab_result]] §1)로는 **knee $F_r$ −9%/$M_t$ −20%·ankle_pitch $F_r$ −14%/$M_t$ −30%·ankle_roll $M_t$ −38%·hip_roll $F_r$ −24%, 유일 역행 hip_yaw $F_r$ +25%**(376N — 캔틸레버 hip_yaw 검토 [[56_humanoid_impact_fall_load_handling]]에 반영). ankle/foot \|M\| max $\approx$1958N·m는 낙상 충격 1$\sim$2 프레임의 아티팩트(P99 127) — **raw peak 사이징 금지**([[65_design_value_uncertainty]] §4). 로즈 판독: 전 관절 반경력이 90° 부근 섹터에 집중되나 dir-conc R 0.12$\sim$0.47로 회전성$\sim$편향 — L10 수명계산은 ROTATING load 가정이 안전측(knee Fr RMC 351·P99 585N, ankle_pitch Fr P99 646N).

## 11. gait + L/R 대칭 분석
**L/R 대칭** (토크 RMS raw N·m·GRF·kinematic, `bent_fc`)

| 지표 | L | R | 비대칭 |
|---|--:|--:|--:|
| hip_pitch 토크 RMS [N·m] | 29.31 | 30.17 | 3% |
| hip_roll 토크 RMS [N·m] | 23.47 | 22.10 | 6% |
| hip_yaw 토크 RMS [N·m] | 13.16 | 13.04 | 1% |
| knee 토크 RMS [N·m] | 31.75 | 34.83 | 9% |
| ankle_pitch 토크 RMS [N·m] | 22.20 | 22.58 | 2% |
| ankle_roll 토크 RMS [N·m] | 3.30 | 3.36 | 2% |
| knee flex min [°] | -120.5 | -99.1 | 18% |
| GRF peak [×BW] | 4.10 | 4.73 | 13% |

- ★해석: **토크 비대칭이 straight arm(knee 16%·ankle_pitch 15%)보다 한층 완화**(knee 9%·ankle_pitch 2%) — bent HOME이 좌우 동형 crouch라 대칭 gait가 유도된 듯. 잔여 비대칭은 R다리 knee(34.8 vs 31.8)와 GRF peak(4.73 vs 4.10BW), 그리고 L무릎이 더 깊이 접히는 kinematic 비대칭(−120.5° vs −99.1°) → 하드웨어 사이징은 **worst leg 기준**(knee RMS 34.8·GRF peak 4.73BW). mirror-equivariant 다듬기는 Gen-2 스택 항목([[62_policy_reward_design_review]]).
- **gait**: air_time 평균 0.176s(학습 로그)·크라우치 순항 base 0.793m·정지 완전 성립. 저속 overshoot·후진/측방 약점은 §3c(사이징 비영향).

## 12. 종합 판정
**init-pose A/B bent arm 완주 — 학습 건강도 동급 + 설계 지배축 우세로 [[2026-07-12_bentinit_ab_result]]의 "Gen-2 init = bent 확정"을 뒷받침하는 부하특성 기록**:
- **성립**: ① 20000 iter 완주·reward 102.3 평탄·**fell 0.000**·ep_len ~1000 ② **고속 전진 93%**(straight 86% 대비 우세, 진행보상 게이트 통과) ③ **knee P99 −20%·GRF peak −37%**(동일 프로토콜 A/B) ④ push 리셋 1.3×(straight 2.4×) ⑤ PD 법 검증($R^2\ge0.96$) ⑥ L/R 토크 비대칭 $\le$9%.
- **비용(설계 반영)**: ⑦ **ankle_pitch RMS 112%(단일)→2-RSU 공동구동 열적 필수**(56%) ⑧ hip_yaw P99 +13%·$F_r$ +25%(캔틸레버 검토 반영) ⑨ 후진 −12%p·저속 overshoot(사이징 비영향).
- **후속**: (a) push-학습 P2 완료·P2-vs-P2 확정판 [[2026-07-12_bentinit_ab_result]] §8-9(**설계앵커 = bentp2_fc**). (b) Gen-2 bent 계보 시작: [[2026-07-12_gen2_bent_p1]]. (c) 저속 overshoot·명령게이팅 클록은 Gen-2 보상스택([[62_policy_reward_design_review]]).

**설계점(flat 2.5 bent 명목부하 — DR-OFF·worst-leg R·SF 규칙은 [[65_design_value_uncertainty]] §5)**:
- **knee = P99 90.8(clip 76%)·RMS 33.3(83%)**: straight의 113.9서 −20% — RS04+링크레버 계획의 여유 확보. 단 **push 시 clip 120 도달(+32%)** → 순시 앵커는 P1 명목이 아니라 **bentp2 109.3×1.25**를 쓸 것.
- **hip_pitch = P99 91.0(76%)·RMS 29.7(74%)**: knee와 나란한 공동최악이나 clip 여유 확보(straight 리포트의 "clip 도달" 병목 해소).
- **ankle_pitch = 열 binding**: RMS 22.4 = 단일 RS03 112% → ★**2-RSU 공동구동(pitch40) 열적 필수 전제**(56%). P99 66.4(clip 90의 74%).
- **GRF 구조 앵커 $\approx$ 1.37BW×SF**(P99 693N). peak 4.73BW(R발)는 충격요건만 — raw peak 사이징 금지.
- **knee $\omega$**: P99.9 14.6 rad/s = RS04 실무부하 19.9의 **73%로 내부 복귀**(straight의 "실한계 초과 적신호"가 bent서 완화) — sim-to-real 속도갭 리스크 축소.

## 6. 관련 학습 / 연구 링크
- straight arm(대조군·템플릿): [[2026-07-10_flat25b_prog_p1]] · A/B 계획: [[2026-07-11_bentinit_ab_plan]] · ★A/B 판정(P1+P2): [[2026-07-12_bentinit_ab_result]] · 구 A/B(저속 레짐, 반전됨): [[55_init_pose_straight_vs_bent]]
- 진행보상 근거연구: [[2026-07-10_highspeed_freeze_progress_reward]] · 중저속 stall/overshoot: [[2026-07-11_midspeed_stall_overshoot]] · 측방 병목: [[2026-07-11_lateral_hiproll_pose_suppression]]
- 설계입력 종합: [[64_joint_bearing_design_inputs]] · CI/안전율 독트린: [[65_design_value_uncertainty]] · 정책·리워드 전수검사: [[62_policy_reward_design_review]] · 실험 레지스트리: [[66_experiment_registry]]
- 모터 실측·사이징: [[robstride-datasheet]] · [[48_motor_util_sizing]] · hip_yaw 캔틸레버: [[56_humanoid_impact_fall_load_handling]] · Gen-2 bent 계보: [[2026-07-12_gen2_bent_p1]]

---

## §R. 부하 선도 (signed + mjlab 한계선)
포화 요약 · GRF · 토크-속도/각도-토크 산점 · 베어링 로즈 (flat 2.5 bent 명목, 1815s full-coverage 스윕):
![[torque_speed_bentp1.png]]
![[q_torque_bentp1.png]]
![[bentp1_grf.png]]
![[bearing_load_bentp1.png]]
- signed T–N·각도-토크 산점(×1.15 보정 포함) + GRF 분포/per-foot 바 + 조인트프레임 반경력 로즈. peak=클립/낙상 아티팩트이므로 **P99×SF에 사이징**([[65_design_value_uncertainty]]). ★flat 2.5 bent 명목 최악 = **hip_pitch·knee P99 91.0/90.8(clip 76% 나란히)**·**ankle_pitch RMS 112%단일→2-RSU 공동구동 필수(56%)**·**GRF R peak 4.73BW(P99 1.37BW)**·**knee $\omega$ P99.9 73% 실무부하 내부(sim-to-real 갭 완화)**. 배포 설계앵커는 DR/push-학습 **bentp2_fc**([[2026-07-12_bentinit_ab_result]] §8) 몫.
