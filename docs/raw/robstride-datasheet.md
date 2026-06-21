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
