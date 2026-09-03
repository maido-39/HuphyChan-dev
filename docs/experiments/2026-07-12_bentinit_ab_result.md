# 2026-07-12 · init-pose A/B 결과 (P1) — 굽힌무릎이 설계부하·push내성·고속추종 모두 우세

> [[2026-07-11_bentinit_ab_plan]]의 판정편. **flat-2.5max progress-reward no-domain-rand (2026-07-10, straight)** vs **동일+bent-knee-init (2026-07-11)** — env.yaml diff = init_state 단 하나(사전 실증), 측정 = 동일 fc/fcp 표준(0.25격자+2D복합면, 15s dwell, in-DR push, ★bent 측정에 `PYG_INIT_BENT=1` 재지정 — 토글 없인 관측/액션 default 시프트로 평가무효, [[pyg-no-dr-gating]]).

## 1. 정량 비교 — 부하 (clean `_fc`, L+R pooled)
![[ab_init_torque_speed.png]]

| 축 | straight | **bent** | Δ |
|---|---|---|---|
| **knee 토크 P99** | 113.9 | **90.8** | **−20%** ★ |
| hip_pitch P99 | 95.3 | 91.0 | −5% |
| hip_roll P99 | 55.5 | 53.7 | −3% |
| hip_yaw P99 | 35.0 | 39.6 | +13% |
| **ankle_pitch P99** | 23.2 | **66.4** | **+186%** (아래 §5) |
| **GRF P99** | 1.52 BW | **1.37 BW** | **−10%** |
| **GRF peak** | 7.52 BW | **4.73 BW** | **−37%** ★충격흡수 재현 |
| 낙상(리셋) | 13 | 15 | ≈동일 |

**joint-frame wrench (베어링·링크 설계축)** — bent가 사실상 전축 우세:
![[ab_init_wrench.png]]

| P99 | straight → bent | Δ |
|---|---|---|
| knee F_r / M_t | 639→582 / 107.7→86.1 | −9% / **−20%** |
| ankle_pitch F_r / M_t | 748→643 / 132.9→93.4 | −14% / **−30%** |
| ankle_roll M_t | 217.3→135.1 | **−38%** ★ |
| hip_roll F_r | 462→353 | −24% |
| hip_yaw F_r (유일 역행) | 302→376 | +25% |

## 2. push 내성 (`_fcp`, in-DR push 4초마다)
| | straight | **bent** |
|---|---|---|
| 낙상 fc→fcp | 13→**31** (2.4×) | 15→**19** (1.3×) ★**push에 더 강건** |
| push 시 클립도달 관절 | hip_pitch 120 (+26%), ankle_pitch +190% | knee 120 (+32%) |
| 재분배 방향 | push 회복을 hip/ankle로 흡수 | push 회복을 knee로 흡수 |

→ 두 정책 모두 push 시 한 관절이 클립에 닿음(진수요 미지, [[65_design_value_uncertainty]] §4) — **P2(push-학습) 비교가 이 항목의 확정판**.

## 3. 추종 (15s dwell 정상상태, 대표 순수축)
| cmd | straight | **bent** |
|---|---|---|
| vx +2.5 | 2.16 (86%) | **2.33 (93%)** ★ |
| vx +2.0 | 2.04 (102%) | 1.98 (99%) |
| vx −2.0 | −1.52 (76%) | −1.29 (64%) |
| 낙상성 이상블록 | 소수 | (2.5,0,±1.0)·(2.25,0,0)서 낙상/텔레포트 아티팩트 |

bent의 학습지표 progress 0.896(>straight 0.80)이 실측 고속추종 우위(93% vs 86%)로 확인. 후진은 straight 우위 — 사이징 비영향 gait 품질 항목.

## 4. ★구 A/B(2026-07-08, [[55_init_pose_straight_vs_bent]]) 결론 반전
구: bent knee토크 **+98%** / GRF −35% → "승자없는 재분배". 신: bent knee **−20%** / GRF peak −37% → **bent 우세**. 반전 원인: 구 A/B는 1.5박스·exp보상 **저속 레짐**(knee 수요 자체가 작아 크라우치 모멘트팔 페널티가 지배). 신 조건은 2.5박스·진행보상 **고속 레짐** — straight가 고속 추진에서 knee/hip을 극한(113.9=클립 95%)까지 모는 반면, bent는 부하를 ankle로 분산+낮은 CoM으로 착지충격 흡수. **"어느 init이 유리한가"는 속도 레짐 의존**이며 우리 설계점(2.5 m/s)에서는 bent.

## 5. bent의 비용 (설계 반영)
- **ankle_pitch 사용 급증**: P99 23→66(클립 90 내부), RMS 9.3→**22.4** = 단일 RS03(20) 기준 112% 초과, **2-RSU 공동구동(40) 기준 56%** → 공동구동 전제 유지 필수(straight도 push 시 67로 튀므로 어차피 필수였음).
- hip_yaw P99 +13%(39.6, RS03 60의 66%)·$F_r$ +25% — 캔틸레버 hip_yaw 커넥션([[56_humanoid_impact_fall_load_handling]]) 검토에 반영.
- 후진 추종 −12%p.

