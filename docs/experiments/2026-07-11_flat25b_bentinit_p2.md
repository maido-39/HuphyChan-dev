# 학습 리포트 — 2026-07-11_21-43-06_flat25b_bentinit_p2 (mjlab flat 2.5 bent-init **Phase2** · DR+push 램프 완주 · ★**현행 push-학습 flat 설계앵커**)

- **task/run**: `2026-07-11_21-43-06_flat25b_bentinit_p2` (mjlab MuJoCo-Warp + rsl_rl PPO) · wandb `pygmalion`
- **풀네임**: **flat-2.5max progress-reward domain-rand+push-ramp bent-knee-init (2026-07-11)**
- **의도/변경점**: **init-pose A/B의 bent arm Phase2** — bent P1 `flat25b_bentinit_p1`([[2026-07-11_flat25b_bentinit_p1]]) `model_19999`에서 **resume + 12000 iter**(총 31999, 최종 ckpt `model_31998`), **`PYG_INIT_BENT=1` 필수 재지정**(토글 없인 obs/action default가 straight로 시프트되어 학습·평가 무효 — [[pyg-no-dr-gating]] 규칙). 변경점 = **DR+push 램프 ON**: straight P2(`flat25b_prog_p2`)와 동일한 `dr_factor` 0→1 선형 램프(iter 20000→32000), push $\pm0.7$ m/s 등 전 DR 채널. 자동 런처 `bentp2_babysitter`가 straight P2 종료 감지 직후 21:43 발진(로그 `analysis/out/bentp2_babysitter.log`).
- **이 런의 위상(정확히)**: ① **init-pose A/B P2-vs-P2의 bent arm이자 최종 승자** — [[2026-07-12_bentinit_ab_result]] §8–9에서 push 453회 **낙상 0**·추종 균일·과반 관절 부하 우세로 **Gen-2 init = bent 확정**의 근거 런. ② 동시에 ★**push-학습(DR-on) flat 2.5 계열의 현행 설계앵커 정책** — 본 리포트의 `bentp2_fc` 데이터가 flat 최악조건 하중의 기준 데이터셋이다(§12).

## 1. 재현성 (Reproducibility)
- **OBS(actor, 45dim)**: base_ang_vel(3)+projected_gravity(3)+joint_pos(12)+joint_vel(12)+last_action(12)+velocity_commands(3). critic(60dim)는 base_lin_vel(3)·foot_height/air_time/contact·foot_contact_forces 추가. flat 태스크라 height_scan 없음. ★joint_pos/action은 **default-pose 상대값**이므로 `PYG_INIT_BENT=1`(bent keyframe: hip_pitch $-0.32$·knee $-0.67$·ankle_pitch $+0.36$ rad, base z 0.83)이 학습·측정 전 과정에 **필수** — 측정 mjb keyframe에서 bent 확인 완료(`bentp2_fc_model.mjb` key_qpos = $[-0.32, 0, 0, -0.67, 0.36, 0]$).
- **Output(action)**: 12 관절 위치타겟(hip p/r/y·knee·ankle p/r ×2), action scale 0.25, use_default_offset(=bent), passive toe 제외.
- **config 백업**: `logs/rsl_rl/pygmalion_velocity/2026-07-11_21-43-06_flat25b_bentinit_p2/params/{env.yaml, agent.yaml}` · seed 42.
- **체크포인트**: `.../model_31998.pt` (resume 20000 + 12000 iter, Time elapsed 5:36:39) · num_envs=8192 · save_interval 100 · resume 소스 = `2026-07-11_06-29-27_flat25b_bentinit_p1/model_19999`.
- **지형**: `terrain_type: plane` (순수 평지).
- **커리큘럼(env.yaml)**: 명령 5-stage는 iter 16000(step 384000)에 이미 상한 도달 → **P2 전 구간 $v_x\,[-2.0,+2.5]$·yaw $\pm1.0$ 고정**(로그 확인). ★신규 = `dr_levels` 커리큘럼: `dr_factor` **0→1 선형**(start 480000 = iter 20000, end 768000 = iter 32000) — P2 전체가 램프 구간이고 최종 iter 31998에서 `dr_factor=1.0000` 도달(§9).
- **측정 소스**: `analysis/out/bentp2_fc.npz`(clean)·`bentp2_fcp.npz`(in-DR push), 각 **90750 steps = 1815 s**, `measure_full.py` 표준(★[[feedback-video-realtime-rule|명령 체류 ≥10 s 규칙]] 준수: **121 명령 × 750 steps = 15 s dwell**, 0.25 격자 + 복합코너 + box 내 랜덤 24), model_31998, `PYG_INIT_BENT=1`, device cpu. fcp는 in-DR push(학습 최대 강도)를 평균 4 s마다 주입 — **총 453회**. 모델 `bentp2_fc_model.mjb`.

## 1b. bentp2 Reward & Gains (config에서 파싱 — 재현용)

**Reward 항목** — ★**P1([[2026-07-10_flat25b_prog_p1]] §1b)과 전 term·weight 완전 동일**(env.yaml 대조). 요약 재게:

