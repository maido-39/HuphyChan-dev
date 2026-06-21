# Training TensorBoard 분석 — stage-4 rough

![tb](assets/stage4_rough_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.32 → **0.47** (미수렴·탐색↑ ⚠️ (std 증가))
- **mean_reward**: 0.4 → **22.2**, ep_len 최종 **909**
- **추종 error_vel_xy**: 최종 **1.081** (낮을수록 good), yaw 0.683
- **안정성 낙상률 20%** (base_contact 1.83 / time_out 7.38) (낙상多 ❌)
- **value loss 최종** 0.077, entropy 6.016, LR 8.6e-04
- **커리큘럼 vx 상한 최종** 2.00

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

