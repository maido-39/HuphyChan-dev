# Planner/coder/researcher multi-agent division of labour — raw research (2026-08-27)

Requested by: three-role split just mandated for this project (Fable 5 = planning/main loop, Opus 5 = coding/docs subagents, Sonnet 5 = research/simple-task subagents, working in parallel). This note is the "find similar use cases, refine" research behind that split. Sonnet 5 (this session) did the research; Fable 5 (planner) applies it. No code/agent-definition edits were made here.

Method: WebSearch (2024-2026 sources) + one direct WebFetch of Anthropic's own multi-agent engineering post. Six search passes covering: (1) Anthropic's production orchestrator-worker system, (2) Claude Code subagent practice, (3) aider architect/editor model-split benchmarks, (4) plan-then-execute vs interleaved empirics + context isolation, (5) failure-mode taxonomy (MAST) + strong/weak model-tier assignment, (6) git-worktree isolation, structured-vs-narrative subagent reports, and stale-context/re-planning failures.

---

## 1. Anthropic's own multi-agent research system (most directly relevant precedent)

Source: [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) (Anthropic Engineering blog).

**Architecture.** Orchestrator-worker: "a lead agent coordinates the process while delegating to specialized subagents that operate in parallel." The lead agent plans, spins up 3-5 subagents in parallel (not serially), each with its own context window, tools, and exploration trajectory, then synthesizes with a separate pass.

**Model tiering — matches our Fable5(plan)/Opus5(code)/Sonnet5(research) split.** Direct quote: "A multi-agent system with Claude Opus 4 as the lead agent and Claude Sonnet 4 subagents outperformed single-agent Claude Opus 4 by 90.2% on our internal research eval." The strong model plans/orchestrates; the cheaper model executes focused, bounded subtasks. This is the closest published analogue to our "Fable5 plans, Sonnet5 researches" arrangement, though note their subagents are same-family (Opus/Sonnet) not cross-vendor, and coding was not the subagent's job in this system (research was).

**Task-brief specificity is the single most load-bearing lever they found.** Direct quote: "each subagent needs an objective, an output format, guidance on the tools and sources to use, and clear task boundaries." Failure mode observed when this was skipped: given a vague brief like "research the semiconductor shortage," subagents "duplicated work" — one explored "the 2021 automotive chip crisis" while another investigated "current 2025 supply chains," with no division of labor, because nobody had partitioned the space. Quote: "Without detailed task descriptions, agents duplicate work, leave gaps, or fail to find necessary information."

**Parallelism was a large, measured win — but only for genuinely independent subtasks.** "These changes cut research time by up to 90% for complex queries" once subagents ran in parallel rather than sequentially; sequential execution had created "bottlenecks... the entire system can be blocked while waiting for a single subagent to finish searching." Cost tradeoff is real: the system uses roughly 15x the tokens of a single chat turn (reported elsewhere on the same system), so parallel fan-out is worth it for complex/high-value tasks, not trivial ones — they added explicit effort-scaling rules to the prompt (1 agent/3-10 tool calls for simple fact-finding vs 10+ subagents for complex research) because the model had no innate judgment about appropriate effort.

**Coordination / statefulness.** Long-running agents accumulate state across many tool calls; rather than restarting a failed agent from scratch (expensive, and loses work), they resume from checkpoint plus deterministic retry logic — "combine the adaptability of AI agents... with deterministic safeguards like retry logic and regular checkpoints."

**What to avoid, explicitly named:**
- Rigid rule-following over heuristics — "our prompting strategy focuses on instilling good heuristics rather than rigid rules."
- Letting the worker default to convenience/SEO-ranked sources over authoritative ones without being told to prefer authority.
- Sequential subagent execution (bottleneck).
- Short/vague task briefs (duplication + gaps, shown above).
- No effort-calibration (agents over-invest tokens in simple queries absent explicit scaling guidance).

**Evaluation practice worth borrowing:** they started with ~20 realistic queries, not a large eval suite, and used an LLM-judge rubric (factual accuracy, citation accuracy, completeness, source quality, tool efficiency) rather than trying to hand-verify everything — useful if we ever want to spot-check whether Sonnet5 research briefs are being followed.

