# 33 · knee 액추에이터 landscape — 실제 휴머노이드 감속비·토크·설계철학 (검증, womafnnro)

> [!question] 검증한 질문
> 실제 동적 휴머노이드/biped의 **무릎** 액추에이터는 어떤 감속비·토크를 쓰나? 왜 그렇게 골랐나(저감속 철학)? 우리 RS04보다 작고·저감속·고토크밀도인 시장 후보가 있나?

> [!abstract] 한 줄
> 동적 레그 무릎은 **두 학파**로 갈린다 — (a) **저감속 QDD/proprioceptive**(MIT Cheetah 5.8~7.67:1, Berkeley 9:1, MIT Humanoid 12:1, Unitree H1/G1) = 내재적 컴플라이언스·고 backdrivability, (b) **고감속 + 직렬스프링 SEA**(Cassie 16:1, Digit) = 외재적 컴플라이언스. **반사관성 J_ref = J_r·N²**(Wensing 2017)이 저감속을 미는 핵심 물리. 우리 RS04 직결(총 9:1)은 **Berkeley와 동일·Cheetah 3 옆 = 동적 무릎의 정통 위치.** 시장엔 "저감속 + RS04(84.5 N·m/kg) 초과 토크밀도"를 동시에 만족하는 **off-the-shelf 단품이 사실상 없다**(Unitree M107 ~189만 우위지만 단품 미판매).

> 검증 원문층(재근거화): [[raw/knee-actuator-landscape]]. 관련 [[31_humanoid_hw_comparison]] · [[32_actuator_damping]] · [[21_motor_power_weight]] · [[30_knee_biomechanics]] · [[experiment_queue]].

---

## 1. 실제 휴머노이드 KNEE 감속비/토크 비교 (검증)

> "총 감속" = 모터축→관절 전체. 1차출처는 §5, 독립 교차검증 = Berkeley Humanoid Table 1(arXiv:2407.21781).

