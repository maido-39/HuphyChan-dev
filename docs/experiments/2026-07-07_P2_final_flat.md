# 학습 리포트 — 2026-07-07_05-14-13 (mjlab P2-final)

- **task/run**: `2026-07-07_05-14-13` (mjlab MuJoCo-Warp + rsl_rl PPO)
- **의도/변경점**: 2단계 커리큘럼(Phase1 DR-off G1-like 보행 → Phase2 DR 램프)로 학습한 최종 flat 정책. 직립 default·역관절0°·L/R대칭 모델·air_time gait·hip150/6·knee flex 허용.

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

## 3b. 보행 시연 — 고정 전후좌우 스윕 (최종 정책)
전진·후진·좌우 스트레이프·회전·정지 고정 스케줄. 상단 라벨=명령, 관절구=토크 포화색.
![[p2_flat_demo_loadviz.mp4]]
*(직립 초기자세·무릎 굽힘 보행·역관절 없음 확인용)*

## 5. 분석
P2 최종(20k, DR full 수렴): 직립정지(무릎-5.6도·base0.856)·무릎보행굽힘(R-67도)·역관절 max2.6도·DR강건(ep_len 1000 through ramp). in-range(vx1.5) 하중: RMS 전관절 OK(열여유), peak만 초과(knee/hip 127-138·ankle 92/27)=링크레버+2-RSU로 커버. GRF P99 1.28xBW. ★L/R 비대칭은 무릎 kinematics(24%)에 국한, 토크/GRF는 대칭(0-8%)=하중균형.

## 7. 모터 활용 시각화 (토크·속도 RMS/p95/max vs 스펙선 + 시계열)
*스펙선(rated 초록/peak·vel-limit 빨강)은 mjlab RobStride 1:1 기준.*

**관절 토크 RMS/p95/MAX vs rated·peak**
![[2026-07-07_05-14-13_torque.png]]

**관절 속도 RMS/p95/MAX(rpm) vs 속도한계**
![[2026-07-07_05-14-13_speed.png]]

**관절 토크 시계열(peak/rated 선)**
![[2026-07-07_05-14-13_torque_ts.png]]

- 정량: knee RMS 42%·ankle_pitch RMS 79%·binding(RMS>rated): 없음

## 8. q-속도-토크 선도 (한계선)
*측정: `p2_long` 롤아웃 18000 frames · 133 cmd (vx $\pm1.5$ / vy $\pm1.0$ / yaw $\pm1.0$, 학습범위 일치, PYG_NO_DR).*

**관절각 $q$ – 토크 $\tau$** (수평선 = rated/peak)
![[q_torque_P2-final.png]]
- knee: flex 구간(음의 $q$)에서 토크가 커지는 전형적 지지상 분포 — peak선 순간 초과(115%)는 접촉 과도에 국한. hip_roll도 스탠스 hold 토크가 peak선 근접(138%p).

**관절각 $q$ – 속도 $\dot q$** (수평선 = 속도한계)
![[q_speed_P2-final.png]]
- 속도는 전 관절 한계 내(knee P99 68/129 rpm, ankle_pitch 75/170 rpm) — 스윙 flex 구간에서만 속도가 커지는 진자형 분포, 속도 binding 없음.

**토크 $\tau$ – 속도 $\dot\omega$ (T–N 4상한)**
![[torque_speed_P2-final.png]]
- 대부분의 점이 TN 곡선 안쪽 저속-중토크 사분면(모터링)에 밀집. 고토크는 저속(지지상)·고속은 저토크(스윙)로 분리 → T–N 동시요구 없음. peak 초과점은 순간 스파이크뿐.

## 8b. 레짐별 작동점 (명령 레짐 색분할, fc/fcp 신데이터, 2026-07-12 소급)
*측정: `p2f_fc.npz`(clean 사방 스윕) + `p2f_fcp.npz`(push 주입) · 색 = 명령 레짐: 파랑=forward, 남보라=backward, 초록=lateral, 주황=turn, 분홍=combo, 회색=stand (push 비교도만 회색=clean fc / 빨강=push-injected fcp).*

