# 링크 구조 판정 (현행) — 해석 리비전 `2026-08-17b`

`tools/fea/report.py`가 생성. 6061-T6 항복 276 MPa,
허용 276 (SF>1) / 184 (SF>1.5) / 138 MPa (SF>2).

설계 응력 = 하중 주입 절점과 구속 절점 근방을 **모두** 제외한 최대값.
초과 절점 수는 특이점(절점 몇 개)과 실제 과부하(영역)를 가른다.

| 링크 | 성격 | 관절 | 노드 | raw MPa | **설계 MPa** | **SF** | p99 MPa | SF>1 | SF>1.5 | SF>2 | SF>2 초과 | 최대점 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L1_ankle_foot | 설계 판정 | ankle_roll | 307071 | 41.2 | **19.4** | **14.25** | 6.3 | PASS | PASS | PASS | — | [-122.4, 181.4, -841.6] |
| L1b_foot_toeoff | 설계 판정 | ankle_roll | 258384 | 289.5 | **289.5** | **0.95** | 145.2 | **FAIL** | **FAIL** | **FAIL** | 3553개 (1.5442 %) | [-163.8, 85.3, -842.6] |
| L2_shin | 설계 판정 | ankle_pitch | 112769 | 60.4 | **60.4** | **4.57** | 9.2 | PASS | PASS | PASS | — | [-151.4, 158.5, -545.3] |
| L3_thigh | 설계 판정 | knee | 127984 | 52.7 | **52.7** | **5.24** | 13.8 | PASS | PASS | PASS | — | [-106.6, 111.6, -107.5] |
| L4_hip_yaw | 설계 판정 | hip_yaw | 218670 | 59.4 | **59.4** | **4.65** | 19.8 | PASS | PASS | PASS | — | [-172.0, 34.8, -26.4] |
| L5_hip_pitchroll | 설계 판정 | hip_roll | 161119 | 74.3 | **74.3** | **3.71** | 20.9 | PASS | PASS | PASS | — | [-73.3, 43.8, 48.1] |
| L6_pelvis | 설계 판정 | hip_pitch | 318937 | 82.8 | **82.8** | **3.33** | 15.2 | PASS | PASS | PASS | — | [-25.5, 130.3, 133.9] |
| L1d_foot_toeoff_fine | 대조 (메시 수렴) | ankle_roll | 340587 | 287.1 | **287.1** | **0.96** | 143.0 | **FAIL** | **FAIL** | **FAIL** | 4437개 (1.431 %) | [-83.6, 85.0, -842.4] |
| L2b_shin_cornerfine | 대조 (메시 수렴) | ankle_pitch | 113180 | 55.4 | **55.4** | **4.98** | 9.2 | PASS | PASS | PASS | — | [-151.4, 158.5, -554.7] |
| L2c_shin_nomotor | 대조 (모터 제외) | ankle_pitch | 113180 | 194.0 | **194.0** | **1.42** | 39.1 | PASS | **FAIL** | **FAIL** | 8개 (0.0073 %) | [-151.4, 158.5, -554.7] |
| L3c_thigh_nomotor | 대조 (모터 제외) | knee | 127984 | 185.8 | **185.8** | **1.49** | 37.5 | PASS | **FAIL** | **FAIL** | 2개 (0.0016 %) | [-98.3, 129.0, -248.1] |
| L5c_hip_nomotor | 대조 (모터 제외) | hip_roll | 176586 | 109.4 | **109.4** | **2.52** | 37.2 | PASS | PASS | PASS | — | [-63.2, 35.8, 115.5] |
| L6c_pelvis_nomotor | 대조 (모터 제외) | hip_pitch | 284036 | 342.6 | **342.6** | **0.81** | 13.1 | **FAIL** | **FAIL** | **FAIL** | 4개 (0.0016 %) | [24.2, 130.6, 134.1] |

## 모터 강체 브래킷 (동일 렌치, 액추에이터 유/무)

강체 하우징은 병렬 하중경로다. 유 = 응력 하한, 무 = 보수적 상한.

| 링크 | 모터 포함 | 모터 제외 | 비 |
|---|---|---|---|
| L2_shin | 60.4 MPa (SF 4.57) | 194.0 MPa (SF 1.42) | ×3.21 |
| L3_thigh | 52.7 MPa (SF 5.24) | 185.8 MPa (SF 1.49) | ×3.53 |
| L5_hip | 74.3 MPa (SF 3.71) | 109.4 MPa (SF 2.52) | ×1.47 |
| L6_pelvis | 82.8 MPa (SF 3.33) | 342.6 MPa (SF 0.81) | ×4.14 |

## 체결부 (측정 렌치 하 볼트 그룹)

