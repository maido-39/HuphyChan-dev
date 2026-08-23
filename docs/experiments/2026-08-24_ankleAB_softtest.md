# ankleAB_softtest — soft-landing 시험 1 (선형 relu(−v_z), w −2, h 0.08) — **해킹으로 기각** (2026-08-24 02:00)

config-test (본 런 아님). `2026-08-24_02-00-19_ankleAB_softtest`: ankleAB_c2r model_3100에서 warm-start, 1024 env, +800 iter(3100→3899), `PYG_SOFT_LANDING=1`(초판: 선형, w −2, h 0.08) + contact_force_cap 420/560. 토글: `PYG_V2=1 PYG_INIT_BENT=1 PYG_ARM_ABD_DEG=15 PYG_ANKLE_MODE=AB`.

## 결과 (model_3899, impact_probe 0.4/0.8 m/s, hack_check)
| 지표 | 기준 3100 | 시험 1 |
|---|---|---|
| 접지속도 중앙/p90 [m/s] | 1.24 / 1.36 | **2.42 / 2.92** (악화) |
| GRF 피크 중앙 [BW] | 1.50 | 1.66 |
| F p99 200 Hz [BW] | 1.47 | 1.22 (캡 재스케일 효과) |
| vx 오차 @0.8 | 0.075 | 0.16 |
| swing / strides/s / apex @0.8 | 0.39 s / 2.4 / 0.116 m | 0.47 / 1.9 / 0.135 |

## 판정
선형 밴드 벌점 Σv·dt = 밴드 높이(속도 무관) → 정책이 밴드를 **더 빨리 통과**하는 해킹. 기각. 제곱형으로 재시험 → [[2026-08-24_ankleAB_softtest2]]. 전체 맥락 [[95_soft_landing_prescription]] §4. 교훈은 memory(feedback-velocity-penalty-speed-invariant)에 저장.