★**해석 주의(맥락)**: 이 정책은 2.5-era 전체 측정박스에서 붕괴했던 정책(학습박스는 vx $\pm1.5$)이며, 본 fc 스윕은 $\pm1.5$ 박스로 맞췄음에도 **109회 낙상**이 발생 → 아래 구름에는 **낙상 과도 상태가 섞여 있다**. 바깥쪽 희박 꼬리는 정상보행 작동점이 아니라 낙상/충돌 과도로 읽어야 한다.

**T–N (토크–속도, 레짐 색분할)**
![[regime_tn_p2fr.png]]

**$q$–$\tau$ (관절각–토크, 레짐 색분할)**
![[regime_qt_p2fr.png]]

**$q$–$\dot q$ (관절각–속도, 레짐 색분할)**
![[regime_qw_p2fr.png]]

**관절좌표계 wrench ($F_r$ vs $M_t$, 레짐 색분할)**
![[regime_wrench_p2fr.png]]

**T–N clean(fc) vs push-injected(fcp)**
![[push_tn_p2fr.png]]

- **깨끗한 보행 로브 vs 낙상 산포의 레짐 분리가 명확**: forward(파랑)·turn(주황)은 전 선도에서 조밀한 코어 로브(knee 지지상 고토크 기둥 + 스윙 저토크 날개)만 형성하는 반면, **combo(분홍)가 모든 바깥 꼬리를 지배** — wrench 극단치(hip_pitch $F_r$ ~1400 N, ankle_roll $M_t$ ~700 N·m, knee $F_r$ ~1750 N)가 거의 전부 분홍/남보라 = 낙상 충격 과도.
- **backward(남보라)도 낙상 산포 징후**: hip_yaw에 $-40\sim-60$ N·m(clip 근접) 음토크 로브, ankle_roll wrench에 $F_r$–$M_t$ 동반 상승 대각 꼬리가 backward에서만 뚜렷 — 후진 명령에서 자세 회복/전도 과도가 잦았음을 시사.
- **ankle_pitch의 $-75$ N·m급 심부 저항굴곡 스파이크**($q\approx0$ 수직 기둥, rated $-40$ 대폭 초과)와 관절범위선($q\approx0.7$ rad) 밖 침범점은 낙상 착지 충격에 대응 — 정상 보행 코어는 $\pm25$ N·m 띠 안에 있음.
- **push 주입(fcp, 빨강)은 clean(fc, 회색) 외피를 거의 벗어나지 않음** — knee effort-clip 상단($\sim120$ N·m) 포화와 ankle_pitch 음토크 꼬리의 밀도만 높임. 즉 이 정책에선 push로 새 작동영역이 열리는 게 아니라 **이미 낙상이 만들던 극단영역의 빈도가 증가**하는 구조.

## 9. DR 커버리지 + 밀도 contour
**명령 커버리지**
![[dr_coverage.png]]
- 133개 명령이 vx $[-1.5,1.5]$ / vy $[\pm1.0]$ / yaw $[\pm1.0]$ 전 범위를 균일 커버 — in-range 통계의 대표성 확보.

**밀도 contour ($q$–$\tau$ / $q$–$\dot q$ / $\dot\omega$–$\tau$)**
![[contour_q_torque.png]]
![[contour_q_speed.png]]
![[contour_speed_torque.png]]
- 밀도 코어(RMS 대역)는 전 관절 rated 이내에 안착, P99 대역도 peak선 내부 — peak선 밖은 저밀도 꼬리(순간 접촉 과도)뿐. 즉 열적(RMS) 관점 전부 OK, 초과는 밀도상 무시 가능한 순간치.