| reward | weight | 왜 | 어떻게 |
|---|--:|---|---|
| track_linear_velocity | +2 | 명령 선속도 추종(정밀도) | \exp(-\lVert e\rVert²/σ²), σ=√(0.75)=0.866 |
| track_lin_vel_progress | +1 | 진행보상(고속 얼어붙음 FIX 핵심) | \min(v_xy·\hatcmd, \lvertcmd\rvert) |
| track_angular_velocity | +2 | 명령 회전속도 추종 | \exp(-e²/σ²), σ=0.707 |
| upright | +1 | 몸통 직립 | \exp 자세, σ=0.447 |
| pose | +1 | variable_posture(★default=bent 기준) | default-pose L2, 속도별 σ |
| air_time | +1 | 체공시간 보상 | thr 0.05\sim0.5 s |
| foot_clearance | -2 | 스윙발 이격 | target 0.1 m |
| dof_pos_limits | -1 | 관절범위 한계 | 한계초과 L1 |
| self_collisions | -1 | 자기충돌 | -접촉수 |
| foot_swing_height | -0.25 | 스윙발 높이 성형 | target 0.1 m |
| action_rate_l2 | -0.1 | 액션 급변 | -\lvertΔ a\rvert² |
| foot_slip | -0.1 | 접지발 미끄러짐 | -\lvert v_contact\rvert |
| body_ang_vel | -0.05 | 몸통 각속도 | -\lvertω\rvert² |
| angular_momentum | -0.02 | 각운동량 | -\lvert L\rvert² |
| thermal_effort | -0.02 | 열분배 | \sum(τ/rated)² |
| contact_force_cap | -0.01 | 충격 cap | -\min(\max(F-600,0),800) |
| soft_landing | -1e-05 | 착지 첫접촉 충격(약) | -첫접촉 GRF |
| torque_limit | -0 | off | — |

- **P1과의 유일한 config 차이 = DR 계열**: `push_robot` interval $1\sim3$ s(속도임펄스 $x/y\,\pm0.7$·$z\,\pm0.4$ m/s, roll/pitch $\pm0.52$·yaw $\pm0.78$ rad/s), `foot_friction` $0.3\sim1.2$, `encoder_bias` $\pm0.015$ rad, `base_com` $\pm0.025/\pm0.03$ m — 전부 `dr_factor` 램프에 종속(§9). reward·gain·지형·초기자세는 P1 그대로.

**관절별 Kp/Kd** (position-PD, env.yaml actuator 파싱 — 전 계열 동일):

| 관절 | 모터 | Kp(stiffness) | Kd(damping) | effort clip [N·m] |
|---|---|--:|--:|--:|
| hip_pitch | RS04 | 150 | 6 | 120 |
| hip_roll | RS04 | 150 | 6 | 120 |
| hip_yaw | RS03 | 150 | 6 | 60 |
| knee | RS04 | **220** | 6 | 120 |
| ankle_pitch | RS03 (2-RSU) | 28.5 | 1.81 | 90 |
| ankle_roll | RS00 (2-RSU) | 28.5 | 1.81 | 50 |

- **PD 법 검증**([analysis/analyze_qtarget.py](../../mujoco-sim/mjlab/analysis/analyze_qtarget.py), $\tau\approx K_p e - K_d\dot q$ 회귀, `bentp2_fc`): 복원 gain **Kp 150/150/150/219/28/29 · Kd 6.0/6.0/6.0/6.0/1.8/1.8 · $R^2$ = 1.00 전 관절** — config와 일치(knee 219는 clip 포화로 220보다 소폭 낮게 적합). 사이징 rated는 RobStride 명목값(RS04 40·RS03 20·RS00 5, ankle 2-RSU는 pitch40/roll10 co-act).

## 2. 지표 (Metrics)
- **최종 Mean reward**: **82.0** (iter 31998, `dr_factor`=1.0). 궤적: resume 직후 3.95(과도)→**96$\sim$99(iter 20500$\sim$22000, dr 0.04$\sim$0.17)**→DR 램프 강해질수록 완만 하강 96.9(23k)→92.6(28k, dr 0.67)→**82$\sim$86(31k$\sim$최종, dr 0.92$\sim$1.0)**. ★하강은 붕괴가 아니라 **push+DR 난도 상승의 정상 대가**(ep_len·낙상 지표는 건강 유지, 아래). 최근 50 iter 평균 83.3(범위 79.3$\sim$85.5)로 평탄.
- **error_vel_xy**: 1.05(램프 초)→**1.32**(최종, dr 1.0) · **error_vel_yaw**: 0.70→**0.85** — push 주입 하 자연 증가.
- **ep_len**: **946$\sim$999** (최근 50 iter 평균 978, max 1000) — DR full에서도 에피소드 거의 완주.
- **낙상**: **fell_over 0.00$\sim$0.04**(최근 50 iter 평균 0.013) / low_base 0.04$\sim$0.63(평균 0.35, dr 램프에 비례 증가) — push 최대강도에서도 전도는 사실상 0.
- (기록) iter 23149에 Mean reward $-474769$ **단일 iter 로깅 스파이크**(동일 iter ep_len 987.8 정상, 23150부터 즉시 정상 복귀) — 소수 env 물리 폭주성 reward 이상치로 학습 영향 없음 확인.

## 2b. Reward 기여 (이름 · 값 · 무엇/왜) — 최종 블록(iter 31998, dr_factor 1.0)
| Reward | 가중치 | 기여(final) | 무엇/왜 |
|---|--:|--:|---|
| `track_linear_velocity` | +2 | **+1.3279** | 명령 선속도 추종 — push 하에서도 P1 straight(+1.55)의 86% 유지 |
| `track_angular_velocity` | +2 | **+1.2675** | 명령 회전속도 추종 |
| `upright` | +1 | +0.9510 | 몸통 직립 유지 |
| `track_lin_vel_progress` | +1 | **+0.8165** | ★진행보상 — bent P1(0.896 progress metric)의 고속추종 우위가 P2에도 유지 |
| `air_time` | +1 | +0.6218 | 체공시간 보상 |
| `pose` | +1 | +0.6200 | variable_posture(bent default) |
| `action_rate_l2` | -0.1 | **-0.7378** | 액션 급변 — push 대응으로 P1 계열(-0.50)보다 증가(정상) |
| `thermal_effort` | -0.02 | -0.2171 | 열분배 정규화 |
| `contact_force_cap` | -0.01 | -0.2146 | 충격 cap |
| `angular_momentum` | -0.02 | -0.1648 | 각운동량 벌점 |
| `foot_clearance` | -2 | -0.1311 | 스윙발 이격 |
| `foot_slip` | -0.1 | -0.0268 | 접지발 미끄러짐 |
| `dof_pos_limits` | -1 | -0.0138 | 관절범위 한계 |
| `foot_swing_height` | -0.25 | -0.0128 | 스윙발 높이 성형 |
| `self_collisions` | -1 | -0.0080 | 자기충돌 |
| `body_ang_vel` | -0.05 | -0.0057 | 몸통 각속도 |
| `soft_landing` | -1e-05 | -0.0005 | 착지 충격(약) |
| `torque_limit` | -0 | +0.0000 | off |

