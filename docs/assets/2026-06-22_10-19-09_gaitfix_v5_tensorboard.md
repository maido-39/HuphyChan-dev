# Training TensorBoard 분석 — 2026-06-22_10-19-09_gaitfix_v5

![tb](assets/2026-06-22_10-19-09_gaitfix_v5_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.25 → **0.26** (정체 ~)
- **mean_reward**: 0.4 → **43.0**, ep_len 최종 **991**
- **추종 error_vel_xy**: 최종 **0.549** (낮을수록 good), yaw 0.497
- **안정성 낙상률 1%** (base_contact 0.08 / time_out 6.33) (안정 ✅)
- **value loss 최종** 0.013, entropy -0.368, LR 3.8e-04
- **커리큘럼 vx 상한 최종** 2.00

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

