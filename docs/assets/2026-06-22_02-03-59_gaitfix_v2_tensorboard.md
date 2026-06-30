# Training TensorBoard 분석 — 2026-06-22_02-03-59_gaitfix_v2

![tb](assets/2026-06-22_02-03-59_gaitfix_v2_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.28 → **0.29** (미수렴·탐색↑ ⚠️ (std 증가))
- **mean_reward**: 0.2 → **37.8**, ep_len 최종 **992**
- **추종 error_vel_xy**: 최종 **0.528** (낮을수록 good), yaw 0.535
- **안정성 낙상률 2%** (base_contact 0.21 / time_out 9.75) (안정 ✅)
- **value loss 최종** 0.020, entropy 0.840, LR 3.8e-04
- **커리큘럼 vx 상한 최종** 1.48

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

