# Training TensorBoard 분석 — 2026-06-28_23-58-20_g1is_v2_flat

![tb](assets/2026-06-28_23-58-20_g1is_v2_flat_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.99 → **0.20** (수렴 ✅)
- **mean_reward**: -0.5 → **49.1**, ep_len 최종 **1000**
- **추종 error_vel_xy**: 최종 **0.245** (낮을수록 good), yaw 0.266
- **안정성 낙상률 0%** (base_contact 0.04 / time_out 8.75) (안정 ✅)
- **value loss 최종** 0.005, entropy -5.087, LR 5.1e-05
- **커리큘럼 vx 상한 최종** nan

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

