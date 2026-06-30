# Training TensorBoard 분석 — 2026-06-21_16-30-58_forefoot_pushoff2

![tb](assets/2026-06-21_16-30-58_forefoot_pushoff2_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.27 → **0.27** (정체 ~)
- **mean_reward**: 0.7 → **40.7**, ep_len 최종 **994**
- **추종 error_vel_xy**: 최종 **0.589** (낮을수록 good), yaw 0.458
- **안정성 낙상률 1%** (base_contact 0.21 / time_out 14.46) (안정 ✅)
- **value loss 최종** 0.022, entropy -0.347, LR 3.8e-04
- **커리큘럼 vx 상한 최종** 2.00

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

