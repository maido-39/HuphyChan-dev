# RobStride 액추에이터 데이터시트 — 검증 (공식 PDF)

> 출처: 워크플로우 wyilgvpyj가 공식 Lingfoot/RobStride PDF(Seeed 미러)·OpenELAB 교차확인. wiki: [[28_reward_actuator_fidelity]] · [[21_motor_power_weight]].

| 모델 | 역할 | rated/peak (N·m) | 무부하/정격부하 속도(rpm) | 감속비 | Kt (N·m/Arms) |
|---|---|---|---|---|---|
| **RS00** | ankle_roll | 5 / 14 | 315 / **100**¹ | 10:1 | 1.48 |
| **RS03** | hip_yaw·ankle_pitch | 20 / 60 | 200 / **100**² | 9:1 | 2.36 |
| **RS04** | hip_pitch·roll | 40 / 120 | 200 / 167 | 9:1 | 2.1 |
| RS04+1:3 belt | knee | 120 / 360 | 66.7 / 55.7 | 9:1×3 | — |
| RS01 / RS02 | ankle_roll 상향 후보 | 6 / 17 | 315·410 / 275·360 | 7.75 | — |

- ¹ RS00 정격부하속도: 공식 PDF·AIFITLAB 매뉴얼=**100rpm**, OpenELAB 리셀러=260rpm (상충, 하단 RS00 섹션 flag). 무부하 315는 일치.
- ² RS03 정격부하속도: **공식 매뉴얼=100rpm**(20N·m@100rpm 명시), 리셀러(AIFITLAB·OpenELAB)=180rpm (상충, 하단 RS03 섹션 flag). 무부하 200은 일치. 이전 "180"은 리셀러값.
- ✅ 우리 *토크* 스펙(robstride_biped.yaml)은 정확.
- ❌ 유일 오류(수정됨): RS03 `velocity_limit_rpm` 220→**200**(무부하 200; 60/20@220 모델 없음).
- ⚠ 미검증: RS00 **열 시상수**(145°C 권선한계 곡선만), 권선저항 R·마찰(Kt만 있음) — bench 식별 필요(T1 thermal·T3 Joule reward용).
- verified yes (PDF 직접). RS00·RS04는 OpenELAB 교차확인.

## MIT-mode 컨트롤러 Kp/Kd 범위 (출력축 기준) — 검증 (w2pkt68gl)
> Seeed "RobStride Control Guide" + CubeMars AK 매뉴얼(MIT 프로토콜 동일). 게인은 **내부 기어박스 이후 출력축** 기준, Kp=N·m/rad, Kd=N·m·s/rad.
- **소형(RS00/01/02/05)**: Kp 0–500, **Kd 0–5**
- **대형(RS03/04/06)**: Kp 0–5000, **Kd 0–100** ← ★ 직결 hip/knee도 Kd 5에 안 묶임
- ⚠ RS01 fw 0.1.3.4가 "kp/kd 계수 오류 수정" → 실기 이식 시 펌웨어 확인.

## 전기 파라미터 (back-EMF) — 검증 (공식 RobStride GitHub)
| 모델 | Kt | line R(Ω) | L(mH) | back-EMF | 극수 |
|---|---|---|---|---|---|
| RS04 | 2.1 | 0.16±10% | 0.211 | 16.9 V/krpm | 42 |
| RS03 | 2.36 | 0.39±10% | 0.275 | 17 | 42 |
| RS00 | 1.48 | 1.5±10% | 0.75 | 9.5 | 28 |
- ⚠ rotor inertia 전 모델 미공개(armature는 sim 추정). per-phase R=line/2(wye).
- **관절 댐핑 = motor_Kd × (외부 감속비)²** (Isaac은 joint-side Kd 직접 사용). knee는 벨트로 증폭 → 직결 한계 초과 가능 → ζ≈0.7용 Kd: hip 24·hip_yaw 6.5·knee 11. [[28_reward_actuator_fidelity]]·[[30_knee_biomechanics]].

