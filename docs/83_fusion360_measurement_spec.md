# 83. Fusion360 측정 명세 — 질량표 검증·심 모델 재구축용 (2026-08-20)

**용도**: 이 문서를 Fusion360 MCP가 연결된 세션에 그대로 전달하면, 그 세션의 Claude가
순서대로 실행할 수 있는 측정 지시서다. 결과는 각 항목의 JSON 형식으로 받아 오면 된다.

★**진행 상황 (2026-08-20)**: **§0·§1 완료 · §2~§7 미착수.**
- §0: 앵커 3종 일치 → **리비전 동일 확정** (Ankle2Feet 나사 = 45+루즈 2 = 47)
- §1: 모터 7종 전부 단일 자리표시자 솔리드 + 범용 "Steel", bbox = 카탈로그 외형 →
  **(a) 질량 오류 확정, (b) 라벨 정상**. 단서: 밀도 수치 직접 조회 실패(정황 판단),
  override 여부 미확정, RS04-Hip_P bbox 161.88 mm는 브래킷 병합 의심(미확인 → §2에서).
- 결과 반영: [[82_final_design_mass_review]] §2·§3 (교정 총질량 44.51 kg).
- **Maido가 직접 답해야 하는 것**(CAD로 확인 불가): Waist_Pitch 실제 액추에이터(§1 추가질문),
  §6 질문 3개(배터리 · 명칭 PipRoll2Yaw/Wlbow2WaistYaw/Ankle_A(1) · 미러 계획).

**배경**: [[82_final_design_mass_review]]의 미결 6건과 [[81_rl_model_vs_cad_mass]]의
심 모델 재구축에 필요한 값들. 캠페인이 가진 CAD는 `Huphy1.0_FullBody.step`(2026-08-14
export)인데 사용자 질량표보다 **옛 리비전**(나사 141개 부재)이라, 현 Fusion 모델에서
직접 측정해야 한다.

**단위 규약**: 길이 mm · 질량 kg · 관성 kg·mm² · 좌표는 **문서 전역(어셈블리 루트) 좌표계**.
모든 좌표 출력에 "어느 좌표계인지"를 명기할 것.

---

## §0 검증 앵커 — 가장 먼저, 같은 리비전인지 확정

측정 전에 아래가 재현되는지 확인한다. 하나라도 어긋나면 **이후 측정값 전부에 리비전
주석을 달아야** 한다.

| 앵커 | 기대값 | 확인 방법 |
|---|---|---|
| 전체 질량(표 범위) | 31.021 kg | 표에 있는 14개 컴포넌트 합 |
| Knee2Ankle 알루미늄 본체 | 0.854 kg | 해당 바디만 선택 → Properties |
| 나사 개수 | CenterParts 69 · HipPitch2Roll 48 · PipRoll2Yaw 30 · HipYaw2Knee 72 · Knee2Ankle 64 · Ankle2Feet 47 | 브라우저 트리에서 ISO4762/ISO10642/JIS B1176 인스턴스 수 |

```json
{"anchor": {"total_kg": null, "knee2ankle_body_kg": null,
  "screw_counts": {"CenterParts": null, "...": null}, "revision_note": ""}}
```

---

## §1 ★최우선 — RS00 · RS02 정체 (1.004 / 1.432 kg의 출처)

표의 RS00 1.004 kg은 카탈로그 310 g의 3.2배(Φ57×51에 넣으면 평균밀도 7.71 g/cm³ = 통강철),
RS02 1.432 kg은 380~405 g의 3.5배다. **질량이 틀렸는지(a), 라벨이 틀렸는지(b)** 가려야 한다
— (a)면 로봇이 −5.9 kg, (b)면 하중 기준 무영향.

대상 5개 어커런스: `RS00 - Elbow_Yaw` · `RS00 - Waist_Pitch` · `RS00 - Neck_Pitch` ·
`RS02 - Shoulder_Yaw` · `RS02 - Neck_Yaw`

