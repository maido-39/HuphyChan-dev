# 링크 구조 판정 (현행) — 해석 리비전 `2026-08-17i`

`tools/fea/report.py`가 생성. 6061-T6 항복 276 MPa,
허용 276 (SF>1) / 184 (SF>1.5) / 138 MPa (SF>2).

> 276 MPa는 6061-T6의 **typical** 항복이다. ASTM B221 **최소보증치는 240 MPa**이므로 
> 구매 소재 보증 기준으로는 모든 SF가 **15 % 낮다**. 두 값을 병기한다.

설계 응력 = 하중 주입 절점과 구속 절점 근방을 **모두** 제외한 최대값.
초과 절점 수는 특이점(절점 몇 개)과 실제 과부하(영역)를 가른다.

| 링크 | 성격 | 관절 | 노드 | raw MPa | **설계 MPa** | **SF (276)** | SF (240 최소보증) | p99 MPa | SF>1 | SF>1.5 | SF>2 | SF>2 초과 | 최대점 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L1_ankle_foot | 설계 판정 | ankle_roll | 307071 | 16.3 | **6.9** | **40.04** | 34.82 | 3.3 | PASS | PASS | PASS | — | [-78.2, 186.9, -823.0] |
| L1b_foot_toeoff | 설계 판정 | ankle_roll | 258384 | 196.8 | **196.8** | **1.40** | 1.22 | 93.0 | PASS | **FAIL** | **FAIL** | 193개 (0.0839 %) | [-137.8, 121.4, -843.0] |
| L2_shin | 설계 판정 | ankle_pitch | 112769 | 135.7 | **135.7** | **2.03** | 1.77 | 36.4 | PASS | PASS | PASS | — | [-151.4, 95.3, -391.2] |
| L3_thigh | 설계 판정 | knee | 127984 | 109.7 | **109.7** | **2.52** | 2.19 | 33.9 | PASS | PASS | PASS | — | [-97.5, 14.7, -116.6] |
| L4_hip_yaw | 설계 판정 | hip_yaw | 218670 | 130.9 | **130.9** | **2.11** | 1.83 | 34.8 | PASS | PASS | PASS | — | [-172.7, 104.9, -26.0] |
| L5_hip_pitchroll | 설계 판정 | hip_roll | 161119 | 348.0 | **348.0** | **0.79** | 0.69 | 106.1 | **FAIL** | **FAIL** | **FAIL** | 275개 (0.2035 %) | [-73.3, 43.8, 48.1] |
| L6_pelvis | 설계 판정 | hip_pitch | 318937 | 426.7 | **426.7** | **0.65** | 0.56 | 45.0 | **FAIL** | **FAIL** | **FAIL** | 21개 (0.0076 %) | [-0.1, 132.5, 60.0] |
| L1d_foot_toeoff_fine | 대조 (메시 수렴) | ankle_roll | 340587 | 241.7 | **241.7** | **1.14** | 0.99 | 91.4 | PASS | **FAIL** | **FAIL** | 229개 (0.0739 %) | [-103.7, 118.0, -834.0] |
| L2b_shin_cornerfine | 대조 (메시 수렴) | ankle_pitch | 113180 | 143.6 | **143.6** | **1.92** | 1.67 | 36.5 | PASS | PASS | **FAIL** | 1개 (0.0009 %) | [-104.0, 187.1, -548.5] |
| L2c_shin_nomotor | 대조 (모터 제외) | ankle_pitch | 113180 | 194.0 | **194.0** | **1.42** | 1.24 | 39.1 | PASS | **FAIL** | **FAIL** | 8개 (0.0073 %) | [-151.4, 158.5, -554.7] |
| L3c_thigh_nomotor | 대조 (모터 제외) | knee | 127984 | 607.0 | **607.0** | **0.45** | 0.40 | 90.7 | **FAIL** | **FAIL** | **FAIL** | 144개 (0.1182 %) | [-98.3, 129.0, -248.1] |
| L5c_hip_nomotor | 대조 (모터 제외) | hip_roll | 176586 | 308.8 | **301.7** | **0.91** | 0.80 | 133.8 | **FAIL** | **FAIL** | **FAIL** | 819개 (0.5836 %) | [-114.6, 104.2, 25.5] |
| L6c_pelvis_nomotor | 대조 (모터 제외) | hip_pitch | 284036 | 522.4 | **522.4** | **0.53** | 0.46 | 31.7 | **FAIL** | **FAIL** | **FAIL** | 18개 (0.0071 %) | [24.2, 130.6, 134.1] |

