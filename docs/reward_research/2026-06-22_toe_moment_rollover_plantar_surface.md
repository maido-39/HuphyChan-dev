# reward 연구 — toe moment(왜 15 N·m뿐인가) + heel→toe rollover로 plantar surface 쓰게 하기 (2026-06-22)

> 트리거: gaitfix_v4 측정 — toe Fz max ~340N(67%BW)이지만 toe joint torque ~15 N·m·굴곡 5–11°(mean −1°)뿐. 사용자: "인간 MTP는 push-off ~40 N·m·30–60° 굴곡인데 우리는 안 굴림." 질문 (1) rollover로 toe moment를 30–40 N·m로 올릴 수 있나, 아니면 스프링을 더 무르게? (2) lateral edge가 아니라 발바닥 전체(heel→mid→forefoot→toe)를 쓰게 하는 보상은? 변경하려는 reward: forefoot_cop / 신규 contact-sequence·foot-pitch 항, 그리고 toe spring k. 웹+geometry 정량분석, confidence high.

## 1. ★ 핵심 정정 — "human MTP ~40 N·m"는 우리 질량에 틀린 기준 (mass-normalize)

문헌 정규화 값(우리 51.8 kg에 스케일):

| 양 | 인간 정규화 | 51.8 kg 환산 | 우리 측정 | 판정 |
|---|---|---|---|---|
| **MTP(toe) moment** | **~0.13 N·m/kg** (4-seg foot model, pre-swing peak) | **~6.7 N·m** | **~15 N·m** | ✅ 우리 toe는 이미 인간 MTP의 **2배+ 적재**. moment 부족 아님 |
| **MTP 굴곡각** | 일반 toe ~30°, 1st-MTP **50–60°** (late stance) | 동일 | **5–11°(mean −1°)** | ✗ **굴곡(굴림) 자체가 없음** — 진짜 결손 |
| **ankle plantarflex moment** | **~1.5 N·m/kg** | **~78 N·m** | (측정요) | push-off 진짜 동력원은 발목 |
| **ankle push-off power** | peak **>2.5 W/kg** | **~130 W** | (측정요) | 타 관절 3배 |

→ docs/12의 "push-off toe ~40 N·m" 산정(GRF 550N×0.07m)은 (a) 무거운 성인 기준이고 (b) **MTP를 발목 모멘트와 혼동**. **질량 정규화하면 toe moment 타깃은 ~6.7 N·m이고 우리는 이미 15 N·m로 초과.** 그러므로 **"toe가 덜 적재돼서 안 굴린다"가 아니라, 굴림(rollover)을 안 해서 CoP가 toe 앞으로 안 가고, moment는 (충분한데도) 짧은 lever라 큰 굴곡을 못 만든다.**

## 2. toe moment = forefoot_Fz × d_cop (CoP가 toe hinge 앞으로 나간 거리) — geometry 정량

robot.xml: L_toe_joint = L_foot_link 기준 **y −0.192 m 전방**(=MTP hinge). toe spring **k=60 N·m/rad**(yaml), 굴곡 = M/k.

| forefoot Fz | d=CoP 전진거리 | toe moment | spring 굴곡(k=60) |
|---|---|---|---|
| 340N(측정 max) | 4cm | 13.6 N·m | 13° |
| 340N | **8.8cm** | **30 N·m** | **28.6°** |
| 340N | 11.8cm | 40 N·m | 38° |
| 560N(1.1×BW) | 5.4cm | 30 N·m | 28.6° |
| 560N | 7.1cm | 40 N·m | 38° |

