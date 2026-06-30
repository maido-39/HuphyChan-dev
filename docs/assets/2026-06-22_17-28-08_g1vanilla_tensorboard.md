# Training TensorBoard 분석 — 2026-06-22_17-28-08_g1vanilla

![tb](assets/2026-06-22_17-28-08_g1vanilla_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.99 → **1.04** (정체 ~)
- **mean_reward**: 0.1 → **22.9**, ep_len 최종 **926**
- **추종 error_vel_xy**: 최종 **0.529** (낮을수록 good), yaw 0.957
- **안정성 낙상률 22%** (base_contact 1.67 / time_out 6.00) (낙상多 ❌)
- **value loss 최종** 0.048, entropy 14.793, LR 3.8e-04
- **커리큘럼 vx 상한 최종** nan

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

