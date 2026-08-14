# 리서치 — ① 자연스러운 보행 ② 토크 분배·부드러운 착지 ③ Passive Toe/Toe-off Reward

> 2026-07-02. 사용자 3개 질문을 deep-research(fan-out 검색→fetch→**3-vote 적대적 검증**→합성)로 조사, 우리 검증 findings와 대조. workflow `wddo420va`→`wp29o9s6k`→`wiqg79n23`(run `wf_85cf590d-b43`, 계 ~300 agents/9.6M tokens). **★ 3차 실행서 합성 완료** — 최종 11개 병합 findings(전부 3-0). 아래 §갱신 참조.

## ★ 합성 결론 (3차 완료분, 최우선)

> **passive-toe biped엔 phase-clock Siekmann 백본이 최선(5+ 논문 독립재현). 부드러운 착지 = Fz→0 지수벌점(Cassie w−7) 또는 역치 cap(REEM-C −0.01·Fz>1500N). AMP style은 위로 얹되 β 소량(과하면 안정성↓ 정량확인). 대칭은 soft loss보다 architectural equivariance(오차 정확히 0). <10항 미니멀 보상이 실기 G1/Booster서 충분(20+항 과설계 경계). ★ toe-off는 어떤 소스도 "toe토크 없이 창발" 직접검증 못 함 → periodic+soft-strike+capped-push-off+base앵커 스택서 CoP-rocker로 창발 유도, 직접 toe항 금지(우리 실증).**

### 신규 확증 findings (합성분, 위 계열표 보강)
- **F3(3-0)**: 착지 = **`exp(−α·Fz)`로 Fz→0** 밀기, Cassie **w−7(walk)** [SAGE Cassie]. F4: REEM-C 역치 cap **$-0.01\cdot(F_{z,L}+F_{z,R})$, 1500N(≈1.9×BW) 초과분만** — cap이 push-off보다 선행(우리 순서교훈 재확증).
- **F5/F7(AMP 트레이드오프, 3-0)**: style은 $r=(1-\beta)r_{AMP}+\beta\cdot r_{task}$ 블렌드(walk ~20% style/80% task). ★ **style↑=human-like↑지만 안정성↓ 정량**: β0.4=최고 종합(0.733)/안전(0.720), β0.9=human-like↑지만 안전 0.679. **소량만.**
- **F6(3-0)**: **State-dependent AMP**(recovery+locomotion 판별자 2개, projected-gravity 역치 게이팅)로 **G1 실기서 walk/run/recover 단일정책**(LAFAN1 3클립). (1차 반박됐던 SD-AMP 주장의 정정판 — 구조 주장은 과장이나 존재 자체는 확증.)
- ★ **F8(3-0)**: **대칭은 architectural equivariant actor/invariant critic**가 soft symmetry-loss보다 압도 — 공간대칭오차 **정확히 0.0**(vs 0.082rad), 추종 최대 40%↑(G1 실기). → 우리 GRF asym도 soft 항보다 **정책 구조 대칭성**이 근본.
- ★ **F9(3-0)**: **<10항 미니멀 보상이 실기 자연보행 충분**(속도추종·swing발높이·default-pose·발평행+no-cross·alive·upright·action-rate) — **20+항 과설계 경계**. 우리 mjlab 15항이 이미 그 범주.
- **F11(3-0)**: ★ **phase-clock 알려진 실패모드** — **standing 모드서 발속도 저벌점이 외란거부 방해**, walk↔stand 전환 시 clock 급변이 최대 드리프트. → **standing/전환엔 clock 게이팅 필요**(우리 gait-mask 도입 근거).

관련: [계획 v2](../mujoco/2026-07-02_training_plan_v2.md) · [분석 기록](../mujoco/2026-07-02_analysis_reward_audit_critique.md) · 우리 계보: [Siekmann](2026-06-29_gait_emergence_siekmann.md) · [toe](2026-06-29_toe_use_reward.md)

---

## Q1. 사람처럼 자연스럽게 걸으려면 — 확증된 방법 지형도

**3개 계열이 실로봇에서 검증됨. 우리 Siekmann 백본이 주류와 일치.**

