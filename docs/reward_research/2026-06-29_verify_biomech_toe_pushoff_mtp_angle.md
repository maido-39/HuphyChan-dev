# 2026-06-29 · ADVERSARIAL VERIFY — biomech-toe-pushoff (MTP 35-45° dorsiflex @ 50-60% gait, phase-gated toe reward)

> 트리거: 부모 workflow가 SOURCE `biomech-toe-pushoff` 클레임을 우리 passive-toe rake-foot 로봇에 대해 적대적 검증 요청.
> 규칙 [[feedback-reward-research-rule]] · [[feedback-research-methodology]](dedicated adversarial verify stage).
> CLAIM: "1st MTP가 push-off서 35-45° dorsiflex, peak는 50-60% gait cycle(terminal stance). 우리 toe는 ~0.1 rad(~5.7°)뿐 = 사람 미달. terminal stance(40-60% phase) phase-gated reward로 35-45°를 타깃하라(gait_reference.py sin/cos phase로 트리거)."
> REFS(클레임): Hetherington 1990 · Perry&Burnfield Gait Analysis · PMC7278053.

## 판정: **supported = FALSE** (use-with-care). 타이밍 직관은 맞으나 클레임의 핵심 처방(35-45° 각도 타깃 + 직접 phase-gated toe reward)은 우리 로봇에 **물리적으로 불가능 + 입증된 안티패턴**.

---

## 1. 클레임의 사실관계 — 부분 정확 (verified vs 1차문헌)

| 클레임 주장 | 문헌 검증 | 판정 |
|---|---|---|
| peak MTP dorsiflex @ 50-60% gait (terminal stance/pre-swing) | pre-swing = 50-62% gait, windlass peak tensile strain @ pre-swing (ScienceDirect S0966636212002809; Hersco). | ✅ **타이밍 정확** |
| "35-45° active dorsiflexion 기능적 요구" | clinical assisted ROM 45-75°(physiopedia 60-75, 다른 출처 45-60). 그러나 ★ **dynamic 보행 측정은 훨씬 낮음**: OA군 mean **25.4°(SD6.7, range 13.8-39.5)** = passive ROM의 ~56%만 사용(PMC7278053, 클레임이 인용한 바로 그 출처). | ⚠ **과대** — 35-45°는 assisted-ROM값(걷는 중 실측 아님). dynamic은 ~25°. |
| "passive ROM 17-62°" | OA passive ROM mean 45.1°(SD10.7). 개인차 큼은 사실. | ✅ |
| windlass = passive | ★ **순수 passive 아님**: PMC8848977 — dynamic heel-rise MTP 신전의 **~5/6는 windlass 외 요인**(plantar intrinsic/extrinsic 근육 active). GRF는 *간접* 기여(관절 모멘트·근육 length). | ⚠ 사람은 **active 우세**; 우리 toe는 근육 없음 = 사람과 다른 기전. |

★ 즉 클레임의 **타이밍(50-60%)은 OK**, 그러나 **각도 타깃 35-45°는 보행 실측(~25°)이 아닌 임상 assisted-ROM**이고, **windlass는 사람에선 active 우세**(우리 passive toe로 재현 불가).

## 2. ★ 결정타 — 35-45°는 우리 로봇 toe에 물리적으로 도달 불가 (geometry, verified)

robot.xml: toe hinge y=-0.192m(foot_link 기준), toe segment **y -0.065..0 = 길이 6.5cm뿐**, range L -0.873/R -0.785 rad(=−50°/−45°, **단방향**). toe spring **k=60 N·m/rad**(yaml). 굴곡 θ = M/k, M = forefoot_Fz × d_cop, d_cop ≤ toe 길이(CoP는 toe tip 앞으로 못 감).

