# bundleCTL_AB — 인간형 착지 번들 시험 (대조군, 2026-08-26)

## §1 목적·설정
c3 완주 정책(AB, `model_31999`)에서 **+800 iter · 1024 env** warm-start로 세 변경을 한 번에 시험한다.
근거: [[2026-08-26_human_landing_bundle]] · 원인 분석 [[104_init_pose_gait_style]] · 상위 계획 [[103_v2_training_plan]].

| | 대조군 `bundleCTL_AB` | 처치군 `bundleTRT_AB` |
|---|---|---|
| 초기자세 | bent (knee −38.4°, hip −18.3°) | **PYG_INIT_MID** (knee −20.05°, hip −10.03°) |
| base_height 앵커 | 없음 | **PYG_BASE_HEIGHT_ANCHOR** (h_ref 0.87, deadband ±0.03, w −5.0) |
| soft-landing | 접지속도 제곱 (현행) | **PYG_SOFT_LANDING_MODE=rate** (접지 후 60 ms dF_z/dt 최대 제곱, w −0.002) |
| 그 외 | 전부 동일 | 전부 동일 |

공통: PYG_V2 · PYG_INIT_BENT · PYG_ARM_ABD_DEG=15 · PYG_INERTIAL_DR · PYG_TN · PYG_MOTOR_MEAS · PYG_ANKLE_MODE=AB,
DR은 이미 만배인 체크포인트를 잇는 것이라 `PYG_DR_START_ITER=0 / END=1`로 즉시 full.
런처: `tools/robot_model/loop_tests/run_landing_bundle_test.sh AB` · 시작 2026-08-26 11:02.

## §2 학습 중 리뷰
| 시각 | iter | reward | ep_len | noise σ | fell | low_base | err_vel | 판정 |
|---|---|---|---|---|---|---|---|---|
| (게이트마다 추가) | | | | | | | | |

## §3 판정 지표 (§4 of 번들 노트)
| 지표 | 목표 | 기각 | 측정값 |
|---|---|---|---|
| 접지 무릎 | ≤ −15° | 변화 <5° | [측정 예정] |
| GRF 2차 봉우리 | 출현 | 없음 | [측정 예정] |
| 스윙 최대굴곡 | −55 ~ −65° 유지 | <−45° | [측정 예정] |
| 낙상 | 0 | >0.005 | [측정 예정] |
| 추종(전진 1.6) | 열화 <10 % | >20 % | [측정 예정] |
| ★air_time·stride | 유지 | 감소 = 하중률 해킹 | [측정 예정] |

## §4 결과
[완주 후 작성]
