# RobStride 액추에이터 데이터시트 — 검증 (공식 PDF)

> 출처: 워크플로우 wyilgvpyj가 공식 Lingfoot/RobStride PDF(Seeed 미러)·OpenELAB 교차확인. wiki: [[28_reward_actuator_fidelity]] · [[21_motor_power_weight]].

| 모델 | 역할 | rated/peak (N·m) | 무부하/정격부하 속도(rpm) | 감속비 | Kt (N·m/Arms) |
|---|---|---|---|---|---|
| **RS00** | ankle_roll | 5 / 14 | 315 / 260 | 10:1 | 1.48 |
| **RS03** | hip_yaw·ankle_pitch | 20 / 60 | 200 / 180 | 9:1 | 2.36 |
| **RS04** | hip_pitch·roll | 40 / 120 | 200 / 167 | 9:1 | 2.1 |
| RS04+1:3 belt | knee | 120 / 360 | 66.7 / 55.7 | 9:1×3 | — |
| RS01 / RS02 | ankle_roll 상향 후보 | 6 / 17 | 315·410 / 275·360 | 7.75 | — |

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