| 요구각 θ | 필요 M=k·θ | 측정 Fz=340N서 필요 d_cop | toe 길이 6.5cm로 가능? |
|---|---|---|---|
| 35° (0.61 rad) | **36.6 N·m** | **10.8 cm** | ✗ **불가**(toe 6.5cm) |
| 45° (0.785 rad) | 47 N·m | 13.8 cm | ✗ 불가 |
| **물리 상한**(d=6.5cm 전부 tip 적재, Fz340) | M_max≈22 N·m | 6.5cm | θ_max≈**21°** = 절대 천장 |
| Fz=560N(1.1BW)·d=6.5cm | M≈36 N·m | 6.5cm | θ≈**35°** (이상적 상한, 전 하중 tip) |

★ **결론: 측정 GRF(340N)·현 spring(k60)·toe 길이(6.5cm)에서 toe는 최대 ~21°만 굴곡 가능. 35-45°는 reward를 아무리 줘도 못 만든다**(천장이 물리적). 35°는 Fz를 1.1BW까지 올리고 *모든* forefoot 하중을 toe tip에 집중시킨 이상적 상한에서만. → **각도 타깃 자체가 우리 로봇에 무의미.**

## 3. ★ 직접 phase-gated "toe-deflection/torque" reward = 입증된 안티패턴 (우리 history)

클레임 IMPLICATION("toe joint를 35-45° dorsiflex하도록 reward, |τ_toe|/deflection을 phase 게이트")은 우리가 **이미 시도→폐기**한 경로:
- **toe_load_stance**(docs/22, `clamp(|τ_toe|/27,0,1)` terminal-stance gate) = bend 강도만↑(0.075→0.108), **타이밍 push-off 아님**(v5 실측). [[2026-06-29_human_gait_reference]] §v5.
- ★ **|τ_toe| = k·deflection** → toe-deflection/torque 보상은 **정적 toe-curl로 reward-hack** 가능(toe over-damped라 held curl이 쌈). [[2026-06-22_12-19_gaitfix_v7_cop_progression]] §3-1(b)서 후보(b) "toe FLEXION late-stance 게이트" **명시적 기각**.
- ★ phase **clock으로 toe-각도를 게이트**해도, deflection은 결국 forefoot 하중 위치(CoP)의 *correlate*. 클록이 "지금 굽혀라" 신호를 줘도 CoP가 forefoot에 없으면 toe는 **swing 관성/정적 curl로 각도만 위장** — 부모 컨텍스트의 "WRONG phase(mid-swing inertia)" 실패가 정확히 이것. 클록 게이트는 **타이밍 창만 좁힐 뿐 인과(CoP roll)를 만들지 못함.**

## 4. ★ mass-normalize 하면 우리 toe는 이미 충분 적재 (기준 오류)

[[2026-06-22_toe_moment_rollover_plantar_surface]] §1(verified): MTP moment 문헌정규화 **~0.13 N·m/kg**(4-seg foot model, PMC4101357) → 51.8kg서 **~6.7 N·m**. 우리 측정 toe moment **~15-19 N·m = 이미 사람 MTP의 2-3배 적재.** 클레임의 "우리 toe 미달"은 **angle(굴림 부재)은 맞지만 moment/load(적재)는 틀림** — moment는 초과인데 lever(6.5cm)가 짧아 각도가 안 나올 뿐. 35-45°를 토크로 강제하면 사람의 3-5배 toe 부하 = 비현실 + HW 과부하.

## 5. ★ 올바른 처방 = 각도/토크 직접 보상 아님 → 우리는 이미 채택 중

