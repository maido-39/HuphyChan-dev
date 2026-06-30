# 2026-06-29 · ADVERSARIAL VERIFY — biomech-toe-pushoff (Hicks WINDLASS stiffness gain 10-20% / fascia strain 2-4% / CoP-progression = only lever)

> 트리거: 부모 workflow SOURCE `biomech-toe-pushoff`의 **windlass-stiffness 변종** 클레임을 우리 passive-toe rake-foot 로봇에 적대적 검증.
> 규칙 [[feedback-reward-research-rule]] · [[feedback-research-methodology]].
> ★ 자매노트 [[2026-06-29_verify_biomech_toe_pushoff_mtp_angle]] = 같은 SOURCE의 **각도-타깃/phase-gate 변종**(FALSE). 본 노트 = **windlass 기전 + CoP 처방 변종**.
> CLAIM: "Hicks windlass coupling이 MTP dorsiflex 시 arch stiffness를 **10-20%** 증가, plantar fascia strain rest 0.5% → push-off **2-4%**, 에너지 ~0.05-0.1 J 저장·반환. **IMPLICATION**: windlass stiffness gain은 marginal(주 push-off 기전 아님, ankle plantarflex 40-60% 지배); toe-stiffness를 레버로 설계하지 말라; **CoP를 forefoot로 굴리는 cop_progression/forefoot_cop reward가 유일한 레버**(GRF 610N × d 0.07-0.10m → 42-60 N·m → k60 spring 적재)."
> REFS(클레임): Hicks 1954 · Bojsen-Møller · Ker et al. JRSI 2009 · Pohl et al. Clin Biomech 2014.

## 판정: **supported = FALSE → use-with-care.** 클레임의 **IMPLICATION(처방)은 SOUND이고 우리가 이미 채택 중**이나, 그것을 정당화하는 **windlass-stiffness PREMISE(10-20% gain, 2-4% strain, energy-store-as-lever)는 outdated/overstated이고, 클레임이 인용한 그 출처가 정반대를 보고**. premise를 못 믿으니 supported=FALSE; 단 결론은 우연히 옳고(premise가 틀려서 *더* 옳다) + 우리 로봇엔 windlass가 *아예 없음* → 처방은 채택.

---

## 1. ★ 결정타 — windlass-stiffness PREMISE가 1차문헌과 충돌 (verified)

| 클레임 주장 | 문헌 검증 | 판정 |
|---|---|---|
| windlass가 arch stiffness **10-20% 증가** | ★ **정반대**. Welte et al. 2018 J R Soc Interface(클레임이 "Ker JRSI 2009"로 **오귀속**한 바로 그 JRSI 논문): dynamic 적재 시 **windlass 작동(MTP dorsiflex)이면 arch가 *더* 늘어남 = stiffness *감소***. "the medial longitudinal arch was more flexible when the windlass mechanism was engaged." | ✗ **반증** |
| fascia strain rest 0.5% → push-off **2-4%**, 에너지 ~0.05-0.1 J 저장·반환 | Welte: energy returned **dorsiflex 15.6 vs plantarflex 14.5 mJ/kg** (±5.4/4.9) = **오차범위 내, 차이 무의미**. 절대량은 ~70kg 기준 **반환 ~1.1 J / 흡수 ~1.6 J** (per body-mass normalize) → 클레임 "0.05-0.1 J"는 **단위/크기 오류**(per-body-mass를 per-foot로 혼동한 듯, 자릿수 어긋남). | ✗ **수치 오류** |
| windlass = passive 기전, "no active contraction required" | cadaver: passive windlass는 foot rigidity의 **~1/3만 생산**(Human Locomotion review). Farris: intrinsic 근육 마비 시 propulsion power 생성 불가. dynamic heel-rise 신전의 **~5/6는 windlass 외 active 근육**(PMC8848977, 자매노트). | ⚠ 사람은 **active 우세**, passive windlass minor |
| ankle plantarflex가 push-off **40-60%** 지배 | ✅ ankle push-off ≈ leg power의 **45%**, sagittal 관절일의 ~½; trailing-leg 에너지 증가의 **90%**가 ankle plantarflex 유래(PMC5201006). | ✅ **정확** |

