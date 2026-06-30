# Training TensorBoard 분석 — forefoot iter~1230

![tb](assets/forefoot_mid_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.32 → **0.28** (정체 ~)
- **mean_reward**: 0.6 → **40.4**, ep_len 최종 **1000**
- **추종 error_vel_xy**: 최종 **0.530** (낮을수록 good), yaw 0.459
- **안정성 낙상률 0%** (base_contact 0.04 / time_out 11.79) (안정 ✅)
- **value loss 최종** 0.014, entropy -0.333, LR 3.8e-04
- **커리큘럼 vx 상한 최종** 2.00

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

