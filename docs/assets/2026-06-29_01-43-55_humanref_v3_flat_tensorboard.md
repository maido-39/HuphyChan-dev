# Training TensorBoard 분석 — 2026-06-29_01-43-55_humanref_v3_flat

![tb](assets/2026-06-29_01-43-55_humanref_v3_flat_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.20 → **0.30** (미수렴·탐색↑ ⚠️ (std 증가))
- **mean_reward**: 0.8 → **59.0**, ep_len 최종 **975**
- **추종 error_vel_xy**: 최종 **0.286** (낮을수록 good), yaw 0.311
- **안정성 낙상률 5%** (base_contact 0.29 / time_out 5.67) (안정 ✅)
- **value loss 최종** 0.014, entropy 0.034, LR 1.7e-04
- **커리큘럼 vx 상한 최종** nan

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

