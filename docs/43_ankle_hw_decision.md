# 43 · 발목 HW 결정 매트릭스 (ankle_roll + ankle_pitch) — gait-fix 검증 후

> 트리거: gaitfix_v5가 **ankle_roll PEAK = HW floor** 확정(reward 3 레버 모두 실패) + [[41_ankle_pitch_pushoff_hw]]가 **ankle_pitch push-off under-spec** 확정. 두 축 모두 reward 아닌 **HW 조치 필요**. 좋은 gait(gaitfix_v6+) 측정으로 *정확한 수치*는 확정 예정 — 이 문서는 **정성적 결정 + 옵션 trade-off**.
> 대전제: ★ **SIZE가 binding 제약** (소형, 3D프린트+알루미늄 1.5-2.7kN 파손). 원위(distal) 질량·관성·패키징이 결정에 크게 작용.

## 0. 결론 요약 (권고)
| 축 | 모터 | 문제 | ★ 1순위 권고 | 근거 |
|---|---|---|---|---|
| **ankle_pitch** | RS03 60N·m, 1:1 링크 | push-off 12-38% 부족(−60 클립·RMS 128%) | **링크 감속 N~1.3-1.5** (모터 유지) | torque-bound+speed여유라 거의 무손실, T-N위반 0%, 비용 0([[41_ankle_pitch_pushoff_hw]]) |
| **ankle_roll** | RS00 14N·m, 직결 | 측방 peak=mg×발반폭 물리바닥(100%·열 107%) | **DM-J4340-2EC drop-in** *또는* **발폭↑** (사이즈 trade-off로 택1) | 아래 §2 |

## 1. ankle_pitch — 링크 감속 (확정적, 비용 0)
- 측정(gaitfix_v4, weak push-off): tau −60 클립(RS03 peak 100%)·RMS 25.6(128% 연속=열과부하)·속도 91rpm(46% no-load) → **torque-bound + speed surplus + torque-speed 분리**.
- 처방: 1:1 링크 → **N=1.3** (joint peak 60→78N·m=인간 push-off 정확히 덮음, motor RMS~연속, T-N위반 0%) ~ **N=1.5** (joint 90, rough+DR 마진). N=2.0은 과토크+no-load 근접(rough 위험).
- 설계: lever arm r_m≥40-45mm(rod force F=tau/r_m ≤1.3kN=HW안전), N=r_a/r_m → r_a~68mm(N=1.5) 패키징 확인. cf. [[37_ankle_linkage_fidelity]].
- 대안: 병렬 스프링/SEA(Achilles recoil — motor peak를 peak-power로 낮춤), 단 복잡도↑. 모터 교체는 비권장(RS03=토크밀도 챔피언).
- ⚠ **gaitfix_v6가 push-off 복원하면 ankle_pitch 부하 더 상승** → v6 §7에서 N 재확정.

## 2. ankle_roll — 결정 매트릭스 (사이즈 trade-off가 핵심)
peak 14N·m = 508N(단일지지 체중) × 2.8cm(발 edge까지 CoP) = **mg×발반폭 기하 천장**. RS00 0.27N·m/kg=피어 최저. 측방 외란/edge worst-case 20-25N·m.

| 옵션 | 효과 | 비용 | 사이즈/원위 | 판정 |
|---|---|---|---|---|
| **A. DM-J4340-2EC** (27/9, Φ57, 362g) | peak 1.9×/연속 1.8× — drop-in 디커플드 roll-직결 | +$30·+52g | ≈RS00 외형(양호) | ★ **사이즈 OK면 1순위**. ⚠ 40:1=저속 → roll-rate 대조 필수 |
| **B. 발폭↑** (mediolateral) | mg×발반폭 *바닥 자체*를 올림 → 모터 안 바꾸고 천장↑ | 기구 변경 | 발 크기↑ (SIZE 제약과 충돌 가능) | ★ **사이즈 여유 있으면 가장 쌈**. A와 병행 가능 |
| **C. 2-RSU 병렬** (RS03×2 차동) | 유효 roll 토크 ~2× | 2모터·2×2 운동학·sim2real | **원위 질량·관성↑(나쁨)** | 사이즈 제약상 비권장(distal) |
| **D. 링크 relocate** (X2식) | 공짜 감속 + 원위 관성↓ | 링크 복잡 | 모터 근위화(사이즈 양호) | sim에 링크 구조하중 미반영([[37_ankle_linkage_fidelity]]) — 검증 필요 |

- ★ **권고**: **A(DM-J4340)** 우선 — RS00과 거의 동형이라 SIZE 제약에 안전. **roll-rate(no-load 100rpm급) vs gaitfix_v6 측정 roll 속도 대조**가 게이트. roll 속도가 낮으면(측정상 ankle_roll은 토크-속도 분리 가능성) A로 충분.
- **B(발폭)**는 *바닥을 직접 올리는* 유일 옵션이라 A와 **병행** 검토 가치(사이즈 예산 내에서 조금만 넓혀도 peak↓).
- C·D는 사이즈/복잡도상 후순위.

## 3. Open items (gaitfix_v6 good-gait 측정 후 확정)
1. ★ 정확한 sizing = **좋은 gait(gaitfix_v6+) §7 재측정**으로(현 수치는 깨진/중간 gait). Phase B/C.
2. DM-J4340 **roll-rate 대조**(40:1 저속 vs 측정 ankle_roll 각속도).
3. ankle_pitch **N 최종값**(v6 push-off 복원 후 부하로).
4. 발폭↑의 **SIZE 예산** 확인(사용자 — 발이 몸통보다 넓어도 되는지).

## 참고
- [[41_ankle_pitch_pushoff_hw]] · [[39_ankle_qdd_uptorque_survey]](RS00 대체 후보) · [[38_parallel_ankle_sim2real]](2-RSU) · [[37_ankle_linkage_fidelity]](relocate) · [[36_all_actuator_tn_envelopes]](T-N 봉투) · [[experiments/2026-06-22_10-19-09_gaitfix_v5]](ankle_roll floor 판별) · [[reward_research/2026-06-22_11-00_ankle_roll_peak_gaitfix_v5_or_hw]]
