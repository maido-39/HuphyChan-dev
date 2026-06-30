# 40. 발-edge 보행 + ankle_roll/측방-CoP 과부하: 근본원인 + 올바른 보상/기법

> 우리 정책이 **발 바깥날(lateral edge)**로 걷는다(ankle_roll 입각기 ~18deg 편향) → 측방 CoP → ankle_roll(RS00 14Nm) 포화(peak100%·RMS110% = 열과부하).
> gaitfix_v3 `foot_roll_flat`(ankle_roll각²·w=−0.5) + `forefoot_cop`(0.8) → edge 20→18deg만 미미하게 감소. 무릎·toe는 크게 개선, 발-edge/ankle_roll은 안됨.
> **질문**: 왜 edge로 걷나? (a)보상아티팩트 (b)측방밸런스 진짜필요 (c)stance-width/foot-placement (d)발기하학? flat 강제가 측방밸런스를 해치나?

## 0. 결론 (TL;DR)

**edge 보행은 (a)아티팩트가 아니라, (c)stance-width/foot-placement 결핍이 (b)측방밸런스 needs를 ankle_roll로 밀어넣은 결과다.** 즉 *원인은 (c), 증상은 (b)를 ankle로 푸는 것*. (d)발 기하학은 2차.

- **생체역학 정설**: 측방(frontal-plane) 밸런스는 **두 메커니즘**으로 푼다 — (1)**foot placement = step width**(주(primary) 메커니즘) + (2)**lateral ankle mechanism = ankle inv/ev로 CoP를 발바닥 안에서 이동**(보조·once-per-step 미세보정). ankle 메커니즘의 CoP 이동량은 **발 폭(foot/shoe width)에 물리적으로 상한**됨. ([nature 2021], [Reimann PLOS 2019])
- **함의**: 정책이 측방밸런스를 ankle_roll로 과하게 푸는 건, **step width(횡방향 foot placement)가 부족**해서 CoM이 지지발 위로 충분히 안 와 → CoP를 발 바깥끝까지 밀어야 하고 → ankle_roll이 발폭 한계까지 포화. **foot_roll_flat 페널티를 더 키우면 측방밸런스 수단을 빼앗는 꼴**(ankle만 막고 대체수단 안 주면 정책은 무릎/힙으로 회피하거나 학습붕괴).
- **올바른 처방(순서)**: ① **stance/step-width를 명시적으로 줌**(feet_separation/feet_distance 보상 + width 커맨드/커리큘럼) → ankle_roll demand의 *원인* 제거. ② **lateral foot-placement 보상**(swing발 횡방향 착지 위치를 CoM 측방상태에 맞춤; Raibert-측방). ③ flat은 **부드러운 orientation 보상**(ankle frame projected-gravity, exp형)으로 — **각²·hard penalty가 아니라** 포화형. ④ CoP-centering(발 내 측방 CoP를 중앙으로) 보상은 ①②가 된 *뒤에* 미세조정용. **flat 페널티 단독증량은 안티패턴** — 원인(stance) 안 고치고 증상(roll각)만 누르면 18deg에서 정체되는 게 정확히 우리 관측.

## 1. 근본원인 4지선다 판정

| 가설 | 판정 | 근거 |
|---|---|---|
| **(a) 보상 아티팩트**(penalty 없어 exploit) | **부분기각** | foot_roll_flat(−0.5)·forefoot_cop(0.8) 이미 줬는데 18deg 정체 → 단순 "페널티 없어서"는 아님. penalty *약함*은 맞으나 그게 1차원인 아님. |
| **(b) 측방밸런스 진짜 needs** | **참(증상)** | ankle inv/ev = 측방 CoP 제어의 **주 수단(sustained locomotion 중)**. 정책이 이걸로 밸런스 푸는 건 *기능적으로 정당*. 막기만 하면 밸런스가 깨짐. |
| **(c) stance-width / foot-placement** | **참(근본원인)** | foot placement(step width)가 측방밸런스 **primary**. width 부족→CoM이 지지발 위에 안 옴→CoP를 발끝까지(=ankle_roll 포화)밀어야 함. **여길 고쳐야 ankle demand 자체가 줄어듦.** |
| **(d) 발 기하학**(평발·passive toe·폭) | **2차** | ankle CoP 이동은 **발폭에 상한** → 발이 좁으면 같은 측방모멘트에 edge로 더 빨리 감. 발폭/접지패치는 상한을 정할 뿐 *왜 edge로 가는지*의 원인은 아님. |

