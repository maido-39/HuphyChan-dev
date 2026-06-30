# Training TensorBoard 분석 — 2026-06-22_19-04-51_g1van_full

![tb](assets/2026-06-22_19-04-51_g1van_full_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 1.00 → **0.33** (수렴 ✅)
- **mean_reward**: 0.2 → **52.8**, ep_len 최종 **1000**
- **추종 error_vel_xy**: 최종 **0.186** (낮을수록 good), yaw 0.274
- **안정성 낙상률 0%** (base_contact 0.00 / time_out 13.50) (안정 ✅)
- **value loss 최종** 0.004, entropy -0.970, LR 1.7e-04
- **커리큘럼 vx 상한 최종** nan

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

