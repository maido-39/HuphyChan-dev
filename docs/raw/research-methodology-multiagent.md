# raw · multi-agent 연구 방법론 — 검증 원문 발췌

> 검증 원문층(읽기만). 출처 URL·발췌·수치. 합성: [[42_research_methodology]].
> 수집일 2026-06-22. 일부 arXiv id는 미래표기(2603/2604/2605 = 2026)로 보고됨 — ⚠ 원문 재확인 권장(아래 [확인필요] 표시).

---

## A. 구조(STRUCTURE) — FOR 근거

### A1. Anthropic, "How we built our multi-agent research system" (2025-06)
출처: https://www.anthropic.com/engineering/multi-agent-research-system
- 토폴로지: **orchestrator-worker**. Opus-4 lead가 Sonnet-4 subagent **3-5개를 병렬 spawn**.
- 단일 에이전트(Opus-4) 대비 **BrowseComp eval에서 +90.2%**. 이득은 특히 **breadth-first 쿼리**(서로 독립인 여러 방향을 동시에; 예 "S&P 500 IT 기업 전 이사회 멤버")에서 나옴 — 레버는 **병렬 분해 + subagent별 컨텍스트 격리**.
- 분산분해: **"token usage by itself explains 80% of the variance"** (성능 분산). tool-call 수 + 모델선택까지 합쳐 **~95%**. → 이득은 *더 많은 탐색/연산 + 컨텍스트 격리*에서 오지, 페르소나 수에서 오지 않음.
- 비용: 에이전트는 chat 대비 ~4× 토큰, multi-agent는 ~15×. **task 가치 높고 병렬화 가능할 때만** 정당.
- 실패/낭비: **공유 컨텍스트 필요하거나 에이전트 간 의존 강한 작업**(Anthropic이 coding을 명시), 좁은 fact-lookup(1 에이전트·3-10 calls면 충분).
- delegation 4필드(각 subagent 프롬프트에 필수): **objective / output format / guidance on tools·sources / clear task boundaries**. 나쁜 task description이 overlap·gap을 만듦.
- 검증: Anthropic의 검증은 **단일 LLM-as-judge 1콜**(0.0-1.0 score + pass/fail), "most consistent"로 평가.
- 프롬프트는 "frameworks for collaboration that define the division of labor"로 프레이밍(역할극/직급 costume 아님). tool-description 재작성이 task 시간 **~40% 단축**.
- effort 스케일 규칙: 단순 fact→1 agent·3-10 calls; comparison→2-4 subagents·각 10-15 calls; broad survey→10+ subagents 가능.

### A2. Self-Consistency Improves CoT (Wang et al., arXiv 2203.11171)
출처: https://arxiv.org/pdf/2203.11171
- 다양한 reasoning path 샘플링 후 다수결: **GSM8K +17.9%, SVAMP +11.0%, AQuA +12.2%, StrategyQA +6.4%**.

### A3. Least-to-most / decomposition
- SCAN에서 plain CoT 대비 **16% → 99.7%**, OOD 일반화 향상. (분해의 효과)

---

## B. 직급/페르소나 라벨(PERSONA) — AGAINST 근거

### B1. Zheng et al., "When 'A Helpful Assistant' Is Not Really Helpful" (EMNLP 2024 Findings, arXiv 2311.10054)
출처: https://arxiv.org/abs/2311.10054 · https://aclanthology.org/2024.findings-emnlp.888/
- 162 페르소나 × 2,410 factual 문항 × 9 모델(4 LLM family).
- 시스템 프롬프트에 페르소나 추가는 **no-persona 대비 정확도 향상 없음**. 신뢰성 있게 돕는 단일 페르소나 없음.
- 자동 role-selection은 **"no better than random selection"**. per-persona 효과 "largely random". 성별/타입/도메인이 결과를 예측불가하게 흔듦.
- best-per-question 페르소나는 *사후*엔 도움되나 *사전* 선택 불가 → actionable하지 않음.

