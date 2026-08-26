# bundleCTL_RP — RP arm 대조군 (2026-08-26)

> *한 줄*: AB에서 확정한 착지 레시피를 RP(직렬 발목)로 이식할 때 쓸 **자체 대조군**. 변경 없음, 배치·iter만 동일하게 맞췄다.

| | |
|---|---|
| 런 | `logs/rsl_rl/pygmalion_velocity/2026-08-26_15-44-45_bundleCTL_RP` |
| 계보 | `ankleRP_c3` `model_31999` → +800 iter → **`model_32798`** (16384 env, ✅완주) |
| 짝 | `bundleD1_RP`(처치군) — 동시 launch, 단일 변인 |
| 변인 | 없음(c3와 같은 보상). `PYG_ANKLE_MODE=RP` |

## §1 재현성
`PYG_V2=1 PYG_INIT_BENT=1 PYG_ARM_ABD_DEG=15 PYG_INERTIAL_DR=1 PYG_ANKLE_MODE=RP PYG_DR_START_ITER=0
PYG_DR_END_ITER=1 PYG_TN=1 PYG_MOTOR_MEAS=1 PYG_SOFT_LANDING=1`, 16384 env, flat, DR 즉시 full(만배 체크포인트 계승).
런처 `tools/robot_model/loop_tests/run_landing_bundle_rp.sh`. 모델 `pygmalion_v3_printed_loop`(v4 아님).

## §2 최종 지표 (학습 로그, iter 32798)
| | 값 |
|---|---|
| Mean reward | **86.44** |
| `error_vel_xy_mean` | 0.4748 |
| `error_vel_xy_steady` | 0.3519 |
| `fell_over` | **0.000** |
| `mean_episode_length` | 993.0 / 1000 |
| `foot_impact_velocity` 기여 | −0.0677 (전 가중치) |

## §3c 추종·판정 (내장 평가기 32 ep, 전진 1.6 m/s, DR·노이즈·push off)
성공률 **96/96**. `eval_raw_stats.py` 중앙값 ± p10–p90:

| 지표 | 중앙값 | p10 | p90 |
|---|---|---|---|
| duty | 0.532 | 0.528 | 0.537 |
| stride/s | 2.667 | 2.506 | 2.889 |
| 피크 GRF (BW) | 1.214 | 1.180 | 1.264 |
| 하중률 (BW/s) | 15.93 | 13.89 | 17.90 |
| 입각 무릎 | 45.87° | 45.30° | 46.88° |
| 전진 오차 | 0.147 | 0.129 | 0.173 |

## §5 충격 (200 Hz × 24 env, `impact_probe_multi.py`)
| 조건 | 피크 GRF | 하중률 | 스트라이크/s/env | 낙상 |
|---|---|---|---|---|
| DR off (평가기 조건) | 1.248 BW | 81.5 BW/s | 2.27 | 0 |

★계측 대역 주의: 50 Hz 평가기의 하중률 15.9와 200 Hz의 81.5는 **같은 양이 아니다**
(50 Hz는 폭 15–25 ms 스파이크를 에일리어싱한다, [[2026-08-26_human_landing_bundle]] §11c).

## §미측정 항목과 사유
`measure_full.py` fc/fcp(15 s dwell 전체 박스), §7 모터활용, §8 설계선도, §10 링크 wrench, §11 떨림 지표는
**돌리지 않았다**. 이 런의 목적은 D1_RP와의 1:1 비교 하나뿐이고, 두 arm 모두 같은 항목이 비어 있어 비교는 성립한다.
설계값으로 쓰려면 fc/fcp부터 다시 돌려야 한다.

## §12 판정
대조군으로서 정상. 낙상 0, 성공률 100 %, 추종 0.147. D1_RP와의 차이는 [[2026-08-26_bundleD1_RP]] §4 참조.

## §R 참조
[[2026-08-26_bundleD1_RP]] · [[103_v2_training_plan]] §4a · [[2026-08-26_human_landing_bundle]]