**핵심 인과사슬**: narrow stance → CoM이 측방으로 지지선 밖 → 측방밸런스 위해 CoP를 외측으로 → ankle_roll이 발 바깥날까지 inversion → roll 포화 + 실제 접지가 edge.

## 2. 생체역학 근거 (검증 인용)

- **ankle가 측방 CoP를 만든다(주 수단)**: "lateral ankle mechanism … is the **main means of modulating the center of pressure under the stance foot during sustained locomotion**." 단 "the magnitude of CoP modulation … is **constrained to the width of the foot or shoe**." → ankle_roll CoP권한은 **발폭이 천장**. ([Reimann et al., PLOS One 2019])
- **foot placement = primary, ankle = 보조·보정**: "ankle moment control **complements** foot placement, by allowing a corrective CoP shift **once the foot has been placed**." 스텝이 너무 medial→ankle inversion으로 CoP 외측; 너무 lateral→eversion으로 CoP 내측. ([Nature Sci.Rep. 2021])
- **둘은 순환(상호의존)관계**: "when foot placement was **constrained, ankle moment control did NOT increase as compensation**" → 단순 백업 아님. *but* 정상보행선 **foot placement가 주, ankle은 imperfect placement 보정**. → **width를 주면 ankle demand가 내려갈 여지**가 인과적으로 존재. ([Nature Sci.Rep. 2021])
- **ankle inv/ev 미세조정은 밸런스 "노력(대사비)"을 줄임**: once-per-step inv/ev torque 보정으로 대사비 6–15% 감소 → ankle 측방조절이 *비용*이라는 직접증거(=정책이 ankle 포화 쓰면 비효율). ([Frontiers NeuroRobotics 2017])
- **외부 측방안정화 시 step-width·placement-제어 감소** → 측방 외란이 step width를 직접 구동함을 역으로 확인(=width가 측방밸런스의 핸들). ([nature 2021] 서론, [biorxiv 2022])

## 3. RL 기법 근거 (실제 휴머노이드는 ankle_roll을 어떻게 낮추나)

실제 SOTA 휴머노이드 보상에서 **flat을 각² hard-penalty로 강제하지 않고**, (i)횡방향 feet-spacing, (ii)부드러운 발-orientation, (iii)ZMP/CoP를 조합:

- **Feet Separation / Feet Distance(횡방향 stance-width 보상)** — 두 발 측방(y) 간격을 목표로 유지. DBHL(narrow-terrain) Table I에 **"Feet Separation"**·**"Feet Edge Distance"**가 정식 gait 항으로 존재. Unitree류 config도 feet 간격/clearance 항 보유. → **stance-width를 직접 보상**하는 게 표준 (우리 빠진 것). ([DBHL arXiv:2502.17219], [unitree_rl_gym])
- **발-orientation을 projected-gravity(ankle frame)로, exp형 부드럽게** — "ankle orientation reward penalizes excessive ankle roll by the **projected gravity vector in each ankle frame**." base-flat은 `r_ori=−w·‖g_xy‖²`(IsaacLab), feet-flat은 `1−exp(−k·Σ|θ_pitch|)` 형. **각의 제곱 hard penalty(우리 −0.5 ankle_roll²)는 측방수단을 끄는 부작용** → exp 포화형이 "거의 평평하면 만족, 끝에서만 강하게"라 측방 미세조절 여지를 남김. ([ULC arXiv:2507.06905], [IsaacLab 표준])
- **Feet Edge Distance** — 발 접지점을 발 가장자리에서 멀리(=중앙접지) 보상. 직접적으로 edge-contact를 줄임. ([DBHL arXiv:2502.17219])
- **ZMP/CoP 기반 보상** — DBHL Eq.7: ZMP를 Zero-Moment-Line 근처로(지지다각형 내부 중심). CoP-centering은 **stance가 확보된 뒤** 발 안에서 압력중심을 중앙으로 모으는 미세항. ([DBHL arXiv:2502.17219])
- **횡방향 foot-placement(측방 Raibert)** — swing발 측방 착지위치를 CoM 측방상태(속도)에 맞춰 보상 → 측방밸런스를 **placement로** 풀게 유도(ankle 부담↓). ([Reimann 2019]가 생체역학 정당성, RL 측은 Raibert footstep 휴리스틱의 측방확장).

## 4. flat 강제가 측방밸런스를 해치는가? — **예, 단독이면 해친다**

