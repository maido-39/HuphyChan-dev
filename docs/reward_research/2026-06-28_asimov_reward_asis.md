# 2026-06-28 · Menlo/Asimov 블로그 reward "그대로" 적용 실험 + 발생 문제

> 트리거(user): 블로그(https://menlo.ai/blog/teaching-a-humanoid-to-walk) reward를 그대로 적용해 한번 돌리고, 이렇게 돌리면 생기는 문제를 알려달라. config = `BipedAsimovRewardEnvCfg`(G1-vanilla=Unitree baseline + 블로그 mods). 분석근거 [[2026-06-28_menlo_blog_review]].

## 적용한 것 (faithful-as-possible)
G1-vanilla(블로그가 "inspired by Unitree/Booster/MJLab") + 블로그 명시 mods:
- ★ **feet_air_time → 실제-airtime 변종(mdp.feet_air_time) @ +0.5** (블로그 flight 레버; 우리 기본 positive_biped는 single-stance라 flight 안 나므로 교체).
- **ang_vel_xy_l2 -0.08** (블로그 body_ang_vel, 좁은 stance 안정).
- **gentle-feet 접촉력 벌점**(foot_impact_force -0.005; 블로그 "place feet gently").
- **비대칭 pose tolerance**: 발목 tight(joint_deviation ankle -0.5; 블로그 ankle 0.2/0.12), hip/knee loose.
- swing_height/cop/foot_flat/우리 impact·anti-trembling = **전부 제외**(블로그 minimal shaping).

## ★ 그대로 돌리면 생기는 문제 (예측 + 실측 예정)
1. ★★ **air_time +0.5 → flight phase → 착지 GRF 폭증**. 블로그 로봇은 *다리 16kg*이라 flight OK라 명시. **우리는 51.8kg → flight = 1.5-2.7kN HW 파손한계 초과 = 저충격 하중측정 목표와 정반대**. (실측: measure의 foot_impact_force/GRF peak가 클 것.) = 가장 큰 문제.
2. ★ **까치발/heel-toe 미해결**: minimal shaping(swing_height·foot_flat·cop 없음)이라 **plantigrade heel→toe를 강제하는 게 없음** → 까치발 지속(블로그도 heel-toe 안 함; Asimov는 발목 ROM 좁아 안 함). = 사용자 현 pain 그대로.
3. ★ **비대칭 발목 pose tolerance 미스매치**: 블로그 ankle 0.2/0.12는 Asimov **parallel-RSU 발목 ±20°/±15° ROM** 전용 HW사실. 우리 발목(DM-J4340, 다른 ROM)엔 안 맞음 → 발목 과구속(hobble) 또는 무의미.
4. ★ **reward-obs 결합 깨짐**: 블로그 reward는 자기 OBS(actor서 base_lin_vel 제외 + 비대칭 critic가 특권관측) 전제. **우리 stock obs(actor에 base_lin_vel, 비대칭 A-C 없음)**에 reward만 얹으면 블로그가 말한 **underdamped 진동** 위험 + 성능 저하 → "reward만 그대로"는 블로그 결과를 재현 못 함.
5. ★ **형태(morphology) 튜닝 미스매치**: 블로그 가중치는 Asimov 전용(좁은 21cm stance→body_ang_vel -0.08, 가벼운 다리→air_time +0.5, canted hip/backward knee). 우리 RobStride(51.8kg, 다른 기구)엔 안 맞아 불안정/절뚝 가능.
6. ★ **underspecified → 정확 재현 불가**: 블로그가 angular_momentum -0.03 외 contact 벌점·기본 가중치를 다 안 줌 → 근사. "그대로"가 원리상 불가.
7. **L/R 절뚝 미해결**: 블로그 reward는 우리 기존 절뚝을 안 다룸(대칭증강 필요).

## 결론(예상)
flight로 **충격↑(하중측정 무효)** + **까치발 지속** + (obs 미스매치) **진동/불안정** 가능. = "블로그 reward 그대로"는 *우리 목표(저충격·인간형·하중측정)*엔 부적합. 실측(measure 후) 확정. 우리 방향(swing_height+cop+비대칭A-C, 단 air_time 회피)이 타당한 이유의 대조군.

## ★ 실측 결과 (run 완료 → [[experiments/2026-06-28_22-20-50_asimov_reward_flat]])
대조 measure(vs g1is_dm4340) — **결론 방향은 예측대로(부적합), 단 메커니즘이 예상과 다름**:
- ✅ **충격↑ 확정**(예측#1): GRF peak **1991N=3.9×BW**(g1is 1079N=2.1×BW) → HW 파손범위(1.5-2.7kN) **진입** = 하중측정 무효.
- ❌ **flight 메커니즘은 빗나감**(예측#1 수정): flight 1.3%·**air_time 기여 -0.0164=DEAD** — 51.8kg는 flight 자체를 못 만듦. 충격↑는 flight가 아니라 **tight ankle deviation의 낮은 컴플라이언스(딱딱한 착지)** 탓.
- ⚠ **까치발은 오히려 덜함**(예측#2와 반대): base_h 0.864·ankle_roll 77% — tight tol이 측방 shuffle 억제.
- ★ **새 발견**: **ankle_pitch 243%rated 과부하**(블로그 joint_deviation_ankle -0.5가 발목을 neutral로 당겨 추종과 충돌; 예측#3 'ankle 과구속'의 실제 형태).
→ 순결론: 블로그 air_time/tight-ankle은 **우리 하중측정 로봇엔 부적합**(충격·발목과부하). v2(swing_height+foot_flat, air_time·tight-ankle 없이)로 진행. 상세 [[experiments/2026-06-28_22-20-50_asimov_reward_flat]] §5.

## 출처
[[2026-06-28_menlo_blog_review]](블로그 항목별 검증) · Menlo blog · IsaacLab mdp(feet_air_time 실제-airtime vs positive_biped 확인).