## ★ RS04 T-N 곡선 (공식 매뉴얼 직접) — 검증 (리서치 wyilgvpyj 재확인, 원본 PDF 추출)
> 출처: **공식 RobStride GitHub `RS04User Manual260428.pdf`** (Product_Information/Product Literature/RS04), §1.3-12 "T-N curve". `/tmp`에서 pdfimages 추출. 곡선 이미지: `assets/rs04_tn_curve_official.png`. **이전 OpenELAB "100rpm까지 평탄, 200rpm서 0" 요약은 부정확** — 공식 곡선과 다름.

**곡선 모양 (출력축, 9:1 후, 48V)**: 그래프 x축은 **90~190rpm만** 표시(저속 평탄부는 잘림). 표시 구간 전체가 **단조 감소**(field-weakening/back-EMF roll-off):
- ~95rpm → **120 N·m** (peak)
- 110rpm → ~110 · 130rpm → ~95 · 150rpm → ~78 · (150rpm 부근서 무릎 모양 변곡, 기울기↑) · 170rpm → ~52 · 185rpm → ~40 · **190rpm → ~10** (급락, ≈ no-load 200rpm로 외삽).
- ⇒ **corner speed(평탄→감소 전이) ≤ ~95rpm**: 매뉴얼이 95rpm서 이미 peak(120)이고 곧장 감소 시작 → **constant-torque(전류제한) 평탄부는 ~95rpm 이하** 구간(그래프 미표시). rated 40N·m는 **100rpm**, peak 120N·m는 **~95rpm 이하**서만. **사용자가 우려한 "peak토크 × max속도 단순박스"는 명백히 틀림** — 고속서 토크 급감.
- ⚠ **무릎 1:3 함의**: 무릎 모터속도 = joint_speed × 27(9×3). joint 71rpm 요구 → 모터 ~? (joint-side 곡선이므로 직접 적용 불가, 모터-side 재투영 필요). 핵심: 모터 출력축 ~150rpm 넘으면 가용토크 120→78↓.

**peak vs continuous 봉투**:
- **연속/정격(thermal)**: **40 N·m** (345×345mm 알루미늄 방열판, GB/T 30549-2014, 100rpm). 작은 방열판(220×200mm)이면 **35 N·m**.
- **peak(순시)**: **120 N·m** (위상전류 90Apk). rated 위상전류 27Apk.
- **과부하 듀티 (§13 "Maximum overload curve", 회전 50rpm·풀 방열판, 25℃)** → `assets/rs04_overload_rotating_official.png`:
  120N·m=3s · 115=9s · 110=10s · 105=13s · 100=15s · 90=24s · 80=38s · 70=61s · 60=108s · 50=324s · **40=rated(무한)**.
- **스톨 듀티 (§14 thermal, stall, 작은 방열판, 단상발열 1.414×)** → `assets/rs04_overload_stall_official.png`:
  120=1s · 110=1s · 100=1.5s · 90=3s · 80=6s · 70=10s · 60=33s · 50=74s · 40=130s · **28.5=rated**. (스톨이 더 엄격: 정격 28.5N·m.)
- 권선한계 145℃(실제 180℃). CANopen 0x6071 "1000=40N·m" → 40N·m이 공식 정격 기준치.

**물리/토크밀도**: 무게 **1420g±20g**, 외형 **Φ120×56mm**(드라이버 Φ84). → peak 토크밀도 **120/1.42 = 84.5 N·m/kg**, 연속 **40/1.42 = 28.2 N·m/kg**. 극수 42, 3상 FOC, 9:1.
- ❌ **효율맵(efficiency map): 공식 매뉴얼·스펙PDF에 없음**(85pp 전수 grep 확인). 효율 곡선 미공개 — 필요시 bench 측정.
- verified **yes** (공식 PDF 곡선 이미지 직접 추출·판독). 3rd-party bench 측정 데이터는 공개본 없음(리셀러 요약만, 부정확).