각각에 대해:
1. **Physical Material** 이름과 밀도 (기본 Steel인지, 지정돼 있는지)
2. **질량이 수동 오버라이드인지**(Properties에서 override 여부)
3. **바운딩 박스** (Φ와 축방향 길이 — 카탈로그 외형 RS00 Φ57×51, RS02 Φ78.5와 대조)
4. 바디 개수(단일 자리표시자 솔리드인지, 상세 모델인지)
5. 비교 기준으로 `RS04 - Hip_P`와 `RS03 - Ankle_A`도 같은 4개 항목 측정
   (이 둘은 카탈로그 +6~10 %라 "정상"의 기준선)

```json
{"motors": [{"occurrence": "RS00 - Waist_Pitch", "material": "", "density_g_cm3": null,
  "mass_kg": null, "mass_overridden": null, "bbox_mm": [null, null, null],
  "n_bodies": null}]}
```

추가 질문(측정 아님, 모델에서 판단): **Waist_Pitch 축에 실제로 달리는 액추에이터가
무엇인가?** 상체 19.4 kg의 정적 요구 29~57 N·m를 RS00(peak 14)은 못 낸다.

---

## §2 ★강체별 질량 속성 — 심 모델 재구축의 핵심 (질량 · COM · 관성텐서)

Fusion Properties는 선택 집합에 대해 질량·COM·관성텐서를 준다. 아래 **강체 정의대로
바디들을 묶어 선택**해서 측정할 것. (컴포넌트 단위가 아니라 강체 단위 — `Ankle2Feet`는
컴포넌트 하나가 강체 셋에 걸쳐 있다.)

| 강체 | 포함할 것 | 제외할 것 |
|---|---|---|
| pelvis | CenterParts 전체 + Waist_Yaw RS04 | Hip_R RS04 (다음 강체) |
| hip_pitch_link | HipPitch2Roll 전체 + Hip_R RS04 스테이터 | |
| hip_roll_link | PipRoll2Yaw 전체 + Hip_P RS04 | ※ Hip_P/Hip_R 라벨이 §4에서 뒤집히면 반영 |
| thigh | HipYaw2Knee 전체 + Hip_Y RS03 | |
| shin | Knee2Ankle 전체 + Knee RS04 + Ankle RS03×2 + **Ankle2Feet 중 정강이측**: 크랭크 2, 로드엔드 상부(JMC-JS06_Ankle-A/B와 그 볼·플랜지) | 로드, 발측 |
| rod ×2 (각각) | 푸시로드 본체 (COM z≈−698, 62 cm³짜리) | |
| foot | Ankle2Feet 중 발측: 발판 솔리드 4개(≈262 cm³) + 발목 크로스(COM z≈−800, ≈25 cm³) + JMC-JS06_FEET-A/B와 볼·플랜지 + 6900ZZ 2개 | |

각 강체마다:
```json
{"rigid_bodies": [{"name": "foot", "mass_kg": null, "com_mm": [null,null,null],
  "inertia_at_com_kg_mm2": {"Ixx": null, "Iyy": null, "Izz": null,
    "Ixy": null, "Iyz": null, "Ixz": null},
  "frame": "assembly_root", "included_bodies_note": ""}]}
```

⚠ 나사는 각자 붙는 강체에 포함시킬 것(호스트 바디와 함께 선택). 애매하면 "나사 포함 여부"를
노트에 남기면 된다 — 우리 쪽에서 보정 가능.

---

## §3 관절 축 좌표 — 6관절/다리

각 관절의 **축 방향 벡터 + 축 위의 한 점**(전역 좌표). Fusion 조인트가 정의돼 있으면
조인트 원점을 읽고, 없으면 해당 베어링/모터의 원통면 축을 읽는다.

hip_pitch · hip_roll · hip_yaw · knee · ankle_pitch · ankle_roll

