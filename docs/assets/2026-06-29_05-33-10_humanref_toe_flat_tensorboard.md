# Training TensorBoard 분석 — 2026-06-29_05-33-10_humanref_toe_flat

![tb](assets/2026-06-29_05-33-10_humanref_toe_flat_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.24 → **0.21** (정체 ~)
- **mean_reward**: 0.9 → **65.8**, ep_len 최종 **1000**
- **추종 error_vel_xy**: 최종 **0.305** (낮을수록 good), yaw 0.331
- **안정성 낙상률 0%** (base_contact 0.00 / time_out 5.33) (안정 ✅)
- **value loss 최종** 0.006, entropy -4.722, LR 7.6e-05
- **커리큘럼 vx 상한 최종** nan

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

