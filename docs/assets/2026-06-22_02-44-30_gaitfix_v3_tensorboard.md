# Training TensorBoard 분석 — 2026-06-22_02-44-30_gaitfix_v3

![tb](assets/2026-06-22_02-44-30_gaitfix_v3_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.28 → **0.26** (정체 ~)
- **mean_reward**: 0.2 → **37.6**, ep_len 최종 **992**
- **추종 error_vel_xy**: 최종 **0.565** (낮을수록 good), yaw 0.527
- **안정성 낙상률 2%** (base_contact 0.08 / time_out 5.25) (안정 ✅)
- **value loss 최종** 0.017, entropy -0.097, LR 5.8e-04
- **커리큘럼 vx 상한 최종** 2.00

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