- ★**진단**: DR full에서도 양(+) 추종 3항(track_lin 1.33 + ang 1.27 + progress 0.82)이 지배 구조를 유지하고, 음항 최대가 action_rate $-0.74$(push 반응 비용)에 그침 — **push-강건화가 추종을 크게 희생하지 않고 얻어졌다**는 정량 신호. §3c 실측(2.5 순수 93%)과 일치.

## 2c. 학습 건강도 (reward·수렴·추종·낙상)
- reward 96→82로의 하강은 `dr_factor` 램프와 정확히 동행(단조·진동 없음) · ep_len 978 유지 · fell_over $\approx$0.013 · 단일 로깅 스파이크 외 이상 없음 → **DR 램프를 정책이 흡수하며 완주**.
- straight P2 대비: 동일 램프에서 straight는 중저속 stall 블록(33$\sim$70%)이 잔존한 반면 bent는 추종 균일(§3c) — [[2026-07-12_bentinit_ab_result]] §8. bent P1 대비: 낙상 강건성(fc/fcp 리셋 15/19 → **0/0**)이 push-학습으로 완성됨.

## 3b. 보행 시연 (accumulate video)
학습 진행 누적 영상(step/iter 캡션, 36 clips 전체). random-cmd 롤아웃이 DR 램프 속에서 안정 보행을 유지하는 과정. ★캡션 iter는 **resume-상대**(0$\sim$11666; 절대 iter = +20000).

![[accum_flat25b_bentinit_p2.mp4]]
*(원본: `.../videos/accumulated_progress.mp4` — `analysis/accum_video.py`로 train 인터벌 클립 스티칭.)*

**부하 시연 (loadviz demo)** — 좌: 3D 뷰 + GRF 화살표 · 우: R_knee 부호 wrench 패널:

![[bentp2_fc_demo_loadviz.mp4]]
*(vx 그리드 스윕 $-2.0 \to +2.5$, 명령당 15 s 체류(블록 0$\sim$17), ★실시간 재생(25 fps = 50 Hz/다운샘플 2) — `analysis/render_loads.py`, `bentp2_fc.npz` step 0$\sim$13500.)*

- 좌우동시(straight P2 vs bent P2, 동일 명령 프레임잠금) 및 A/B 하중 비교 영상은 [[2026-07-12_bentinit_ab_result]] §7(`ab_p2_sidebyside.mp4`) 참조.

## 3c. 추종 (15 s dwell 정상상태, `bentp2_fc` 121블록)
`analysis/track_from_npz.py`(qpos_full body-frame 유한차분+yaw회전, settle 15) · 전표: `analysis/out/bentp2_fc_tracking.txt`

**고속 전진 $v_x=2.5$ 전조합(11블록)** — ★straight P2의 stall 널뛰기(33$\sim$70%) 대비 **균일 추종**:

| cmd (2.5, vy, wz) | 달성 vx | vx% |
|---|--:|--:|
| (2.5, 0, 0) 순수 | 2.33 | **93%** |
| (2.5, 0, ±1.0) | 2.36 / 2.41 | 95 / 96% |
| (2.5, 0, +0.5) | 2.34 | 93% |
| (2.5, ±1.0, 0) | 2.30 / 2.37 | 92 / 95% |
| (2.5, +0.5 / -0.5, 0) | 2.17 / 1.97 | 87 / **79%** |
| (2.5, ±0.8, ±0.75) 복합 | 2.25 / 2.43 | 90 / 97% |
| (2.5, 0, -0.5) | 1.50 | **60%** ⚠ 유일 저조 |

| 축 | 결과 | 판정 |
|---|---|:--:|
| v_x +2.5 조합 | **10/11 블록 79\sim97%** (순수 93%), 예외 1블록(2.5,0,-0.5) 60% | ✅ |
| v_x +2.0\sim+2.25 | 95\sim98% | ✅ |
| **후진 v_x≤-1.75** | **13/14 블록 89\sim99%**, 예외 (-2.0,0.5,0) 63% | ✅ ★straight P2(56\sim89%)보다 우세 |
| 잔여 저조(<75%) | **9/121 블록만**, 산발( (1.38,-1.0) 47%·(1.0,0,0) 58%·(-0.88,0,-1.0) 41% 등) | 계통적 stall 밴드 없음 |

- ★**판정**: straight 계보의 중저속/고속 stall이 **계통 결함으로는 부재**(고립 블록 9/121만 잔존, straight P2는 2.5 전조합이 33$\sim$70%로 계통 붕괴) — A/B §8 "균일 79$\sim$97%" 확인, 단 (2.5,0,$-0.5$) 60% 1블록은 예외로 병기. 잔여 고립 블록은 Gen-2 명령게이팅/mirror 수정 몫([[2026-07-11_midspeed_stall_overshoot]], [[62_policy_reward_design_review]]).

