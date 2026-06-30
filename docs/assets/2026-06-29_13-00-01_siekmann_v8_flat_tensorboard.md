# Training TensorBoard 분석 — 2026-06-29_13-00-01_siekmann_v8_flat

![tb](assets/2026-06-29_13-00-01_siekmann_v8_flat_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.99 → **0.15** (수렴 ✅)
- **mean_reward**: -0.3 → **75.7**, ep_len 최종 **1000**
- **추종 error_vel_xy**: 최종 **0.272** (낮을수록 good), yaw 0.239
- **안정성 낙상률 0%** (base_contact 0.00 / time_out 9.00) (안정 ✅)
- **value loss 최종** 0.004, entropy -8.212, LR 1.7e-04
- **커리큘럼 vx 상한 최종** nan

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

