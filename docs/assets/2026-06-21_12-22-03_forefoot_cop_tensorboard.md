# Training TensorBoard 분석 — 2026-06-21_12-22-03_forefoot_cop

![tb](assets/2026-06-21_12-22-03_forefoot_cop_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.32 → **0.27** (정체 ~)
- **mean_reward**: 0.6 → **39.7**, ep_len 최종 **984**
- **추종 error_vel_xy**: 최종 **0.545** (낮을수록 good), yaw 0.455
- **안정성 낙상률 3%** (base_contact 0.38 / time_out 13.00) (안정 ✅)
- **value loss 최종** 0.013, entropy -0.464, LR 3.8e-04
- **커리큘럼 vx 상한 최종** 2.00

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