★ 즉 클레임의 **PREMISE 3개 중 2개(stiffness +10-20%, strain/energy 크기)가 인용출처와 충돌**. windlass는 사람에서도 marginal(클레임이 self-aware하게 인정)이고, 최신 연구는 그조차 *stiffness를 낮춘다*고 본다. **klaim이 인용한 Ker/JRSI는 사실 Welte이며 반대 결론** = 출처 신뢰성 손상.

## 2. ★ 그런데 우리 로봇엔 windlass가 *아예 없다* (premise 무관)

robot: passive toe = **선형 토셔널 스프링**(k60 N·m/rad, d4, armature0.008 — robstride_biped.yaml, 자매노트 §2). **plantar fascia 없음, arch 없음, intrinsic 근육 없음.** → windlass coupling(기하 구속에 의한 arch 강성변조)이라는 기전 자체가 모델에 부재.
- ∴ "passive windlass로 toe가 EMERGE"라는 경로는 **우리 로봇에 존재하지 않는다**. toe는 오직 **외부 GRF 모멘트 M=Fz_toe·d_cop**로만 굽는다(θ=M/k).
- → windlass premise가 맞든 틀리든 **우리 설계엔 무관**. 유일하게 작동하는 레버 = **CoP를 forefoot로 굴려 d_cop·Fz를 키우는 것** = 클레임 IMPLICATION과 동일. **premise가 marginal/틀림이 오히려 처방을 강화**(toe-stiffness를 레버로 쓸 환상조차 없음).

## 3. ★ IMPLICATION(처방)의 물리수치 검증 — SOUND (자체계산)

클레임: GRF 610N(1.2BW, 51.8kg) × d_cop 0.07-0.10m → **42-61 N·m** → k60 스프링 **41-58°** 적재. CoP가 heel/mid면 d_cop·Fz↓ → **5-12 N·m → 거의 안 굽음**.

| CoP 위치 d_cop | M=Fz·d (Fz=610N) | θ=M/k (k60) | 평가 |
|---|---|---|---|
| heel/mid (d≈2cm) | 12 N·m | **11.6°** | 현 실패 동작점(swing 관성 curl과 구분 안 됨) |
| forefoot (d≈5cm) | 30 N·m | 29° | 목표대 |
| forefoot tip (d≈7cm) | 43 N·m | 41° | 클레임값 일치 (단 d>toe 6.5cm 불가, 자매노트 §2 천장 ~21° @ Fz340실측) |

★ **수치 자체는 맞다**(610N·0.07-0.10m=43-61 N·m verified). 단 자매노트의 **geometry 천장**(toe 6.5cm·실측 Fz340N → θ_max≈21°)이 우선: 클레임의 GRF 610N(1.2BW)·d 0.10m은 **이상적 상한**(실측 forefoot Fz는 340N, d≤toe길이 6.5cm). → **방향은 옳고 d_cop가 레버라는 인과는 정확**, 절대 각도는 클레임이 낙관적.

★ **ζ(overdamping) 검증**: 클레임 "ζ~2.9, 변형에 高하중 필요" = c/(2√(k·I)). I=armature 0.008 대입 → **ζ=2.89** ✅ (저관성 passive toe라 armature가 지배 inertia). over-damped → 진동 없이 하중에 단조 적재 = slap 억제 의도와 일치(docs/15). 단 over-damped라 **정적 held-curl이 싸다** = toe-각도 직접보상이 hack되는 이유(자매노트 §3).

## 4. ★ 처방은 우리가 이미 채택 — 클레임이 새로 요구하는 것 없음

클레임 IMPLICATION("cop_progression/forefoot_cop weight↑가 유일 레버") = **우리가 v6→v7서 독립적으로 도달한 결론**:
- `forefoot_cop`(정적 분율, weight 0.8) → v6 기여 **+0.0251 = reward의 0.06%**(무용). [[2026-06-22_12-19_gaitfix_v7_cop_progression]] §1 측정확증 = **정적 분율은 시간 시퀀스를 못 만든다** → 클레임의 "forefoot_cop weight↑"는 **이미 시도해 약함**.
- ✅ 교체채택 = `cop_progression`(weight +1.2): `τ_n·frac·gate`, late-stance(τ_n→1)에 forefoot fraction 높을 때만 = heel→toe **시간적 전진**. 정적 curl 구조적 배제.
- ✅ `periodic_contact`(Siekmann +1.5): contact 리듬 legislate(siekmann_v8서 절뚝 0.83→0.18).
- ⚠ 미해결: siekmann_v8 toe 최대굽힘 위상 L69%/R41% = 60% push-off 미정밀 → **클레임의 ankle-dominance(40-60%)가 가리키는** terminal-stance ankle-power가 forefoot rocker 엔진(PMC5201006) → CoP를 굴려 passive toe 적재. ([[2026-06-29_gait_emergence_siekmann]] Stage4. 단 ankle_pitch RS03 −60 포화 → 무한크랭크 금지.)

