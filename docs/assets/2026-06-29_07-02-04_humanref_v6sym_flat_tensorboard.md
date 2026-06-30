# Training TensorBoard 분석 — 2026-06-29_07-02-04_humanref_v6sym_flat

![tb](assets/2026-06-29_07-02-04_humanref_v6sym_flat_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.32 → **0.35** (미수렴·탐색↑ ⚠️ (std 증가))
- **mean_reward**: 0.8 → **59.8**, ep_len 최종 **974**
- **추종 error_vel_xy**: 최종 **0.282** (낮을수록 good), yaw 0.315
- **안정성 낙상률 3%** (base_contact 0.29 / time_out 9.29) (안정 ✅)
- **value loss 최종** 0.011, entropy 0.208, LR 7.6e-05
- **커리큘럼 vx 상한 최종** nan

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