## 5. 분석
flat 2.5 + 진행보상 + **bent-init + DR/push full** (측정 fc = clean 121블록/1815 s, fcp = 453 push, L+R pooled, raw N·m):
- **★낙상 ZERO**: fc 리셋 **0** · fcp(453 push) 리셋 **0**(스텝간 최대 변위 0.058/0.068 m — 텔레포트 부재로 교차검증). bent P1(fc 15·fcp 19)→P2에서 완전 소거 = **push-학습 독트린 검증**.
- **base_height**: 평균 **0.796 m**·p5 0.762·min 0.726 — bent 크라우치 유지(straight P1 0.819보다 낮음), low_base(0.7) 여유 확보.
- **RMS(열여유)**: ★**knee 43.5 = 109%**(43.5/40, **유일 rated 초과 = RMS binding이 ankle→knee로 이동**)·ankle_pitch 76%(15.3/20 단일 RS03; **2-RSU co-act pitch40 기준 38%로 여유**)·hip_pitch 71%·ankle_roll 64%·hip_yaw 62%·hip_roll 54%. bent 크라우치의 관절모멘트팔이 knee 상시토크를 키운 구조적 결과(구 A/B [[55_init_pose_straight_vs_bent]]의 knee 열비용 재현).
- **P99(순시/반복 앵커)**: **knee 109.3**(clip 120의 **91%**)·**hip_pitch 95.0**(79%)·ankle_pitch 60.5(67%)·hip_roll 54.7(46%)·hip_yaw 31.7(53%)·ankle_roll 11.0(22%). ★straight P2(knee 91.9·hip_pitch 98.6) 대비 knee +19%/hip_pitch $-4$%인데, **knee +19%에는 achieved-confound**(straight는 stall 블록에서 명령을 못 낸 몫이 빠짐)가 섞임 — [[2026-07-12_bentinit_ab_result]] §8†. knee 109.3은 클립의 91%로 얇으나 **계획된 knee 링크레버(1.5:1)가 커버**.
- **push delta (fcp vs fc, P99)**: hip_pitch **+5.3%**·knee **$-1.0$%**·ankle_pitch **+0.0%**·hip_roll $-1.3$%·ankle_roll +6.4%·GRF +5.1% — ★**주부하 관절이 $-1\sim+6$%로 수렴 = push-학습이 push 하중을 in-distribution으로 흡수 완료**(bent P1은 push 시 knee가 clip +32% 튀었음). 유일 예외 hip_yaw +16.4%(31.7→36.9, 절대값 작아 rated 내). fcp에서도 sat% 최대 0.62%(knee)로 clean과 동급.
- **knee $\omega$ 수요 (★sim-to-real 갭 대폭 완화)**: P99 **11.7**·P99.9 **15.3**·max 28.1 rad/s. RS04 무부하 실측 **19.9 rad/s**([[reference-robstride-motor-specs]]) 대비 **P99.9 = 77%로 실한계 안**(straight P1은 18.9로 95%에 붙었음) — bent gait가 knee 속도수요도 낮춘다. max 28.1(141%)은 초과 표본 **0.0017%**(수 샘플)의 순간 스파이크로 사이징 비대상. ankle_pitch max 22.8(fcp 32.7 — push 회복 스윙).
- **GRF**: pooled P99 **1.30$\times$BW**(655 N, BW=505 N)·P99.9 3.21BW·peak 9.61BW(4853 N, L발 단발 충격 — raw peak 사이징 금지 [[65_design_value_uncertainty]] §4). fcp P99 1.36BW·peak 6.84BW. ★전 계보 최저 수준 P99(straight P2 1.35·bent P1 1.37·straight P1 1.52BW) = bent 착지흡수 + push-학습 사뿐착지의 합.

## 7. 모터 활용 시각화 (토크·속도 RMS/p95/max vs 스펙선 + 시계열)
*스펙선(rated 초록/peak-clip 빨강)은 mjlab RobStride 1:1 기준. 사이징 rated: RS04 40·RS03 20·RS00 5(ankle 2-RSU는 pitch40/roll10 co-act). effort clip은 raw(120/60/90/50). 표는 raw 토크(sim→real $\times1.15$는 [[65_design_value_uncertainty]] §5 SF에서 반영).*

**관절 토크 RMS/p95/MAX vs rated·peak-clip**
![[bentp2_torque.png]]

**관절 속도 RMS/p95/MAX(rpm) vs 무부하 실속도**
![[bentp2_speed.png]]

**관절 토크 시계열(peak/rated 선, 첫 12 s)**
![[bentp2_torque_ts.png]]

| 관절 | RMS | %rated | p95 | max(=clip) | P99 | %peak(P99) | sat%(≥99%clip) | binding |
|---|--:|--:|--:|--:|--:|--:|--:|:--:|
| hip_pitch | 28.5 | 71% | 67.7 | 120.0* | **95.0** | **79%** | 0.01% | P99 2위 |
| hip_roll | 21.7 | 54% | 42.1 | 92.5 | 54.7 | 46% | 0.00% | |
| hip_yaw | 12.4 | 62% | 25.3 | 52.8 | 31.7 | 53% | 0.00% | |
| knee | **43.5** | **109%** | 80.5 | 120.0* | **109.3** | **91%** | 0.67% | ★**RMS+P99 양쪽 binding** |
| ankle_pitch | 15.3 | 76% | 32.2 | 90.0* | 60.5 | 67% | 0.02% | 2-RSU co-act 기준 38% 여유 |
| ankle_roll | 3.2 | 64% | 7.5 | 24.1 | 11.0 | 22% | 0.00% | |

- 정량: **RMS binding = knee(109%)** — 유일 rated 초과(straight 계열의 ankle_pitch binding이 knee로 이동; bent 크라우치 상시토크). saturation%(≥99% clip): knee 0.67%·hip_pitch 0.01%로 **hip_pitch 포화가 straight P1(1.06%)서 사실상 소거** — bent가 hip 순시부하를 분산. max(*)는 clip 상한이므로 정적사이징 금지. 속도 p95(rpm): knee 77.9·ankle_pitch 58.4·hip_pitch 35.5 — 전 관절 p95 실한계 내, knee max 268 rpm(28.1 rad/s)만 RS04 실 190 rpm 초과(표본 0.0017%, §5).
- (교차검증) `actuator_eval.py`(sim→real $\times1.15$·TN/열모델, `actuator_eval_bentp2.csv`): knee RMS$\times$1.15 = 125% ⚠·hip_pitch 열 $T_{ss}$ 105 °C ⚠ — **1:1 직결 가정 시 knee/hip_pitch 열이 미달**이므로 knee 링크레버(1.5:1)+열설계가 전제(§12). 2-RSU co-act ankle은 pitch40 기준 통과.

