# bundleCTL_RP — RP arm 대조군 (2026-08-26)

> *한 줄*: AB에서 확정한 착지 레시피를 RP(직렬 발목)로 옮길 때 **RP 자신의 대조군**. 변경 없음.

| | |
|---|---|
| 런 | `logs/rsl_rl/pygmalion_velocity/2026-08-26_15-44-45_bundleCTL_RP` |
| 계보 | `ankleRP_c3` `model_31999` → +800 iter → **`model_32798`** (16384 env) |
| 변인 | **없음**(c3와 동일 보상). `PYG_ANKLE_MODE=RP` |
| 짝 | [[2026-08-26_bundleD1_RP]] — 같은 체크포인트·같은 배치·같은 iter, 세 변경만 다름 |

## §1 재현성
```
PYG_V2=1 PYG_INIT_BENT=1 PYG_ARM_ABD_DEG=15 PYG_INERTIAL_DR=1 PYG_ANKLE_MODE=RP
PYG_DR_START_ITER=0 PYG_DR_END_ITER=1 PYG_TN=1 PYG_MOTOR_MEAS=1 PYG_SOFT_LANDING=1
--env.scene.num-envs 16384 --agent.max-iterations 800
```
모델 `pygmalion_v3_printed.xml`(35.347 kg, 직렬 발목 + 루프 자코비안 크랭크공간 클램프).
정본 env: `analysis/out/watchdog_runs.json`.

## §2 최종 지표 (평가기 32 ep × 3시나리오, 전진 1.6 m/s, DR off)
성공률 **96/96**. `eval_raw_stats.py` 중앙값(p10–p90):

| duty | stride/s | peak GRF | rate | 입각 무릎 | 전진 오차 |
|---|---|---|---|---|---|
| 0.532 | 2.667 | 1.214 BW | 15.93 BW/s | **45.9°** | 0.147 |

## §3 200 Hz 다중 env 충격 (24 env, DR off / DR on)
| | peak GRF | 하중률 | 스트라이크/s | 낙상 |
|---|---|---|---|---|
| DR off | 1.248 BW | **81.5 BW/s** | 2.27 | 0 |
| DR on | 1.253 BW | 79.9 BW/s | 2.28 | 0 |

⇒ 50 Hz 평가기(15.9)와 200 Hz(81.5)가 5배 차이나는 것은 [[2026-08-26_human_landing_bundle]] §11c의
에일리어싱 그대로다. **판정은 200 Hz 쪽을 쓴다.**

★기록해둘 관찰: AB 대조군(`bundleCTL_AB`)은 같은 조건에서 피크 **2.353 BW / 하중률 277 BW/s**에
DR 하 낙상 12회였는데, **RP 대조군은 1.248 BW / 81.5 BW/s / 낙상 0**이다. 초기자세가 같은데도
RP 쪽이 훨씬 부드럽게 딛는다 — 발목 기구가 다르면 같은 초기자세라도 착지 충격이 다르다는 뜻이고,
AB의 "굽힌 초기자세 = 하드랜딩"이 **AB 고유 현상**일 가능성을 남긴다. 단일 체크포인트 비교라 확정은 아니다.

## §4 판정
대조군으로 유효. 절대 성능도 정상(낙상 0, 성공률 100 %).

## §R 참조
[[2026-08-26_bundleD1_RP]] · [[2026-08-26_human_landing_bundle]] · [[103_v2_training_plan]] §4a
