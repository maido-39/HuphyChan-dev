# gen21_rough_uneven2_p1 — rough 트랙 소생 (계단·급슬로프 제거로 fell 0.3→0.00)

> **한 줄**: rough P1 실패([[2026-07-13_gen21_rough_p1]], fell 0.3 정체)의 진단([[2026-07-14_rough_p1_blind_stairs_diagnosis]])을 2단 처방(계단 제거→슬로프 45°→17°)으로 검증. **fell iter 600서 ~0.00 수렴** = 진단 완전확증. DR-off P1(gait 형성) 완주, 다음은 v2 측정 + P2(DR+push).

## §1 가설·변인
- **단일변인**: 지형 구성 `UNEVEN_TERRAINS_CFG`(계단 0%·**슬로프 rise/run 0.3=~17°**·random_rough·wave) — vs 실패 P1의 `ROUGH_TERRAINS_CFG`(계단 40%·슬로프 45°). reward/gains/init/warm-start는 동일.
- 가설: "장님 액터(height_scan=critic-only)는 걸을 수 없는 지형(계단·급슬로프)에서만 실패한다. walkable uneven만 남기면 fell→0."

## §1b Reward & Gains
- 앵커 [[2026-07-13_gen21_bent_p2]]와 동일(Gen-2.1 번들: 상대임계 stand_still·knee_overspeed·bent init·hip_roll std 0.4). Kp/Kd·effort·speed limit 변경 없음. 지형만 변인.

## §2 설정
- run: `logs/rsl_rl/pygmalion_velocity/2026-07-14_18-21-12_gen21_rough_uneven2_p1` (최종 model_11999)
- launch: `PYG_UNEVEN=1 PYG_NO_DR=1 PYG_INIT_BENT=1 PYG_FRESH_STEPS=1` + actor-only warm-start(flat 앵커 gen21_bent_p2 model_31998, `analysis/train_actor_warmstart.py`), 4096 env, 12k iter, DR-off.
- 코드: `src/mjlab/terrains/config.py` UNEVEN_TERRAINS_CFG(slope_range 0.3), `velocity_env_cfg.py` PYG_UNEVEN 토글. end-to-end 검증(토글 on→계단없음·슬로프0.3, off→계단있음, stale-pyc 아님).

## §2b 변인격리 3단 (진단의 핵심)
| run | 계단 | 슬로프 | fell 종착 | 판정 |
|---|---|---|---|---|
| gen21_rough_p1 | 40% | 45° | **0.30 영구정체** | 장님×불가지형 |
| gen21_rough_uneven_p1 | 0% | 45° | 0.32 (감소하나 둔화) | 슬로프 잔여병목 |
| **gen21_rough_uneven2_p1** | 0% | **17°** | **~0.00 (iter 600)** | ✅ walkable |
→ 각 요인 기여 분해: 계단이 주범(제거로 명확 감소), 급슬로프가 잔여(하향으로 완치).

## §12 결과·판정
- **fell_over: iter 600서 ~0.002 수렴, 종료까지 0.000–0.012 유지** (최종 0.0000). 계단런 0.3정체·uneven1 0.32와 극명 대비.
- 추종: track_linear reward 1.10–1.17·track_angular 0.99–1.04, Mean reward ~57–58. (DR-off P1 기준 건강; 절대 추종%는 v2 측정에서 확정.)
- **판정: ✅ 진단 완전확증 + rough P1 성공.** rough 트랙 소생. 다음: v2 텔레포트 측정(tile 오염 없이) → P2(DR+push).

## §11 이상징후 — 주기적 reward 스파이크 (watch-item)
- **36/12000 iter(0.3%)** 에서 reward가 −26k~−36k로 순간 폭락(그 외 정상 57–70). ~3–4k iter 주기. **fell엔 영향 0**(0.000 유지), reward 즉시 회복 → PPO가 흡수.
- 추정: uneven 지형 엣지의 드문 대형 접촉 → **캡 없는 페널티 항**(토크/가속/action_rate류)이 특정 env서 폭주. DR-off라 희소하나 **P2(DR+push)에선 빈발 가능** → P2 npz에서 어느 항이 튀는지 진단 필요(캡 추가 후보).

## ★P2 DR-ramp 버그 & 수정 (2026-07-15)
- 첫 P2(`00-58-24_p2`)에서 **dr_factor가 iter 17571에도 0.0 고정** 발견 → P2가 robust 앵커 무효(DR 미주입).
- 근본원인: `dr_levels` 윈도우가 `start_step=20000×24=480000`(P1=20k iter 하드코딩). 본 P1은 **12k+PYG_FRESH_STEPS**라 common_step_counter가 288000에서 끝 → P2가 counter 576000까지만 가 **dr=0.33에서 정체**.
- 수정: `env_cfgs.py`에 **`PYG_DR_START_ITER`/`PYG_DR_END_ITER` env override** 추가(기본 20k/32k=flat 파이프라인 보존). P2 재학습(`03-48-03_p2b`)을 `12000/24000`로 정렬 → **dr가 P2b 시작(iter 12068)부터 램프**(0.0057→...→1.0@iter24000) 검증.
- 교훈: **P1 iter 길이를 바꾸면 dr 윈도우도 맞춰야** 함(counter는 resume 시 복원됨). ★rolloff30 등 12k-P1 파생 P2도 동일 override 필수.

## 후속 (파이프라인)
1. **v2 텔레포트 측정**(measure_full_v2, PYG_UNEVEN·INIT_BENT 재지정, block별 중심 텔레포트+tile_dwell 기록) → 깨끗한 rough 부하 + tile>90% 확인.
2. **P2**(DR+push 램프, resume from model_11999) → rough 설계앵커 후보.
3. 스파이크 항 진단 → 필요시 캡(Gen-2.2 후보).

## 계보/링크
[[2026-07-13_gen21_rough_p1]](FAIL) → [[2026-07-14_rough_p1_blind_stairs_diagnosis]] → [[2026-07-14_gen21_rough_uneven_p1]](부분) → **본 런**(성공) → P2. flat 앵커 [[2026-07-13_gen21_bent_p2]] warm-start 모체. 등록: [[66_experiment_registry]] Era-9, [[experiment_map.canvas]].
