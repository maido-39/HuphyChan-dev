# Training TensorBoard 분석 — 2026-06-22_03-53-57_gaitfix_v4

![tb](assets/2026-06-22_03-53-57_gaitfix_v4_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.26 → **0.25** (정체 ~)
- **mean_reward**: 0.4 → **37.2**, ep_len 최종 **974**
- **추종 error_vel_xy**: 최종 **0.547** (낮을수록 good), yaw 0.501
- **안정성 낙상률 5%** (base_contact 0.33 / time_out 6.58) (안정 ✅)
- **value loss 최종** 0.016, entropy -0.514, LR 3.8e-04
- **커리큘럼 vx 상한 최종** 2.00

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

