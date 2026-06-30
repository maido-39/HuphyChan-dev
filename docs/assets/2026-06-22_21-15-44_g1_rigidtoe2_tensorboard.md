# Training TensorBoard 분석 — 2026-06-22_21-15-44_g1_rigidtoe2

![tb](assets/2026-06-22_21-15-44_g1_rigidtoe2_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 1.00 → **0.31** (수렴 ✅)
- **mean_reward**: 0.1 → **52.8**, ep_len 최종 **991**
- **추종 error_vel_xy**: 최종 **0.207** (낮을수록 good), yaw 0.267
- **안정성 낙상률 1%** (base_contact 0.12 / time_out 13.17) (안정 ✅)
- **value loss 최종** 0.002, entropy -1.383, LR 5.1e-05
- **커리큘럼 vx 상한 최종** nan

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

