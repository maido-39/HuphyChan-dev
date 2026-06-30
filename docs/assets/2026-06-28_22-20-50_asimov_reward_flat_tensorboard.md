# Training TensorBoard 분석 — 2026-06-28_22-20-50_asimov_reward_flat

![tb](assets/2026-06-28_22-20-50_asimov_reward_flat_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.99 → **0.26** (수렴 ✅)
- **mean_reward**: -0.3 → **50.6**, ep_len 최종 **982**
- **추종 error_vel_xy**: 최종 **0.217** (낮을수록 good), yaw 0.228
- **안정성 낙상률 1%** (base_contact 0.12 / time_out 9.04) (안정 ✅)
- **value loss 최종** 0.006, entropy -1.651, LR 2.6e-04
- **커리큘럼 vx 상한 최종** nan

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

