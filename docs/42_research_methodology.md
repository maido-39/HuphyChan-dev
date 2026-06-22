# 42 · 연구 방법론 — multi-agent 구조 vs 직급 페르소나 (검증, research-methodology)

> [!question] 검증한 질문
> 우리 연구 워크플로(orchestrator가 병렬 finder subagent를 spawn → synthesis subagent가 노트 작성)에 **명시적 학술 위계**(senior post-doc orchestrator → 박사급이 sub-topic을 SET/FRAME → 석사급이 다양한 legwork)를 프롬프트하면 연구 성능이 오르나? **증거 기반으로**, 두 가지를 분리: (1) **구조/오케스트레이션 토폴로지**(분해·병렬·검증·종합) vs (2) **직급/페르소나 라벨 자체**(에이전트에게 "senior post-doc"라 말하면 objective task 품질이 오르나?).

> [!abstract] 한 줄 — 증거 방향이 정반대
> **구조는 YES(강한 근거), 직급 라벨 자체는 NO(objective task에서 효과 없음~음의 효과).** Anthropic orchestrator-worker가 단일 에이전트 대비 **BrowseComp +90.2%** — 그러나 그 이득의 **80%는 토큰 사용량만으로 설명**되고(tool-call+모델까지 ~95%), 레버는 *병렬 breadth + 컨텍스트 격리*이지 페르소나 수가 아님. 반대로 페르소나 직급 라벨은 162 페르소나×2,410 문항에서 no-persona를 못 이기고(role 자동선택 = random과 동급), expert persona는 MMLU **71.6%→68.0%→66.3%로 정확도를 깎음**. → **구조는 유지·강화, 직급 라벨은 버린다.** 직급은 *focusing device*로만 가볍게(예: synthesis에 "senior reviewer: 반박하라").
>
> 우리 현재 설계(orchestrator + 병렬 finder + synthesis)는 *이미* 근거-기반 이득을 거의 다 잡고 있다. 바꿀 것은 5가지(§5).

> 검증 원문층: [[raw/research-methodology-multiagent]]. 운영 규칙 연결: [[27_training_review_loop]](보수적 검토 루프) · `memory/feedback-research-recording-rule.md`(기록 규칙). ⚠ 일부 arXiv id는 보고서가 미래표기(2026)로 줌 — raw에 [확인필요] 표시.

---

## 1. 직답 — 직급 위계 프롬프트가 성능을 올리나?

| 분리 항목 | 판정 | 근거 강도 |
|---|---|---|
| **(1) 구조** (분해·병렬·컨텍스트격리·검증·종합·effort스케일) | ✅ **YES, 올린다** | **높음** (Anthropic +90.2%, self-consistency +6-18%pt, 분산의 80-95% 설명) |
| **(2) 직급 라벨 자체** ("senior post-doc/박사/석사") | ❌ **거의 효과 없음, objective엔 음(-)** | **높음**(부정방향) (162페르소나 = no-persona 못 이김; expert persona MMLU −3.6~−5.3%pt) |