특히:
- **knee 축 z 좌표** — 캠페인 STEP은 −310(힙피치 −370 아래). 심 모델은 −446.5라 77 mm
  차이가 났다. 현 모델 확정값 필요.
- **ankle pitch/roll 축** — 2-RSU라 두 축이 어디서 교차하는지(발목 크로스 중심).

```json
{"joints": [{"name": "knee", "axis_dir": [1,0,0], "point_on_axis_mm": [null,null,null],
  "frame": "assembly_root", "source": "joint|bearing_cylinder"}]}
```

---

## §4 라벨 검증 — Hip_P / Hip_R 축 방향

캠페인 STEP에서 `RS04 - Hip_P`의 원통축이 **y(전후)**, `RS04 - Hip_R`이 **x(좌우)** 로
검출됐다. 피치는 좌우축 회전이므로 **두 이름이 서로 바뀐 것으로 보인다.** 현 모델에서
두 모터의 회전축 방향을 확인하고, 바뀌었으면 어느 쪽이 맞는지 답할 것.

```json
{"hip_label_check": {"Hip_P_axis": [null,null,null], "Hip_R_axis": [null,null,null],
  "swapped": null}}
```

---

## §5 발자국 기하 (빠름)

- 발목 피치축의 전역 좌표(§3에서 나옴)
- 밑창 바닥면의 전후 방향 최소/최대 좌표, 바닥 z
- → 발끝 레버 / 뒤꿈치 레버 / 밑창-축 수직거리. 캠페인 STEP 값: 180 / 80 / 43 mm.

```json
{"footprint": {"sole_fore_aft_mm": [null, null], "sole_z_mm": null,
  "ankle_axis_mm": [null,null,null], "toe_lever": null, "heel_lever": null}}
```

---

## §6 상체 8행 상태 점검 (측정 반, 질문 반)

Neck · Torso · Shoulder-Pitch2Roll · Shoulder-Roll2Yaw · Shoulderyaw2Elbowpitch ·
Wlbow2WaistYaw · WaistYaw2Pitch · Waist2HandAdapt — 각각:
- 바디 수, 나사/베어링 존재 여부 (표에서 이 8행만 나사=0이라 자리표시자 의심)
- 알루미늄 바디의 material 지정 여부

그리고 질문 3개 (측정 아님):
1. **배터리** — 표에는 PSU(RSP-2000-48, 유선 전원)만 있다. 배터리 계획이 있으면 질량·위치.
2. **명칭** — `PipRoll2Yaw`(→HipRoll2Yaw?), `Wlbow2WaistYaw`의 "Waist"(→Wrist?),
   `Ankle_A (1)`(→Ankle_B?)
3. **미러** — 설계가 편측+중앙이 맞는지, 반대편은 미러 피처로 생성 예정인지.

---

## §7 ★재-export — FEA 재검증용

측정과 별개로, **현 리비전 전체를 STEP으로 재-export** 해서 전달해 줄 것
(`refs/Huphy_1.0_STEP/`에 날짜 붙여서). 캠페인 STEP에는 표에 있는 나사 141개(L1 47,
L2 64, L3 30개분)가 없고 알루미늄 차이가 링크별 +31~−11 %로 양방향이라, 6개 링크 FEA
지오메트리 전부 재확인이 필요하다. export 옵션: 솔리드 전부 포함, 어셈블리 구조 유지.

---

## 우선순위 요약

| 순위 | 항목 | 걸리는 것 |
|---|---|---|
| 1 | §1 RS00/RS02 정체 | 로봇 총질량(44.5~52 kg 밴드 확정), 페이로드 |
| 2 | §2 강체 질량·관성 | 심 모델 재구축 → 하중 재측정 전부 |
| 3 | §3 관절 축 | 〃 (기하) |
| 4 | §7 재-export | FEA 6링크 재검증 |
| 5 | §4·§5·§6 | 라벨·발자국·상체 상태 |

관련: [[81_rl_model_vs_cad_mass]] · [[82_final_design_mass_review]]