---

## 2. Claude Code subagent practice (closest match to our actual harness)

Source: WebSearch aggregate over Anthropic's Claude Code best-practices doc, PubNub, hidekazu-konishi.com, agentkit.best, buildthisnow.com, response-awareness Substack.

Recurring, convergent claims across independent write-ups:
- "Give each subagent one clear goal, input, output, and handoff rule... a pile of overlapping agents is harder to manage than a few sharp ones."
- Orchestrator discipline: "The orchestrator has exactly one job: holding the entire multi-phase plan... the orchestrator must remain a pure coordinator" — i.e., the planner should not also try to do research or code inline; if it does, the separation degrades back into a single-agent system with extra ceremony.
- "Separate research and planning from implementation to avoid solving the wrong problem" — research/plan-mode exploration happens in a context walled off from the implementation context, specifically so exploratory noise doesn't pollute the diff-producing context.
- Subagent context isolation is framed as a token/attention-budget mechanism, not just an organizational one: "one important advantage of agents is that they have their own context window and can provide a summary after doing extensive research to the main agent" — the parent never sees the subagent's scratch exploration, only its distilled output.

This directly supports "results reported as numbers not narratives" — multiple independent sources converge on: subagent output should be a short structured summary (final answer, brief note on what was done, file paths touched with one-line deltas), not a transcript.

---

## 3. Aider architect/editor split — controlled empirical evidence that role-splitting beats a single strong model

