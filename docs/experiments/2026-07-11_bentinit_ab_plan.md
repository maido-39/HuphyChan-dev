# 2026-07-11 · Bent-knee init A/B (재실험) — 설계·가설·큐 (진행보상 계보)

> Request 2 (user). 이전 init-pose A/B([[55_init_pose_straight_vs_bent]]·[[init-pose-straight-vs-bent]])는 **구 config**(Kd6·PYG_NO_DR·exp추종, 진행보상 없음)에서 수행됐다. 현행 최적 recipe(진행보상 + 2.5 커리큘럼 + DR 램프)로 결론이 유지되는지 **동일조건 단일변수 재실험**. 이 노트는 계획·가설이며, 완주 시 정식 리포트가 결과를 채운다.

## 1. 단일변수 설계 (무엇이 다른가)
- **대조군 (straight)** = `flat25b_prog_p1` (2026-07-10_21-37-09, 현재 학습중). HOME 키프레임: 전관절 0°, base 0.87.
- **실험군 (bent)** = `flat25b_bentinit_p1` (큐). `KNEES_BENT` 키프레임: **knee −38°(−0.67), hip_pitch −18°(−0.32), ankle_pitch +21°(+0.36), base 0.83.**
- **오직 다른 것**: `PYG_INIT_BENT=1` 환경변수 하나 ([pygmalion_constants.py:237](../../mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/pygmalion_constants.py)). 나머지 전부 동일 — 진행보상(`track_lin_vel_progress` w=1.0), 2.5 커리큘럼(vx −2.0→+2.5), DR-off Phase1(`PYG_NO_DR=1`), 8192 envs, 20000 iter, seed, 보상표.
- **hip/ankle 동반이 "무릎만"에 위배 아님**: pose 보상이 `default_joint_pos`(=init 키프레임)를 타깃하므로, 무릎만 굽히고 hip/ankle을 0으로 두면 CoM이 발 앞으로 나가 **서 있는 자세가 불성립**(즉시 전도) → 몇 스텝 만에 정책이 무릎을 펴 타깃으로 복귀 = A/B 무효화. hip/ankle은 굽힌-무릎 standing을 **역학적으로 성립시키는 종속변수**이고, **설계 변수는 무릎 굴곡 유무**. docs/55와 동일 방법론(magnitude도 −38°로 일치 → 직접 비교 가능).

## 2. 가설 (구 A/B 결과가 진행보상에서도 유지되나?)
구 A/B 확정([[init-pose-straight-vs-bent]]): bent = **GRF −35%(충격흡수)** but **knee토크 +98%**·CoT −8%·속도추종↓; straight = 효율·추종 우세 but 착지 딱딱. "승자 없는 재분배"(가설 기각).
- **H1**: 진행보상이 straight의 추종약점을 이미 크게 개선했으므로, bent의 "추종↓" 페널티가 **줄어** bent가 상대적으로 유리해질 수 있다.
- **H2 (경쟁가설)**: knee토크 +98%는 **기하(모멘트팔)** 기인이라 보상과 무관 → bent knee토크 열세는 **유지**. 그렇다면 설계 관점 결론(straight 채택)은 불변.
- **판정축**: 링크별 wrench(P99/peak/RMS) · GRF(P99/peak·xBW) · knee/hip/ankle 토크 RMS·P99 · CoT · 방향별 cmd 추종률. **설계 결론은 [[65_design_value_uncertainty]] 안전율 규칙**(열=RMS×1.15, 순시=P99×1.25, raw peak 사이징 금지)으로 낼 것.
- **★이 A/B가 왜 지금 필요**: 방금 백필한 [[2026-07-10_flat25_p1]]에서 **straight-knee(+DR-off+고명령)** knee P99가 **96.1**로 bent였던 구 p2_long(42.4)·rough(55.1)의 ~2×로 관측됐다. 그러나 이는 DR·명령·보상이 전부 다른 **confound된 다중런 비교**라 init-pose 기여를 분리 못한다. 이전 init A/B([[init-pose-straight-vs-bent]])는 반대로 "bent knee토크 +98%"였다 — **두 관측이 상충**하는 건 조건이 달라서다. 본 A/B(동일 현대조건, 단일변수)만이 **"굽힌-무릎이 knee 부하를 늘리나 줄이나"의 통제된 답**을 준다. H2(기하 기인 knee 증가)면 bent가 knee 열세, H1(자세 유리)이면 완화 — flat25_p1의 straight 고부하는 후자를 시사하나 확정은 이 런.

## 3. 실행 (큐)
- **launcher**: `analysis/bentinit_babysitter.sh` (백그라운드). flat25b_prog_p1이 model_20000 또는 proc 종료(ckpt≥19000)에 도달하면 GPU 확보 후 자동 launch. crash(ckpt<19000)면 launch 중단(수동검사).
- **커맨드**(대조군 /proc 검증본에 `PYG_INIT_BENT=1`만 추가):
  `PYG_NO_DR=1 PYG_INIT_BENT=1 python3 analysis/train_wandb_video.py Mjlab-Velocity-Flat-Pygmalion --video True --video-interval 8000 --video-length 500 --env.scene.num-envs 8192 --agent.max-iterations 20000 --agent.run-name flat25b_bentinit_p1 --agent.logger wandb`
