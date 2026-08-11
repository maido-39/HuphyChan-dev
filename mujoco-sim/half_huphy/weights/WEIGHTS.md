# Half Huphy checkpoints

경로: `mujoco-sim/half_huphy/weights/<task>/model_*.pt`  
play는 sync한 mjlab에서, `--checkpoint-file`에 이 파일 경로를 주면 된다.

| 폴더 | Task ID | 권장 ckpt | 출처 run |
|------|---------|-----------|----------|
| `balance/` | `Mjlab-Balance-HalfHuphy` | `model_34699.pt` | `20deg_rand_push2p0_from4700` |
| `jump/` | `Mjlab-Jump-HalfHuphy` | `model_31499.pt` | `hop_w2x_clear10_from1500` |
| `jump_knee/` | `Mjlab-JumpKnee-HalfHuphy` | `model_20150.pt` | `hop_knee_crouch_extend` |
| `jump_knee_ankle14/` | `Mjlab-JumpKneeAnkle14-HalfHuphy` | `model_29999.pt` | `hop_knee_ankle14` |
| `jump_knee_ankle14_torque/` | `Mjlab-JumpKneeAnkle14Torque-HalfHuphy` | `model_29999.pt` | `..._push1_fricDR` |

중간 스텝 (토크 비교용):
- `jump_knee_ankle14/model_8500.pt`, `model_14000.pt`
- `jump_knee_ankle14_torque/model_8000.pt`

```bash
# 예: Ankle14 최종
uv run play Mjlab-JumpKneeAnkle14-HalfHuphy \
  --checkpoint-file /path/to/HuphyChan-dev/mujoco-sim/half_huphy/weights/jump_knee_ankle14/model_29999.pt \
  --num-envs 1 --viewer native
```
