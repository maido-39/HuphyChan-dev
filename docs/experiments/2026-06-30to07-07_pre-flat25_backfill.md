# pre-flat25 era 백필 — 2026-06-30~07-07 익명 학습 run 14건 (소급 기록)

> **목적**: audit(2026-07-15)에서 발견된 **per-run 노트 누락 14건**을 빠짐없이 기록. 모두 `--agent.run-name` 미지정(익명, 디렉토리명=타임스탬프만)이라 이름으로 추적 안 됐던 pre-flat25 era 런들. 전부 **현행 앵커 계통(flat25b→gen2→gen21)으로 대체(superseded)** 됐고, 설계 하중은 그 앵커들의 fc/fcp가 권위(이 구형 체크포인트 재측정 불필요·미실시). config는 각 `logs/rsl_rl/pygmalion_velocity/<ts>/params/{agent,env}.yaml`에 보존.

## 시대 맥락 (계보상 위치)
- **mjlab 이관 초기(06-30~07-01)**: MuJoCo-Warp 최초 velocity 런. IsaacLab→mjlab 재현.
- **gains/reward 튜닝(07-04)**: R1b(07-03)와 R2(07-05) 사이 flat 튜닝.
- **Kd·init-pose 통제 A/B(07-06)**: under/saturated/under-damped Kd 및 init-pose(straight vs bent) 통제실험 arm들 → 분석은 [[53_bc_kd_controlled_ab]] / [[55_init_pose_straight_vs_bent]]에 종합(결론: link-critical Kd 기각·under-damped Kd6 유지 / bent는 GRF−35% but knee토크+98% 재분배).
- **P2 최종화(07-07)**: flat P2-final 계열. 05-16-24가 [[rough-terrain-warmstart]] 등에서 참조된 **구 flat 앵커**(이후 flat25b→gen21로 승계).

## 런 목록 (검증된 사실 + 처분)
| run (ts) | 지형 | iter | 계보(load) | 성격/추정 | 처분 |
|---|---|---|---|---|---|
| 2026-06-30_20-12-31 | plane | 30k | fresh | mjlab 최초 velocity base | superseded → A-campaign |
| 2026-07-01_10-43-34 | plane | 60k | ←06-30 | 위 이어학습(60k) | superseded |
| 2026-07-04_11-07-07 | plane | 3.2k | fresh | 단명(설정검증성) | superseded/abort |
| 2026-07-04_12-13-48 | plane | 40k | fresh | flat gains/reward 튜닝 | superseded → R2 |
| 2026-07-06_00-33-28 | plane | 3.1k | fresh | 단명 arm | superseded |
| 2026-07-06_01-32-43 | plane | 20k | fresh | Kd/init A/B arm | [[53_bc_kd_controlled_ab]] |
| 2026-07-06_07-48-39 | rough(gen) | 8.9k | fresh | rough 시도 arm | superseded → R2 |
| 2026-07-06_11-11-33 | plane | 10k | fresh | Kd/init A/B arm | [[53_bc_kd_controlled_ab]]/[[55_init_pose_straight_vs_bent]] |
| 2026-07-06_18-27-33 | plane | 3.2k | fresh | 단명 arm | superseded |
| 2026-07-06_19-27-36 | plane | 10k | fresh | Kd/init A/B arm | [[55_init_pose_straight_vs_bent]] |
| 2026-07-06_22-40-19 | plane | 9.1k | fresh | Kd/init A/B arm | [[53_bc_kd_controlled_ab]] |
| ★2026-07-07_05-16-24 | plane | 20k | ←07-07_01-46-23 | **구 flat P2-final 앵커** | superseded by flat25b [[2026-07-11_flat25b_bentinit_p2]]; 부모 01-46-23=[[2026-07-07_P2_final_analysis]] |
| 2026-07-07_18-51-51 | plane | 10k | fresh | P2 튜닝 arm | superseded |
| 2026-07-07_23-18-16 | plane | 20k | ←07-07_18-51-51 | P2 튜닝 이어학습 | superseded |

## 처분 근거 (왜 재측정 안 함)
- 전부 **익명·중간·대체됨**. 설계 하중값 세트의 권위는 현행 앵커(flat=[[2026-07-13_gen21_bent_p2]] gen21p2_fc, rough=uneven2 진행중)이며, 이 구형 정책들의 fc 재측정은 새 정보 없이 7h+ CPU만 소모 → 비실시(docs/62 "베이스라인 우선·수렴만" 원칙).
- Kd·init-pose A/B의 **정량 결론은 이미 노트화**([[53_bc_kd_controlled_ab]], [[55_init_pose_straight_vs_bent]])되어 분석 누락 아님 — 누락은 "per-run 파일" 형식뿐이었고 본 노트가 소급 충족.
- ★특정 런의 **전체 §1–§12 측정 리포트가 필요하면 지목** 시 해당 체크포인트로 fc/fcp 측정해 개별 작성 가능(구 flat 앵커 05-16-24가 1순위 후보).

## 등록
INDEX.md·registry 참조 추가. audit_notes.sh는 본 노트가 14 타임스탬프를 모두 포함하므로 해제됨.

<!-- SPEC-TABLES:BEGIN (analysis/run_spec_tables.py) -->

**§1b-2 / §1b-3 / §1b-4 (설정 명세 표)** — 이 노트는 14개 런 일괄 소급 노트이라 단일 런의 config가 없다. 리워드 가중치·모터 게인·토크 한계·ROM/액션 창·`PYG_*` 플래그는 **각 런 노트의 §1b~§1b-4**에 있다(모두 그 런의 `params/env.yaml`에서 기계 생성).

<!-- SPEC-TABLES:END -->