- ankle inv/ev는 측방 CoP 제어의 *기능적 주 수단(sustained)*([Reimann 2019]) → ankle_roll각을 직접 누르면 **측방밸런스 핸들 하나를 제거**. 대체핸들(step width / lateral placement)을 **먼저** 안 주면 정책은 (i)밸런스 악화로 reward 손해를 보거나 (ii)힙/무릎으로 비정상 회피 → 우리 관측(roll 18deg 정체 = penalty와 밸런스-needs가 평형)과 일치.
- **올바른 순서 = 원인 먼저**: stance-width·lateral placement로 **ankle demand의 원인을 제거** → 그 다음 flat orientation 보상은 *낮아진* demand를 마무리. 이때 flat penalty는 작아도 듣는다(원인이 사라졌으므로).

## 5. 우리 케이스 적용 (E-시리즈 처방)

1. **feet_separation 보상 추가**(횡방향 y-간격 목표; 51.8kg 하체비례로 골반폭+α, 커리큘럼으로 넓→좁). **이게 1순위** — ankle_roll demand의 *원인*.
2. **lateral foot-placement 보상**(swing발 측방착지를 base 측방속도에 매칭; 측방 Raibert).
3. `foot_roll_flat`을 **각²(−0.5) → ankle-frame projected-gravity exp형**으로 교체(포화형, 측방 미세조절 여지 보존). 가중치는 ①② 후 재튜닝.
4. CoP-centering / feet_edge_distance는 **①②가 stance를 확보한 뒤** 미세조정용.
5. (HW연계) 발폭이 ankle CoP권한의 상한 → **접지패치 폭**이 sizing 변수로 측방밸런스에 직접 기여(=발폭↑이면 같은 측방모멘트에 edge 덜 감). [[37_ankle_linkage_fidelity]]·[[36_all_actuator_tn_envelopes]](RS00 봉투)와 연계.

> [!warning] 안티패턴
> "foot_roll_flat 페널티만 더 키우기"는 원인(narrow stance) 미해결 + 측방밸런스 수단 박탈 → 18deg 정체/회피동작/학습붕괴. **stance-width를 먼저 줄 것.**

## 6. References (하이퍼링크)

- [Reimann et al. (2019), "Interdependence of balance mechanisms during bipedal locomotion," PLOS One](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0225902) — foot placement=primary, ankle=보조·보정, CoP는 발폭 상한.
- [van Leeuwen et al. (2021), "Ankle muscles drive mediolateral center of pressure control to ensure stable steady state gait," Sci. Rep.](https://www.nature.com/articles/s41598-021-00463-8) ([PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC8563802/)) — ankle inv/ev↔측방 CoP, placement 부정확시 ankle 보정.
- [Antonellis et al. (2017), "Step-to-Step Ankle Inversion/Eversion Torque Modulation Can Reduce Effort Associated with Balance," Front. Neurorobot.](https://www.frontiersin.org/journals/neurorobotics/articles/10.3389/fnbot.2017.00062/full) — inv/ev 미세조정으로 대사비 6–15%↓(=ankle 측방조절은 비용).
- [Long et al. (2025), "Humanoid Whole-Body Locomotion on Narrow Terrain (DBHL)," arXiv:2502.17219](https://arxiv.org/html/2502.17219v2) — Feet Separation·Feet Edge Distance·ZMP(Eq.7) 보상 항.
- [Yin et al. (2025), "ULC: Unified Controller for Humanoid Loco-Manipulation," arXiv:2507.06905](https://arxiv.org/pdf/2507.06905) — ankle orientation 보상 = ankle frame projected-gravity.
- [unitree_rl_gym (Unitree H1/G1 RL config)](https://github.com/unitreerobotics/unitree_rl_gym) — feet 간격/clearance/gait 항(표준 구현 참조).

> [!note] 솔직성 노트
> 생체역학 3편(Reimann/van Leeuwen/Antonellis)은 본문 직접대조(verified). RL측 Feet Separation·Feet Edge Distance·ZMP는 DBHL Table I에 **항목명으로 명시**되나 **verbatim 식·가중치는 본문 미공개**(implementation/code) — 식 형태(projected-gravity, exp 포화)는 ULC·IsaacLab 표준에서 보강. "flat 단독증량 안티패턴"은 생체역학(ankle=측방 주수단)+우리 관측(18deg 정체)의 추론이며 단일 논문의 직접주장은 아님.
