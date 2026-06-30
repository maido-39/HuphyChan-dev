# Training TensorBoard 분석 — 2026-06-29_03-43-21_humanref_baseh_flat

![tb](assets/2026-06-29_03-43-21_humanref_baseh_flat_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.20 → **0.24** (미수렴·탐색↑ ⚠️ (std 증가))
- **mean_reward**: 0.8 → **61.5**, ep_len 최종 **980**
- **추종 error_vel_xy**: 최종 **0.296** (낮을수록 good), yaw 0.328
- **안정성 낙상률 3%** (base_contact 0.12 / time_out 4.29) (안정 ✅)
- **value loss 최종** 0.006, entropy -3.388, LR 2.6e-04
- **커리큘럼 vx 상한 최종** nan

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