★ **답(질문1): rollover만으로 30 N·m·~30° 굴곡 달성 가능 — 스프링 더 무르게 할 필요 없음.** 현재 k=60(인간 MTP ~56 일치)에서 30 N·m가 정확히 28.6° 굴곡을 줌(=인간 일반 toe 30° 일치). 필요한 건 **CoP를 toe hinge 앞 ~5–9cm까지 굴려보내는 GAIT**이지 스프링 변경이 아님.
- 현재 5–11° 굴곡 ⇒ CoP가 toe hinge 앞 **~2–4cm**(M~7–14 N·m)에서 멈춤 = **mid/forefoot pivot에서 정지, toe rocker 진입 실패**. 측정 15 N·m와 정합.
- ⚠️ **스프링을 무르게(k↓20–30) 하면 안 됨**: 같은 작은 CoP·moment(7–14 N·m)에서 굴곡 각도만 부풀려져(겉보기 "굴림") **rollover한 것처럼 보이지만 인과는 그대로**(forefoot 적재·push-off 없음) + sim2real 갭↑(docs/15: k=60이 인간 일치·armature와 함께 수치안정). 무르게 = 증상(각도)만 위장, **안티패턴**.

## 3. ★ 답(질문2): sagittal forefoot 사용 ≠ lateral edge 문제 — 둘은 분리, 동시 처방

- **lateral edge(ankle_roll)** = frontal-plane 문제, **stance-width / foot-placement** 결손(이미 [[40_foot_edge_ankle_roll]]·gaitfix_v5에서 처방 중). 발이 옆으로 기울면 forefoot의 **sole가 땅에 평평히 안 닿아** rollover 물리적 불가 → **edge부터 고쳐야 rollover가 성립**(전제조건, 약한 결합).
- **sagittal rollover(heel→mid→fore→toe)** = 별도. Perry **4-rocker 모델**이 정확히 사용자가 원하는 시퀀스 (AAPM&R):
  1. **heel rocker** (loading 2–12%): heel만 접지, 발목 plantarflex→foot-flat. tibialis ant. **eccentric**(controlled lowering = slap 방지).
  2. **ankle rocker** (midstance 12–31%): foot-flat, tibia가 발 위로 전진, ~5° dorsiflex. soleus eccentric.
  3. **forefoot rocker** (terminal 31–50%): **heel 들림**, CoP가 metatarsal로 전진, plantarflexor **concentric**(push-off 가속). ← **우리가 멈추는 지점 직전**
  4. **toe rocker** (pre-swing): MTP 30°(1st 50–60°) dorsiflex하며 toe-off.
- **CoP 전진폭**: heel→toe로 **발 길이의 ~80–83%**(plantigrade). rocker 반경 ~다리길이 30%.

### sagittal rollover를 유도하는 보상 (heel→toe)
1. ★ **ankle_pitch가 rollover의 엔진**: forefoot rocker = 발목 plantarflexor가 만든다("ankle push-off의 주기능은 forefoot rocker 보존" — unified perspective, Perry). 우리는 ankle_pushoff_work(w0.1)로 de-emphasize 중인데, **edge/self-conflict 해소 후 ankle_PITCH plantarflex work를 다시 키워야 CoP가 forefoot로 전진**. (forefoot_cop는 *결과* 보상, ankle_pushoff는 *원인* 보상 — 둘 다 필요.)
2. **contact-sequence / phase-clock 보상**(Siekmann/Walk-These-Ways 계열, [[34_cop_contact_rewards]]): swing=force penalty·stance=velocity penalty를 **위상클록 게이트**. **sub-foot으로 확장**(초기=heel body force, 종말=forefoot/toe body force) → heel-first→forefoot-last 시퀀스 직접 보상. 단 verbatim CoP항은 표준 아님(자체 합성).
3. **flat-foot slap 페널티 = foot_landing_vel**(이미 w−1.0): heel rocker의 eccentric controlled-lowering 대응. 유지.
4. **foot-pitch 보상**: 착지 시 발끝 살짝 든(heel-first) pitch + 종말기 heel-rise pitch를 보상. foot-BODY orientation(projected-gravity)로, **각² hard 금지·exp 포화형**(균형 안 해치게, [[40]]와 동일 교훈).
5. **straight-knee**(Gait-Conditioned RL 2505.20619·Duke Humanoid): toe가 유효다리 연장 → 무릎 펴짐 동반. knee_straight_penalty와 상충 주의(과굴곡 막되 종말기 신전 허용).