## 모터 강체 브래킷 (동일 렌치, 액추에이터 유/무)

강체 하우징은 병렬 하중경로다. 유 = 응력 하한, 무 = 보수적 상한.

| 링크 | 모터 포함 | 모터 제외 | 비 |
|---|---|---|---|
| L2_shin | 135.7 MPa (SF 2.03) | 194.0 MPa (SF 1.42) | ×1.43 |
| L3_thigh | 109.7 MPa (SF 2.52) | 607.0 MPa (SF 0.45) | ×5.53 |
| L5_hip | 348.0 MPa (SF 0.79) | 301.7 MPa (SF 0.91) | ×0.87 |
| L6_pelvis | 426.7 MPa (SF 0.65) | 522.4 MPa (SF 0.53) | ×1.22 |

## 티어 통합 (설계 P99 · 과부하 peak · 피로 · 조립)

| 링크 | 설계 SF | peak SF | peak 항복초과 | 피로 SF@P99 | 피로 SF@RMS | 조립 판정 |
|---|---|---|---|---|---|---|
| L1_ankle_foot | **40.04** | — | — | 22.72 | 55.29 | HOLDS |
| L1b_foot_toeoff | **1.40** | 0.44 | 4501 | 0.8 | 1.94 | FAILS |
| L2_shin | **2.03** | — | — | 1.2 | 2.98 | FAILS |
| L3_thigh | **2.52** | — | — | 1.43 | 3.39 | FAILS |
| L4_hip_yaw | **2.11** | — | — | 1.2 | 3.09 | HOLDS |
| L5_hip_pitchroll | **0.79** | — | — | 0.45 | 1.11 | FAILS |
| L6_pelvis | **0.65** | — | — | 0.37 | 0.84 | FAILS |

> peak은 정적 사이징 기준이 아니라 **소성 미발생 확인**용이다(docs/62 §3c–4). 
> 항복 초과 절점이 수천이면 국부가 아니라 형상 조치 대상이다.


## 체결부 (측정 렌치 하 볼트 그룹)

| 체결면 | 볼트 | 인장/예압 | 분리여유 | 전단 (힘+비틀림) | 마찰여유 | 볼트전단 |
|---|---|---|---|---|---|---|
| L2_shin | 6×M5 | 1212/2386 N | 1.97 | 1702 N (161+1694) | **0.24** | 1.2 |
| L2_shin | 8×M4 | 16/1475 N | 95.36 | 323 N (121+300) | 1.58 | 3.91 |
| L3_thigh | 6×M4 | 2308/1475 N | 0.64 | 1298 N (57+1297) | **0.0** | 0.97 |
| L4_hip_yaw | 6×M5 | 1399/2386 N | 1.71 | 334 N (120+312) | 1.03 | 6.12 |
| L5_hip_pitchroll | 6×M5 | 974/2386 N | 2.45 | 944 N (132+934) | **0.52** | 2.17 |
| L5_hip_pitchroll | 10×M4 | 41/1475 N | 35.65 | 190 N (69+177) | 2.64 | 6.64 |
| L6_pelvis | 10×M4 | 173/1475 N | 8.51 | 198 N (42+193) | 2.3 | 6.39 |
| L6_pelvis | 10×M4 | 14/1475 N | 107.28 | 213 N (77+198) | 2.4 | 5.94 |

## 형상 최적화 (제거 가능 / 보강 필요)