★ ∴ 클레임은 **새 레버를 주지 않음**(cop_progression 이미 채택). 기여하는 건 **windlass를 레버로 삼지 말라는 negative 가드**인데, 우리 모델엔 windlass가 없어 그 함정에 빠질 일도 없음.

## 5. 종합 판정
- **supported = FALSE**: PREMISE(windlass +10-20% stiffness, strain 2-4%/energy 0.05-0.1J)가 **인용출처(Welte/JRSI, 클레임이 Ker로 오귀속)와 충돌** + 단위·크기 오류 + 우리 모델엔 windlass 기전 부재. 클레임이 자기 논거의 토대를 잘못 인용.
- **건질 것(use-with-care)**: (a) **IMPLICATION(CoP-progression이 레버, toe-stiffness 아님, ankle 40-60% 지배)은 SOUND** — 단 **우리가 이미 채택**(cop_progression +1.2). (b) ζ=2.89·M=Fz·d 물리수치 검증 통과. (c) **windlass premise를 인용하지 말 것**(틀림); 처방은 premise 없이도 우리 geometry(toe 6.5cm·k60·실측 Fz340)에서 직접 정당화됨 → **자매노트 §2 geometry 천장(~21°)이 클레임의 41-58°보다 우선.**

## refs (verified, web+내부)
- [Welte et al. 2018 — windlass 작동 시 arch *더 유연*(stiffness 감소), energy 반환 dorsi 15.6 vs plantar 14.5 mJ/kg=오차내 (PMC6127178, JRSI)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6127178/) — ★ 클레임이 "Ker JRSI 2009"로 오귀속, 실제론 **반대 결론**.
- [Rethinking the windlass — passive windlass는 rigidity의 ~1/3만, Farris intrinsic 근육 지배 (Human Locomotion)](https://www.humanlocomotion.com/rethinking-the-role-of-the-plantar-fascias-windlass-mechanism/) — windlass marginal·active 우세.
- [ankle push-off ≈ leg power 45%, trailing-leg 에너지↑의 90%가 ankle plantarflex (PMC5201006)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5201006/) — 클레임의 ankle-dominance 정확.
- [windlass는 dynamic heel-rise MTP 신전의 ~1/6, 근육 active 우세 (PMC8848977)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8848977/).
- 내부: [[2026-06-29_verify_biomech_toe_pushoff_mtp_angle]](자매·geometry 천장 21°)·[[2026-06-22_12-19_gaitfix_v7_cop_progression]](cop_progression 채택·forefoot_cop 0.06% 무용)·[[2026-06-29_gait_emergence_siekmann]]·[[15_toe_joint_research]](k60·armature0.008). 자체계산: ζ=c/(2√kI)=2.89(I=armature0.008); θ=Fz·d/k.

> [!note] 솔직성
> verified(web): Welte/JRSI 반증(arch 더 유연, energy 오차내)·ankle 45%·windlass 1/6. 자체계산: ζ=2.89(armature0.008 inertia)·M=610N·0.07-0.10m=43-61N·m·θ=M/60. spec(robstride_biped.yaml k60·d4·armature0.008 = 학습 로드값; 별도 assets/.../biped_cfg.py의 k20은 stale MJCF 변환 아티팩트, 학습 미사용 — spec.py가 yaml에서 빌드). 내부 history(forefoot_cop +0.0251, cop_progression +1.2, siekmann_v8 toe phase)는 노트 직접인용. 추정: 클레임 "0.05-0.1J"이 per-foot인지 per-body인지 불명(Welte는 per-body mJ/kg)=자릿수 어긋남으로 판정. 클레임 d 0.10m는 toe 6.5cm 초과(이상적 상한).
