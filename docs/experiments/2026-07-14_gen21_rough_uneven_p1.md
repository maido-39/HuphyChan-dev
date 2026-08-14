# gen21_rough_uneven_p1 (중간 진단 런, iter 1900서 종료·uneven2로 대체)

> **성격**: 정식 앵커 후보가 아니라 **rough 실패진단의 1차 처방 실험**. 계단 제거는 맞았으나 슬로프를 과대(45°)로 남겨 반쯤만 성공 → 슬로프 하향한 [[2026-07-14_gen21_rough_uneven2_p1]]로 대체. 계보/근거는 [[2026-07-14_rough_p1_blind_stairs_diagnosis]].

## §1 가설·변인
- **단일변인**: `ROUGH_TERRAINS_CFG`(계단 40%) → `UNEVEN_TERRAINS_CFG`(계단 0%, PYG_UNEVEN 토글). 나머지(reward/gains/init/warm-start)는 실패한 [[2026-07-13_gen21_rough_p1]]과 동일.
- 가설: rough P1 fell 0.3 정체의 주원인이 "장님 액터 × 계단 40%"라면, 계단 제거만으로 fell이 0.3→<0.1로 떨어져야 함.

## §2 설정
- run: `logs/rsl_rl/pygmalion_velocity/2026-07-14_17-18-44_gen21_rough_uneven_p1`
- actor-only warm-start(flat 앵커 gen21_bent_p2 model_31998) + `PYG_UNEVEN=1 PYG_NO_DR=1 PYG_INIT_BENT=1 PYG_FRESH_STEPS=1`, 4096 env, DR-off P1.
- ★UNEVEN cfg 초판: flat 0.2 + hf_slope 0.15+0.15 (**slope_range (0.0, 1.0)=최대 45°**) + random_rough 0.25 + wave 0.25.

## §12 결과·판정
- **fell 추세(200 iter avg)**: 0.60→0.52→0.50→0.41→0.39→0.37→0.38→0.35→0.32 (iter 0→1800). **감소는 명확**(계단 런은 iter 1000부터 0.3 정체였음 = 계단이 주범임을 부분확증) BUT ~0.33에서 둔화.
- **잔여 병목 = 슬로프 45°**: fell 종착 0.33 ≈ 슬로프 비율 0.30 일치 → 슬로프 지형이 거의 전부 실패. slope_range는 rise/run 기울기(1.0=45°)이며 장님 이족보행엔 불가.
- reward: iter 800–1200 −180~−260 급락(급슬로프 페널티 폭발) 후 iter 1600 +56 회복 — 불안정.
- **판정**: ⚠️ **부분 성공·중간 폐기**. 계단 제거 방향은 옳음이 입증됨. 처방 완성 위해 slope_range 0.3(~17°)로 낮춰 iter 1900서 종료 후 재launch([[2026-07-14_gen21_rough_uneven2_p1]], fell iter 600서 ~0.00 수렴 = 진단 완전확증).

## 교훈
- "걸을 수 없는 지형"은 계단만이 아니라 **급슬로프(45°)도 포함** — 장님(height=critic-only) 정책엔 둘 다 구조적 불가. rough=uneven ground의 "walkable" 경계를 지형별로 봐야 함(slope ≤~0.3, 계단 0).
- 변인 격리 검증 3단(계단40%→계단0%슬로프45%→계단0%슬로프17%)이 **각 요인의 기여를 분해**해 줌 = 한 번에 다 바꾸지 않은 것이 진단에 유효.
