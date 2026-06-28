# 2026-06-29 · 까치발(tiptoe) 근본원인 = base_height 제약 회귀 (gaitfix→G1)

> 트리거(user): "gaitfix 계통은 8자걸음(figure-8)이었지 까치발은 없었다. 까치발은 Critical하니 **근본원인**을 찾아 해결(학습/수학)하고 학습 이어가라." → reward 덧칠(v1 swing_height·v2 foot_flat·v3 human-ref)이 아니라 **무엇이 바뀌어 까치발이 생겼는지** 회귀분석. 규칙 [[feedback-reward-research-rule]]. 검증 워크플로 `tiptoe-root-cause`(wbpisjawi, 진행).

## ★ 근본원인 (직접 증거)
**까치발은 RL 본질 문제가 아니라 G1 계통에서 생긴 회귀** — gaitfix(BipedRewards)→G1(G1VanillaRewards) 전환서 **자세 제약항들을 버림**:
1. **git `527fd48`** = "reward_tuning robot model 채택 + G1ImpactStable reward" = G1 계통(=까치발) 시작점.
2. **G1VanillaRewards 주석이 명시**: *"NO forefoot_cop / ankle_pushoff / cop_progression / foot_roll_flat / lateral_foot_placement / feet_distance / feet_lateral_sep / upright / **base_height** / power_cot / knee_straight / double_support. Just G1's terms."* → **gaitfix의 자세제약 전부 제거**.
3. gaitfix `BipedRewards`는 ★ **`base_height = base_height_l2, weight -1.0, target 0.85`** + `foot_roll_flat` + `upright` 보유.
4. **실측 base height**: gaitfix v5/v6/v7 = **0.803/0.825/0.828 (평발)** vs **g1is_dm4340 0.952 (까치발)**. v2(foot_flat) 0.738.

## 메커니즘 (수학)
`base_height_l2 = (base_z − 0.85)²` (weight −1.0, track와 동급 강도).
- **제거 시(G1)**: PPO가 속도추종 reach를 키우려 **다리를 신전** → base 0.95. 발을 지면에 붙이는 유일한 방법 = **발목 plantarflex = 까치발**. ankle plantarflex도 G1서 무벌점 → 까치발이 자유로운 attractor.
- **존재 시(gaitfix)**: base를 0.85로 끌어 **다리가 굽은 채** 유지 → 신전 불가 → 발목 중립 → **평발**.
- v2 foot_flat(−0.5)이 부분효과(base 0.95→0.74)였던 건 **증상(발 기울기)을 약하게 친 것**; base_height는 **원인(신전 유인)을 제거**.

## figure-8 vs 까치발 구분
gaitfix의 **lateral 항**(feet_distance −2.0, lateral_foot_placement, feet_lateral_sep)이 발을 벌려 **figure-8(8자)** 유발 — 이건 별개 문제. **자세 항**(base_height, foot_roll_flat, upright)이 **평발** 유지. G1은 둘 다 버려 figure-8은 없으나 까치발 발생.

## ★ 해결 (근본 fix, 적용함)
**`base_height` 복원**(gaitfix 검증값: `mdp.base_height_l2`, weight **−1.0**, target **0.85**)을 human-ref config(`_apply_human_ref`)에 추가. = **버린 근본 제약을 되돌림**(증상 패치 아님). lateral 항은 **복원 안 함**(figure-8 원인; 대칭 human-ref엔 불필요).
- 1차는 **base_height 단독**(원인 격리·검증). 부족 시(발 여전히 기울면) `foot_roll_flat`(gaitfix의 발-body 평탄항) 추가.
- human-ref(v3, base_height 無) **vs** human-ref+base_height(v4) 비교 = base_height 효과 **귀속(attribution)**.

## 검증
- ★ **base_height ~0.85** (g1is 0.95 → ↓) = 신전 억제.
- `gait_toe_timing.py`: toe 최대굽힘이 push-off대로 이동 / 발 평탄.
- `gait_humanlikeness.py`: score↑·corr↑·GRF 대칭.
- 낙상<5%·error_vel≤0.3·noise_std 수렴.

## refs
git 527fd48·189db20 · `velocity_env_cfg.py:94`(base_height -1.0@0.85)·`g1_vanilla_env_cfg.py`(G1VanillaRewards 주석)·`mdp/rewards.py:20`(base_height_l2) · 실측 gaitfix_v5-7 vs g1is_dm4340 npz · 워크플로 wbpisjawi(확정+geometry 점검) · [[2026-06-29_human_gait_reference]]·[[experiments/2026-06-28_19-55-27_g1is_dm4340_flat]].
