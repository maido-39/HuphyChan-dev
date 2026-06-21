# knee 액추에이터 landscape — 실제 휴머노이드 무릎 감속비/토크 (원문 검증)

> 출처: workflow womafnnro (3-subagent web research) · fetched 2026-06-21 · verified yes/partial(필드별)
> 규칙([[raw/README]]): 여기엔 검증 발췌/수치 + 출처 URL만. 수정 금지.

---

## 1. 실제 dynamic biped/humanoid KNEE 액추에이터 스펙 (검증)

> 출처: Berkeley Humanoid (arXiv:2407.21781) Table 1 = 독립 교차검증층. 로봇별 1차출처는 §4.
> 표기: "총 감속" = 모터축→관절 전체 감속비. verified=YES/PARTIAL은 워크플로우 판정.

| 로봇 | knee 액추에이터 타입 | 총 감속 | peak knee 토크 | peak knee 속도 | verified |
|---|---|---|---|---|---|
| MIT Mini Cheetah (HT-03 모듈) | QDD 단단 유성, BLDC 팬케이크 | **6:1** | **17 N·m** (연속 6.9) | **40 rad/s** @24V | YES |
| MIT Cheetah 2 (원조 액추에이터) | QDD 단단 유성 | **5.8:1** (상용 단단 유성 최대비) | n/a | n/a | YES(비율) |
| MIT Cheetah 3 | QDD 단단 유성 | **7.67:1** | **230 N·m** | **21 rad/s** | YES |
| MIT Humanoid (U12 + 벨트) | proprioceptive, 유성 + 벨트단 | **12.0:1** | **136 N·m** | **22.5 rad/s** | YES |
| Cassie | 사이클로이드 + 직렬 리프스프링(SEA) | **16:1** (URDF mechanicalReduction) | **~195 N·m** (모터 12.2 N·m × 16) | **8.5 rad/s** (URDF 관절한계) | YES |
| Agility Digit | 사이클로이드 + 하모닉, SEA + 케이블/리프 | high | **230 N·m** (Berkeley 표) | n/a | PARTIAL |
| Unitree H1 (M107 모터) | 유성 PMSM (QDD형) | low | **360 N·m** | 미공개 | YES(토크)/PARTIAL(속도) |
| Unitree G1 (EDU) | 유성 PMSM (QDD형) | low | **120 N·m** EDU / 90 base (Berkeley 139) | 미공개 | YES(토크)/PARTIAL(속도) |
| Unitree B2 (M107급) | 유성 PMSM | low | **360 N·m** peak 관절 | n/a | PARTIAL |
| Berkeley Humanoid (8518 모듈) | QDD 단단 유성 | **9:1** (4모듈 공통) | **62.6 N·m** | **29 rad/s** @48V | YES |
| Fourier GR-1 (FSA) | 하모닉 드라이브 (비 7~120) | 하모닉 | ~230 N·m max 관절 (knee 미분리, hip 300) | n/a | PARTIAL |
| Tesla Optimus | **선형** 액추에이터 (frameless 모터 + 유성 롤러스크류) — 회전 아님 | 롤러스크류 리드(감속비 아님) | 선형 ~8000 N급; 회전라인 20/110/180 N·m | n/a | PARTIAL |

### Berkeley Humanoid Table 1 — MaxKFE(knee flex/ext) peak 토크 (독립 교차검증, 모두 해당 논문서 검증)
전동타입 H=하모닉, P=유성, C=사이클로이드, S=서보:
- TORO 130(H) · LOLA 390(H) · WALK-MAN 270–400(H) · Unitree H1 360(P) · Digit 230(C,H)
- ARTEMIS 250(P) · Cassie 195(C,H) · MIT Humanoid 144(P) · Unitree G1 139(P)
- HECTOR 51.9(P) · iCub 40(H) · BRUCE 10.5(P) · Surena-Min 7.3(S) · NAO 1.61(S)

> 주의(워크플로우 caveat): Unitree H1/G1/B2 knee **각속도는 per-joint 미공개**(토크만). Fourier GR-1 knee 토크 별도 미공개. Tesla Optimus knee 선형 force/stroke 공식 미공개(teardown/analyst 출처). Cassie ~195는 URDF effort 12.2 × 16:1 계산값(Berkeley 195와 일치). ANYdrive 하모닉비는 2차출처가 50:1 vs 100:1로 불일치 → 미확정.

## 2. 동적 레그 액추에이터 설계철학 — 저감속(proprioceptive) 패러다임 (검증, verified=yes)

