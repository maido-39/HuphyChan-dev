# reward_research — reward 변경 전 *원인 연구·분석* 노트 (HARD RULE, user 2026-06-22)

> **규칙**: 학습이 끝난 뒤 reward 항(weight/term)을 바꾸기 *전에*, **반드시** 아래 과정을 거쳐 이 폴더에 노트를 남긴다. 반응적 "그냥 weight 조정" 금지. **PreToolUse 훅(`require_reward_research.sh`)이 강제** — 90분 내 이 폴더의 노트가 없으면 reward 파일(flat_env_cfg/velocity_env_cfg/rewards.py) 수정이 차단된다.

## 순서 (무조건)
1. **직전 학습 결과 분석** — 지표(error_vel·낙상·reward항 기여) + **영상 audit**(클로즈업) + **§7 모터 활용**(RMS/p95/peak·포화) + 측정. *무엇이 문제인가*.
2. **이전 이력 활용** — `docs/experiments/`·`docs/log.md`·관련 docs 노트에서 *전에 뭘 시도했고 어떻게 됐나* (같은 실수 반복 금지).
3. **학술/자료조사** — 관련 논문·레퍼런스를 **면밀히** 조사(workflow/web). 하이퍼링크 + 검증 원문(`docs/raw/`).
4. **원인·문제 규명** — 위를 종합해 *근본 원인*이 무엇인지 결론.
5. **제안** — 그래서 어떤 reward를 *왜* 어떻게 바꾸는지(또는 reward 아닌 다른 해법인지).
6. 그 다음에만 reward 수정 → 학습.

## 파일명
`docs/reward_research/<YYYY-MM-DD_HH-MM>_<주제>.md` (예: `2026-06-22_03-10_toe_loading.md`)

## 템플릿
```markdown
# reward 연구 — <주제> (<날짜>)
> 트리거: <어느 run 결과>. 바꾸려는 reward: <무엇>.

## 1. 직전 결과 분석
- 지표: error_vel … / 낙상 … / 기여 큰 항 …
- 영상 audit: …  · §7 모터: RMS/p95/peak …  · 측정: …
- → 관측된 문제: …

## 2. 이전 이력
- [[experiments/<run>]] / docs/log: 전에 <무엇> 시도 → <결과>. 교훈: …

## 3. 학술/자료조사 (출처 하이퍼링크)
- <논문/레퍼런스> — <핵심>. [[raw/<slug>]]

## 4. 원인·문제 규명
- 근본 원인: …

## 5. 제안 (reward 변경 + 왜)
- <항> <기존>→<신규> 이유: …  (또는 reward 아닌 해법: …)
```
