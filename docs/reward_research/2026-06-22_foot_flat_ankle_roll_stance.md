# reward 연구 — 발 edge / ankle_roll 과부하 (2026-06-22)
> 트리거: gaitfix_v3 측정 — ankle_roll 여전히 100%peak/110%cont 포화, 발 edge 18°(foot_roll_flat −0.5로 20→18°만). 바꾸려는 reward: foot_roll_flat 강화? 연구(workflow `wycgc5rlb`, 3 agent, high confidence).

## 1. 직전 결과 분석 ([[experiments/2026-06-22_02-44-30_gaitfix_v3]])
- 무릎(하이퍼익스텐션 제거)·토우(13°)는 개선. **ankle_roll 미해소**: 토크 max14(100%peak)·RMS5.5(110%cont 열과부하), edge각 20→18°(미미).
- → 관측: foot_roll_flat(ankle_roll 각² 페널티, −0.5)이 edge를 거의 못 줄임.

## 2. 이전 이력
- ankle_roll(RS00 14N·m)은 처음부터 binding actuator([[36_all_actuator_tn_envelopes]]·[[37_ankle_linkage_fidelity]]). 발 edge→roll 과부하 가설(사용자). forefoot_cop·ankle_pushoff 시도사.

## 3. 학술/자료조사 (high confidence)
- ★ **생체역학(Reimann/Fettrow/Jeka 2018·Reimann PLOS 2019)**: ankle 내번/외번(roll)이 **단일지지 측면균형의 주 CoP 조절 기구**. 단 그 CoP 범위는 **발 너비에 물리적으로 cap**. 좁은 stance→큰 ankle-roll(edge적재) 강요. **넓은 stance(예 27cm)는 바깥날 rolling을 막고 측면안정↑**. 측면균형의 *1차* 기구는 **foot placement(step width)**, ankle은 보조. [출처](https://jekalab.org/wp-content/uploads/2018/02/Reimann-Fettrow-Jeka_2018.pdf)
- **RL 표준 = foot-BODY orientation 페널티**(우리처럼 *관절각* 아님): `flat_orientation_l2 = sum(square(projected_gravity_b[:,:2]))`를 **발 링크**에 적용(발 normal vs world up). 관절각은 base lean·hip-roll·지형에 따라 실제 접촉기울기와 달라 *오귀속*. [legged_gym](https://github.com/leggedrobotics/legged_gym)·[IsaacLab](https://github.com/isaac-sim/IsaacLab/blob/main/source/isaaclab/isaaclab/envs/mdp/rewards.py).
- **가중치(중요)**: 균형부담이라 작게: Booster Gym([2506.15132](https://arxiv.org/html/2506.15132v1))·SoFTA = base ||g||² **−5.0**, **feet roll ||φ||² −0.1**(의도적 작음), feet yaw −1.0. 크게 주면 균형 해침.
- 근원해법 동반: **stance-width target + hip-roll 측면균형 경로**(ankle 대신 hip이 측면부담 분담), feet_contact_force 페널티(edge stomp 억제), sole-sample-point 거리분산(edge 직접·더 sharp).

## 4. 원인·문제 규명
- ★ edge-walking은 **(a) reward 결함 아님**. **(c) STANCE-WIDTH 부족이 (b) 실제 측면균형 need를 ankle_roll로 풀게 강요**. (d) 발 geometry는 ceiling만. 18° plateau = 페널티 vs 균형 평형 → *관절각만 더 누르면 안 됨*(검증됨).
- 우리 `foot_roll_flat`은 **(i) 관절각**(body orientation 아님)이라 약하고 **(ii) 대안 균형 handle 없이** 눌러서 막힘.

## 5. 제안 (gaitfix_v4 — reward 변경 + 왜)
1. ★ **STANCE 넓히기(근원)**: yaml init hip_roll 0→**+0.06rad**(외전) + `feet_distance` min 0.20→**0.24**(넓은 target). = 측면 CoP를 *넓은 base*에서 → ankle_roll 명령 감소. (생체역학: CoP가 발너비에 cap, wide stance가 edge-roll 제거.)
2. **foot_roll_flat(관절각) → foot-BODY orientation** 으로 교체: `sum(proj_grav_of_FOOT[:,:2]²)` per foot, weight **−0.3**(작게, 균형 안 해치게). 관절각보다 실제 접촉평탄 직접 타깃.
3. (선택) hip-roll이 측면부담 분담하도록 — wide stance가 그 경로 제공.
4. ★ **검증 = HW 질문의 답**: 재측정시 **ankle_roll RMS 떨어지면 → gait/stance 결함**(RS00 OK, 모터상향·2-RSU 불필요). **넓은 평탄 stance서도 포화 유지면 → RS00 14N·m 진짜 부족(HW under-spec)** → 그때 상향/2-RSU/링크 정당. **이 실험이 "gait artifact vs HW 부족"을 판별**.

출처: 위 하이퍼링크. verified=생체역학·repo 공식 / 추정=우리 케이스 적용은 실험으로 확인.