### 결합 여부 (사용자 질문 "are these coupled?")
- **약하게 결합, 인과는 단방향**: edge(roll)가 있으면 sole 비접지 → rollover 불가 ⇒ **edge 먼저(필요조건)**. 그러나 edge를 고친다고 rollover가 *자동* 생기진 않음 — **sagittal forefoot-rocker는 별도 보상(ankle_pitch push-off + contact-sequence)이 추가로 필요**. 즉 "flat 유지(pitch·roll)"는 전제, "forward roll"은 별도 엔진.

## 4. 제안 (실행 순서)
1. **toe spring k=60 유지**(무르게 금지 — §2). armature 0.008·damping 4 유지.
2. edge/ankle_roll 먼저 해소(gaitfix_v5: stance-width + foot-body orientation) — rollover 전제조건.
3. 그 후 **ankle_pushoff_work(ankle_PITCH) weight 복원·상향**(self-conflict 해소됐으므로) + **forefoot_cop 유지**(원인+결과 짝).
4. (선택) **sub-foot contact-sequence 보상**(heel body 초기·toe body 종말, phase-clock 게이트)으로 heel→toe 직접 형성.
5. **검증**: toe 굴곡 5–11°→25–35°·forefoot Fz fraction 종말↑·**GRF 2차(toe-off) 피크** 출현. 굴곡↑인데 CoP 전진/GRF 2차피크 없으면 = 정적 curl 위장(적대적 probe, [[23_toe_use_methods]]).
6. **HW 함의**: toe moment 타깃 = mass-norm ~7 N·m(이미 초과), 진짜 push-off 동력 = **ankle_pitch ~78 N·m·~130 W**(RS03 60 N·m effort 한계 주시 — push-off에서 ankle_pitch가 binding 가능성, [[36]]). toe 스프링은 인간 일치(k60)로 **현 설계 정당**.

## 5. References
- [MTP kinetics 4-seg foot model, J Foot Ankle Res (PMC4101357)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4101357/) — MTP moment ~0.13 N·m/kg pre-swing.
- [MTP dorsiflexion ~30°, 1st-MTP 50–60° late stance (ScienceDirect MTP overview)](https://www.sciencedirect.com/topics/medicine-and-dentistry/metatarsophalangeal-joint)
- [A unified perspective on ankle push-off (PMC5201006)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5201006/) — ankle push-off가 forefoot rocker 보존(Perry).
- [Ankle plantarflex moment ~1.5 N·m/kg, power >2.5 W/kg (PMC4664043)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4664043/)
- [Biomechanics of Normal Gait — 4 rockers (AAPM&R KnowledgeNow)](https://now.aapmr.org/biomechanics-normal-gait/)
- [Rolling foot shape: rocker radius ~30% leg length, foot length ~29% (PMC3694099)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3694099/)
- [CoP excursion ~80–83% foot length (CoP trajectory study, PMC4029865)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4029865/)
- [Gait-Conditioned RL: straight-knee + smooth heel-to-toe rewards (arXiv 2505.20619)](https://arxiv.org/html/2505.20619v1)
- [Duke Humanoid passive dynamics, CoT −31~50% (arXiv 2409.19795)](https://arxiv.org/abs/2409.19795)
- [DBHL ZMP reward Eq.7 + Feet Separation/Edge (arXiv 2502.17219)](https://arxiv.org/html/2502.17219v2)

> [!note] 솔직성 노트
> MTP 0.13 N·m/kg·angle 30°/50–60°·ankle 1.5 N·m/kg·power 2.5 W/kg·rocker는 문헌 직접인용(verified). toe lever-arm·30 N·m=8.8cm·굴곡각은 우리 robot.xml geometry(d=0.192m hinge·k=60)와 M=Fz·d, defl=M/k로 자체계산. contact-sequence sub-foot 보상은 Siekmann/WTW를 sub-foot으로 *확장*하는 합성안(verbatim 표준 아님, [[34]]). edge↔rollover 결합 판정은 추론(생체역학+우리 측정).