> 1차출처: **Wensing, Wang, Seok, Otten, Lang & Kim (2017), "Proprioceptive Actuator Design in the MIT Cheetah," IEEE T-Robotics 33(3):509–522, DOI 10.1109/TRO.2016.2640183.** 워크플로우가 전문 대조 검증.

- 설계규칙 verbatim: *"the optimal actuator for a given mass will thus consist of a motor with the largest gap radius as allowed by space and the smallest gear ratio as required by torque specifications."* — "less is more".
- **반사관성 N² 법칙 (Eq.43): J_ref = J_r · N².** Cheetah 로터 관성 3.03×10⁻⁴ kg·m² × 5.8² = **0.0102 kg·m²** (~34배). (Firgelli 가이드 교차: 100:1 = 로터 10,000배 무겁게, 10:1 = 100배 → 같은 출력토크에 100배 반사관성.)
- **충격 완화**: 고감속은 "gear ratios too high … can break a leg upon contact or even could prevent a desired dynamic motion due to excessive mechanical impedance." footstrike 충격(sub-ms, 체중 2~3배)은 제어루프보다 빠름 → 기구가 양보해야.
- **투명 force control**: 저 N → 모터 phase 전류로 관절토크 추정(센서·스프링 불요), 고대역. Cheetah는 contact 85 ms / peak >450 N 제어(abstract).
- **IMF (Impact Mitigation Factor)** ξ=det(Ξ), 0≤ξ≤1(스케일 무관 비교). 저감속 리지드 Cheetah IMF = 가상 SEA버전의 **90%**, 고감속 HUBO = **52%**. → 저감속 리지드가 스프링 없이 SEA 충격완화의 ~90% 달성.
- 트레이드 회피: torque density ∝ r_g^0.8, torque/rotor-inertia ∝ r_g^1.6 → 큰 air-gap 반경으로 작은 N 가능("no tradeoff in its purest form"). 한계는 기하(직결 Cheetah 모터 = Φ76.2cm×5mm, 불가) → 5.8:1 = 실용 타협 + 상용 단단 유성 최대비. Cheetah 커스텀 모터 **~27 N·m/kg** (off-the-shelf Emoteq HT-5001 ~9의 3배).
- **카운터뷰(고감속, 같은 논문이 인정)**: load-carrying·저속·효율 과제엔 고감속 유리("low gear ratios cost higher energy in generating torque via Joule heating"). 범용 휴머노이드 "sweet spot" ~30:1–50:1(Firgelli). <10:1 = "agile but weak/overheats standing still", >100:1 = "strong but dangerous/cannot feel impacts".
- **두 컴플라이언스 학파**: (a) 내재적 = 저 N (MIT Cheetah QDD), (b) 외재적 = 고 N + 직렬스프링 (SEA, ANYmal/ANYdrive). 동적·고대역·충격엔 (a)가 현대 주류.
- 1차인용: Katz, Di Carlo, Kim (2019) Mini Cheetah ICRA(QDD 6:1); Seok et al. (2013/2015) T-Mech(에너지손실 분류); Hutter et al. (2016) ANYmal IROS(SEA 카운터). 신뢰도: Wensing 수치·인용 HIGH(전문 대조), ANYdrive 정확비 MEDIUM(2차출처 불일치).

## 3. RS04보다 작고·저감속·고토크밀도 후보 — 액추에이터 시장 (verified=partial)

> 기준 RobStride RS04: 120 N·m peak / 40 rated / 1.42 kg / 9:1 / Φ110×56. 토크밀도 = 120/1.42 = **84.5 N·m/kg**(벤더 ~85.7 @1.40kg). 목표 = "≤9:1 저감속에서 이 토크밀도 초과".
> TD = 토크밀도 N·m/kg = peak/mass. V=벤더/aggregator 검증, E=추정/도출.
> 1차출처: openelab.io RobStride QDD 비교가이드 외(§4).

