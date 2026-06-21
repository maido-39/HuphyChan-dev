# 무릎 생체역학 — 로봇 설계 (학술조사 검증, wsx14ecd0)

> 사용자 체감 관찰(무릎 역관절 안 됨·기본 자세 굽힘) → 설계. 검증 출처 [[raw/knee-biomechanics]]. 관련 [[29_natural_gait_reward_hw]] · [[Paperreview/kuo-donelan-dynamic-walking]].

> [!warning] ★ 정정 — 제 이전 답이 틀렸음(검증이 잡음)
> 이전에 "로봇 기본자세=전관절 0(곧은 무릎)"이라 했으나 **그건 *stale* `robot.xml`의 `keyframe "stand"`**(학습 미사용). **실제 env가 로드하는 single-source `robstride_biped.yaml`엔 이미 굽힌 nominal**: hip_pitch −0.20rad(−11.5°)·**knee −0.40rad(−22.9° 굴곡)**·ankle_pitch +0.20rad — 주석 "slight knee/hip flex helps walking learn". = **Cassie/H1 관례와 일치, 이미 맞음.** (live spec을 안 보고 stale 파일을 본 실수.)

## Q1 — 과신전/ROM + 비대칭 (검증)
- 인간 무릎 = **굴곡 전용 경첩**(1 DOF, 역관절 불가). 신전 **0° 하드스톱**(AAOS), 종말 신전서 **screw-home이 락**. 굴곡 **135°**(135-150). 과신전: 선수 평균 **−5~−6°**, **>5° genu recurvatum·>10° 병리·>15° 수술**.
- 보행 사이클 내내 무릎은 **굴곡서만** 작동(0°~swing 60°), 과신전 안 함.
- **우리 로봇**(robot.urdf 검증): `L knee` 굴곡 **−140°**·과신전 **+10°**, `R knee` 굴곡 **−125°**·과신전 +10°. + **hip_pitch도 비대칭**(L±50°/R±40°) = 일반 CAD 결함.
  - ⚠ **+10° 과신전 = 병리선** → 정책의 "과신전 락" 치트면.
- **→ 권장(검증 기반)**: 과신전 +10→**~0° (여유 +2-3° max)**, **L/R 무릎 대칭화**(+ hip_pitch도). **USD 재변환 필요 = 사용자 확인 후**(보류).

## Q2 — 굽힌 무릎: 이미 nominal은 됨, *유지·흡수*가 남음
- **왜 인간이 굽히나**: 곧은 다리 = 운동학 특이점 + **짧은 충격시간 → 큰 무릎 힘**. 굽힌 무릎 = 컴플라이언트 흡수. 보행 "double knee bend": **loading response 15-20° 굴곡**(초기 stance, eccentric quad 흡수) → swing peak 60°. Kuo: heel-strike collision 음의 일(**0.205 J/kg·step**)이 걸음길이⁴로 늘어 → 굽힌 무릎이 충돌 완화 = **에너지 감소**. 곧은 무릎은 *정지(screw-home 락)*서만 정당.
- **이미 된 것**: flexed nominal(knee −22.9°) ✅.
- **남은 일** (검증된 gap): **무릎 자세/한계 보상 없음**(dof_pos_limits=발목만·joint_deviation=hip만) → 에너지-min이 −22.9°를 풀어 곧게 만들 수도, 과신전 스톱에 park할 수도 있는데 막는 게 없음.
  - **→ 추가**: ① **무릎 joint_deviation**(target ~−0.30~−0.40rad, w~−0.05~−0.1) ② **무릎 dof_pos_limits**(과신전 스톱 park 벌점) ③ **loading-response 흡수 보상**(접지서 GRF 상승 시 ~15-20° 무릎 굴곡 + GRF 상승률 페널티 = collision 완화, [[29_natural_gait_reward_hw]]의 collision 항과 통합).
  - 단 **얕게**: 깊은 crouch(BHBK)는 대사 **+50-60%**(Carey&Crompton).

## 검증 비교 (로봇 관례)
- **Cassie**: 무릎 −164~−37°(항상 ≥37° 굴곡, **과신전 0**, bird topology). **H1**: nominal 무릎 0.3rad(~17° 굴곡). → 둘 다 **과신전 없음 + flexed nominal** = 우리 방향 맞음.

## 추후 업데이트 (미검증/확인 필요)
- screw-home 각도(10° vs 15° 출처 상이)·genu recurvatum 수술 임계(단일출처)·gait 무릎각%(PT 2차출처, Perry 원전 미fetch)·"곧은무릎=GRF X%↑"(정량 1차출처 없음)·Carey&Crompton 정확%·Digit/ATRIAS 스펙(미fetch).
- **측정 확인**: 학습된 정책서 무릎 −0.40rad가 stance서 *유지되나* vs 에너지-min이 곧게 펴나(measure.py).
- 새 무릎 보상 3종 가중 config-test 튜닝.