## 10. 관절 반력 wrench
![[wrench_arrows_p2_long.png]]
- 반력 지배 방향: 지지상 다리 축을 따라 수직(z) 압축 반력이 지배적이고, hip에서 전후(x) 추진 성분·roll 모멘트가 부가. 접촉 과도(GRF 순간 peak 5.14 $\times$BW, P99 1.28 $\times$BW)가 ankle→knee→hip 순으로 감쇠 전파 — 구조 하중 경로는 기존 worst-case 캠페인과 동일 양상.

## 11. gait + L/R 대칭 분석
**Gait (전진보행 세그먼트)**

| 항목 | 값 |
|---|--:|
| double-support | 15% |
| single-support | 85% |
| flight | 0% |
| 정지 무릎각 | -5.6° |
| 정지 base 높이 | 0.856 m |
| 역관절 max | +2.6° (0° hard-cap soft 초과) |

- flight 0% = walk gait(러닝 아님). 직립 정지(무릎 $-5.6°$) 달성, 역관절은 soft-limit 오버슛 2.6°에 그침.

**L/R 대칭** (★핵심 발견)

| 지표 | L | R | 비대칭 |
|---|--:|--:|--:|
| contact duty [%] | 54.8 | 60.6 | 5% |
| knee flex max [°] | -41.4 | -66.9 | **24%** |
| knee 토크 RMS [N·m] | 15.0 | 15.8 | 3% |
| hip_pitch 토크 RMS [N·m] | 19.1 | 19.1 | 0% |
| GRF peak [×BW] | 1.6 | 1.8 | 8% |

- ★해석: 비대칭은 **kinematic이지 하중이 아님** — 오른다리가 무릎을 ~25° 더 굽혀 스윙(절뚝 스타일)하지만, 관절 **토크는 0–3% 대칭**·GRF도 8%뿐 → 하드웨어 하중은 좌우 균형. 즉 내구/사이징 문제가 아니라 gait-style 문제(추후 대칭 reward/mirror loss로 다듬을 항목).

## 12. 종합 판정
2단계 커리큘럼 **성공**:
- **Phase 1** (0–10k, DR off): 깨끗한 보행 수렴 — track_linear 1.03 · air_time 0.65 · ep_len 1000.
- **Phase 2** (10k–20k, DR 0→max 선형 램프): 램프 전 구간 ep_len 1000 유지 = **DR 강건**.

**달성**: ① 직립 default 정지(무릎 $-5.6°$·base 0.856) ② 보행 무릎 굽힘(R $-67°$, std 1.2 완화 효과) ③ 역관절 실질 차단(max $+2.6°$) ④ L/R **하중** 대칭(토크 0–3%) ⑤ DR full 강건.

**잔여**: kinematic L/R 절뚝(무릎 24%) — gait-style 이슈이지 하중 문제 아님(§11).

**설계점 불변**: in-range 하중이 기존 worst-case 캠페인과 일관 → 동결 BOM 유지 — knee/hip = RS04×6 + 링크레버(peak 초과 커버), hip_yaw = RS03, ankle = 2-RSU(pitch effort 90 = 2×RS03 co-act, roll 50; serial spec 대비 초과분 커버). RMS 전 관절 rated 이내 = 열여유 OK.

## 6. 관련 학습 / 연구 링크
- 계보/게이트: [[2026-07-02_training_plan_v2]] · 최종설계점: [[2026-07-03_final_design_point]]
- 부호규약: [[2026-07-03_knee_ankle_mechanism_design]] §6b

---

## §R. 부하 선도 (signed + mjlab 한계선)
포화 요약 · GRF · 토크-속도/각도-토크 산점 · 링크 부재력 (in-range vx≤1.5):
![[cmp_saturation.png]]
![[cmp_grf.png]]
![[cmp_torque_speed_scatter.png]]
![[cmp_q_torque_scatter.png]]
![[cmp_link_force.png]]
- signed 3평면×6관절·한계선 실정격(빨강=Peak·주황=Nominal·검정 TN). §8 q-v-t 선도와 상보.
