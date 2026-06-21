# 무릎 생체역학 — 로봇 설계 (살아있는 노트)

> [!info] 상태: **학술조사 진행 중(wsx14ecd0)** — 완료 시 검증 수치로 본문 작성 + [[raw/knee-biomechanics]] 적재. 아래는 config 기반 잠정.
> 사용자 체감 관찰(무릎 역관절 안 됨·기본 자세 굽힘) → 설계. [[29_natural_gait_reward_hw]] · [[Paperreview/kuo-donelan-dynamic-walking]].

## Q1 — 과신전/ROM (잠정, 검증 예정)
- 인간 무릎 = **굴곡 전용**(~0–140°), 과신전 0~5°(그 이상 genu recurvatum). 역관절 X.
- 우리 로봇 (robot.xml): `L_knee [−140°, **+10°**]`, `R_knee [−125°, +10°]`.
  - ⚠ **+10° 과신전은 인간(~5°)보다 큼** → 정책이 과신전으로 "락" 가능.
  - ⚠ **L/R 비대칭**(L 140° vs R 125° 굴곡) = MJCF 결함.
- → **권장(검증 후 확정)**: 과신전 +10→~+3-5°, L/R 대칭화. **USD 재변환 필요 = 사용자 확인 후 진행**(보류).

## Q2 — 왜 로봇은 무릎을 안 굽히나 (잠정)
- **원인**: 기본자세(`keyframe "stand"`) 전관절 0 = 곧은 무릎 + **무릎 자세 보상 없음**(hip만 joint_deviation) + **에너지(power_cot)가 곧은(락) 무릎 선호**(굴곡 유지=토크 비용).
- **인간**: 정지선 거의 펴서 락(screw-home, 절약) = 로봇 직립이 틀린 건 아님. 단 **보행 중엔 무릎 굽힘**(heel-strike 충격흡수=loading response ~15-20° 굴곡, eccentric quad).
- → **핵심 수정 = collision 페널티**(Kuo: 강한 heel-strike GRF 벌점 → 무릎 굴곡으로 흡수 emerge). **다음 reward 실험에 포함 예정.** 보조: 약간 굽힌 nominal·작은 무릎 deviation.

## 추후 업데이트 (학술조사 완료 시)
ROM·과신전 임계 / 보행 무릎 kinematics(loading-response·double-knee-bend·swing) / screw-home / 로봇설계(과신전 hard-stop·flexed nominal 관례) 검증 수치로 본문 + 권장 확정.