## 8. 설계·부하 선도 — $q$·속도·토크 작동평면 (signed + 한계선)
*§8~8c가 설계선도(=부하선도) 계통이다: 작동평면(§8) → 레짐 색분할(§8b) → 실측 TN 엔벨로프·컨투어(§8c). wrench(힘·모멘트) 계통은 §10.*
*측정: `bentp2_fc` 90750 frames · $v_x[-2.0,2.5]$/$v_y\pm1.0$/yaw$\pm1.0$ 전 box 0.25격자, 1815 s. 산점 토크축은 $\times1.15$(sim→real) 표기.*

**관절각 $q$ – 토크 $\tau$** (수평선 = rated/peak-clip)
![[q_torque_bentp2.png]]
- knee: bent 크라우치라 지지상이 **$q\approx-40\sim-60°$ flex 대역에 상주**하며 고토크 — straight 계열보다 작동점이 깊은 flex 쪽으로 이동, clip(120) 도달은 0.67%. hip_pitch는 straight P1처럼 양·음 clip에 상시 붙지 않음(포화 0.01%).

**관절각 $q$ – 속도 $\dot q$** (수평선 = 무부하 실속도)
![[q_speed_bentp2.png]]
- knee flex 대역 진자형 분포, max 268 rpm 소수 표본만 실무부하선(190 rpm) 초과 — straight P1 대비 속도수요 완화(§5).

**토크 $\tau$ – 속도 $\dot\omega$ (T–N 4상한)**
![[torque_speed_bentp2.png]]
- 고토크는 저속(지지상)·고속은 저토크(스윙)로 분리, T–N 동시요구 없음. knee가 rated box 밖 저속-고토크 구역을 straight보다 넓게 점유(크라우치 상시토크) — RMS binding의 기하적 원인.

**q/qtarget 오차 + 토크 P/D 분해** ($\tau\approx K_p e - K_d\dot q$, [[feedback-qtarget-analysis-rule|q/qtarget 규칙]])
![[qtarget_error_bentp2.png]]
![[qtarget_error_bymove_bentp2.png]]
- ★**knee P-term RMS 46.4 / D-term 21.4**로 양쪽 모두 6관절 최대 — 오차구동(err_rms 0.21 rad)과 감쇠가 함께 knee에 집중(RMS 109%의 제어적 내역). hip_pitch P 30.7/D 10.4. ankle_pitch는 err_rms 0.57·p95 1.22 rad로 오차 크나 soft Kp28.5라 토크 낮음(2-RSU 유연 발목 특성, straight 계열과 동일 패턴). 전 관절 $R^2=1.00$으로 PD 법 검증(§1b).

## 8b. 레짐별 작동점 (명령 레짐 색분할, 2026-07-12 소급)
*§8과 동일 데이터(`bentp2_fc` 90750 frames)를 **명령 레짐**으로 색분할: forward/backward/lateral/turn/combo(다축 동시명령)/stand. push 대조는 `bentp2_fcp`(in-DR push 453회). ★본 런 = 설계 앵커이므로 "어느 레짐이 어느 한계를 미는가"가 곧 사이징 근거.*

**T–N 작동점 (레짐 색분할)**
![[regime_tn_bentp2r.png]]

**$q$–$\tau$ (레짐 색분할)**
![[regime_qt_bentp2r.png]]

**$q$–$\dot q$ (레짐 색분할)**
![[regime_qw_bentp2r.png]]

**T–N: clean(fc, 회색) vs push 주입(fcp, 적색)**
![[push_tn_bentp2r.png]]

- ★**knee 120 clip vs RMS binding의 레짐이 다르다**: RMS binding(§7 109%)의 본체는 **forward** — 크라우치 지지대역($q\approx-0.7\sim-1.2$ rad, $+50\sim110$ N·m, 저속)에 청색이 상주. 반면 **120 N·m clip 평탄대에 실제 닿는 점은 backward·combo**(T–N·$q$–$\tau$ 상단 띠가 진보라/분홍). 즉 열(RMS) 사이징은 전진보행이, 순시 clip은 후진·다축 명령이 규정 — 열=RMS·순시=in-DR P99 원칙([[62_policy_reward_design_review]])의 레짐별 실체.
- **속도 외피는 backward가 확장**: knee $\dot q$ 극단($\pm15\sim18$ rad/s)과 ankle_pitch 고속 아크($+10\sim15$ rad/s, $+20$ N·m)가 진보라 — 후진 시 스윙 리듬이 깨져 고속 재스윙이 발생. 단 토크 동반 없음(T–N 4상한 분리 유지)이라 T–N 동시요구는 여전히 미발생.
- **push 외피 ≈ clean 외피**: 적색(fcp)이 회색(fc) 외곽을 사실상 넘지 않음(6관절 모두 중첩, hip_yaw만 미세 확장). §9의 push delta P99 $-1\sim+6$% 수렴과 정합 — clean 121블록 통계를 그대로 앵커로 써도 push에 강건.

## 8c. 속도-토크 설계선도 — 실측 TN 엔벨로프 + RMS/P99/Peak 컨투어 + flat/rough 색분리 (구 §R 부하선도 통합)
*`analysis/tn_design.py` — 실측 48V 벤치 TN 곡선(Motor_Spec CSV, 4상한 미러) 위에 **flat 앵커(`bentp2_fc`, 청색) vs rough 앵커(`p2r_fc`, 갈색)** 작동점 클라우드 + 방향분위 컨투어(RMS-scale $q=0.5$ 초록 / P99 $q=0.99$ 주황 / Peak hull $q=1.0$ 빨강; 실선=flat·파선=rough) + 축별 극값 빨간점. ankle은 2-RSU co-act(곡선 토크 $\times2$) 기준, raw sim 토크(무derate).*

