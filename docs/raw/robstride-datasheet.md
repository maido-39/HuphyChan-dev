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