- **구조**: Anthropic orchestrator-worker는 단일 Opus-4 대비 [BrowseComp +90.2%](https://www.anthropic.com/engineering/multi-agent-research-system). 핵심 인용: *"token usage by itself explains 80% of the variance"* (tool-call+모델 포함 ~95%). 이득은 **breadth-first 쿼리**(독립 방향 다수 동시 추적)에서 나오고, 메커니즘은 **병렬 분해 + subagent별 컨텍스트 격리**. → 위계가 *암시하는 분업·다양한 독립 탐색·상급 종합·연산 확대*가 진짜 값.
- **직급 라벨**: [Zheng et al. EMNLP 2024](https://arxiv.org/abs/2311.10054)(162 페르소나 × 2,410 문항 × 9 모델) — 페르소나 추가는 no-persona 대비 정확도 향상 **없음**, role 자동선택은 **"no better than random"**. [PRISM 2603.18507](https://arxiv.org/abs/2603.18507): MMLU **71.6% → 68.0%(minimal) → 66.3%(longer)** — expert persona가 정확도를 *깎음*(coding −0.65, math −0.10). 페르소나는 tone/format/safety(JailbreakBench +17.7%)엔 도움 — 그러나 **연구 합성엔 그게 필요 없다**.
- **종합 결론**: "post-doc/박사/석사 팀"의 값은 거의 전부 *구조*에 있다. 직급 라벨은 잘해야 중립, objective 검색/추론에선 순음(-). **verified.**

---

## 2. 무엇이 진짜 효과 (구조 — 채택·강화)

1. **좋은 분해 (decomposition)** — 각 finder에 self-contained spec: **objective / output format / tools·sources guidance / task boundaries** 4필드(Anthropic 필수). 나쁜 task description이 overlap·gap을 만든다. SCAN에서 분해는 16%→99.7%.
2. **다각도 독립 탐색 (diverse parallel angles)** — finder마다 *다른 제목*이 아니라 *다른 lens/sub-question/source-type*. 이 다양성 + 컨텍스트 격리가 +90.2%를 만든 메커니즘. self-consistency도 다양한 reasoning path에서 +6.4~17.9%pt.
3. **구조적 adversarial 검증 (verifier)** — synthesis 안/전에 **전용 verifier 패스**: LLM-as-judge(0.0-1.0 + pass/fail) + claim-vs-source 대조 + abstain. 검증 trace가 hallucination **9.7-53.3%** 절감. ([Self-Reflection 2405.06682](https://arxiv.org/pdf/2405.06682): 단, 초기정확도 낮음·난이도 높음·외부체크 존재 시에만 이득 — 연구는 출처가 외부체크라 잘 맞음.)
4. **종합 (synthesis as verifier, not stapler)** — finder 간 claim 교차대조, 불일치 flag, 별도 citation/grounding 패스. Anthropic도 citation을 분리 패스로.
5. **effort/token 스케일** — 분산의 80-95%가 토큰+tool-call. **쿼리 타입에 맞춰 노력 배분**: 단순 fact→1 agent·3-10 calls / comparison→2-4 subagent·각 10-15 calls / broad survey→10+ subagent. 에이전트 수가 아니라 *targeted 탐색량*에 예산.
6. **명확한 목표·도구** — orchestrator *직함*이 아니라 *프롬프트*를 최적화(분해법·콜예산·중단조건 명시). tool-description 재작성만으로 task 시간 −40%.

### 2-tier vs 3-tier — 언제?
- **기본은 2-tier** (lead → 병렬 finder → synthesis). Anthropic 프로덕션도 2-tier(재귀 sub-lead 없음).
- **3-tier**(sub-lead가 sub-topic을 frame)는 **질문이 1 lead가 탐색 각도를 다 열거 못 할 만큼 진짜 broad일 때만**. 그 대가는 조정 오버헤드: [Silo-Bench](https://arxiv.org/pdf/2603.01045) — **k=2에서 이미 15-49% 손실**, TREE 토폴로지가 chain/star보다 최악. 대부분의 단일 연구질문은 2-tier가 이김.
- 동일 토큰 예산에선 [single-agent가 multi-hop에서 이김](https://arxiv.org/pdf/2604.02460) — multi-agent의 진짜 이득은 *병렬 breadth + 격리*뿐임을 재확인.

---

## 3. 무엇이 cargo-cult (피한다)

- ⚠ **맨 직급 라벨** ("senior post-doc / 박사 / 석사"): objective 연구·QA 품질에 측정된 이득 없음, factual에선 *해롭다*(71.6→68.0→66.3). 직함은 fact 0개 추가 + "authoritative-sounding > correct" 편향. → 중립적·task-specific 지시로 대체.
- ⚠ **위계 깊이 그 자체** (필요 없는데 3+ tier): 조정비용이 지배(k=2에 15-49% 손실, tree 최악). 더 많은 tier ≠ 더 좋음.
- ⚠ **무차별 multi-agent debate / "society of minds" 투표**를 품질 부스터로: 동일/훨씬 높은 비용에 self-consistency를 [거의 못 이김](https://arxiv.org/html/2605.00914v1)(problem-drift). **debate club 대신 단일 구조적 verifier.**
- ⚠ **"에이전트 많을수록 추론 좋다" 가정**: 동일 토큰엔 single-agent가 multi-hop 우위. 레버는 breadth+격리+총연산이지 headcount 아님.
- ⚠ **공유 컨텍스트/강한 의존 작업에 fan-out** (예: coding) — Anthropic이 poor-fit으로 명시(~15× 토큰 낭비).
- ⚠ **장황한 페르소나 backstory** 로 추론 이득 기대 — 그 예산은 더 명확한 spec·다양한 각도·검증 패스에 쓰는 게 낫다.

---

## 4. ★ 채택할 워크플로 템플릿 (구체)

> 직급은 *focusing device*로만 가볍게. 라벨이 아니라 **기능적 역할 서술**("너는 분해·위임한다" / "너는 다양한 1차 출처를 찾아 verbatim 추출한다" / "너는 대조·인용·반박한다")로 프레이밍.

```
[ORCHESTRATOR]  (전략·분해 — 직함 X, 기능 서술)
  역할: 질문을 독립 sub-question으로 분해, effort 예산 배정, 중단조건 정의.
  쿼리 트리아지:
    · 단순 fact      → finder 1, tool-call 3-10, verify 생략 가능
    · 비교/2-4관점   → finder 2-4, 각 10-15 calls
    · broad survey   → finder 10+; (정말 broad면) sub-lead 1층 추가 = 3-tier
  각 finder 프롬프트에 4필드 필수: OBJECTIVE / OUTPUT FORMAT / TOOLS·SOURCES / BOUNDARIES + 깊이지정(콜·토큰).

      │  (병렬 fan-out — 서로 다른 lens, 겹치지 않게)
      ▼
[FINDER ×N]  (각자 다른 각도, 명확 목표 + 깊이지정)
  예 lens: 1차 논문 / 산업·제품 데이터시트 / 반대·실패 사례 / 정량 벤치마크 / 최신(SOTA)
  출력: 구조화(주장 + verbatim 인용 + 출처 URL+날짜 + self-confidence).
  ※ 제목이 아니라 lens가 달라야 함.

      ▼
[ADVERSARIAL VERIFY]  (검증 — "senior reviewer: 반박하라"는 여기서만 가볍게)
  · LLM-as-judge: claim별 0.0-1.0 + pass/fail
  · claim-vs-source 대조, 근거 없으면 abstain/flag
  · finder 간 불일치 + 소수의견을 *적극 반박* (debate club 아님, 단일 구조적 패스)

      ▼
[SYNTHESIS]  (종합 — stapler 아닌 verifier)
  · 교차대조 후 합성, 별도 citation/grounding 패스
  · 명시: 출처 하이퍼링크 / confidence / verified vs 추정 구분
  · wiki 규약: raw 적재 → NN_note 합성 → [[링크]] → index/log → lint ([[SCHEMA]])
```

---

## 5. 우리 현재 워크플로에서 *바꿀 점* (5개)

> 현 설계(orchestrator + 병렬 finder + synthesis)는 이미 근거-기반 이득을 거의 다 잡음. 델타만:

1. **직급 라벨 제거 → 기능 서술로 교체.** "senior post-doc/박사/석사" 프롬프트를 쓰고 있다면 빼고, "분해·위임 / 다양 출처 verbatim 추출 / 대조·인용·반박"으로. *(근거: 페르소나 = no-persona 못 이김, expert persona MMLU −3.6~5.3%pt)*
2. **finder 프롬프트에 4필드 강제** (objective/output-format/tools·sources/boundaries) + **깊이지정**(콜·토큰 예산). 현재 "각자 다른 검색 각도"는 좋음 — 거기에 spec 계약을 얹어 overlap·gap 제거. *(근거: Anthropic delegation 4필드)*
3. **전용 adversarial VERIFY 단계를 synthesis 앞에 신설.** LLM-as-judge(0.0-1.0+pass/fail) + claim-vs-source + abstain + 소수의견 반박. 지금 synthesis가 종합+검증을 겸하면 분리. *(근거: 검증 trace hallucination −9.7~53.3%; debate는 회피)*
4. **쿼리-타입 트리아지로 effort 스케일.** finder 수·콜·토큰을 질문 타입에 매핑(단순fact 1 / 비교 2-4 / survey 10+). 고정 개수 금지. *(근거: 분산의 80-95% = 토큰+tool-call)*
5. **2-tier 기본 유지, 3-tier는 예외.** 위계 깊이를 늘리지 말 것 — 정말 broad해 1 lead가 각도를 못 열거할 때만 sub-lead 1층. *(근거: k=2에 조정손실 15-49%, tree 토폴로지 최악)*

> [!success] 한 문장 처방
> **구조는 날카롭게(4필드 spec·다각도 독립 lens·전용 verify·effort 트리아지·2-tier 기본), 직급 라벨은 버리고(focusing device로만 가볍게), 예산은 에이전트 수가 아니라 targeted 탐색량에 쓴다.**

---

## 6. 출처 (하이퍼링크)

- [Anthropic — How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) *(verified — 구조 +90.2%, 분산 80-95%, delegation 4필드, LLM-as-judge)*
- [Zheng et al. — When "A Helpful Assistant" Is Not Really Helpful (EMNLP 2024 Findings, 2311.10054)](https://arxiv.org/abs/2311.10054) · [ACL](https://aclanthology.org/2024.findings-emnlp.888/) *(verified — 페르소나 = random)*
- [PRISM — Expert Personas Improve Alignment but Damage Accuracy (2603.18507)](https://arxiv.org/abs/2603.18507) *(⚠ arXiv id 미래표기 — MMLU 71.6→68.0→66.3 수치는 [SEJ 보도](https://www.searchenginejournal.com/research-you-are-an-expert-prompts-can-damage-factual-accuracy/570397/) 경유, 추정 신뢰도 중)*
- [Persona is a Double-edged Sword (2408.08631)](https://arxiv.org/pdf/2408.08631) *(verified)*
- [Self-Consistency Improves CoT (2203.11171)](https://arxiv.org/pdf/2203.11171) *(verified)*
- [Self-Reflection in LLM Agents (2405.06682)](https://arxiv.org/pdf/2405.06682) *(verified)*
- [Du et al. — Multiagent Debate (2305.14325)](https://arxiv.org/abs/2305.14325) *(verified)*
- [Should we be going MAD? (PMLR v235, Smit et al.)](https://proceedings.mlr.press/v235/smit24a.html) *(verified)*
- [The Cost of Consensus (2605.00914)](https://arxiv.org/html/2605.00914v1) *(⚠ id 미래표기 — 추정)*
- [Silo-Bench: coordination cost / topology (2603.01045)](https://arxiv.org/pdf/2603.01045) *(⚠ id 미래표기 — 추정)*
- [Benchmarking Multi-Agent Architectures (2603.22651)](https://arxiv.org/html/2603.22651v1) *(⚠ id 미래표기 — 추정)*
- [Single-Agent Outperforms Multi-Agent Under Equal Token Budgets (2604.02460)](https://arxiv.org/pdf/2604.02460) *(⚠ id 미래표기 — 추정)*

> [!note] verified vs 추정
> **verified**: Anthropic 블로그, Zheng EMNLP 2024(2311.10054), self-consistency(2203.11171), Du debate(2305.14325), Self-Reflection(2405.06682), Smit MAD(PMLR) — 정착된 출처.
> **추정/⚠ 미확인**: PRISM·Silo-Bench·Cost-of-Consensus·Benchmarking·Single-vs-Multi(2603/2604/2605.xxxxx) — arXiv id가 미래 연월 표기로 보고됨. 결론 *방향*(persona 라벨 무효~해, 위계 깊이 오버헤드, 동일토큰 single 우위, debate 비효율)은 verified 출처와 일치하나, **개별 수치는 원문 재확인 권장.**
