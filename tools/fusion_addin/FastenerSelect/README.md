# FastenerSelect — Fusion 360 애드인

시뮬레이션에서 **나사 구멍을 하나하나 클릭하는 작업**을 없애는 선택 도우미.
구멍 하나만 찍으면 같은 치수 구멍을 전부 찾아주고, 그중 원하지 않는 것은 빼고,
임의 면은 더할 수 있다. 결과는 그대로 다음 커맨드(구속조건/하중)에 들어가거나
**Selection Set**으로 저장된다.

## 왜 "선택" 도구인가 (중요)

Fusion API에는 **시뮬레이션 스터디 객체가 없다** — `Design` 객체에 구속조건·하중·스터디
컬렉션이 존재하지 않는다([Design object 레퍼런스](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Design.htm)).
즉 애드인이 "볼트 구속조건"을 직접 생성할 방법은 없다.

대신 API로 **선택은 완전히 제어**할 수 있고([`UserInterface.activeSelections`](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/UserInterface.htm),
[`Selections.add`](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Selections_add.htm)),
Fusion 커맨드는 **미리 선택된 엔티티를 첫 선택 입력으로 흡수**한다. 그래서 흐름은:

> FastenerSelect로 면들을 선택 → 곧바로 *Structural Constraints* / *Loads* 실행 → 이미 채워져 있음

추가로 `Design.selectionSets`가 API에 존재하므로([SelectionSets](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/SelectionSets.htm))
**이름 붙은 Selection Set**으로 저장해 두고 나중에 브라우저에서 다시 불러 쓸 수 있다.

## 설치

폴더째 복사:

- Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\FastenerSelect`
- macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FastenerSelect`

Fusion에서 **Utilities → Add-Ins → Scripts and Add-Ins → Add-Ins 탭 → FastenerSelect → Run**
(“Run on Startup” 체크). 버튼은 Design의 Add-Ins 패널과 Simulation 워크스페이스 패널에
자동 등록되고, 등록에 실패하면 메시지로 알려준다(그 경우 Scripts and Add-Ins에서 직접 실행).

## 사용법

1. **Reference hole** — 기준 구멍 원통면 하나를 찍는다.
2. **Find matching** — 같은 지름 구멍을 전부 찾는다.
3. 표에서 **그룹 단위 체크 해제**, 또는 **Deselect** 입력으로 개별 면 제거.
4. **Extra faces**로 임의 면/바디를 추가.
5. **OK** → 선택 상태로 남거나 Selection Set으로 저장(드롭다운에서 선택).

### 옵션

| 옵션 | 의미 |
|---|---|
| Search scope | 전체(보이는 것) / 활성 컴포넌트 / 선택한 바디·컴포넌트 |
| Diameter tolerance | 기본 0.05 mm. 설계 규칙이 공칭+0.15로 정확하면 더 좁혀도 된다 |
| Same axis direction only | 같은 방향 구멍만(예: +Z 플랜지 볼트만) |
| Same component only | 다른 부품의 같은 치수 구멍 제외 |
| Within distance | 기준 구멍에서 반경 N mm 안쪽만 (0 = 제한 없음) |
| Full 360° cylinders only | 필렛·릴리프 같은 부분 원통 제외 |
| Include counterbore faces | 동축의 큰 구멍(머리 자리)도 함께 선택 |
| Include the flat seat face | 구멍에 접한 **평면(머리·와셔가 누르는 좌면)** 도 함께 선택 — 구속면으로 자주 쓰는 그 면 |

## 검증 상태 (솔직히)

- Python 문법·구조는 검사했지만, **실제 Fusion에서 실행 검증은 사용자 환경에서 해야 한다**
  (이 개발 환경에는 Fusion이 없다).
- 첫 실행에서 어긋날 가능성이 있는 세 곳:
  1. **Simulation 워크스페이스 패널 ID** — 버전에 따라 다르다. 실패해도 애드인은 살아 있고
     Design 쪽 버튼/Scripts and Add-Ins로 실행 가능. 실제 ID를 알려주면 `TARGET_PANELS`에 넣으면 된다.
  2. **Selection Set 생성** — 빌드에 따라 미지원일 수 있어 예외 처리해 두었다(선택 자체는 유지).
  3. **표 컬럼 비율/체크박스 렌더링** — `addTableCommandInput(..., '5:2:1')` 비율은 취향에 맞게 조정.
- 대형 어셈블리에서 전체 스캔은 면 수에 비례한다. 느리면 scope를 *Selected bodies* 로 좁히거나
  *Within distance* 를 쓰면 된다. 진행 다이얼로그에서 취소 가능.

## 이 프로젝트에서의 쓰임

Huphy 조립체 기준 검출 결과(별도 도구 `tools/fea/detect_bolts.py`): 관통공 = 공칭+0.15
(M4 4.15 / M5 5.15), 탭홀 = 탭드릴(M4 3.3 / M5 4.2), 카운터보어 깊이로 소켓헤드/저두 구분.
FastenerSelect의 기본 공차 0.05 mm는 이 규칙에 맞춰져 있어 M3 관통(3.15)과 M4 탭(3.3)이
섞이지 않는다.