![[tn_design_anchors.png]]

- ★**P99(주황) 컨투어는 6관절 모두 실측 TN 엔벨로프(보라) 내부** — 순시앵커(P99) 기준으로는 flat·rough 어느 관절도 실모터 커버리지를 벗어나지 않는다. 엔벨로프를 넘는 것은 **Peak hull(q100, 빨강)의 속도축 꼬리뿐**: knee flat 극값 $+22.0\sim28$ rad/s와 ankle_pitch flat $-22.8$ rad/s가 실 무부하선($\pm19.9$, 적점선)을 초과 — §5의 0.0017% 스파이크와 동일 사건으로 저토크 스윙 구간이라 T–N 동시요구는 아님(사이징 비대상, 단 sim-to-real 속도갭 잔존 표시).
- **knee = 엔벨로프 마진이 가장 얇은 관절**: flat P99가 저속에서 $+110$ N·m 부근까지 올라가 보라 상단($\approx120$)과 clip(120)에 근접(마진 $\sim8$%), Peak hull은 flat·rough 모두 $+120$ clip 평탄대에 접촉(적점 +120 N·m 2개) — §7 knee 양축 binding·링크레버 1.5:1 전제의 TN 선도상 재확인.
- **flat vs rough 클라우드의 역할 분담**: flat(청)은 고속명령(2.5 m/s) 때문에 **속도축으로 넓게**(knee·ankle_pitch $\pm15\sim20$ rad/s대 점유), rough(갈)는 저속이지만 **토크축 밀도가 높음** — hip_roll rough 극값 $-117$ N·m(clip 근접, flat $-92$)·hip_pitch rough $-117$ 등 험지 착지 토크꼬리가 flat보다 김. 즉 속도 설계는 flat이, 저속 고토크(험지 스텝다운)는 rough가 규정.
- **ankle 2-RSU co-act의 여유 확인**: ankle_pitch는 co-act 엔벨로프(2$\times$RS03) 안에서 P99가 저토크 대역에 납작하게 깔리고(빨간 극값 $-90/-85$ N·m만 clip 90 부근), ankle_roll은 전 컨투어가 2$\times$RS00 엔벨로프 중심부에 소형으로 수렴(극값 $-24/-28$ N·m) — 공동구동 전제([[project-2rsu-ankle-tool]])의 TN 선도상 검증.
- **설계 요약(구 §R)**: peak=클립/단발충격 아티팩트 → **P99$\times$SF 사이징**([[65_design_value_uncertainty]]). flat push-학습 앵커 최악 = **knee P99 109.3(91% clip·worst-leg L 116.7)+RMS 109%(유일 양축 binding → 링크레버 1.5:1 커버)** · hip_pitch P99 95.0 · ankle_pitch 60.5(2-RSU 여유) · knee $\omega$ P99.9 77% 실무부하 · push 453회 낙상 0.

## 9. DR 커버리지 (★Phase2 = DR+push 램프 완주 — 본 계보 최초의 DR-on flat 앵커)
- **`dr_factor` 램프**: 0(iter 20000)→**1.0000(iter 31998)** 선형 완주(로그 실측: 0.25@23k·0.50@26k·0.83@30k·1.0@final). 적용 채널 = **push**(interval $1\sim3$ s, $v\,x/y\,\pm0.7$·$z\,\pm0.4$ m/s·roll/pitch $\pm0.52$·yaw $\pm0.78$ rad/s) + **foot_friction** $0.3\sim1.2$ + **encoder_bias** $\pm0.015$ rad + **base_com** $\pm0.025/\pm0.03$ m. straight P2와 동일 스케줄(A/B 변인통제 유지, diff = init 단 하나).
- **측정 커버리지**: fc = 학습 box 전범위($v_x[-2.0,2.5]$·$v_y\pm1.0$·yaw$\pm1.0$) 0.25 격자 121블록 균일 15 s dwell — **in-DR 원칙**([[62_policy_reward_design_review]]) 충족. fcp = 동일 스케줄 + **in-DR 최대강도 push 453회**.
- ★따라서 본 리포트의 하중은 **DR-on·push-포함 배포급 통계**다 — straight/bent P1(DR-OFF 명목 하한)과 달리 **설계 앵커로 직접 사용 가능**. push delta가 P99 기준 $-1\sim+6$%(주부하 관절)로 수렴했으므로 fc(clean) 통계가 push 유무에 둔감 = 앵커의 강건성 근거(§5).

## 10. 관절 반력 wrench (per-LINK)
*측정 소스: `bentp2_fc`(90750 steps, L+R pooled). 상세 조인트프레임 $F_r/F_a/M_t$·RMS/RMC/p99/peak·동시6벡터: [[wds_bentp2_fc]]. A/B 조인트프레임 대조(straight P2 vs bent P2): [[2026-07-12_bentinit_ab_result]] §8.*

**GRF 분포·per-foot (wrench 계통의 입력 — 구 §R에서 이동)**
![[bentp2_grf.png]]
- GRF P99 **1.30BW**(계보 최저)·peak 9.61BW는 단발충격(충격요건 참조용).

**조인트프레임 wrench $F_r$–$M_t$ 레짐 색분할 (§8b에서 이동)**
![[regime_wrench_bentp2r.png]]
- **극단 꼬리는 전 관절에서 combo 레짐이 지배**(hip_pitch $F_r>600$ N·knee $>700$ N·ankle_pitch $>1$ kN·ankle_roll $M_t>200$ N·m, 단일축은 주 클라우드 내부) → **구조 하중(P99 wrench$\times$SF) worst-case는 combo 구간이 결정**, 단일축만 훑는 프로토콜은 과소평가.

