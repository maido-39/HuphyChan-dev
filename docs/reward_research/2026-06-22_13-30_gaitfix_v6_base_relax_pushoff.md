# reward 연구 — gaitfix_v6: base 완화 + push-off 복원 (골반 swing + 토우 롤오버, 결합) (2026-06-22 13:30)
> 트리거: gaitfix_v5 완료(ankle_roll=HW floor 확정, 별개 HW 축). 토우 미사용·골반 swing 부족은 별개 축이고 **base_height가 공통 범인**. 바꾸려는 reward: base_height·lin_vel_z·flat_orientation 완화 + ankle_pushoff 복원 + foot_flat roll-only.

## 1. 직전 결과 분석 (gaitfix_v5, [[experiments/2026-06-22_10-19-09_gaitfix_v5]])
- ★ ankle_roll PEAK = **HW floor 확정**(3 reward 레버 모두 peak 14=100% 못 내림; edge 19→13°만). → ankle_roll은 reward 아닌 **HW**(task4). gaitfix_v6는 **건드리지 않음**.
- 골반 baseline(새 로깅): 수직 bob std 1.2cm(인간 2.5cm의 ~half), pitch std 1.4°, roll std 3.9°. 토우(v4): Fz 340N 오나 moment 15N·m·bend 11°.

## 2. 원인 (정본 연구 종합)
- [[2026-06-22_12-30_toe_rollover_cop_progression_gaitfix_v6]]: 토우 미사용 = CoP 전진 부재(스프링 정상). ankle_pushoff 0.1로 꺼둠 + push-off가 torque/energy에 상쇄(interference) + 단일 forefoot_cop는 정적.
- [[2026-06-22_11-30_base_overconstrain_pelvis_swing_gaitfix_v6]]: ★ **`base_height_l2`(−1.0)가 single-support vault(CoM 상승)를 페널티 → push-off를 막아 골반 bob·토우 롤오버 동시 억제** = 공통 범인. IsaacLab G1/H1은 lin_vel_z=0·base_height 항 없음. Ortega&Farley: CoM 평탄화 = 대사 +6%.

## 3. 원인·문제 규명
- 골반 안 swing + 토우 안 굴림 = **base를 너무 rigid하게 묶어(특히 base_height) push-off/vault를 억제**한 *공통* 결과. + ankle_pushoff 꺼둠 + foot_flat이 pitch까지 눌러 heel-rise 차단.

## 4. 제안 (gaitfix_v6 reward 변경 + 왜)
| 변경 | 기존→신규 | 왜 |
|---|---|---|
| `base_height_l2` | −1.0→**−0.25** | vault CoM 상승 허용(IsaacLab humanoid는 아예 drop; 안전 위해 약하게 유지) |
| `lin_vel_z_l2` | −0.2→**−0.05** | vault 속도 허용(bounce 방지로 0 아닌 약하게) |
| `flat_orientation_l2` | −1.0→**−0.5** | 골반 pitch/roll swing(4-7°) 허용 |
| `ankle_pushoff` | 0.1→**0.5** | push-off(CoP 전진) 엔진 복원 — v5가 ankle_roll self-conflict 해소 |
| `foot_flat_orientation` | 양축→**roll-only** | pitch 페널티가 heel-rise 막던 충돌 해소(roll만 평평 유지=ankle_roll용) |
- **HOLD**: CoP-anterior-progression 전용 보상은 gaitfix_v7로(위 5개로 push-off/vault 복원 후에도 토우 안 굴면 추가). 한 번에 항 과다 변경 회피.
- **검증**: 수직 bob 1.2→~2.5cm(M자), 골반 pitch↑, 토우 bend 11→25-35°·CoP 전진·2nd(toe-off) GRF peak, 낙상 안정(완화가 불안정 유발 안 하는지). ★ 가짜(육안 curl·bounce)면 측정서 드러남.

출처: 정본 [[2026-06-22_11-30_base_overconstrain_pelvis_swing_gaitfix_v6]]·[[2026-06-22_12-30_toe_rollover_cop_progression_gaitfix_v6]] + docs/41(ankle_pitch push-off↑ 예상). verified=문헌/측정 / 추정=완화폭·weight는 config-test로 확인.