## 6. 좌우 동시 영상 (동일 명령 프레임잠금)
좌 = straight, 우 = bent. 대표 8블록(전진 2.5/1.0·후진 −2.0·측방 ±1.0·선회 +1.0·복합 2코너) × 15초, 실시간 25fps, 부하색 구체 + GRF 벡터(0.4m=1BW).
![[ab_init_sidebyside.mp4]]

## 7. 판정 (P1) + Gen-2 반영
- **bent-knee init 승** — 근거: 설계 지배축(knee P99 −20%·GRF peak −37%·전관절 $M_t$↓)·push 강건성(낙상 1.3× vs 2.4×)·고속추종(93% vs 86%) 모두 우세; 비용(ankle 2-RSU 듀티·hip_yaw +13%)은 정격 내.
- **Gen-2 init = bent 잠정 확정**, 단 P2-vs-P2(push-학습 상태의 동일 비교, `ab_p2` 산출물)로 최종 검증 — push 시 클립도달 관절이 다른 만큼(straight=hip, bent=knee) push-학습이 재분배를 바꿀 수 있음.
- 데이터: `bent_fc/fcp.npz`(90750 steps×2) · 도구 `ab_compare.py`/`ab_sidebyside.py` · 추종 전표 `analysis/out/bent_fc_tracking.txt`(측정시 자동 생성분은 chain 로그).

---
# P2-vs-P2 (2026-07-12, 양팔 push-학습 완료 후 동일 재비교) — 최종 확정

![[ab_p2_torque_speed.png]]
![[ab_p2_wrench.png]]
![[ab_p2_sidebyside.mp4]]

## 8. P2 정량 (fc, straight P2 vs bent P2)
| 축 | straight P2 | **bent P2** | 판정 |
|---|---|---|---|
| **낙상 (push 453회, fcp)** | 3 | **0** ★ | bent |
| 추종 일관성 (2.5 전조합) | **널뛰기**: (2.5,0,+1)→33%·(2.5,0,0)→69%·(2.5,±0.5,0)→63~70% | **균일 79~97%** (순수 93%) | bent ★ |
| 후진 −2.0 계열 | 56~89% | **89~96%** | bent |
| knee P99 | **91.9** | 109.3 (+19%) | straight† |
| hip_pitch/roll/yaw P99 | 98.6/57.2/34.4 | **95.0/54.7/31.7** | bent |
| ankle_pitch P99 | 62.0 | **60.5** (양팔 수렴 — P1 straight의 23은 취약 억제였음) | ≈ |
| ankle_roll M_t P99 | **160.0** | 192.7 (+20%) | straight |
| GRF P99 | 1.35 BW | **1.30 BW** | bent |
| push delta (P99) | +2~13% | **−1~+6%** | 양팔 수렴 = 2단계 독트린 검증 |

†**knee +19%의 confound**: straight P2의 낮은 knee는 **stall 블록(33~70% 달성)에서 명령을 못 낸 몫**이 섞임 — bent는 실제로 달성(93% 균일)하며 그 일을 한 부하. 동일-달성 조건 보정 시 격차는 축소. knee 109.3은 클립(120)의 91%로 얇으나 **계획된 knee 링크레버(1.5:1)가 커버**.

## 9. ★최종 판정: **Gen-2 init = bent-knee 확정**
- P1·P2 양 단계에서 bent가 **추종 일관성·push 강건성(낙상 0)·과반 관절 부하·GRF** 우세. straight의 유일 우위(knee·ankle_roll $M_t$)는 achieved-confound 포함 + 레버/정격 내.
- ★부수 확인: **straight 계보의 중저속 stall이 P2(DR+push)에서도 잔존** — stall은 DR로 안 고쳐지는 보상 문제임을 확증([[2026-07-11_midspeed_stall_overshoot]] Gen-2 수정 필요성 강화). bent는 stall 패턴이 크게 완화(레짐 차이 or init 효과 — Gen-2에서 함께 해소).
- 데이터: `p2push_fc/fcp` · `bentp2_fc/fcp` (각 90750 steps). push-학습 flat 설계앵커 = **bent P2 (bentp2_fc)**: knee 109.3·hip_pitch 95.0·GRF 1.30BW — [[65_design_value_uncertainty]] §2 갱신 대상.

관련: [[2026-07-11_bentinit_ab_plan]] · [[2026-07-10_flat25b_prog_p1]] · [[55_init_pose_straight_vs_bent]] · [[65_design_value_uncertainty]] · [[66_experiment_registry]]

<!-- SPEC-TABLES:BEGIN (analysis/run_spec_tables.py) -->

**§1b-2 / §1b-3 / §1b-4 (설정 명세 표)** — 이 노트는 bentinit A/B 2런 비교이라 단일 런의 config가 없다. 리워드 가중치·모터 게인·토크 한계·ROM/액션 창·`PYG_*` 플래그는 **각 런 노트의 §1b~§1b-4**에 있다(모두 그 런의 `params/env.yaml`에서 기계 생성).

<!-- SPEC-TABLES:END -->