| 체결면 | 볼트 | 인장/예압 | 분리여유 | 전단 (힘+비틀림) | 마찰여유 | 볼트전단 |
|---|---|---|---|---|---|---|
| L2_shin | 6×M5 | 1212/2386 N | 1.97 | 1610 N (161+1601) | **0.26** | 1.27 |
| L2_shin | 8×M4 | 16/1475 N | 95.36 | 284 N (121+257) | 1.8 | 4.45 |
| L4_hip_yaw | 6×M5 | 1399/2386 N | 1.71 | 445 N (120+429) | **0.78** | 4.59 |
| L5_hip_pitchroll | 10×M4 | 41/1475 N | 35.65 | 237 N (69+226) | 2.12 | 5.34 |
| L6_pelvis | 10×M4 | 14/1475 N | 107.28 | 239 N (77+226) | 2.14 | 5.29 |

## 형상 최적화 (제거 가능 / 보강 필요)

| 링크 | 총 체적 | SF>1.5 제거가능 | SF>2 제거가능 | SF>2 보강필요 |
|---|---|---|---|---|
| L1_ankle_foot | 262.01 cm³ | 83.9 % | 83.9 % | — |
| L1b_foot_toeoff | 261.98 cm³ | 90.4 % | 84.3 % | 0.3 cm³, 두께 ×1.32 |
| L2_shin | 323.05 cm³ | 71.5 % | 71.5 % | — |
| L3_thigh | 493.89 cm³ | 55.6 % | 55.6 % | — |
| L4_hip_yaw | 209.32 cm³ | 75.7 % | 75.7 % | — |
| L5_hip_pitchroll | 242.52 cm³ | 33.3 % | 33.3 % | — |
| L6_pelvis | 292.82 cm³ | 47.1 % | 47.1 % | — |
| L2b_shin_cornerfine | 323.06 cm³ | 93.9 % | 93.9 % | — |

## 케이스 설명

- **L1_ankle_foot** (액추에이터 자동) — 기본 케이스
- **L1b_foot_toeoff** (액추에이터 자동) — same foot as L1, loaded at the forefoot instead of the heel: the ankle axis sits at y=145, so the forefoot patch is 100-180 mm away against the heel's 0-80 mm and is the longer bending lever
- **L2_shin** (액추에이터 3개 강체) — 기본 케이스
- **L3_thigh** (액추에이터 2개 강체) — 기본 케이스
- **L4_hip_yaw** (액추에이터 없음) — 기본 케이스
- **L5_hip_pitchroll** (액추에이터 2개 강체) — 기본 케이스
- **L6_pelvis** (액추에이터 2개 강체) — 기본 케이스
- **L1d_foot_toeoff_fine** (액추에이터 자동) — mesh-convergence check on the only failing case: the forefoot bending band is meshed at 2.6 mm instead of ~10 mm. If 289.5 MPa holds, the verdict is real; if it climbs, the sole needs a finer study; if it drops, the coarse mesh over-read it.
- **L2b_shin_cornerfine** (액추에이터 3개 강체) — same shin as L2, with a 2 mm mesh at the four symmetric corners that carry its 311 MPa peak. If the peak climbs with refinement the corner is a geometric singularity (an unfilleted internal corner) and the verdict must come from the nominal field; if it converges, the corner is a real stress riser.
- **L2c_shin_nomotor** (액추에이터 없음) — same link and same wrench as L2_shin, with the actuator housings left out. A rigid housing bolted across the structure is a parallel load path, so the pair brackets the answer: with motors = lower bound on stress, without = conservative upper bound. L2 moved 311 -> 60 MPa when the load began entering through the rigid housing, which is exactly the effect this isolates.
- **L3c_thigh_nomotor** (액추에이터 없음) — same thigh and wrench as L3, actuator housings left out - the knee load enters through the RS04 housing, so this is the conservative half of the bracket.
- **L5c_hip_nomotor** (액추에이터 없음) — same link and same wrench as L5_hip_pitchroll, with the actuator housings left out. A rigid housing bolted across the structure is a parallel load path, so the pair brackets the answer: with motors = lower bound on stress, without = conservative upper bound. L2 moved 311 -> 60 MPa when the load began entering through the rigid housing, which is exactly the effect this isolates.
- **L6c_pelvis_nomotor** (액추에이터 없음) — same link and same wrench as L6_pelvis, with the actuator housings left out. A rigid housing bolted across the structure is a parallel load path, so the pair brackets the answer: with motors = lower bound on stress, without = conservative upper bound. L2 moved 311 -> 60 MPa when the load began entering through the rigid housing, which is exactly the effect this isolates.