### B2. PRISM, "Expert Personas Improve LLM Alignment but Damage Accuracy" (arXiv 2603.18507) [확인필요: id]
출처: https://arxiv.org/abs/2603.18507 · 수치 경유 https://www.searchenginejournal.com/research-you-are-an-expert-prompts-can-damage-factual-accuracy/570397/
- MMLU: baseline **71.6%** → minimal expert persona **68.0%** → longer persona **66.3%**.
- expert persona는 **alignment/safety/tone/format에 도움**(JailbreakBench +17.7%, writing +0.2..+0.65 MT-Bench)이나 **지식검색·math(-0.10)·coding(-0.65) 정확도는 저하**.
- 모델이 "sounding correct over actually being correct"를 우선하게 됨.

### B3. "Persona is a Double-edged Sword" (arXiv 2408.08631)
출처: https://arxiv.org/pdf/2408.08631
- role-play 프롬프트가 맞던 zero-shot 답을 틀리게 뒤집을 수 있음. 순효과는 일관성 없고 task/모델 의존.

---

## C. 위계 깊이(2-tier vs 3-tier) — 조정 오버헤드

### C1. Silo-Bench (arXiv 2603.01045) [확인필요: id]
출처: https://arxiv.org/pdf/2603.01045
- **Relative Coordination Cost**: 팀 크기 **k=2에서 이미 단일 에이전트 대비 15-49% 손실**, k=50에서 80-100%까지 누적.
- "coordination overhead, not task difficulty, drives the performance gap."
- 토폴로지 비교: **TREE(계층) 구조가 chain/star보다 최악**.

### C2. Benchmarking Multi-Agent Architectures (arXiv 2603.22651) [확인필요: id]
출처: https://arxiv.org/html/2603.22651v1
- supervisor/hierarchical 패턴은 **중간 스케일까지만 정확도 우위 유지, 이후 급격히 저하**.

### C3. Single-Agent vs Multi-Agent under equal tokens (arXiv 2604.02460) [확인필요: id]
출처: https://arxiv.org/pdf/2604.02460
- **token budget을 동일하게 맞추면** multi-hop reasoning에서 **single-agent가 이김**. → multi-agent 진짜 이득은 *병렬 breadth + 컨텍스트 격리*이지 reasoner 복수성이 아님.

---

## D. 검증(VERIFICATION) — 구조적 검증 YES, 무차별 debate NO

### D1. 구조적 verifier/critique
- VeriFY-style 검증 trace가 factual hallucination을 **9.7-53.3%** 절감(모델 family 전반). RAG + Reflexion critique이 사실상 표준 품질층.

### D2. Self-Reflection in LLM Agents (arXiv 2405.06682)
출처: https://arxiv.org/pdf/2405.06682
- self-critique 평균 **~+3.3%, 최대 +14%** — 단, **초기 정확도 낮고 / 난이도 높고 / 외부(oracle) 체크 존재**할 때만. 강한 모델·쉬운 문항에선 오히려 저하. Best-of-N이 동일 토큰 비용에서 종종 iterative self-refine보다 나음.

### D3. 무차별 debate는 cargo-cult
- "Should we be going MAD?" (Smit et al., PMLR v235): https://proceedings.mlr.press/v235/smit24a.html
- "The Cost of Consensus" (arXiv 2605.00914) [확인필요: id]: https://arxiv.org/html/2605.00914v1
  - default multi-agent debate는 self-consistency/CoT를 **"only rarely outperform"**, 훨씬 높은 비용 + problem-drift. **isolated self-correction이 더 나은 비용-정확도 trade-off.**
- 단, Du et al. "Multiagent Debate" (arXiv 2305.14325): https://arxiv.org/abs/2305.14325 — *여러 인스턴스가 제안·비판 라운드*는 factuality/reasoning 향상·hallucination 감소를 보고(다양한 각도 + 교차검증의 효과로 해석). → 핵심은 "debate club"이 아니라 *구조화된 교차검증*.

---

## 한 줄 요약(증거 방향)
- STRUCTURE(분해·병렬·격리·구조적검증·종합·effort스케일) = **강한 FOR 근거**.
- PERSONA 직급 라벨 자체 = **objective task에서 효과 없음~음(-)**.
- 3-tier 깊이 = breadth가 정말 1 lead 범위를 넘을 때만, 아니면 조정오버헤드 순손실.