## RS04 2차출처 교차검증 (공식 GitHub 매뉴얼 外) — 검증 2026-06-21
> 요청: 공식 RobStride GitHub 매뉴얼 **외** 2개 이상 독립출처로 120/40·200rpm·T-N모양·연속정격·Kt2.1·9:1 재확인, 불일치 출처 flag. 출처 URL 2+.

**독립출처별 RS04 스펙 (전부 헤드라인 일치)**:
| 출처 | peak/rated | 무부하/정격속도 | Kt | 감속비 | back-EMF |
|---|---|---|---|---|---|
| OpenELAB (리셀러) | 120 / 40 N·m | 200 / 167 rpm ±10% | 2.1 N·m/Arms | 9:1 | — |
| AIFITLAB (리셀러) | 120 / 40 N·m | 200 / 167 rpm ±10% | 2.1 N·m/Arms | 9:1 | 16.9 Vrms/krpm |
| Seeed wiki (control guide) | max 120 N·m | max 200 rpm ±10% | — | — | — |
| 공식 RobStride X(@RobStride_com) | 120 / 40 N·m | — | — | (9:1) | — |
- 전기파라미터도 일치: 정격위상전류 27Apk, peak 90Apk, line R 0.16Ω, L 0.211mH, 42극, 700W±10%, 48V.
- **무부하 전류** 0.7 Arms±10% (OpenELAB).
- → **120/40·200/167·Kt2.1·9:1·700W·48V 모두 ≥2 독립출처 교차검증 PASS.** rotor inertia·연속(thermal) 정격값(N·m)·효율맵은 리셀러도 미공개(공식 PDF만 40N·m@100rpm·345mm 방열판).

**⚠ DISAGREE flag — T-N 곡선 모양**:
- **OpenELAB**(complete-guide 블로그)·WebSearch 요약: "~120 N·m를 ~100rpm까지 **유지(평탄)**, 200rpm서 0으로 점감" → **사다리꼴/평탄플래토 후 roll-off** 묘사.
- **공식 매뉴얼 §12 곡선(원본 PDF 추출)**: 표시구간 90~190rpm 전체가 **단조 감소**, **95rpm서 이미 peak 120 → 곧장 감소**(110rpm~110, 150rpm~78, 190rpm~10). constant-torque 평탄부는 **≤~95rpm**(그래프 미표시 저속부).
- ⇒ 리셀러 "100rpm까지 평탄" = **부정확(over-optimistic)**. 단 방향성(평탄→roll-off 사다리꼴)은 정성적으로 맞음; corner를 95→100rpm으로, 고속 토크유지를 과대평가. **설계엔 공식 곡선(95rpm corner) 사용**, 리셀러 요약 불채택.
- 헤드라인 수치(120/40/200/Kt2.1/9:1)는 **불일치 출처 없음** — 전 출처 동일.

**출처 URL**:
- OpenELAB 제품: https://openelab.io/products/robstride04-qdd-120n-m-integrated-joint-motor-module
- OpenELAB 가이드: https://openelab.io/blogs/learn/robstride04-qdd-120n-m-integrated-joint-bldc-gear-motor-complete-guide
- AIFITLAB: https://aifitlab.com/products/robstride-04-motor
- Seeed wiki: https://wiki.seeedstudio.com/robstride_control/
- 공식 RobStride X: https://x.com/RobStride_com/status/1802891697912737824
- 공식 GitHub 매뉴얼: https://github.com/RobStride/Product_Information (RS04User Manual260428.pdf)
- verified **yes** (5개 독립출처 교차확인 + 공식 PDF 곡선).

## ★ RS00 T-N·과부하 곡선 + 전기파라미터 (공식 PDF 직접) — 검증 2026-06-21 (ankle_roll, 포화 액추에이터)
> 요청: RS00 T-N 데이터 2+ 신뢰출처. rated/peak·무부하/정격속도·T-N 모양·연속(thermal)·Kt·line R·감속비·질량/외형 추출, 교차검증·불일치 flag. RS00 = ankle_roll(최소 모터, 우리 데이터서 151% RMS%rated 포화 → 바인딩 후보).
> 출처: **공식 RobStride GitHub `RobStride Product Specification Document 20250626.pdf`** (p.2 = RS00) — `/tmp`에서 curl+pdftotext+pdftoppm 추출. 곡선 이미지: `assets/rs00_tn_overload_official.png`, 전체 스펙페이지 `assets/rs00_spec_page_official.png`.

