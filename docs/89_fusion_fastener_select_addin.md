# 89. FastenerSelect — Fusion 360 시뮬레이션용 나사 일괄선택 애드인 (2026-08-16)

코드: `tools/fusion_addin/FastenerSelect/` (README 포함) · 배경: 사용자 요청 — "해석 모드에서
나사 구속조건을 걸 때 나사를 하나하나 선택해야 해서 너무 불편, 동일치수 자동선택 +
일부 선택취소 + 임의영역 추가가 되는 애드온"

## §1 핵심 발견 — Fusion API에는 시뮬레이션 객체가 없다

설계 전에 API 지원 범위를 조사한 결과가 이 도구의 형태를 결정했다:

| 사실 | 근거 | 귀결 |
|---|---|---|
| `Design` 객체에 시뮬레이션 스터디·구속조건·하중 컬렉션이 **존재하지 않음** | [Design object 레퍼런스](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Design.htm) | 애드인이 "볼트 구속조건"을 **직접 생성할 수 없다** |
| 선택은 완전 제어 가능 (`UserInterface.activeSelections`, `Selections.add`) | [Selections.add](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Selections_add.htm) | Fusion 커맨드는 **미리 선택된 엔티티를 첫 선택입력으로 흡수** → 선택을 자동화하면 실질 문제가 풀림 |
| `Design.selectionSets`로 이름 붙은 선택집합 저장 가능 | [SelectionSets](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/SelectionSets.htm) | 같은 면 집합을 나중에 브라우저에서 재호출 |

**워크플로**: FastenerSelect로 면 선택 → 곧바로 *Structural Constraints* / *Loads* 실행 →
선택입력이 이미 채워져 있음. 또는 Selection Set으로 저장 후 재사용.

## §2 기능 (요청 3항목 + 시뮬레이션 실무 2항목)

1. **동일치수 자동선택**: 기준 구멍 원통면 1개 → 같은 지름 전부 탐색.
   필터: 지름공차(기본 0.05 mm), 같은 축방향만, 같은 컴포넌트만, 기준에서 N mm 이내,
   부분원통(필렛·릴리프) 제외(랩 비율 80 % 판정)
2. **일부 선택취소**: 결과를 지름 그룹별 체크박스 표로 표시 + 개별 면 Deselect 입력
3. **임의영역 추가**: Extra faces로 면/바디째 합집합
4. **카운터보어 면 포함** 옵션 (동축 큰 구멍 자동 탐지 — docs/77 §14 검출기와 같은 원리)
5. **평면 좌면 포함** 옵션 (구멍에 접한 평면 = 머리·와셔가 누르는 면, 구속면으로 상용)

기본 공차 0.05 mm는 이 프로젝트의 구멍 설계규칙(관통 = 공칭+0.15 / 탭 = 탭드릴)에 맞춰
M3 관통(3.15)과 M4 탭(3.3)이 섞이지 않는 값이다.

## §3 검증 상태 (솔직)

- Python 문법·구조 검사만 완료. **Fusion 실행 검증은 미완**(개발환경에 Fusion 없음).
- 방어해 둔 취약점: ①Simulation 워크스페이스 패널 ID(버전 의존 — 후보 5종 시도, 전부
  실패해도 Scripts and Add-Ins에서 실행 가능) ②Selection Set 미지원 빌드(예외처리, 선택은
  유지) ③표 컬럼 비율.
- 대형 어셈블리 전체 스캔은 면 수 비례 — scope 축소/Within distance로 완화, 진행 다이얼로그
  취소 가능.

## §4 논문 관점 메모

API가 막힌 지점(시뮬레이션 객체 부재)을 **사전 선택 흡수(pre-selection consumption)**라는
UI 계약으로 우회한 사례. 수백 개 동일 파스너를 가진 로봇 어셈블리에서 구속조건 셋업 시간을
O(나사 수)→O(1)로 줄이는 보조도구로, 설계-해석 루프의 병목이 "솔버"가 아니라 "셋업 UI"에
있음을 보여주는 소재.

관련: [[77_structural_fea_lightweighting]] §14(구멍 휴리스틱 볼트검출) · [[83_fusion360_measurement_spec]](Fusion MCP 측정)
