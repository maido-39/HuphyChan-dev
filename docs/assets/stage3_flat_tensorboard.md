# Training TensorBoard 분석 — stage-3 flat ankle-offload

![tb](assets/stage3_flat_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.37 → **0.32** (정체 ~)
- **mean_reward**: 0.5 → **36.2**, ep_len 최종 **1000**
- **추종 error_vel_xy**: 최종 **0.502** (낮을수록 good), yaw 0.507
- **안정성 낙상률 1%** (base_contact 0.21 / time_out 15.29) (안정 ✅)
- **value loss 최종** 0.014, entropy 1.314, LR 3.8e-04
- **커리큘럼 vx 상한 최종** 2.00

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