**공식 RS00 스펙 (PDF p.2 직접)**:
| 항목 | 공식값 |
|---|---|
| rated / peak 토크 | **5 / 14 N·m** |
| 무부하 속도 | **315 rpm ±10%** |
| 정격부하 속도 | **100 rpm ±10%** ← ★공식 (리셀러는 260) |
| Kt | **1.48 N·m/Arms** |
| line R | **1.5±10% Ω** |
| 인덕턴스 L | **750±20 μH** (=0.75mH) |
| back-EMF | **9.5 Vrms/krpm ±10%** (=0.095 Vrms/rpm) |
| 정격출력 | **50W ±10%** ← ★공식 (리셀러는 170W) |
| 무부하 전류 | 0.5 Arms |
| 정격 위상전류 | 4.7 Apk ±10% |
| peak 위상전류 | 15.5 Apk ±10% |
| 감속비 | 10:1 |
| 극수 / 상 | 28 / 3 (FOC) |
| 질량 | **310g ±3g** |
| 외형 | **57×57×51 mm** |
| 절연 | Class B, 사용온도 -20~50℃ |

**★ T-N 곡선 모양 (공식 "48V T-N curve", p.2 좌측 곡선, 출력축 10:1 후)** → `assets/rs00_tn_overload_official.png`:
- x축 **0~350rpm**, y축 토크(3·6·9·12·15 N·m 그리드).
- 모양: **0~~100rpm 평탄(≈14 N·m peak 근처)** 후 **단조 concave-down 감소(field-weakening/back-EMF roll-off)** → ~150rpm 부근부터 기울기↑ → **~315rpm(무부하)서 0 근처로 급락**. RS04와 동일한 전압제한 봉투(평탄 corner → droop), **이산점 아닌 연속 곡선**.
- ⇒ **corner speed ≈ 100rpm** (= 공식 정격부하 속도와 일치!). peak 14N·m는 **저속(<~100rpm)**서만, 고속선 토크 급감. **"14N·m × 315rpm 단순 박스" 가정 틀림.**

**★ 과부하 듀티 (공식 "Max Overload" 곡선, p.2 우측, 부하 vs 工作时间 s, log축)**:
| 부하 N·m | 지속시간 |
|---|---|
| **5** | **rated (무한·연속)** |
| 7 | 120 s |
| 10 | 18 s |
| 12 | 10 s |
| 14 | 5 s |
- ⇒ **연속/thermal 정격 = 5 N·m** (= rated 토크). **peak 14 N·m는 단 5초** 듀티. 우리 데이터 ankle_roll이 RMS 기준 151%%rated 포화 = **연속 5N·m 한계를 1.5배 초과** = 바인딩 액추에이터 정합. (10N·m=18s, 12N·m=10s 듀티는 짧은 push-off 트랜지언트만 허용.)

**교차검증 (5+ 독립출처)**:
| 출처 | rated/peak | 무부하/정격속도 | Kt | line R | 감속비 | 질량 |
|---|---|---|---|---|---|---|
| **공식 PDF(GitHub)** | 5 / 14 | **315 / 100** | 1.48 | **1.5Ω** | 10:1 | 310g |
| OpenELAB 가이드 | 5 / 14 | 315 / **260** | 1.48 | — | 10:1 | 310g |
| OpenELAB 비교가이드 | 5 / 14 | 315 / **260** | — | — | 10:1 | 310g |
| AIFITLAB wiki 매뉴얼 | 5 / 14 | 315 / **100** | 1.48 | — | 10:1 | 310g |
| Seeed wiki | (max)14 | (max)315 | — | — | — | — |
| device.report 매뉴얼 | 14 peak | 315 | — | — | — | 310g |

