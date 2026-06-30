# Training TensorBoard 분석 — forefoot iter~124 (mid-review)

![tb](assets/forefoot_cop_iter124_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.32 → **0.29** (정체 ~)
- **mean_reward**: 0.6 → **40.5**, ep_len 최종 **996**
- **추종 error_vel_xy**: 최종 **0.468** (낮을수록 good), yaw 0.489
- **안정성 낙상률 1%** (base_contact 0.17 / time_out 11.50) (안정 ✅)
- **value loss 최종** 0.012, entropy -0.054, LR 2.6e-04
- **커리큘럼 vx 상한 최종** 1.24

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

