# Training TensorBoard 분석 — 2026-06-21_15-40-30_forefoot_pushoff

![tb](assets/2026-06-21_15-40-30_forefoot_pushoff_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.27 → **0.34** (미수렴·탐색↑ ⚠️ (std 증가))
- **mean_reward**: 0.7 → **484.5**, ep_len 최종 **975**
- **추종 error_vel_xy**: 최종 **1.732** (낮을수록 good), yaw 1.618
- **안정성 낙상률 6%** (base_contact 0.88 / time_out 12.62) (주의 ⚠️)
- **value loss 최종** 17.723, entropy 2.802, LR 2.6e-04
- **커리큘럼 vx 상한 최종** 1.49

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