**⚠ DISAGREE flag — 정격부하 속도 & 정격출력**:
- **정격부하 속도**: 공식 PDF·AIFITLAB 매뉴얼 = **100 rpm**. OpenELAB(리셀러 블로그 2건) = **260 rpm**. → 우리 기존 노트·`robstride_biped.yaml` 트레이스의 "260"은 **OpenELAB 리셀러값**; 공식·매뉴얼 원전은 **100 rpm**. 100rpm이 T-N corner(평탄→droop 전이)와 일치하므로 **물리적으로 100이 정합**(260은 무부하315와 정격간 중간 모호값). → **공식 100 채택 권장**, 단 sim velocity_limit(무부하 315)은 영향 없음(velocity limit은 무부하 기준).
- **정격출력**: 공식 PDF = **50W±10%**, OpenELAB = **170W**. (170W는 peak/순시 출력 추정값으로 보임; 공식 연속 정격 = 50W.) 5N·m×100rpm×(2π/60)≈52W → **공식 50W가 연속정격과 자기일치**. 170W는 14N·m·peak 구간 순시.
- 헤드라인(5/14·무부하315·Kt1.48·R1.5Ω·10:1·310g·57×57×51)은 **불일치 출처 없음** — 전 출처 동일.

**우리 값 대조 (사용자 제시)**: peak 5/14 ✅정확. 무부하 315 ✅. **정격 260 → 공식은 100(리셀러값 채택했음, flag)**. Kt 1.48 ✅. line R 1.5Ω ✅. 감속비 10:1 ✅. → 토크·Kt·R·감속비·무부하속도 전부 공식과 일치, **정격부하속도만 리셀러(260) vs 공식(100) 불일치**.

**출처 URL**:
- 공식 GitHub 스펙PDF: https://github.com/RobStride/Product_Information (RobStride Product Specification Document 20250626.pdf, p.2)
- OpenELAB RS00 가이드: https://openelab.io/blogs/learn/robstride00-qdd-14n-m-integrated-joint-motor-module-complete-guide
- OpenELAB 비교가이드: https://openelab.io/blogs/learn/complete-guide-to-robstride-qdd-motors-model-comparison-and-selection
- AIFITLAB wiki 매뉴얼: https://wiki.aifitlab.com/robstride-docs/robstride-00-instruction-manual
- Seeed wiki: https://wiki.seeedstudio.com/robstride_control/
- device.report 매뉴얼: https://device.report/m/2e42a909a1575b641836a027c2f4a7f8a4841e2f2b37898548c87a4c67028947
- verified **yes** (공식 PDF 곡선 직접 추출·판독 + 4 독립 리셀러/매뉴얼 교차).

## ★ RS03 T-N·과부하·열 곡선 + 전기파라미터 (공식 매뉴얼 PDF 직접) — 검증 2026-06-21 (hip_yaw·ankle_pitch)
> 요청: RS03 T-N 데이터 2+ 신뢰출처(공식 GitHub Product_Information + Seeed/OpenELAB/리셀러/매뉴얼). rated/peak·무부하/정격속도·T-N 모양(corner+roll-off)·연속(thermal)·Kt2.36·line R·감속비9:1·질량/외형 추출, 교차검증·불일치 flag, URL 2+.
> 출처: **공식 RobStride GitHub `RS03User Manual260428.pdf`** (Product_Information/Product Literature/RS03), §1.3 전기특성+§12 "T-N curve"+§13 "Maximum overload curve"+§14 thermal/stall. `webfetch→pdftoppm`로 p.9-11 렌더 직접 판독. 곡선 이미지: `assets/rs03_tn_curve_official.png`(T-N), `assets/rs03_overload_thermal_official.png`(과부하+스톨 듀티 표).