부모 컨텍스트 "toe가 right phase에 USED/EMERGE" = **CoP를 terminal stance에 forefoot로 굴리면(원인) passive windlass가 toe를 적재(결과)**. 직접 toe 보상이 아니라 **간접 CoP/push-off 보상**:
- ✅ `cop_progression`(현 weight +1.2, flat_env_cfg): `τ_n·frac·gate` = late-stance(τ_n→1)에 forefoot fraction 높을 때만 보상 = heel→toe **시간적 전진** 직접 인코딩. 정적 curl 구조적 배제. [[2026-06-22_12-19_gaitfix_v7_cop_progression]].
- ✅ `periodic_contact`(Siekmann, +1.5): contact 리듬 legislate. siekmann_v8서 절뚝 0.83→0.18·충격 8→3.1BW·hip corr +0.9·CoT↓. ([[experiments/2026-06-29_13-00-01_siekmann_v8_flat]]).
- ⚠ **단 siekmann_v8 측정: toe 최대굽힘 위상 L69%/R41% = 60% push-off 미정밀** → 클레임의 **타이밍 직관(60%로 모아라)은 유효한 미해결 과제**. 처방은 클레임의 toe-각도 게이트가 아니라 **Stage4 terminal-stance(40-60%) gated ankle-power burst**([[2026-06-29_gait_emergence_siekmann]] Stage4) — ankle plantarflex가 forefoot rocker 엔진(PMC5201006), 그게 CoP를 굴려 passive toe 적재. (단 ankle_pitch RS03 −60 포화 주시 → 무한 크랭크 금지.)

## 6. 종합 판정
- **supported = FALSE**: 클레임의 처방(35-45° 각도 타깃 + 직접 phase-gated toe-deflection/torque reward)은 (a) **물리 불가**(toe 6.5cm·k60·Fz340 → 천장 21°), (b) **기준 오류**(35-45°=assisted-ROM, 보행 dynamic은 ~25°; mass-norm 시 우리 moment는 이미 초과), (c) **입증된 reward-hack 안티패턴**(toe_load_stance 폐기·v7 후보(b) 기각).
- **건질 것(use-with-care)**: 타이밍 직관 **"toe-off peak ~50-60% gait, terminal-stance에 집중"은 맞고 우리 미해결 과제**(siekmann_v8 L69%/R41%). 단 처방은 **toe-각도 게이트가 아니라 CoP-progression(채택)+terminal-stance ankle-power burst(Stage4)** = 간접 원인 보상.

## refs (verified)
- [PMC7278053 — dynamic 1st MTP DF 보행 mean 25.4°(SD6.7), passive 45.1°, dynamic=passive 56%](https://pmc.ncbi.nlm.nih.gov/articles/PMC7278053/) — 클레임 인용출처가 35-45°(보행)를 지지하지 않음.
- [PMC8848977 — windlass는 dynamic heel-rise 신전의 ~1/6뿐, 근육 active 우세](https://pmc.ncbi.nlm.nih.gov/articles/PMC8848977/) — 사람 toe-off는 active; passive toe로 미재현.
- [windlass/pre-swing 50-62% (ScienceDirect S0966636212002809)](https://www.sciencedirect.com/science/article/abs/pii/S0966636212002809) — 타이밍 50-60% 지지.
- [Hetherington 1990 — necessary 1st MTP DF during gait (PubMed 2380493)](https://pubmed.ncbi.nlm.nih.gov/2380493/) — 클레임 인용(assisted ROM 계열).
- [MTP moment ~0.13 N·m/kg (PMC4101357)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4101357/) — mass-norm 기준.
- [ankle push-off = forefoot rocker 엔진 (PMC5201006)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5201006/).
- 내부: [[2026-06-22_toe_moment_rollover_plantar_surface]]·[[2026-06-22_12-19_gaitfix_v7_cop_progression]]·[[2026-06-29_human_gait_reference]]·[[2026-06-29_gait_emergence_siekmann]]·[[experiments/2026-06-29_13-00-01_siekmann_v8_flat]]. geometry: robot.xml(toe hinge y-0.192·길이6.5cm·range-0.873/-0.785) + robstride_biped.yaml(toe k60·d4·armature0.008).

> [!note] 솔직성
> verified: 문헌수치(dynamic 25.4°·windlass 1/6·pre-swing 50-62%·MTP 0.13N·m/kg)·로봇 geometry(robot.xml toe 6.5cm·hinge·range·k60). 자체계산: θ=M/k, M=Fz·d, 천장 21°(Fz340·d6.5cm). 내부 history(toe_load_stance 폐기·v7 (b) 기각·siekmann_v8 toe phase L69/R41)는 노트 직접인용. 추정: "35°는 Fz560·tip집중서만"은 이상적 상한 계산(실제 분포는 더 낮음).
