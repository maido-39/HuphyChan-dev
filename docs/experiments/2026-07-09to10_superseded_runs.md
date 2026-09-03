# 폐기·중간 런 기록 (2026-07-09~10) — supersession 노트

> 2026-07-11 소급작성. 정식 리포트가 낭비인 dead-end/중간/폐기 런을 한 곳에 기록해 학습 이력을 완결(메모리 규칙: 과도기 과도기록 금지). 각 런의 "왜 폐기됐나 + 무엇으로 대체됐나 + 측정 데이터 위치". 권위 런은 별도 정식 리포트: rough 최종 [[2026-07-09_rough_p2_final]], flat 2.5 [[2026-07-10_flat25_p1]], flat 진행보상 현행(학습중).

## 1. rough_warmstart_p2final (2026-07-09_11-45-26) — ★churn 실패
- **의도**: flat P2-final → rough를 actor-only warm-start(1차 시도), DR full·명령 ±1.5 즉시.
- **폐기 사유**: `MjlabOnPolicyRunner.load()`가 `common_step_counter`를 무조건 복원 → DR·명령커리큘럼이 iter0부터 최대 → **축 churn**(자식이 부모 flat 도메인에서 vx 81%→26%, yaw 상실). iter 9.6k서 중단. 진단·근거: [[61_velocity_tracking_review]] §5, [[rough-terrain-warmstart]].
- **대체**: 2단계 커리큘럼(P1 DR-off+FRESH_STEPS→P2 램프)으로 재설계 = rough_p1_nodr→rough_p2_dr.
- **데이터**: `analysis/out/rough_ws_6000.npz`(+_b, 지형 2회). 방향별 추종표는 [[61_velocity_tracking_review]].

## 2. rough_p1_nodr (2026-07-09_16-21-00) — 중간(Phase1), 정상
- **역할**: rough 2단계의 Phase1 — PYG_NO_DR=1 + PYG_FRESH_STEPS=1, flat P2-final(model_19998) actor warm-start, 10000 iter DR-off. 명령커리큘럼 ±0.8→±1.5 fresh 램프.
- **결과**: track_linear 0.33(실패런)→**0.98** 즉치 회복(iter 2200) = 재설계 성공 입증. 낙상 극소, 지형레벨 정상 진행. 계보상 중간단계라 정식 리포트 대신 여기 기록.
- **대체**: 완주 model_9999 → Phase2(rough_p2_dr) resume.
- **데이터**: `analysis/out/p1_3000.npz`·`p1_6000_a/b.npz`(방향별 추종, [[61_velocity_tracking_review]]).

## 3. flat25_p2 (2026-07-10_12-31-40) — 영상 추가 위해 kill
- **의도**: flat25 2.5독트린 Phase2(DR 램프), P1(model_19900) resume.
- **폐기 사유**: `--video` 없이 실행돼 wandb 영상 모니터링 부재 → 영상 래퍼(train_wandb_video.py) 붙여 재개하려 **의도적 중단**(iter 26800). 학습 실패 아님.
- **대체**: flat25_p2_vid로 재개(model_26800서).

## 4. flat25_p2_vid (2026-07-10_16-52-10) — 완주했으나 구 보상 폐기
- **의도**: flat25 2.5독트린 Phase2 완결 + wandb 영상. 32000 완주.
- **폐기 사유**: 완주는 했으나 **보상이 exp-추종 std0.71 단독** → 고속 명령서 **얼어붙음**(cmd 2.0→0.10 m/s, 2.5→0.03, HW는 30~50%만 사용). 근본원인=gradient 소실. 진단: [[2026-07-11_lateral_hiproll_pose_suppression]] 인접·[[65_design_value_uncertainty]] 계열, 상세 [[reward_research/2026-07-10_highspeed_freeze_progress_reward]].
- **대체**: 선형 진행보상(A) 추가 → **flat25b_prog_p1**(현행). 진행보상 검증: cmd 2.0 얼어붙음 0.10→**1.62(81%)** 해소.
- **데이터**: `analysis/out/prog_hispeed_13400.npz`(신 정책 고속측정). wandb run swkg08cg에 10초 실시간 영상 다수.

## 5. 2026-07-08_03-29-40 = straight 베이스라인 (init-pose A/B) — 기록 완료
- init-pose A/B의 **straight(Bbase_kd6)** 학습 런(PYG_NO_DR·Kd6, HOME 자세). 짝인 bent(07-08_13-33)와 함께 [[55_init_pose_straight_vs_bent]]·[[init-pose-straight-vs-bent]]에 이미 정식 분석됨(GRF −35% vs knee토크 +98% 재분배). 별도 리포트 불필요.
- **데이터**: `analysis/out/Bbase_kd6.npz`·`bent_kd6.npz`, 비교영상 `ghost_straight_vs_bent.mp4`.

## 6. gen2_rough_p1 (2026-07-13_02-45-30) — 투기 launch 후 의도적 kill
- **의도**: gen2 P2 완주 직후 GPU 유휴 방지용 험지 Gen-2 P1 투기 warm-start.
- **kill 사유(iter ~3.4k)**: gen2 P2 최종 게이트에서 stand_still_penalty **creep-게이밍 확정**(고속 57%/56%) → 결함 보상을 상속한 험지 학습은 낭비. Gen-2.1(상대임계) 완성 후 험지 재개. 학습 실패 아님.

<!-- SPEC-TABLES:BEGIN (analysis/run_spec_tables.py) -->

**§1b-2 / §1b-3 / §1b-4 (설정 명세 표)** — 이 노트는 폐기된 6개 런 정리이라 단일 런의 config가 없다. 리워드 가중치·모터 게인·토크 한계·ROM/액션 창·`PYG_*` 플래그는 **각 런 노트의 §1b~§1b-4**에 있다(모두 그 런의 `params/env.yaml`에서 기계 생성).

<!-- SPEC-TABLES:END -->