**per-link 요약(P99/max, N·N·m, L+R pooled)**

| body | \|F\| P99 [N] | \|F\| max [N] | \|M\| P99 [N·m] | \|M\| max [N·m] |
|---|--:|--:|--:|--:|
| hip_pitch_link | 478 | 2144 | 111.1 | 317.3 |
| hip_roll_link | 491 | 2219 | 111.6 | 324.3 |
| thigh_link | 514 | 2269 | 112.8 | 310.5 |
| shin_link | 567 | 2985 | 134.3 | 455.8 |
| ankle_pitch_link | 616 | 4330 | 172.8 | 1019.0 |
| foot_link | 620 | 4395 | 169.8 | 1012.3 |

**베어링-로드 로즈(조인트프레임 반경력 방향분포 + 설계수치)**
![[bearing_load_bentp2_fc.png]]

- 지지상 다리축 압축(z) 지배, 접촉 과도가 **foot→ankle→shin→thigh→hip 순 감쇠 전파**($\lvert F\rvert$ P99 620→478 N·$\lvert M\rvert$ 173→111 N·m). ★straight P1 flat 앵커(foot $\lvert F\rvert$ P99 834·$\lvert M\rvert$ 192) 대비 **P99가 전 링크 $-25\sim-13$% 낮음** — bent 착지흡수의 구조하중 이득. max 열(4395 N 등)은 GRF peak 9.61BW 단발 충격과 동일 사건(1425.1 s 부근, [[wds_bentp2_fc]] 동시6벡터)으로 **충격요건 참조용**(P99$\times$SF 사이징 원칙).

## 10b. 3D wrench 벡터공간 (F·M 방향분포 + RMS/P99/peak 표면, 2026-07-12)
*`analysis/wrench3d.py` — `bentp2_fc` 조인트프레임(joint-local frame) 반력 벡터 $(F_x,F_y,F_z)$·$(M_x,M_y,M_z)$를 3D 성분공간에 직접 표시(L+R pooled, R 미러). **표면 = 방향별 분위수 반경**(36각 빈 방향분위): 초록 = RMS-scale($q50$), 주황 = P99($q99$), 적색 와이어 = peak hull. 빨간점 = 축별 P99/절대 peak 극값('out' = 표시박스 밖 클립).*

**반력 $F$ 3D 성분공간 (knee · hip_pitch · ankle_pitch · hip_yaw)**
![[wrench3d_F_bentp2.png]]

**반력모멘트 $M$ 3D 성분공간**
![[wrench3d_M_bentp2.png]]

**턴테이블(전 6관절, 관절별 F·M 쌍 3×4 그리드) — ★슬로 턴테이블(실시간 데이터 아님, 시점 회전용)**
![[wrench3d_turntable_bentp2.mp4]]

- ★**$F$ 공간은 전 관절 $-F_z$(다리축 압축) 이방성**: 축별 P99가 knee $(+91,\,+255,\,-541)$·hip_pitch $(+112,\,-320,\,-403)$·ankle_pitch $(-597)$ N로 압축축이 횡력의 2$\sim$6배. ankle_pitch는 $+F_x/-F_z$ **대각 로브**(전진 push-off 반력 방향)가 뚜렷 — 발목 구조하중의 주방향이 순수 수직이 아니라 전방 경사라 베어링/링크 배치 시 방향 고려 필요.
- **절대 peak 꼬리(암적색 'out')는 P99의 $\approx5\times$**: knee $F_z\,-2837$·ankle_pitch $F_z\,-2971$·hip_pitch $F_z\,-2092$ N — §10의 단발 충격 사건(GRF 9.61BW, 1425 s 부근)과 동일 스파이크로 표시박스 밖 클립. **P99 표면(주황)$\times$SF로 사이징, raw peak 금지** 원칙의 시각적 실체.
- **$M$ 공간은 구동축이 아닌 횡굽힘이 지배**: ankle_pitch $M_x$(롤 굽힘) P99 $-142$ > 구동축 $M_y$ P99 $+94$(peak $M_x\,+793$ out), knee도 $M_x$ P99 $\approx+140$·peak $+271$이 구동 $M_y$ P99 $+83$을 상회 — 2-RSU 발목·knee 하우징의 구조/베어링 설계는 **모터 토크가 아니라 조인트프레임 횡모멘트**가 규정(§10 로즈의 방향 편중과 정합).
- **RMS(초록) 표면은 P99(주황)의 1/3 내외이고 최대방향도 불일치** — 열하중(RMS)과 구조하중(P99)의 지배 방향이 다르므로, 프레임/베어링은 방향별 P99 표면·열은 RMS로 분리 적용([[65_design_value_uncertainty]] 원칙의 3D 확인).

## 11. gait + L/R 대칭 분석
**L/R 대칭** (토크 RMS raw N·m·GRF·kinematic, `bentp2_fc`)

| 지표 | L | R | 비대칭 |
|---|--:|--:|--:|
| hip_pitch 토크 RMS [N·m] | 28.88 | 28.03 | 3% |
| hip_roll 토크 RMS [N·m] | 20.99 | 22.35 | 6% |
| hip_yaw 토크 RMS [N·m] | 12.32 | 12.45 | 1% |
| knee 토크 RMS [N·m] | 45.30 | 41.71 | 8% |
| ankle_pitch 토크 RMS [N·m] | 17.57 | 12.57 | **28%** |
| ankle_roll 토크 RMS [N·m] | 3.11 | 3.30 | 6% |
| knee flex min [°] | -97.5 | -100.1 | 3% |
| GRF peak [×BW] | 9.61 | 6.84 | 29% (단발 스파이크 포함) |