| 로봇 | knee 타입 | 총 감속 | peak 토크 | peak 속도 | 컴플라이언스 |
|---|---|---|---|---|---|
| [MIT Mini Cheetah](https://robotsguide.com/robots/minicheetah) (HT-03) | QDD 단단 유성 | **6:1** | 17 N·m | 40 rad/s | 내재적(저감속) |
| [MIT Cheetah 2](https://fab.cba.mit.edu/classes/865.18/motion/papers/mit-cheetah-actuator.pdf) | QDD 단단 유성 | **5.8:1** ¹ | — | — | 내재적 |
| [MIT Cheetah 3](https://dspace.mit.edu/server/api/core/bitstreams/b93369ab-d87a-4fcf-a1e0-3bd34be52761/content) | QDD 단단 유성 | **7.67:1** | 230 N·m | 21 rad/s | 내재적 |
| [MIT Humanoid](https://arxiv.org/pdf/2104.09025) (U12+벨트) | proprio + 벨트단 | **12:1** | 136 N·m | 22.5 rad/s | 내재적 |
| [Cassie](https://github.com/UMich-BipedLab/cassie_description) | 사이클로이드 + 리프스프링 | **16:1** | ~195 N·m ² | 8.5 rad/s | **외재적(SEA)** |
| [Agility Digit](https://arxiv.org/abs/2407.21781) | 사이클로이드+하모닉, SEA+케이블 | high | 230 N·m | n/a | 외재적 |
| [Unitree H1](https://www.unitree.com/h1) (M107) | 유성 PMSM | low | **360 N·m** | 미공개 ³ | 내재적 |
| [Unitree G1](https://docs.quadruped.de/projects/g1) (EDU) | 유성 PMSM | low | 120 N·m (Berkeley 139) | 미공개 ³ | 내재적 |
| [Berkeley Humanoid](https://arxiv.org/pdf/2407.21781) (8518) | QDD 단단 유성 | **9:1** | 62.6 N·m | 29 rad/s | 내재적 |
| [Fourier GR-1](https://www.fftai.com/products-gr1) (FSA) | 하모닉(비 7–120) | 하모닉 | ~230 max 관절 ⁴ | n/a | (고감속) |
| [Tesla Optimus](https://optimusk.blog/blog/tesla-optimus-hardware-specs) | **선형**(frameless+롤러스크류) ⁵ | 롤러스크류 리드 | 선형 ~8000 N급 | n/a | (load cell) |

¹ 5.8:1 = 상용 단단 유성에서 가능한 **최대 단단 비**(Cheetah 2). ² Cassie ~195 = 모터 effort 12.2 N·m × 16:1(URDF), Berkeley 독립값 195와 일치. ³ Unitree H1/G1/B2 knee **각속도 per-joint 미공개**(토크만). ⁴ GR-1 knee 토크 별도 미공개(hip 300, 전신 max ~230). ⁵ Optimus knee는 **회전관절 아님** → "감속비/관절 N·m" 직접 적용 불가; force/stroke 공식 미공개(teardown 출처).

> [!info] Berkeley Table 1 교차검증 (MaxKFE knee peak, H=하모닉 P=유성 C=사이클로이드 S=서보)
> TORO 130(H) · LOLA 390(H) · WALK-MAN 270–400(H) · Unitree H1 360(P) · Digit 230(C,H) · ARTEMIS 250(P) · Cassie 195(C,H) · MIT Humanoid 144(P) · Unitree G1 139(P) · HECTOR 51.9(P) · iCub 40(H) · BRUCE 10.5(P) · NAO 1.61(S).

## 2. 저감속 철학 — *왜* 동적 무릎은 N을 낮게 두나 (검증, Wensing 2017)

> 1차출처: **Wensing, Wang, Seok, Otten, Lang & Kim (2017), "Proprioceptive Actuator Design in the MIT Cheetah," IEEE T-Robotics 33(3):509–522** — 워크플로우가 전문 대조(검증 verified=yes).

설계규칙(verbatim): *"the optimal actuator … largest gap radius as allowed by space and the smallest gear ratio as required by torque specifications"* — **"less is more".**

**핵심 물리 — 반사관성 N² 법칙 (Eq.43):**
$$J_{ref} = J_r \cdot N^2$$
Cheetah 로터 3.03×10⁻⁴ kg·m² × 5.8² = **0.0102 kg·m²** (~34배). (Firgelli 교차: 100:1 = 로터를 관절에서 **10,000배** 무겁게 느끼게 함; 10:1 = 100배 → 같은 출력토크에 **100배** 반사관성.)

| 측면 | 저감속 (proprioceptive / QDD) | 고감속 (하모닉 / 고전) |
|---|---|---|
| 대표 감속 | Cheetah 5.8:1, Mini 6:1, QDD ~2–15:1 | 하모닉 100:1+, 고전 50–300:1, 휴머노이드 sweet spot 30–50:1 |
| 반사관성 J_ref=J_r·N² | 낮음 (Cheetah ~34배) | 매우 높음 (100:1 → ~10,000배) |
| backdrivability | 높음(투명) | 낮음/비backdrivable |
| 충격완화 IMF | 높음; Cheetah = 가상 SEA의 **90%** | 낮음; HUBO = **52%** |
| force control | 모터전류서 센서리스 고대역(85 ms / >450 N contact 제어) | 토크센서/직렬스프링 필요, 저대역 |
| 토크밀도/효율 | per-motor 낮음, Joule 발열 큼 | per-motor 높음, stall/holding 효율 우수 |
| 적합 | 동적·민첩·고속·충격 많은 보행 | 정적토크·저속·load-carrying·에너지예산 |
| 컴플라이언스 | **내재적(저 N)** | **외재적(고 N + 직렬스프링 = SEA, ANYmal)** |

- **충격**: "gear ratios too high … can break a leg upon contact" — footstrike 충격(sub-ms, 체중 2~3배)은 제어루프보다 빨라 **기구가 양보**해야.
- **IMF**(Impact Mitigation Factor) ξ=det(Ξ)∈[0,1], 스케일 무관 비교: 저감속 리지드 Cheetah가 가상 SEA의 90% 충격완화를 **스프링 없이** 달성.
- **트레이드 회피**: torque density ∝ r_g^0.8 → 큰 air-gap 반경으로 작은 N 가능("no tradeoff in its purest form"). 한계는 기하(직결 Cheetah = Φ76.2cm×5mm, 불가) → 5.8:1 = 실용 타협.
- **카운터뷰(같은 논문 인정)**: load-carrying·저속·효율 과제엔 고감속 유리("low gear ratios cost higher energy … via Joule heating"). 두 컴플라이언스 학파: (a) 내재적 저 N, (b) 외재적 고 N + 직렬스프링(SEA, ANYmal/ANYdrive).

## 3. 우리 RS04는 어디? — 직결(총 9:1)이 정통

우리는 RS04 **내부 9:1**을 이미 깔고 있다([[32_actuator_damping]]). 외부 벨트 비에 따라:

| 우리 옵션 | 총 감속 | 위치 |
|---|---|---|
| **직결 1:1** | **9:1** | **Berkeley(9:1)와 동일, Cheetah 3(7.67:1) 옆 — 동적 무릎 정중앙** |
| 벨트 1.8 | 16.2:1 | Cassie(16:1, 단 Cassie는 리프스프링으로 컴플라이언스 회복) 근처 |
| 벨트 2.5 (이전) | 22.5:1 | **Cassie보다도 높음** — 물리 스프링 없는 리지드엔 과함 |

> [!note] 핵심 정합성
> MIT Cheetah(5.8~7.67:1)·Berkeley(9:1)·MIT Humanoid(12:1) 모두 **총 감속을 낮게** 유지하는 proprioceptive/QDD 학파. 우리 측정 토크 demand(p95 58, peak ~200 N·m)는 동종 peak(195~360) 대비 낮아 **고감속으로 토크를 짜낼 동기가 약하다.** 반사관성 관점(J_ref∝N²): 외부 2.5 = 6.25배, 1.8 = 3.24배, 직결 = 1배의 추가 반사관성. 6.7kN 측정 충격 + <1.5kN HW 한계 상황에서 **외부 감속 축소는 HW 생존의 핵심 레버**(자세한 belt/Kd 산정은 [[32_actuator_damping]], 측정/실험 큐는 [[experiment_queue]]).

## 4. 액추에이터 시장 — RS04보다 작고·저감속·고토크밀도? (검증 partial)

> 기준 RS04: 120 N·m / 1.42 kg / 9:1 → **84.5 N·m/kg**. 목표 = "≤9:1 저감속에서 이 토크밀도 초과". TD=peak/mass. 전체 표 → [[raw/knee-actuator-landscape]] §3.

| 후보 | 질량 | peak | 감속 | TD | 비고 |
|---|---|---|---|---|---|
| **Unitree M107** | ~1.9(추정) | **360** | low ~6–10:1 | **~189** | 유일하게 저감속서 RS04 압도. 단 H1/G1 **내장형·단품 미판매**, 질량 도출 |
| MyActuator X12-150 | 1.30 | ~120(rated 50) | 12:1 단단 | ~92 peak | RS04급 토크를 더 작은 프레임·단단. 약간 높은 감속 |
| **RS04 (기준)** | 1.42 | 120 | 9:1 | 84.5 | — |
| RobStride RS06 | 0.621 | 36 | 9:1 | 58.0 | 더 작지만 토크밀도 낮음 |
| CubeMars AK10-9 | 0.96 | 48 | 9:1 | 50.0 | 더 작지만 토크 부족 |
| MyActuator X12-320 | 2.37 | 320 | 20:1 | 135 | TD↑이나 **고감속**(반사관성 손해, 목적 배반) |
| CubeMars/T-Motor AK80-64 | ~0.85 | 120 | 64:1 | ~141 | 순수 고감속 플레이 |

**판정**:
1. RS04는 9:1에서 이미 ~85 N·m/kg로 **상용 QDD 중 매우 공격적** — 동일/낮은 감속에서 이를 넘는 off-the-shelf 단품은 사실상 없음.
2. "더 작은 프레임 + 더 높은 토크밀도 + 저감속"의 진짜 승자는 **Unitree M107(~189)** 뿐이나 **구매 불가** → 설계 옵션이 아니라 "목표 벤치마크"로만 의미.
3. 시장에서 RS04를 토크밀도로 이기는 것(X12/X15·AK80-64)은 **전부 20~64:1 고감속으로 이긴 것** → backdrivability/대역 희생, 우리 저반사관성 목적과 정반대.
4. **실용 결론**: 현재 시장에서 "저감속 + 충분토크"의 최선 조합은 **RS04를 그대로 (직결/저비 벨트로) 쓰는 것.**

## 5. References (하이퍼링크)

- [Wensing et al. 2017 — Proprioceptive Actuator Design in the MIT Cheetah (IEEE T-RO 33(3))](https://fab.cba.mit.edu/classes/865.18/motion/papers/mit-cheetah-actuator.pdf) — 설계규칙·J_ref=J_r·N²·IMF·5.8:1·27 N·m/kg(전문 검증).
- [MIT Cheetah 3 (IROS 2018) — 7.67:1, 230 N·m, 21 rad/s](https://dspace.mit.edu/server/api/core/bitstreams/b93369ab-d87a-4fcf-a1e0-3bd34be52761/content)
- [MIT Humanoid (arXiv:2104.09025) — U12 knee 12:1, 136 N·m, 22.5 rad/s](https://arxiv.org/pdf/2104.09025)
- [Berkeley Humanoid (arXiv:2407.21781) — 9:1, 62.6 N·m, 29 rad/s + Table 1 교차검증](https://arxiv.org/pdf/2407.21781)
- [Mini Cheetah (robotsguide) — 6:1, 17 N·m, 40 rad/s](https://robotsguide.com/robots/minicheetah) · Katz, Di Carlo, Kim (2019) Mini Cheetah ICRA.
- [Cassie URDF (UMich-BipedLab) — 16:1, 8.5 rad/s](https://github.com/UMich-BipedLab/cassie_description)
- [Unitree H1 — M107, 360 N·m knee](https://www.unitree.com/h1) · [docs.quadruped.de H1](https://docs.quadruped.de/projects/h1) · [G1](https://docs.quadruped.de/projects/g1)
- [Fourier FSA (하모닉 비 7–120)](https://fftai.github.io/fsa/fsa) · [GR-1](https://www.fftai.com/products-gr1)
- [Tesla Optimus 하드웨어(선형 knee, 롤러스크류)](https://optimusk.blog/blog/tesla-optimus-hardware-specs)
- [RobStride QDD 모델비교/선정 가이드 — RS04 84.5 N·m/kg](https://openelab.io/blogs/learn/complete-guide-to-robstride-qdd-motors-model-comparison-and-selection)

> [!note] 솔직성 노트
> Unitree H1/G1/B2 knee **각속도** 및 Fourier GR-1 knee 토크는 **per-joint 미공개**(PARTIAL). Tesla Optimus knee는 **선형 액추에이터**라 "감속비/관절 N·m" 직접 비교 불가(force/stroke 공식 미공개). ANYdrive 정확 하모닉비는 2차출처 불일치(50:1 vs 100:1, 미확정). M107 질량은 360÷189로 **도출치**(공식 미공개). 정성 결론(저감속=정통, J_ref∝N²)은 Wensing 전문 검증으로 HIGH.