**공식 RS03 스펙 (매뉴얼 직접 추출)**:
| 항목 | 공식값 | 비고 |
|---|---|---|
| rated / peak 토크 | **20 / 60 N·m** | rated CW |
| 무부하 속도 | **200 rpm ±10%** | ★사용자 "200" 일치 (리셀러 195) |
| 정격부하 속도 | **100 rpm** (20N·m@100rpm 명시) | ★공식 (리셀러는 180, flag) |
| Kt | **2.36 N·m/Arms** | 유효값 |
| line R | (공식 매뉴얼 전기특성 미기재) → 리셀러 **0.39Ω±10%** | 매뉴얼은 절연저항만; R은 리셀러 교차 |
| 인덕턴스 L | (매뉴얼 미기재) → 리셀러 **0.275mH±10%** | |
| back-EMF | **17 Vrms/krpm ±10%** | |
| 무부하 전류 | **2 Arms** | ★공식 (리셀러는 0.6, flag) |
| 정격 위상전류 | **13 Apk ±10%** | ★공식 (리셀러는 12) |
| peak 위상전류 | **43 Apk ±10%** | 일치 |
| 정격전압 / 범위 | **48 VDC / 24–60 VDC** | ★공식 범위 24–60 (리셀러·Seeed는 15–60, flag) |
| 정격출력 | 380W±10% (리셀러; 매뉴얼 미기재) | |
| 감속비 | **9:1** | 일치 |
| 극수 / 상 | **42 / 3** (FOC) | |
| 질량 | **880g ±20g** | |
| 외형 | **106×106×56 mm** (드라이버 Φ70) | |
| 절연 / 사용온도 | Class B / -20~50℃, 권선한계 145℃(실제180℃) | |

**★ T-N 곡선 모양 (공식 §12 "T-N curve", 출력축 9:1 후, 48V)** → `assets/rs03_tn_curve_official.png`:
- x축 **120~195rpm만** 표시(저속 평탄부는 잘림, RS04/RS00과 동일 패턴), y축 토크 10~60 N·m.
- 표시구간 전체 **단조 감소(field-weakening/back-EMF roll-off), concave-down 연속곡선**:
  - ~120rpm → **60 N·m** (peak) · 135rpm → ~57 · 150rpm → ~50 · 165rpm → ~42 · 180rpm → ~30 · (180rpm 부근 무릎 변곡, 기울기 급증) · 185rpm → ~22 · **188~190rpm → ~13으로 급락** (≈ no-load 200rpm로 외삽 0).
- ⇒ **corner speed(전류제한 평탄→전압제한 droop 전이) ≤ ~120rpm**: 120rpm서 이미 peak 60 후 즉시 감소 → **constant-torque 평탄부는 ~120rpm 이하**(그래프 미표시 저속부). peak 60N·m는 저속(<~120rpm)서만, 고속선 토크 급감. **"60N·m × 200rpm 단순 박스" 가정 틀림** — RS04/RS00과 동일 결론. **이산점 아닌 연속 곡선.**

**★ 과부하 듀티 (공식 §13 "Maximum overload curve", 회전 100rpm·풀 방열판 215×220mm, 25℃)** → `assets/rs03_overload_thermal_official.png` 상단표:
| 부하 N·m | 지속시간 |
|---|---|
| **60** (peak) | **13 s** |
| 50 | 34 s |
| 40 | 67 s |
| 30 | 393 s |
| **20** | **rated (무한·연속)** |
- ⇒ **연속/thermal 정격(회전) = 20 N·m** (= rated 토크). peak 60N·m는 단 13초. 40N·m=67s·30N·m=393s는 짧은 트랜지언트(push-off)만.

**★ 스톨 듀티 (공식 §14 thermal, 스톨, 축소 방열판, 단상발열 1.414×)** → 동 이미지 하단표:
| 부하 N·m | 지속시간 |
|---|---|
| 60 | 1 s |
| 50 | 4 s |
| 40 | 9 s |
| 30 | 25 s |
| 20 | 190 s |
| **13** | **rated (무한)** |
- ⇒ 스톨이 훨씬 엄격: **스톨 연속정격 = 13 N·m**(회전 20N·m 대비). 스톨서 60N·m는 1초만. (단상발열 1.414× 때문.)

