# Training TensorBoard 분석 — stage-5 rough converge (in-progress)

![tb](assets/stage5_rough_converge_tensorboard.png)

## 자동 평가 (정량)
- **수렴(noise_std)**: 0.47 → **0.54** (미수렴·탐색↑ ⚠️ (std 증가))
- **mean_reward**: 0.3 → **10.4**, ep_len 최종 **812**
- **추종 error_vel_xy**: 최종 **0.858** (낮을수록 good), yaw 0.845
- **안정성 낙상률 24%** (base_contact 2.38 / time_out 7.33) (낙상多 ❌)
- **value loss 최종** 0.098, entropy 8.215, LR 3.8e-04
- **커리큘럼 vx 상한 최종** 2.00

## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**

