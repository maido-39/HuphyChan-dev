# Training TensorBoard 분석 — 2026-06-21_10-33-47_stage5_rough_converge

![tb](assets/2026-06-21_10-33-47_stage5_rough_converge_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.47 → **0.62** (미수렴·탐색↑ ⚠️ (std 증가))
- **mean_reward**: 0.3 → **5.3**, ep_len 최종 **879**
- **추종 error_vel_xy**: 최종 **0.918** (낮을수록 good), yaw 0.989
- **안정성 낙상률 20%** (base_contact 1.88 / time_out 7.29) (낙상多 ❌)
- **value loss 최종** 0.141, entropy 10.124, LR 5.8e-04
- **커리큘럼 vx 상한 최종** 2.00

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