- ★해석: hip 3관절·knee kinematic은 1$\sim$8%로 straight P1(최대 16%)보다 **개선**. 잔여 비대칭은 **ankle_pitch 28%**(L 17.6 vs R 12.6 — L발 push-off 과부담)와 GRF peak 29%(L 단발 충격 4853 N 포함; P99 기준 pooled 1.30BW로 양발 유사). 하드웨어 사이징은 **worst leg 기준**: knee L RMS 45.3·knee L P99 116.7·ankle_pitch L RMS 17.6. 잔여 비대칭은 Gen-2 mirror-equivariant 항목([[62_policy_reward_design_review]]).
- **tracking**: §3c — 2.5 전조합 79$\sim$97% 균일(1블록 예외)·후진 89$\sim$99%·고립 저조 9/121. push 453회 낙상 0.

## 12. 종합 판정
**bent-init Phase2 = init-pose A/B 최종 승자이자 ★현행 push-학습 flat 설계앵커** ([[2026-07-12_bentinit_ab_result]] §9 확정):
- **성립**: ① `dr_factor` 1.0 완주(reward 82 평탄·ep_len 978·fell 0.013) ② **push 453회 낙상 ZERO**(fc/fcp 리셋 0/0) ③ 고속 2.5 전조합 79$\sim$97% 균일 추종(straight P2의 33$\sim$70% stall 계통결함 부재)·후진 89$\sim$96% ④ push delta P99 $-1\sim+6$%(주부하) = push in-distribution 흡수 ⑤ PD 법 검증($R^2=1.00$) ⑥ GRF P99 1.30BW로 전 계보 최저 수준.
- **잔여 결함(사이징 비영향)**: ⑦ 고립 저조 블록 9/121((2.5,0,$-0.5$) 60% 등 — 계통 아님) ⑧ ankle_pitch L/R 28% 비대칭 ⑨ hip_yaw push delta +16%(절대값 작음). Gen-2 보상스택(명령게이팅 클록·mirror-equivariant, [[62_policy_reward_design_review]])의 몫.
- **★설계앵커 지정**: 본 런의 **`bentp2_fc`가 push-학습 flat 최악조건의 기준 데이터셋**이다. [[65_design_value_uncertainty]] §2의 flat 표는 현재 구세대 런 기준이므로 **bentp2_fc 값(knee P99 109.3·hip_pitch 95.0·ankle_pitch 60.5·GRF P99 1.30BW)으로 재앵커가 필요** — 65 문서 갱신은 별도 작업으로 남긴다(본 리포트에서는 지정만).

**설계점(flat 2.5 push-학습 하중 — in-DR·worst-leg·SF는 [[65_design_value_uncertainty]] §5 규칙: 열=RMS$\times$1.15, 순시=P99$\times$1.25, raw peak 금지)**:
- **knee = 유일 양축 binding**: P99 **109.3**(clip 120의 91%, worst-leg L 116.7)·RMS **43.5(109% rated — 유일 RMS 초과)**. 순시앵커 = P99$\times$1.25 $\approx$ **137**, 열앵커 = RMS$\times$1.15 $\approx$ **50**(RS04 40의 125%). ★1:1 직결로는 열·순시 모두 미달 → **계획된 knee 로터리+링키지 레버(1.5:1, [[reference-rotary-linkage-knee]])가 양쪽을 동시 커버**(모터측 P99 73·RMS 33 = 82%). straight P2 대비 +19%에는 achieved-confound 포함(§5).
- **hip_pitch**: P99 **95.0**(79% clip)·RMS 28.5(71%). straight P1(P99 119.8 clip 도달·sat 1.06%)의 순시병목이 **bent에서 해소**(sat 0.01%) — RS04 유지 타당.
- **ankle_pitch**: P99 60.5(67% clip)·RMS 15.3 — **2-RSU 공동구동(pitch40 co-act) 기준 RMS 38%·P99 76%로 여유**(단일 RS03 가정 시 RMS 76%). 공동구동 전제 유지([[project-2rsu-ankle-tool]]). ankle_roll P99 11.0(22%).
- **GRF 구조앵커 = P99 1.30BW$\times$SF**(655 N; P99.9 3.21BW 참조·peak 9.61BW는 충격요건만). 전 계보 최저 P99 — bent+push-학습의 착지흡수 이득.
- **knee $\omega$**: P99.9 **15.3 rad/s = RS04 실무부하(19.9)의 77%** — straight P1의 95% 적신호가 **정상 마진으로 회복**. max 28.1(141%)은 0.0017% 스파이크로 비사이징. 감속비 재검토 압력 완화(단 링크레버 1.5:1 채택 시 모터측 $\omega$ 1.5$\times$ 재확인 필요).

## 6. 관련 학습 / 연구 링크
- **부모(bent P1, DR-OFF)**: [[2026-07-11_flat25b_bentinit_p1]] · straight 대조(P1): [[2026-07-10_flat25b_prog_p1]] · straight P2 run `flat25b_prog_p2`(별도 노트 없음, A/B 결과에 수록)
- **A/B 계획·판정**: [[2026-07-11_bentinit_ab_plan]] · ★[[2026-07-12_bentinit_ab_result]] §8–9(P2-vs-P2 최종: bent 확정) · 구 A/B 반전 배경: [[55_init_pose_straight_vs_bent]]
- 진행보상 FIX 근거: [[2026-07-10_highspeed_freeze_progress_reward]] · 중저속 stall 연구: [[2026-07-11_midspeed_stall_overshoot]]
- 설계입력 종합: [[64_joint_bearing_design_inputs]] · CI/안전율·앵커 규칙: [[65_design_value_uncertainty]] · 정책·리워드 전수검사: [[62_policy_reward_design_review]]
- knee 링크레버 선례: [[reference-rotary-linkage-knee]] · RobStride 실측: [[reference-robstride-motor-specs]] · wrench 상세: [[wds_bentp2_fc]] · rough 최종(대조): [[2026-07-09_rough_p2_final]]
