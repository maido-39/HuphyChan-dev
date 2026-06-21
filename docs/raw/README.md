# raw/ — 검증 원문층 (불변)

> [!warning] 규칙 ([[SCHEMA]])
> 여기엔 **우리가 원문서 fetch·검증한 발췌/수치만** 둔다(출처 URL + 날짜 + verbatim). **읽기만·수정 금지.** wiki 페이지의 수치는 여기로 추적가능해야 한다(재근거화).
> 저작권 *원문 PDF/figure*는 두지 않는다(`assets/refs/` gitignore) — *우리가 작성한 발췌/수치*만 두므로 git 포함 OK.

## 목적
"추측" 차단. wiki 페이지가 "X = 60-70%"라 하면, raw/에 그 수치의 *원문 인용 + 출처*가 있어야 한다. 나중에 의심되면 raw로 재검증.

## 적재 방식 (ingest 시)
연구(WebFetch) → 검증된 핵심 발췌/수치 → `raw/<slug>.md`:
```
# <주제> (원문 검증)
> 출처: <title> (<url>) · fetched <date> · verified yes/no
- "<verbatim 인용/수치>" — <세부 출처(페이지/표)>
```

## 현재 raw
- [[raw/kuo-canon-numbers]] — Kuo/Donelan/Ruina dynamic-walking 검증 수치
- [[raw/robstride-datasheet]] — RobStride 액추에이터 스펙(공식 PDF)
- [[raw/knee-biomechanics]] — 무릎 ROM/과신전·gait·screw-home·로봇관례 검증
- [[raw/humanoid-hw-specs]] — 실제 휴머노이드 질량·세그먼트·PD 검증

(이후 연구는 ingest 워크플로우대로 여기에 추가.)