- **★실행됨 (2026-07-11 06:29)**: straight arm `flat25b_prog_p1` 완주(model_19999, progress 0.799)한 직후 bent arm launch. wandb run `e5n1xebb`(`2026-07-11_06-29-27_flat25b_bentinit_p1`), 8192 envs, ETA ~8h. straight 최종(model_19999)은 CPU로 `flat25b_final` 측정 병행. (babysitter가 `python3` 하드코딩 버그로 자동launch 실패 → `.venv/bin/python3`로 수동 재launch·스크립트 수정, [[reference-mjlab-venv-python]].)
- **중간검토 (iter 6000, ~148min)**: 건강 — Mean reward **111~112**(straight 정점 106보다 높음), track_linear 1.74, progress 0.51, **fell_over 0.000**. 굽힌무릎 초기자세가 불안정·낙상 유발 안 함(오히려 크라우치가 안정적). reward가 straight보다 소폭 높으나 pose 타깃(default_joint_pos)이 달라 직접비교는 부하·추종 완주측정으로. mid-training 규칙(건강런 보존)에 따라 계속.
- **중간검토 (iter 14000, ~218min)**: 건강 지속 — reward 105, progress 0.79(straight 완주 0.80과 동급), 낙상 0. 2.5 스테이지(16000) 진입 직전.
- **★완주 (iter 19999, 2026-07-11 15:51)**: Mean reward **102.3**, progress **0.896**(★straight 완주 0.80보다 높음 — bent가 진행보상 더 잘 챙김, 고속 추종 우위 시사), 낙상 0.000 전 구간. 측정: `bent_fc`/`bent_fcp`(0.25격자+push, 캠페인 뒤 자동 체인) → A/B 비교 리포트 예정. GPU는 straight P2(`flat25b_prog_p2`, DR+push 램프, iter 20039/31999, dr_factor 램프 확인)로 즉시 전환됨.
- **⚠ push 캐비앳 (2026-07-11 사용자 지적)**: 본 A/B 양팔 모두 Phase1(`PYG_NO_DR`)이라 **push 미학습** — A/B 내부 비교는 유효(조건 일치)하나 절대 부하값은 push-학습 정책(P2)이 설계 앵커. straight 계보는 완주 즉시 **flat25b_prog_p2**(DR+push 램프 20k→32k)가 자동 launch됨(p2_babysitter).
- **★변인통제 실증 (2026-07-11, config diff)**: 두 P1의 `env.yaml` diff = **init_state 단 하나**(base 0.87→0.83, 관절 0→hip −0.32/knee −0.67/ankle +0.36), `agent.yaml`(seed·PPO) = run_name 외 동일. 측정도 동일 프로토콜(fc/fcp) → **P1-vs-P1 1:1 성립**.
- **P2까지 1:1 연장 (사용자 지시)**: bent P2(`flat25b_bentinit_p2`)를 straight P2와 동일 레시피(resume P1 19999, +12000, DR 램프)로 자동 큐잉(`bentp2_babysitter.sh`, straight P2 완주 후 발화). ★핵심 함정: **`PYG_INIT_BENT=1`을 P2/험지 launch에도 반드시 재지정** — 토글은 checkpoint에 안 실리고 env 생성 시 읽힘; 누락 시 bent 가중치+straight init/pose 타깃 혼합 = 통제 파괴. 험지 단계도 동일 규칙으로 양팔 연장 시 전 계보 1:1 유지. (bent P1 측정 판정이 명백 열세면 발화 전 취소 가능: `pkill -f bentp2_babysitter`)
- **완주 후**: play 근접영상 + `wrench_design_stats.py`·`bearing_load_viz.py`(링크별 로즈)·`analyze_qtarget.py`(q/qtarget/error·토크 P/D분해) 측정 → straight와 나란히 비교하는 정식 리포트 + ghost 비교영상(straight vs bent) 작성. 이 노트를 대체.

## 4. 관련
[[55_init_pose_straight_vs_bent]] · [[init-pose-straight-vs-bent]] · [[62_policy_reward_design_review]] · [[65_design_value_uncertainty]] · [[feedback-qtarget-analysis-rule]] · 진행보상 계보 [[2026-07-10_flat25_p1]]

<!-- SPEC-TABLES:BEGIN (analysis/run_spec_tables.py) -->

**§1b-2 / §1b-3 / §1b-4 (설정 명세 표)** — 이 노트는 A/B 실행 계획(런 없음)이라 단일 런의 config가 없다. 리워드 가중치·모터 게인·토크 한계·ROM/액션 창·`PYG_*` 플래그는 **각 런 노트의 §1b~§1b-4**에 있다(모두 그 런의 `params/env.yaml`에서 기계 생성).

<!-- SPEC-TABLES:END -->