| 계열 | 실증 | 핵심 (검증 인용) |
|---|---|---|
| **① Phase-clock 주기접촉** (우리 백본) | Cassie(Siekmann 원전)·Humanoid-Gym 실로봇·H1-2(ALMI)·G1 | C14: `R = c·I(φ)·q(s)`, swing엔 발힘 벌·stance엔 발속도 벌 **만으로 레퍼런스 없이** 보행 학습 [arXiv:2011.01387]. C15: 원전 가중치 = **주기접촉 블록 0.4로 최대**(tracking 0.3, smooth 0.1). C10: Humanoid-Gym도 sin/cos clock + 접촉패턴 보상(w1.0) 실로봇 zero-shot [arXiv:2404.05695]. C7: ALMI(H1-2 실기)는 binary-XOR형 w+0.18 [arXiv:2504.14305] |
| **② 레퍼런스-프리 생체역학 보상** | **Unitree G1 실기** | C13: 모캡 없이 gait-조건 생체역학 항 + sin/cos phase로 human-like [arXiv:2505.20619]. C1: **gait mask** — 모드(stand/walk/run)별로 관련 보상만 활성(one-hot gait ID) |
| **③ AMP(모션프라이어)** | H1(HumanMimic) | C4: 표준 AMP는 불안정 → **Wasserstein-1 + tanh 소프트경계**로 안정화 필요 [arXiv:2309.14225]. C6: 보상 단 2항(속도추종+style). ★C5: **vanilla BCE AMP는 모드붕괴 → 까치발**로 수렴(우리 tiptoe attractor와 동일 현상, 다른 원인!) |

**★ 우리 finding(b) "관절각 추종 실패"의 정밀화** (반박 아닌 조건 규명):
- C2(Cassie 실기, 3-0): 모션모방(관절추적 w15) 성공 — 단 **참조 프레임 preview(t+1,4,7)를 정책이 관찰** = phase 불일치 원천 차단.
- C12(Humanoid-Gym, 3-0): 관절추적 w1.5가 최대항으로 성공 — 단 참조가 **정책이 보는 clock과 동일 위상에서 생성**.
- → **교훈: 관절각 추종은 "참조 위상 = 접촉 위상"이 보장될 때만 작동.** 우리 v3-v7은 독립 고정주기 참조라 실패(우리 결론 유지). 레퍼런스-프리(①②)로 충분하니 백본 변경 불요.

**base 앵커 교차확증**: C12 Humanoid-Gym base_height w0.5 상시 포함. ⚠(미검증) REEM-C는 17항 중 base_height **w −100로 압도적 최대** [arXiv:2407.05148] — 우리 finding(f) 강력 부합.

---

## Q2. 토크 균등분배 + 부드러운 착지 — 실로봇 검증 공식

**(i) 분배 — "hip을 쓰게" 하려면 원위(ankle/knee)를 상대적으로 더 벌줘라**:
- ★ C8(ALMI, H1-2 실기, 3-0): **관절군별 차등 페널티** — ankle 토크 벌점을 일반 관절의 **5×**(−5e-5 vs −1e-5), ankle action rate **2×**. = 원위 관절 extra-regularize → 근위(hip)로 부하 이동. **B2의 직접 템플릿**(torque_limit 단독보다 정교).
- C9(ECO, 3-0): 에너지는 보상이 아니라 **PPO-Lagrangian 경성 제약**($\Sigma|\tau\dot q|$ ≤ b)으로 — 무한보상 해킹 원천 차단 [arXiv:2602.06445]. 우리 v9 파워해킹 교훈과 정합(cap=제약의 저렴한 근사). 대규모 변경이라 옵션.
- ⚠(미검증) Duke Humanoid: 관절별 **passive 계수 $\alpha$**($\tau=\alpha\cdot$PD)에 미세 passivity 보상(0.005) → **스윙 중 knee 자발적 탈력 창발**, 실기 전력↓ [arXiv:2409.19795] — 에너지·토크 동시 절감 아이디어.

**(ii) 부드러운 착지 — 검증된 2개 공식**:
- ★ C11(Humanoid-Gym, 3-0): **역치형 GRF 벌점 `−0.01·min(max(F_foot−400N, 0), 100)`** — 발당 400N(≈1.2×BW) 초과분만 벌점, 클립 100. 실로봇 검증. **우리 로봇 환산: 역치 ≈ 600N(1.2×505N)**. 상시(첫접촉만이 아닌) 작동이라 mjlab soft_landing(첫접촉 raw N)보다 견고.
- C3(Cassie, 2-1): 충격벌점이 smoothing 중 최대(w10 vs 토크 w3) + ★**커리큘럼 — 후반에 충격/smoothing↑·tracking↓** 스케줄. 우리 "impact cap 먼저" 순서 교훈과 정합.

---

## Q3. Passive Toe / Toe-off — 리서치 결과와 우리 계보의 종합

**인터넷 검증분은 Q3서 가장 약함**(toe 특화 claim들이 세션한도에 걸림). 검증된 관련 사실 + 우리 자체 연구가 여전히 최선 가이드:
- C5: 까치발은 AMP 모드붕괴로도 발생 = **toe/발목 자세는 보상지형의 취약 attractor** — 간접·위상게이팅 필수(우리 결론 강화).
- C13/C1: 생체역학 항은 **gait mask(위상·모드 게이팅)**로만 안전 — toe 항도 동일 원칙.
- 반박됨(1-2): "에너지 최소화가 heel-toe를 억제한다" 주장은 **검증 실패** — 에너지 페널티와 toe-off 공존 가능성 열림.
- ⚠(미검증) REEM-C: 인간형 타이밍 고정 clock(double support 0.35s/single 0.75s ≈ stance 66%) — 우리 60%와 근접.

