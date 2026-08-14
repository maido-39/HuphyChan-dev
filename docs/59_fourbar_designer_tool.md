# 59 · 4절 링크 무릎 설계기 — 기능 명세 & 최적화 방법론

> 2026-07-09. [tools/fourbar_designer.html](../tools/fourbar_designer.html) (단일 HTML, vanilla JS). 무릎 로터리+링키지 방향([[57_rotary_linkage_knee_precedents]])의 4절 링크 설계 도구. RS04 peak 초과분(무릎 peak 112~138%)을 링크 레버비로 커버하는 설계탐색용 — [[2026-07-03_final_design_point]].

## 1. 기능 명세 (요구 이력 순)

| 기능 | 구현 |
|---|---|
| 링크 4길이 입력 + 2D 드래그 시각화 + 실시간 기구학 | circle-circle IK, g=dθ_4/dθ_2 수치미분, 전달각 μ |
| 링크별 🔒잠금 / ◇범위 | lock=0/1/2, 범위는 최적화 박스제약 겸용 |
| 실측 하중수요 오버레이 | 무릎각 5° bin 통계곡선 + 산점(§2), 각도별 비선형 |
| 실측 액추에이터 TN | RS04/03/02/00 프리셋 (Motor_Spec 48V 실측, [[reference-robstride-motor-specs]]) |
| **P99/Peak 통계 선택** | bin별 (τ_p99,ω_p95) vs (τ_peak,ω_peak) 드롭다운 |
| **속도 수요곡선** | 속도플롯의 수요가 상수선이 아니라 **각도별 bin 곡선**; 판정에 bin별 ω마진 포함 |
| 크랭크0=무릎초기각 싱크 | kOff를 기하 종속변수로 유도(자유변수 아님) |
| **출력 사용범위** | 물리 가동범위(회색 호)와 별개의 안전/최적 범위(녹색 호+플롯 녹색밴드). **범위 제한 ON** → 드래그 클램프 + 수요 bin 필터 + 전달각 창 + 최적화 커버리지 제약 |
| 전달각 제약 | 사용범위(없으면 수요 span) 내 μ\in[40,145]^°, UI 뱃지/음영도 동일 기준 |
| 입력측 특이점 회피 | strict Grashof 마진(≥6mm) + 입력크랭크=최단링크 |
| localStorage 영속화 | 길이·잠금·범위·전 입력·사용범위·제한모드 |

## 2. 수요 데이터 출처 (재현)
`analysis/out/b3_demo.npz`(nom)·`worstcase_rough.npz`(worst), L+R 무릎 pooled, 5° bin(표본<20 bin은 낙상 과도로 제외):
```python
np.percentile(|tau|,99), |tau|.max(), np.percentile(|omega|,95), |omega|.max()  # bin별
```
nom peak가 p99 대비 최대 +44%(−42.5° bin: 71.7→103.2 N·m), $\omega_{peak}$ 최대 51 rad/s(p95 10~22) — **Peak 선택 시 수요가 실질적으로 커짐**. 종전 툴은 p99만 사용했음.

## 3. 최적화 = DE + Deb 규칙 (2026-07-09 교체, ★[[60_fourbar_optimizer_research]])
문제 구조: 연속 4변수(박스제약) + 이산 2변수(kSign·조립분기) + **정수 계단항** + 조립불가 구멍 = **비볼록·다봉**. 1차 개선(LHS 멀티스타트 경사상승, 검증 `verify_multistart.py`: 단일시작 경계고착 20716 → 내부점 20806)도 soft 합성점수의 **페널티 트레이드 병리**(제약 위반 해를 "최고점"으로 선택 — 실측 전달각 149.8°>145)는 못 고침 → 같은 날 **DE/rand/1/bin + Deb 실행가능성 규칙**으로 재교체:
- **HARD 제약 9종**(전회전·Grashof≥6·입력최단·스윙·전달각 40~145·범위커버·bin도달·ω마진≥0)과 **목적**(최악 τ마진 max)을 사전식 분리 — 페널티 가중치 없음.
- 4조합(kSign×조립) 전부 순차 DE, NP=40, F 디더, 정체 30세대 종료, best-feasible-ever, 좌표 정제, 시드 고정=재현.
- 우측 **HARD 체크패널**이 상시 ✓/✗+실측값 표시; feasible 없으면 "위반: ω마진 1.13, …" 형태로 원인 보고.

## 4. 잔여/주의
- worst 수요는 τ가 RS04 peak(120)로 클리핑된 bin이 많음 — 수요 자체가 이미 "모터가 낸 만큼"이라 과소평가 가능([[2026-07-03_final_design_point]] worst-case 캠페인 caveat와 동일).
- ★worst 데이터 포함 시 **ω마진 hard 제약은 물리적으로 불만족**(수요 ω p95 22 > RS04 무부하 19.9 rad/s; 토크증폭 레버는 ω를 더 줄임) — 툴이 infeasible로 정직 보고. 상세: [[60_fourbar_optimizer_research]] §4.