**교차검증 (공식 매뉴얼 + 4 독립출처)**:
| 출처 | rated/peak | 무부하/정격속도 | Kt | line R | 감속비 | 질량 | 전압범위 |
|---|---|---|---|---|---|---|---|
| **공식 매뉴얼(GitHub)** | 20 / 60 | **200 / 100** | 2.36 | (미기재) | 9:1 | 880g | **24–60V** |
| AIFITLAB (리셀러) | 20 / 60 | 195 / **180** | 2.36 | 0.39Ω | 9:1 | 880g | 15–60V |
| OpenELAB 제품 | 20 / 60 | 195 / **180** | 2.36 | 0.39Ω | 9:1 | 880g | 15–60V |
| rcdrone (리셀러) | 20 / 60 | 195 / **180** | 2.36 | 0.39Ω | 9:1 | 880g | — |
| Seeed wiki | (max)60 | (max)**195** | — | — | — | — | — |
| roboticscenter (리셀러) | 20 / 60 | — | — | — | 9:1 | 880g | — |

**⚠ DISAGREE flag**:
1. **정격부하 속도**: 공식 매뉴얼 = **100 rpm**(20N·m@100rpm 명시, T-N corner와 정합). 리셀러 4곳 = **180 rpm**. → RS00(공식100 vs 리셀러260)·RS04(공식167)와 **동일 패턴**: 리셀러 정격속도는 over-optimistic. **설계엔 공식 100rpm 채택 권장.**
2. **무부하 속도**: 공식 = **200 rpm**(사용자값 일치), 리셀러 = **195 rpm**. 5rpm 차이(±10% 내 무시 가능). 공식 200 채택.
3. **무부하 전류**: 공식 = **2 Arms**, 리셀러 = 0.6 Arms ±10%. → 큰 불일치(리셀러가 더 낙관적). 공식 2 Arms 채택.
4. **정격 위상전류**: 공식 **13 Apk**, 리셀러 **12 Apk**(드라이버 정격은 12Apk로 표기). 소차.
5. **전압범위**: 공식 매뉴얼 **24–60V**, 리셀러·Seeed **15–60V**. (15V는 최저 동작, 24V는 정격 권장 하한 추정.)
- **헤드라인(20/60·무부하200·Kt2.36·9:1·880g·106³·42극·back-EMF17·peak43Apk)은 불일치 출처 없음** — 전 출처 동일.

**우리 값 대조 (사용자 제시)**: peak 20/60 ✅정확. 무부하 200 ✅(공식). **정격 "~180" → 공식은 100(리셀러값, flag)**. Kt 2.36 ✅. line R 0.39Ω ✅(리셀러·매뉴얼 전기특성엔 절연저항만). 감속비 9:1 ✅. → 토크·Kt·R·감속비·무부하속도 일치, **정격부하속도만 리셀러(180) vs 공식(100) 불일치**.
- ⚠ **미공개**: rotor inertia(전 모델 미공개, sim armature 추정 유지). 효율맵 미공개(RS04와 동일). line R/L은 공식 매뉴얼 전기특성 항목엔 없고 리셀러 스펙시트에만(0.39Ω/0.275mH) — 리셀러 단일출처지만 RS04 패턴상 신뢰.

**출처 URL**:
- 공식 GitHub 매뉴얼: https://github.com/RobStride/Product_Information (Product Literature/RS03/RS03User Manual260428.pdf)
- AIFITLAB: https://aifitlab.com/products/robstride-03-motor
- OpenELAB 제품: https://openelab.io/products/robstride03-qdd-60n-m-integrated-joint-motor-module
- rcdrone: https://rcdrone.top/products/robstride-03-qdd-60n-m-integrated-actuator-module-48v-dual-encoders-planetary-reducer-ip52-9-1-ratio
- Seeed wiki: https://wiki.seeedstudio.com/robstride_control/
- roboticscenter: https://www.roboticscenter.ai/store/product/robstride-03
- verified **yes** (공식 매뉴얼 T-N·과부하·스톨 곡선 직접 렌더·판독 + 5 독립 리셀러/wiki 교차).