| 링크 | 총 체적 | SF>1.5 제거가능 | SF>2 제거가능 | SF>2 보강필요 |
|---|---|---|---|---|
| L1_ankle_foot | 262.01 cm³ | 83.9 % | 83.9 % | — |
| L1b_foot_toeoff | 261.98 cm³ | 판정 미달 — 보강 먼저 | 판정 미달 — 보강 먼저 | 0.0 cm³, 두께 ×1.1 |
| L2_shin | 323.05 cm³ | 71.5 % | 71.5 % | — |
| L3_thigh | 493.89 cm³ | 55.6 % | 55.6 % | — |
| L4_hip_yaw | 209.32 cm³ | 75.7 % | 75.7 % | — |
| L5_hip_pitchroll | 242.52 cm³ | 판정 미달 — 보강 먼저 | 판정 미달 — 보강 먼저 | 0.1 cm³, 두께 ×1.33 |
| L6_pelvis | 292.82 cm³ | 판정 미달 — 보강 먼저 | 판정 미달 — 보강 먼저 | — |
| L1d_foot_toeoff_fine | 261.87 cm³ | 판정 미달 — 보강 먼저 | 판정 미달 — 보강 먼저 | 0.0 cm³, 두께 ×1.1 |
| L2b_shin_cornerfine | 323.06 cm³ | 93.9 % | 판정 미달 — 보강 먼저 | — |
| L2c_shin_nomotor | 323.06 cm³ | 판정 미달 — 보강 먼저 | 판정 미달 — 보강 먼저 | — |
| L3c_thigh_nomotor | 493.89 cm³ | 판정 미달 — 보강 먼저 | 판정 미달 — 보강 먼저 | 0.03 cm³, 두께 ×1.29 |
| L5c_hip_nomotor | 242.52 cm³ | 판정 미달 — 보강 먼저 | 판정 미달 — 보강 먼저 | 0.32 cm³, 두께 ×1.31 |
| L6c_pelvis_nomotor | 320.7 cm³ | 판정 미달 — 보강 먼저 | 판정 미달 — 보강 먼저 | 0.0 cm³, 두께 ×1.14 |

> 제거 가능 체적은 **액추에이터 강체 포함** 모델(응력 하한)로 계산된 값이므로 절감의 **상한**으로 읽어야 한다. 보수적 경계(모터 제외)에서는 L5를 제외한 링크가 판정 자체를 통과하지 못하므로, 실제 절감량은 하우징 강성을 실제 값으로 모델링한 뒤에 확정된다.


## 케이스 설명

- **L1_ankle_foot** (액추에이터 자동) — 기본 케이스
- **L1b_foot_toeoff** (액추에이터 자동) — same foot as L1, loaded at the forefoot instead of the heel: the ankle axis sits at y=145, so the forefoot patch is 100-180 mm away against the heel's 0-80 mm and is the longer bending lever
- **L2_shin** (액추에이터 3개 강체) — 기본 케이스
- **L3_thigh** (액추에이터 2개 강체) — 기본 케이스
- **L4_hip_yaw** (액추에이터 없음) — 기본 케이스
- **L5_hip_pitchroll** (액추에이터 2개 강체) — 기본 케이스
- **L6_pelvis** (액추에이터 없음) — pelvis. The two actuators previously listed here sit 30-90 mm off this geometry (hip_p is on the leg side at x=-124, hip_r_1_ is above the pelvis top) and were silently skipped, so the "motors included" model never had any. They are removed rather than pretended.
- **L1d_foot_toeoff_fine** (액추에이터 자동) — mesh-convergence check on the only failing case: the forefoot bending band is meshed at 2.6 mm instead of ~10 mm. If 289.5 MPa holds, the verdict is real; if it climbs, the sole needs a finer study; if it drops, the coarse mesh over-read it.
- **L2b_shin_cornerfine** (액추에이터 3개 강체) — same shin as L2, with a 2 mm mesh at the four symmetric corners that carry its 311 MPa peak. If the peak climbs with refinement the corner is a geometric singularity (an unfilleted internal corner) and the verdict must come from the nominal field; if it converges, the corner is a real stress riser.
- **L2c_shin_nomotor** (액추에이터 없음) — INVALID as a model, and that is the finding: without the RS03 housings four bodies of the shin have nothing joining them within 12 mm. The actuator housings are structural members of this link, not just masses, so a "conservative no-motor" bracket cannot be built for L2 at all. The correct next step is a housing modelled with REAL stiffness (aluminium case + flange bolts), not rigid and not absent.
- **L3c_thigh_nomotor** (액추에이터 없음) — same thigh and wrench as L3, actuator housings left out - the knee load enters through the RS04 housing, so this is the conservative half of the bracket.
- **L5c_hip_nomotor** (액추에이터 없음) — same link and same wrench as L5_hip_pitchroll, with the actuator housings left out. A rigid housing bolted across the structure is a parallel load path, so the pair brackets the answer: with motors = lower bound on stress, without = conservative upper bound. L2 moved 311 -> 60 MPa when the load began entering through the rigid housing, which is exactly the effect this isolates.
- **L6c_pelvis_nomotor** (액추에이터 없음) — same pelvis, second mesh density. It was set up as the no-motor half of a bracket, but L6 has no attachable motor, so this is really a MESH CONVERGENCE control: 284k vs 319k nodes on an identical model gave 342.6 vs 82.8 MPa, which is a mesh-sensitivity finding, not a motor effect.
