# Training TensorBoard 분석 — 2026-06-22_02-36-09_gaitfix_collisiontest

![tb](assets/2026-06-22_02-36-09_gaitfix_collisiontest_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.28 → **0.31** (미수렴·탐색↑ ⚠️ (std 증가))
- **mean_reward**: 0.1 → **14.0**, ep_len 최종 **819**
- **추종 error_vel_xy**: 최종 **0.647** (낮을수록 good), yaw 0.580
- **안정성 낙상률 38%** (base_contact 0.88 / time_out 1.42) (낙상多 ❌)
- **value loss 최종** 0.050, entropy 1.523, LR 2.6e-04
- **커리큘럼 vx 상한 최종** 1.06

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

