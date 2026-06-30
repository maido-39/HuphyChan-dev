# Training TensorBoard 분석 — 2026-06-21_21-59-35_softcontact2

![tb](assets/2026-06-21_21-59-35_softcontact2_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.23 → **0.27** (미수렴·탐색↑ ⚠️ (std 증가))
- **mean_reward**: 0.4 → **25.6**, ep_len 최종 **972**
- **추종 error_vel_xy**: 최종 **0.705** (낮을수록 good), yaw 1.094
- **안정성 낙상률 4%** (base_contact 0.29 / time_out 6.42) (안정 ✅)
- **value loss 최종** 0.027, entropy -0.013, LR 2.6e-04
- **커리큘럼 vx 상한 최종** 1.13

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

