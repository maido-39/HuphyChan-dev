# Training TensorBoard 분석 — 2026-06-22_12-29-19_gaitfix_v7

![tb](assets/2026-06-22_12-29-19_gaitfix_v7_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.26 → **0.26** (정체 ~)
- **mean_reward**: 0.5 → **45.1**, ep_len 최종 **1000**
- **추종 error_vel_xy**: 최종 **0.545** (낮을수록 good), yaw 0.514
- **안정성 낙상률 0%** (base_contact 0.00 / time_out 6.75) (안정 ✅)
- **value loss 최종** 0.014, entropy -0.540, LR 5.8e-04
- **커리큘럼 vx 상한 최종** 2.00

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

