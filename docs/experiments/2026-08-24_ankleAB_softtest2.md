# ankleAB_softtest2 — soft-landing 시험 2 (제곱 relu(−v_z)², w −1, h 0.10) — **채택** (2026-08-24 02:43)

config-test. `2026-08-24_02-43-36_ankleAB_softtest2`: ankleAB_c2r model_3100 warm-start, 1024 env, +800 iter, `PYG_SOFT_LANDING=1`(제곱형) + cap 420/560. 토글은 시험 1과 동일 + `PYG_SOFT_LANDING=1`.

## 결과 (model_3899)
| 지표 | 기준 3100 | 시험 2 |
|---|---|---|
| 접지속도 중앙 / p90 [m/s] | 1.24 / 1.36 | **0.98 / 1.33** |
| GRF 피크 중앙 / p90 [BW] | 1.50 / 1.64 | **1.31** / 1.67 |
| F p99 200 Hz [BW] | 1.47 | 1.21–1.25 |
| vx 오차 0.4 / 0.8 | 0.082 / 0.075 | 0.040 / 0.085 |
| swing / strides/s / stride @0.8 | 0.39 s / 2.4 / 0.60 m | 0.43 / 2.1 / 0.67 |
| 스윙 최고높이 @0.4 / 0.8 [m] | 0.091 / 0.116 | 0.036 / 0.080 (감시) |
| 정지 발 움직임 [m/s] | 0.007 | 0.011 |

## 판정
접지속도 −21 %·피크 −13 %, 추종·보폭·정지 유지, 해킹 징후 없음(스윙 높이 감소는 감시). → 두 본 arm에 적용: [[2026-08-24_ankleAB_c3]] / [[2026-08-24_ankleRP_c3]]. 문헌 대응: LimX TRON1 `foot_landing_vel`(Σv_z², h<0.08, w −0.15) — [[95_soft_landing_prescription]] §3.