**우리 계보(v5/v6/v9 실패 + toe 연구 w2cauzd19)와 종합한 처방** — 순서가 생명:
1. **지오메트리 먼저 (물리적 가능성)**: toe sole이 flush(z≈−0.0598, 상시접촉) → forefoot 신호·rocker 롤 약함. **toe 접촉 분리(gap/곡률)** 없이는 어떤 보상도 약함(v6 기여 0.06%의 원인). ★ mjlab 이식 시 발 지오메트리 검토가 선행.
2. **Siekmann 백본 + impact cap(Q2 공식) 안착 후**에만 push-off 항(v9 순서교훈; C3 커리큘럼도 동일).
3. **CoP 전진 보상은 clock 말기-stance(φ 0.45~0.6)에 게이팅**(v9는 접촉시간 proxy라 실패) + **ankle push-off power는 cap+말기-단일지지 게이트 필수**(무캡=GRF 11.5×BW 실증).
4. 대안 운동학 신호(파워 아님=해킹 면역): **말기-stance heel-rise/발 pitch 보상** — toe-off의 기하학적 표현. 파워 항보다 게이밍 여지 작음.
5. **|τ_toe| 직접 보상 금지** 유지(정적 curl 게임, 우리 실증 + 반례 없음).

---

## 종합 — Phase B 설계 확정에의 반영

| Phase | 설계 (리서치 반영) | 근거 |
|---|---|---|
| B1 impact | ★ Humanoid-Gym 역치형 `−w·min(max(ΣF_foot−600N,0),cap)` (w≈−2e-3~−0.01 스케일 확인) — mjlab soft_landing(첫접촉만) 대신/병행. 커리큘럼: gait 형성 후 가중치↑ | C11·C3 |
| B1b Siekmann | 이식 스펙 유지(+1.5, 60% stance). 가중치 비중 재확인: 원전은 주기블록이 전체 0.4로 최대 | C14·C15·C10 |
| B2 분배 | torque_limit(replay 산정) + ★**ALMI식 관절군 차등**: ankle 토크벌 5×·action rate 2× | C8 |
| B3 보폭 | clock 속도-스케줄(B1b 내장) — Q1 ①계열의 자연 확장 | C10·C7 |
| Toe(Stage4) | 지오메트리(toe 접촉 분리) → clock-게이트 CoP + capped push-off + heel-rise 운동학 항. impact cap 후에만 | 우리 계보+C5 |
| (옵션) | 에너지 경성제약(PPO-Lagrangian)·Duke passive-α — 여유 시 | C9·⚠Duke |

**우리 findings와의 모순 여부**: 모순 없음. (b)만 "위상동기 참조면 가능"으로 정밀화(백본 변경 불요). base 앵커(f)·impact-먼저(d)·간접 toe(c)는 **독립 실로봇 사례들로 교차확증**됨.

---

## B1 구현 기록 (2026-07-03)

본 리서치 F4/C11 공식을 mjlab에 구현: `mdp.contact_force_cap(sensor, threshold=600N≈1.2×BW, clip=400N)` — **역치 초과분만·클립·상시작동**(soft_landing의 첫접촉-한정과 달리 GRF 스파이크 전체를 bound; 기립 지지력 ~0.5BW/발은 미발동). weight **−0.005**(최대 벌점 ≈ tracking 최대와 동급, 정상보행선 0). 배선: `config/pygmalion/env_cfgs.py`(rough→flat 상속). 게이트: GRF P99 ↓≥20% vs A1b 동일iter ∧ air_time≥0.2s(무비행 셔플 게이밍 감시).
전제 확정: A1b 게인 동결(제어스택 accept — knee 열은 게인 불변으로 정책수요 판명, 본 B-phase가 표적).

## 방법 / 기록
- deep-research workflow: Scope→5각도 병렬 WebSearch→상위 15 소스 fetch→claim 추출→**3-vote 적대적 검증**→합성. 1차(`wddo420va`) 검증 2건 후 세션한도, 재개(`wp29o9s6k`)로 15건 확증. **합성 단계 + 7건 투표 미완**(한도 18:20 리셋 후 재개 예정 — resumeFromRunId `wf_85cf590d-b43`).
- 주요 소스: arXiv 2011.01387(Siekmann)·2404.05695(Humanoid-Gym)·2504.14305(ALMI)·2505.20619(G1 ref-free)·2309.14225(HumanMimic)·2602.06445(ECO)·2407.05148(REEM-C⚠)·2409.19795(Duke⚠)·SAGE 02783649241285161(Cassie 모방).
- 반박 3건(오독/과장 판정): SD-AMP 구조 주장(0-3)·"에너지가 heel-toe 억제"(1-2)·팔스윙 모멘텀 주장(0-3) — 사용 금지.
