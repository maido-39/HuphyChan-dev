# Training TensorBoard 분석 — 2026-06-29_10-30-47_humanref_v7_flat

![tb](assets/2026-06-29_10-30-47_humanref_v7_flat_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.24 → **0.21** (정체 ~)
- **mean_reward**: 1.3 → **88.4**, ep_len 최종 **1000**
- **추종 error_vel_xy**: 최종 **0.385** (낮을수록 good), yaw 0.409
- **안정성 낙상률 0%** (base_contact 0.00 / time_out 4.00) (안정 ✅)
- **value loss 최종** 0.011, entropy -3.766, LR 1.1e-04
- **커리큘럼 vx 상한 최종** nan

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

