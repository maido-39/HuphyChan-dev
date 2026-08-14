# rough Gen-2.1 P1 실패 진단 — "장님 액터 × 계단 40%" (2026-07-14)

## 증상
`2026-07-13_21-10-17_gen21_rough_p1`(actor-only warm-start from flat gen21_bent_p2, DR-off P1, 10k iter):
- **fell_over가 iter ~1000부터 10000까지 내내 0.25~0.4 진동, 0으로 수렴 안 함** (정체, 부족학습 아님)
- Mean reward iter 1000에 ~55로 붙고 정체 (flat P2 ~74 대비)
- P1 게이트: vx 1.5→17%·tile_dwell 31.6%·resets 41

## 진단 (2요인)
### ① 액터가 "장님"인데 지형 40%가 계단 — 구조적 불가능 (주원인)
- `height_scan`·`foot_height` obs가 **critic에만 존재, policy(actor) obs엔 없음** (env.yaml 확인). 액터는 지형 인지 없이 proprioception만으로 보행.
- `ROUGH_TERRAINS_CFG`([src/mjlab/terrains/config.py:282]) 구성: flat 0.2 + **pyramid_stairs 0.2 + pyramid_stairs_inv 0.2 (=계단 0.4)** + hf_slope 0.2 + random_rough 0.1 + wave 0.1.
- **장님 정책은 계단을 오를 수 없다** — 계단 엣지 위치를 못 보므로 발 배치가 도박. random_rough·wave·완만슬로프는 장님도 가능(발목 순응). 계단 40%가 fell을 ~0.3에 고정.
- ★warm-start 방식은 정상이었음(로그 `[warmstart] actor-only load` + `PYG_FRESH_STEPS=1` 확인) → warm-start 버그 **아님**. 문제는 지형 구성 vs 관측 능력의 불일치.

### ② 측정 oation (부차)
- tile_dwell 31.6% — 게이트가 로봇을 rough 타일 밖(플랫 갭/낙상)에서 68% 측정. p2r_fc(60%)와 동류. 겉보기 추종 실패를 가중(v2 텔레포트 프로토콜로 분리 필요).

## 결정: 우리 부하연구의 "rough" 재정의
- 목표는 **울퉁불퉁한 지면의 실측 부하**(발목/무릎/힙 wrench)이지 **계단 등반이 아님**. 계단 loads는 설계 타깃이 아니고, 계단을 배우려면 액터에 지형인지(height_scan을 policy obs로)를 넣어야 하는데 이는 obs차원·warm-start 파이프라인 전체를 바꾸는 큰 변경.
- ∴ **계단 제거, 장님 정책이 수렴 가능한 uneven-ground로 재구성**이 목표에 부합하고 clean warm-start 유지.

## 처방: `UNEVEN_TERRAINS_CFG` (PYG_UNEVEN 토글)
- flat 0.2 + hf_pyramid_slope 0.15 + inv 0.15 + random_rough 0.25 + wave_terrain 0.25 (**계단 0%**).
- 재학습: actor-only warm-start(flat gen21_bent_p2) + PYG_UNEVEN + DR-off P1 → 게이트(fell<0.1·tile>90% v2측정) 통과 시 P2(DR+push).
- 반증 가능 예측: 계단 제거만으로 fell이 0.3→<0.1로 떨어지면 ①이 주원인임이 확증. 여전히 높으면 slope/wave 난이도(slope 0~1.0 rad 과대) 하향 2차 실험.

## 계보/링크
[[2026-07-13_gen21_rough_p1]] 실패 → 이 진단 → uneven 재학습. 측정오염은 [[62_policy_reward_design_review]] rough 함정 참조. flat 앵커 [[2026-07-13_gen21_bent_p2]] 유지.
