# Training TensorBoard 분석 — 2026-06-29_22-48-47_siekmann_pushoff_v9_flat

![tb](assets/2026-06-29_22-48-47_siekmann_pushoff_v9_flat_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.15 → **0.11** (수렴 ✅)
- **mean_reward**: 0.9 → **84.0**, ep_len 최종 **1000**
- **추종 error_vel_xy**: 최종 **0.299** (낮을수록 good), yaw 0.224
- **안정성 낙상률 0%** (base_contact 0.00 / time_out 11.12) (안정 ✅)
- **value loss 최종** 0.003, entropy -11.800, LR 1.1e-04
- **커리큘럼 vx 상한 최종** nan

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