| 모델 | 질량(kg) | peak 토크(N·m) | 감속비 | TD(N·m/kg) | 검증 |
|---|---|---|---|---|---|
| **RobStride RS04 (기준)** | 1.42 | 120 | 9:1 | **84.5** (벤더 ~85.7) | V |
| RobStride RS03 | 0.88 | 60 | 9:1 | 68.2 | V |
| RobStride RS06 | 0.621 | 36 | 9:1 | 58.0 | V |
| RobStride RS02 | 0.405 | 17 | 7.75:1 | 42.0 | V |
| RobStride RS00 | 0.310 | 14 | 10:1 | 45.2 | V |
| RobStride RS05 (EduLite) | 0.191 | 5.5 | 7.75:1 | 28.8 | V |
| MyActuator X8-120 (RMD-X8) | 1.40 | 120 | 19.61:1 | 85.7 | V |
| MyActuator X12-320 | 2.37 | 320 | 20:1 | 135.0 | V |
| MyActuator X15-450 | 3.50 | 450 | 20.25:1 | 128.6 | V |
| MyActuator X4-36 | 0.36 | 34 | 36:1 | 94.4 | V |
| MyActuator X10-40 (RMD-X10) | ~0.85 | 40 | 7:1 | ~47 | V(토크/비) E(질량) |
| MyActuator X8-20 (RMD-X8 6:1) | 0.78 | 20 | 6:1 | 25.6 | V |
| MyActuator X12-150 | 1.30 | ~120 (rated 50) | 12:1 단단 | ~92 peak / 38 rated | E(peak) V(rated/질량/비) |
| CubeMars AK10-9 V2.0 | 0.96 | 48 (V3.0 ~53) | 9:1 | 50.0 | V |
| CubeMars AK80-9 | 0.485 | 22 | 9:1 | 45.4 | V |
| CubeMars AK80-64 (T-Motor) | ~0.85 | 120 | 64:1 | ~141 | V(토크/비) E(질량) |
| Steadywin GIM8115-6 | ~0.7 | 38 (stall) | 6:1 | ~54 | V(토크/비) E(질량) |
| Steadywin GIM6010-8 | 0.388 | 11 | 8:1 | 28.4 | V |
| **Unitree M107 (H1 knee)** | ~1.9 (추정) | **360** | low ~6–10:1 | **189** (벤더) | V(TD,토크) E(질량 도출) |

**판정**:
- 저감속(≤~9:1)에서 RS04 토크밀도를 압도하는 유일 후보 = **Unitree M107(~189, 2배 이상)**. 고 Kt·저관성 내부로터 PMSM + 저감속. 단 H1/H1-2 내장형, 단품 미판매, 질량은 360÷189로 도출(추정).
- off-the-shelf RobStride/CubeMars/Steadywin 중 동일/낮은 감속에서 RS04 초과는 **없음**(RS03/06 더 작지만 TD 낮음 68/58; AK10-9 9:1 ~50; GIM8115-6 6:1 ~54).
- 토크밀도가 높은 MyActuator X12/X15/X4-36·AK80-64는 전부 **20~64:1 고감속**으로 이긴 것 → backdrivability/대역 희생, "저감속" 목표 배반.

> caveat: E 질량은 도출(peak÷벤더TD 또는 aggregator gross). RobStride peak는 벤더 peak(단시간), 연속은 ~1/3. apples-to-apples엔 전압/열한계 정합 필요(벤더 미표준화). LinkerHand=손 제품군(레그 액추에이터 아님), Tsinghua/Tianbot 공개 데이터시트 없음.

## 4. 1차/주요 출처 (하이퍼링크)

- MIT Cheetah 액추에이터(proprioceptive, 5.8:1, IMF, N²): https://fab.cba.mit.edu/classes/865.18/motion/papers/mit-cheetah-actuator.pdf
- MIT Cheetah 3(7.67:1, 230 N·m, 21 rad/s, IROS 2018): https://dspace.mit.edu/server/api/core/bitstreams/b93369ab-d87a-4fcf-a1e0-3bd34be52761/content
- Mini Cheetah 모듈(6:1, 17 N·m, 40 rad/s): https://biomimetics.mit.edu · https://robotsguide.com/robots/minicheetah
- MIT Humanoid(U12 knee, 12:1, 136 N·m, 22.5 rad/s, 벨트단): https://arxiv.org/pdf/2104.09025
- Cassie URDF(16:1, 12.2 N·m, 8.5 rad/s): https://github.com/UMich-BipedLab/cassie_description
- Berkeley Humanoid(9:1, 8518 knee 62.6 N·m, 29 rad/s + Table 1 비교): https://arxiv.org/pdf/2407.21781
- Unitree H1(M107, 360 N·m knee): https://www.unitree.com/h1 · https://docs.quadruped.de/projects/h1
- Unitree G1(knee 120 EDU / 90 base): https://docs.quadruped.de/projects/g1
- Fourier FSA(하모닉, 비 7–120): https://fftai.github.io/fsa/fsa · https://www.fftai.com/products-gr1
- Tesla Optimus(선형 knee, 롤러스크류): https://optimusk.blog/blog/tesla-optimus-hardware-specs
- RobStride QDD 모델비교/선정 가이드(RS04 기준 84.5 N·m/kg): https://openelab.io/blogs/learn/complete-guide-to-robstride-qdd-motors-model-comparison-and-selection