Source: [Separating code reasoning and editing](https://aider.chat/2024/09/26/architect.html) (aider blog), [R1+Sonnet SOTA post](https://aider.chat/2025/01/24/r1-sonnet.html), GitHub aider-AI/aider architect post.

This is the most directly quantified "planner (strong reasoning) + executor (formats the diff)" result available:
- 2024: pairing a stronger reasoning model as "Architect" (describes the fix) with a separate "Editor" model (turns the description into an actual patch) beat both models running solo on aider's code-editing benchmark. Sonnet+Sonnet (architect/editor with itself) scored 80.5% vs Sonnet solo's 77.4% — i.e., **splitting the same model into two roles with two different system prompts/responsibilities was worth ~3 points by itself**, before even changing which model fills which role.
- o1-preview (architect) + DeepSeek or o1-mini (editor) hit 85% SOTA at the time; o1-preview + Sonnet got 82.7%.
- 2025 update: DeepSeek R1 as architect + Claude 3.5 Sonnet as editor set a new SOTA (64.0%) on the harder polyglot benchmark at ~14x lower cost than the prior o1-based SOTA — reinforcing that a cheap/fast executor paired with a strong planner is a cost-effective combination, not just a quality one.

Relevance to us: this is direct evidence for "reasoning/planning" and "produce the artifact" being different competencies worth splitting even when using the *same* underlying model, which argues for us keeping Fable5's plan and Opus5's code-diff as genuinely separate turns/prompts rather than one agent doing both in one pass.

---

## 4. Plan-then-execute vs interleaved, and context isolation — what the literature says empirically

Sources: emergentmind.com plan-then-execute topic page, arXiv 2601.13243 (single- vs multi-agent reasoning survey), arXiv 2502.01390 (user trust/team performance study), Anthropic multi-agent post (above).

- "Plan-then-execute is more legible and parallelizable; interleaved adapts to surprises. Most production agents use a hybrid — high-level plan upfront, step-level decisions interleaved." This matches what we're already doing structurally: Fable5 sets the plan/direction, but each worker (Sonnet5/Opus5) is expected to interleave its own tool-call decisions within its bounded task, not follow a rigid script.
- "Task-Decoupled Planning decomposes tasks into a DAG of sub-goals with scoped contexts, reducing token consumption by up to 82%" — scoped/isolated context per subtask is a large, measured token-efficiency win, not just a cleanliness preference.
- Context isolation's stated mechanism of benefit: "reduces interference from irrelevant history, improves modularity, and allows the sub-agent to operate with a specialized prompt and tool configuration tailored to the delegated task" — directly supports giving each Sonnet5/Opus5 worker a self-contained brief rather than a slice of the main transcript.

---

## 5. Failure-mode taxonomy (MAST) — what to guard against, with base rates

Source: MAST (Multi-Agent System Failure Taxonomy), Cemri et al., NeurIPS 2025 Datasets & Benchmarks track spotlight; summarized via [Augment Code guide](https://www.augmentcode.com/guides/why-multi-agent-llm-systems-fail-and-how-to-fix-them), [alphaXiv](https://www.alphaxiv.org/abs/2503.13657), and independent syntheses (futureagi, hakunamatatatech). Built from 1,600+ annotated execution traces across 7 popular multi-agent frameworks; 14 failure modes, 6 annotators, Cohen's Kappa 0.88 (strong inter-annotator agreement, i.e. the taxonomy is reproducible, not a subjective list).

Three root categories with measured prevalence:
- **Specification problems — 41.77%** of failures: role ambiguity, unclear task definitions, missing constraints, poor task decomposition, duplicate agent roles, missing termination conditions. This is the *largest* bucket, and it is squarely an upstream-briefing problem, not a model-capability problem — i.e., most multi-agent failures are prevented (or caused) by the quality of the brief the orchestrator writes, before any worker does anything.
- **Coordination failures — 36.94%**: communication breakdowns, state-sync issues, conflicting objectives between agents.
- **Verification gaps — 21.30%**: inadequate output checking, downstream stages not verifying upstream evidence/claims.

Separately, real-world benchmarking context: "Multi-agent LLM systems fail at rates between 41-86.7% in production," and across "seven popular multi-agent frameworks... performance gains from multi-agent coordination over single-agent baselines are frequently minimal," with "observation overhead with N agents monitoring U updates" scaling O(N×U) — i.e., coordination overhead can grow faster than the parallelism gain if agents are made to watch/report to each other rather than to one coordinator. This argues for a strict hub-and-spoke topology (workers report only to the planner, never peer-to-peer) rather than a mesh.

---

## 6. Model-tier assignment: strong-plans/cheap-executes is the empirically supported direction

Sources: arXiv 2505.20182 (strong-weak model collaboration for repo-level code gen), general LLM-routing literature (RouteLLM), and manager-worker architecture studies surfaced in search.

- "Using a stronger LLM for task planning significantly improves the utility-cost trade-off while preserving robustness... strong planners can compensate for weaker executors by generating better-structured subgoals."
- Cost asymmetry favors this direction: "Planning typically accounts for only about 20% of total token usage, which makes performance gains from stronger planners relatively inexpensive." Concretely, upgrading only the planner (GPT-4o-mini→o4-mini) while keeping a cheap executor raised task success 57%→64% for a small cost increase ($6.73→$7.99).
- Manager/worker architecture result: "comparable quality (62% vs 60%) while achieving a ~5x reduction in strong-model tokens, with ~90% of tokens shifted to the cheap model" — i.e. the quality loss from moving most of the work to a cheap executor is small if the planner stays strong and the task is well-decomposed.
- Caveat found in the same search: "small models tend to perform well when the task has a clear boundary, a compact input, and an answer that can be checked, but their reliability falls when the work requires them to preserve an ambiguous plan across a long chain of steps" — i.e. the cheap executor needs a *bounded, checkable* task, which again comes back to brief quality (section 5).

Net: the literature does **not** support the reverse (cheap model plans, strong model executes) as a generally good pattern — the asymmetry in gains specifically favors putting the expensive reasoning where the plan is made.

---

## 7. Resource-contention isolation: git worktrees as the general pattern for "single writer per resource"

Sources: [Augment Code git-worktrees guide](https://www.augmentcode.com/guides/git-worktrees-parallel-ai-agent-execution), MindStudio git-worktree posts, Upsun developer blog.

- "Git worktrees enable parallel AI agent execution by giving each agent its own isolated working directory and git index while sharing a single object store, preventing file-level conflicts, context contamination, and lock contention when multiple agents operate on the same repository."
- Key framing that generalizes past git specifically: "The core of running multiple agents without conflicts is not clever coordination between agents, but hard isolation at the infrastructure level so they don't need to coordinate at all." This is the same principle our GPU/Fusion-360-tunnel single-user constraints already rest on — for those two specific resources, the fix isn't a coordination protocol between Opus5/Sonnet5, it's making them structurally unable to touch the resource at the same time (a lock/queue/reservation), because coordination protocols are exactly the category (36.94% of MAST failures) that breaks down under LLM agents.
- Named limitation, worth remembering: "git worktree only provides low-level workspace isolation. It does not solve task decomposition, dependency tracking, semantic conflicts, or merge selection" — i.e. isolating the resource prevents two agents from clobbering the same file simultaneously, but does not prevent two agents from doing logically redundant or conflicting work on two different files; that still requires the planner to partition the task space up front (ties back to section 5's "specification" failure bucket being the largest one).

---

## 8. Structured/numeric worker reports vs narrative transcripts

Sources: AI SDK subagents docs (ai-sdk.dev), MindStudio sub-agent guide, arXiv 2510.26585 ("Stop Wasting Your Tokens").

- "Sub-agents should return structured, concise summaries — not raw file content," with "structured outputs reducing the data returned to the main agent by 90-98% compared to raw web content."
- Recommended shape, directly reusable as our worker report template: "the final answer/deliverable, a short narrative of what the sub-agent did (not the raw transcript), and file paths touched with what changed (one line each)."
- "Token-constrained output (1,000-2,000 tokens) forces sub-agents to prioritize and filter, which is what you want" — i.e. a hard length cap on worker reports is itself a quality mechanism, not just a cost-saving one; it forces the worker to commit to numbers/conclusions instead of hedging with narrative.

This directly backs the requirement in our setup that "results [be] reported as numbers not narratives."

---

## 9. Stale context / re-planning loops — the failure mode most likely to hit an always-on parallel setup

Sources: Galileo "Why Multi-Agent Systems Fail," Redis engineering blog, arXiv 2606.22953 ("Plans Don't Persist"), Tacnode blog.

- "When AI agents stall, re-plan, and loop, it's usually caused by stale context. Agents operate in observe-decide-act loops; when the second observation returns outdated state, the agent detects a mismatch and re-plans, burning tokens." In a multi-agent setting specifically: "Agent B can operate on a stale snapshot of reality... when multiple agents read shared state at different times, they can act on information already superseded by another agent's concurrent actions."
- "Plans are written early, used for many steps, and [are the] first to be evicted [from context]... standard LLM agents do not carry plans forward as persistent state, and instead depend on the plan remaining in context." This is a direct argument for the planner (Fable5) re-stating the current plan/ground-rules explicitly in every worker brief rather than assuming a worker "remembers" a plan from earlier in a shared thread — each Sonnet5/Opus5 subagent spawn is a fresh context, so the brief has to be self-contained by construction, which the harness's own Agent-tool guidance already states ("a fresh agent has no memory of prior runs, so the prompt must be self-contained").
- Named anti-pattern to avoid: workers "re-deciding" the plan — i.e. a worker that, mid-task, second-guesses the higher-level strategy it was handed rather than flagging the mismatch back to the planner and stopping. The literature frames this as workers needing clear task *boundaries* (section 1/5) specifically so there's no ambiguity about what falls inside "just execute" vs "escalate."

---

## Adopt / avoid list for our Fable5(plan) / Opus5(code) / Sonnet5(research) split

1. **ADOPT — strong model plans, cheaper/specialized model executes.** Anthropic's own system (Opus lead + Sonnet subagents, +90.2% vs solo Opus) and the strong-weak collaboration literature (57%→64% task success from upgrading only the planner, at ~20% of total token cost) both support keeping Fable5 as the sole planner and never having Sonnet5/Opus5 re-derive the plan. *Source: Anthropic multi-agent research system post; arXiv 2505.20182.*

2. **ADOPT — write self-contained, bounded briefs for every worker spawn (objective, output format, tool/file guidance, explicit boundary of scope).** This is the single highest-leverage fix in Anthropic's own postmortem (vague brief → two subagents duplicated the same investigation) and matches MAST's finding that specification problems are the largest failure category (41.77%). *Source: Anthropic multi-agent post; MAST/Cemri et al.*

3. **ADOPT — hub-and-spoke reporting only; no peer-to-peer coordination between Opus5 and Sonnet5 workers.** Coordination failures are the second-largest MAST category (36.94%), and observation overhead among peers scales O(N×U). Only the planner should read worker reports; workers should not read each other's in-flight state. *Source: MAST; multi-agent framework benchmarking summary.*

4. **ADOPT — hard resource isolation over coordination protocols for single-user resources (GPU, Fusion 360 tunnel).** Treat these like git-worktree isolation: a reservation/lock that makes simultaneous use structurally impossible, rather than a "please don't both use it" convention — conventions are exactly the coordination-failure category that breaks down. *Source: git-worktree parallel-agent guides.*

5. **ADOPT — worker reports are short, structured, and numeric: final result, one-paragraph note on what was done, file paths + one-line deltas — not a transcript.** Backed both by explicit token-savings data (90-98% reduction vs raw content) and by the Claude Code subagent convention of a distilled summary only. Cap report length to force prioritization. *Source: AI SDK subagents docs; arXiv 2510.26585; Claude Code best-practice write-ups.*

6. **ADOPT — give each worker its own isolated context window per task, never a slice of the main transcript.** Reduces token cost (up to 82% in DAG-scoped-context studies), removes irrelevant-history interference, and lets each worker use a specialized prompt/toolset. Also means every brief must restate current ground rules and plan state explicitly — workers cannot rely on "remembering" anything from a shared thread. *Source: task-decoupled planning literature; "Plans Don't Persist" (arXiv 2606.22953); Agent-tool's own guidance that a fresh agent has no memory of prior runs.*

7. **ADOPT — parallel fan-out for genuinely independent subtasks, sequential/single-agent for anything with a shared dependency or shared file.** Anthropic measured up to 90% time reduction from parallelizing independent research threads, but this only works when the planner has actually partitioned the task space so subtasks don't overlap; partition quality is the prerequisite, not the parallelism itself. *Source: Anthropic multi-agent post.*

8. **ADOPT — same-model role-splitting still helps even with no model-tier change.** Aider found Sonnet-as-architect + Sonnet-as-editor (80.5%) beat Sonnet solo (77.4%) — i.e., separating "decide what to do" from "produce the artifact" is worth doing even between two calls to the same model, so Fable5 should still write an explicit plan/brief turn rather than letting a worker infer intent from a one-line instruction. *Source: aider architect-mode blog post.*

9. **AVOID — letting a worker re-decide or silently deviate from the plan it was handed.** If a worker's findings contradict the plan's premise, the correct behavior is to report the mismatch back to the planner and stop, not to unilaterally re-plan — re-planning inside a worker is invisible to the orchestrator and is a named driver of stale-context loops. *Source: Galileo/Redis "why multi-agent systems fail" write-ups; "Plans Don't Persist."*

10. **AVOID — vague or short task briefs, and briefs that don't state explicit task boundaries.** This is the direct cause of the semiconductor-shortage duplication failure in Anthropic's own system and the largest MAST failure category by far. A brief without an explicit "boundary" (what NOT to touch/decide) is the primary predictor of duplicated work. *Source: Anthropic multi-agent post; MAST.*

11. **AVOID — no effort/scope calibration.** Anthropic explicitly had to add prompt rules scaling subagent count/tool-call budget to query complexity, because the model has no innate sense of "this is a quick lookup" vs "this needs deep research" — worth mirroring in how Fable5 decides whether a question needs one Sonnet5 lookup or a multi-agent research fan-out (as this very task was). *Source: Anthropic multi-agent post.*

12. **AVOID — mesh-style status-checking between agents ("did the other worker finish yet") instead of the planner polling/gating.** This reintroduces the O(N×U) observation overhead and coordination-failure surface that a hub-and-spoke topology avoids; the planner should be the only one that waits on or synthesizes across workers. *Source: MAST; multi-agent framework benchmarking summary (Augment Code guide).*

---

## Sources (deduplicated)

- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) — Anthropic Engineering
- [Best practices for Claude Code](https://www.anthropic.com/engineering/claude-code-best-practices) — Anthropic
- [Best practices for Claude Code subagents](https://www.pubnub.com/blog/best-practices-for-claude-code-sub-agents/) — PubNub
- [Claude Code Subagents and Multi-Agent Orchestration Guide](https://hidekazu-konishi.com/entry/claude_code_subagents_and_orchestration_guide.html)
- [Claude Code Subagents: Common Mistakes & Best Practices](https://agentkit.best/blog/vc-04-subagents-from-basic-to-deep-dive-i-misunderstood)
- [Sub-Agents in Claude Code (Response Awareness Methodology)](https://responseawareness.substack.com/p/sub-agents-in-claude-code-the-subagent)
- [Separating code reasoning and editing](https://aider.chat/2024/09/26/architect.html) — aider blog
- [R1+Sonnet set SOTA on aider's polyglot benchmark](https://aider.chat/2025/01/24/r1-sonnet.html) — aider blog
- [Why do Multi Agent LLM Systems Fail? The Scaling Myth Exposed](https://www.hakunamatatatech.com/our-resources/blog/why-do-multi-agent-llm-systems-fail)
- [Multi-Agent AI Systems: Why They Fail and How to Fix Coordination Issues](https://www.augmentcode.com/guides/why-multi-agent-llm-systems-fail-and-how-to-fix-them) — Augment Code
- [Why Do Multi-Agent LLM Systems Fail?](https://www.alphaxiv.org/abs/2503.13657) — alphaXiv (MAST / Cemri et al.)
- [Why do multi agent LLM systems fail (and how to fix)- 2026 Guide](https://futureagi.substack.com/p/why-do-multi-agent-llm-systems-fail)
- [Why Multi-Agent LLM Systems Fail & How to Fix Them](https://redis.io/blog/why-multi-agent-llm-systems-fail/) — Redis
- [Are Your Multi-Agent Systems Failing for These 7 Reasons?](https://galileo.ai/blog/why-multi-agent-systems-fail) — Galileo
- [Plans Don't Persist: Why Context Management Is Load Bearing for LLM Agents](https://arxiv.org/html/2606.22953) — arXiv 2606.22953
- [An Empirical Study on Strong-Weak Model Collaboration for Repo-level Code Generation](https://arxiv.org/pdf/2505.20182) — arXiv 2505.20182
- [OpenAI Swarm: Lightweight Multi-Agent Orchestration Guide](https://www.morphllm.com/openai-swarm)
- [openai/swarm](https://github.com/openai/swarm) — GitHub
- [Handoffs — AutoGen](https://microsoft.github.io/autogen/dev//user-guide/core-user-guide/design-patterns/handoffs.html)
- [CrewAI vs LangGraph vs AutoGen: Which AI Agent Framework in 2026?](https://www.groovyweb.co/blog/crewai-vs-langgraph-vs-autogen-framework-comparison-2026)
- [CrewAI vs LangGraph vs AutoGen: Choosing the Right Multi-Agent AI Framework](https://www.datacamp.com/tutorial/crewai-vs-langgraph-vs-autogen) — DataCamp
- [How to Use Git Worktrees for Parallel AI Agent Execution](https://www.augmentcode.com/guides/git-worktrees-parallel-ai-agent-execution) — Augment Code
- [Git worktrees for parallel AI coding agents](https://developer.upsun.com/posts/ai/git-worktrees-for-parallel-ai-coding-agents) — Upsun
- [Git Worktrees for AI Coding: How to Run Multiple Agents Without Conflicts](https://www.mindstudio.ai/blog/git-worktrees-parallel-ai-coding-agents) — MindStudio
- [Agents: Subagents](https://ai-sdk.dev/docs/agents/subagents) — Vercel AI SDK docs
- [How to Use Sub-Agents for Codebase Analysis Without Hitting Rate Limits](https://www.mindstudio.ai/blog/how-to-use-sub-agents-for-codebase-analysis) — MindStudio
- [Stop Wasting Your Tokens: Towards Efficient Runtime Multi-Agent Systems](https://arxiv.org/pdf/2510.26585) — arXiv 2510.26585
- [Context Drift in AI Agents: Causes and How to Prevent It](https://tacnode.io/post/your-ai-agents-are-spinning-their-wheels) — Tacnode
- [Plan-then-Execute LLM Agents](https://www.emergentmind.com/topics/plan-then-execute-llm-agents) — EmergentMind
