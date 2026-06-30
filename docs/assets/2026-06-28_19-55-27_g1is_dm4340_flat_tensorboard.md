# Training TensorBoard 분석 — 2026-06-28_19-55-27_g1is_dm4340_flat

![tb](assets/2026-06-28_19-55-27_g1is_dm4340_flat_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.99 → **0.31** (수렴 ✅)
- **mean_reward**: -0.3 → **51.9**, ep_len 최종 **1000**
- **추종 error_vel_xy**: 최종 **0.228** (낮을수록 good), yaw 0.244
- **안정성 낙상률 0%** (base_contact 0.00 / time_out 4.33) (안정 ✅)
- **value loss 최종** 0.005, entropy -0.264, LR 2.6e-04
- **커리큘럼 vx 상한 최종** nan

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

