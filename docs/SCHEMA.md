# SCHEMA — LLM Wiki 규약 (Karpathy-style)

> 이 docs/ 는 **에이전트가 유지하는 compounding 지식베이스**다(Karpathy LLM Wiki 패턴). 매번 raw를 재검색하지 말고, **영속 wiki 페이지**를 읽고/갱신해 지식을 *누적*한다. 새 에이전트(컨텍스트 압축 후 포함)는 **이 파일을 먼저 읽어** 규약을 안다.
> 원전: [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

## 층 (3-layer)
| 층 | 위치 | 무엇 | 규칙 |
|---|---|---|---|
| **raw** | `docs/raw/` | 불변 *검증 원문 발췌*(논문 인용·수치·표, 출처 URL+날짜) | 읽기만·수정 금지. wiki 수치는 여기로 추적가능해야 함. (저작권 *원문 PDF*는 X — 우리가 쓴 발췌/수치만, 그래서 git 포함) |
| **wiki** | `docs/*.md`, `docs/Paperreview/`, `docs/experiments/` | LLM이 합성한 개념/실험/리뷰 페이지 | `[[링크]]`로 상호참조. 주장은 raw/출처로 근거. **미검증은 "⚠ 미검증" 명시.** |
| **schema** | 이 파일 + `memory/` rule들 | 규약·운영 워크플로우·rule | schema=구조, memory rule=운영규칙(리포트·검토·디버깅 루프) |

## 카탈로그 / 로그
- **`docs/index.md`** — 전 wiki 페이지 카탈로그(주제·실험·논문·raw). 매 ingest마다 갱신. 임베딩 없이 검색.
- **`docs/log.md`** — append-only ingest 로그. 형식 `## [YYYY-MM-DD] <kind> | <제목>` (kind=research/experiment/decision/fix). unix 도구로 타임라인 조회.
- 보조 인덱스: `memory/MEMORY.md`(운영 메모리), `Paperreview/INDEX.md`, `experiments/INDEX.md`.

## 명명 규약
- **`NN_topic.md`** (00-99) — 주제 노트. (연구/설계 종합.)
- **`Paperreview/<slug>.md`** — **검증된** 논문 리뷰(원문 fetch·숙독·수치 검증·인용주의). INDEX 등재.
- **`experiments/<run>.md`** — 학습 리포트(make_run_report). `experiments/<run>_monitor.md` — 중간검토 누적.
- **`raw/<slug>.md`** — 검증 원문 발췌(출처·날짜·verbatim 수치).
- **`assets/`** — 자작 플롯/이미지(git). **`assets/refs/`** — 저작권 figure(gitignore).
- `[[링크]]` = 파일 basename(확장자 없이). 끊긴 링크 금지(lint로 점검).

## INGEST 워크플로우 (새 지식 추가 시)
1. **검증**: 원문 fetch(WebFetch)·숙독. 수치는 원문 확인. **추측 금지**(못 읽으면 미검증 표시).
2. **raw 적재**: 핵심 발췌/수치 → `docs/raw/<slug>.md`(출처 URL·날짜).
3. **wiki 합성**: 해당 주제 페이지(`NN_*.md`/`Paperreview/`) 작성/갱신. raw로 근거. 관련 페이지들도 갱신(보통 여러 페이지 건드림).
4. **상호참조**: `[[링크]]` 추가(양방향). **모순 flag**(기존 주장과 충돌 시 명시).
5. **index 갱신** + **log append**(`## [날짜] research | 제목`).
6. **lint**: `bash pygmalion_locomotion/scripts/lint_docs.sh` (끊긴 링크·orphan 점검).

## 유지보수 (linting)
주기적으로 `lint_docs.sh` — 점검: 끊긴 `[[링크]]`, orphan(inbound 없는 페이지), raw 없는 수치주장, 오래된(superseded) 주장. (예: 감사 wk0sj39aj가 끊긴 04_reward_reference 링크를 잡음 → 04_reward_experiments로 수정됨.)

## 역할
- **사람**: 출처 선정·분석 방향·질문. **LLM(에이전트)**: 전 유지·합성·bookkeeping(index/log/lint).

관련: [[index]] · [[log]] · [[raw/README]]
