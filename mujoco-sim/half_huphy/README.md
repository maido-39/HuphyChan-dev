# Half Huphy RL — 밸런스 + 퐁퐁(점프) 학습

mjlab 위에서 돌리는 **Half Huphy(한쪽 다리)** balance / hop 태스크 산출물.
upstream `mujocolab/mjlab` 본체는 여기 없고, 동료는 clone 후 `sync_to_mjlab.sh`로 얹는다.
(Pygmalion과 같은 패턴: `../pygmalion/`)

## 구성

| 경로 | 내용 |
|------|------|
| `robots_half_huphy/` | MJCF·메시·`half_huphy_constants.py` → `asset_zoo/robots/half_huphy/` |
| `tasks_half_huphy/` | balance + jump MDP/env/rl → `tasks/half_huphy/` |
| `sync_to_mjlab.sh` | 위 디렉토리 복사 + 로봇 import 패치 |
| `REGISTRATION.md` | 수동 등록 요약 |

## 동료 사용법

```bash
# 1) mjlab 본체 (최근 main 권장; 작업 당시 tip 예: 66742ce5)
git clone https://github.com/mujocolab/mjlab.git
cd mjlab
# git checkout <known-good>   # 선택

# 2) 이 폴더 적용 (HuphyChan-dev 안 경로 예시)
bash /path/to/HuphyChan-dev/mujoco-sim/half_huphy/sync_to_mjlab.sh .

# 3) 환경
uv sync

# 4) 태스크 확인
uv run list-envs | grep HalfHuphy
```

### 학습

```bash
# 밸런싱(서기)
uv run train Mjlab-Balance-HalfHuphy --env.scene.num-envs 4096

# 퐁퐁 — 권장(무릎 웅크림 + ankle ±14 Nm)
uv run train Mjlab-JumpKneeAnkle14-HalfHuphy \
  --env.scene.num-envs 4096 \
  --agent.run-name hop_knee_ankle14

# 퐁퐁 — 토크 soft-limit + push×2 + 지면마찰 DR
uv run train Mjlab-JumpKneeAnkle14Torque-HalfHuphy \
  --env.scene.num-envs 4096 \
  --agent.run-name hop_knee_ankle14_torque
```

로그: `logs/rsl_rl/<experiment_name>/<timestamp>_.../`

### Play

```bash
uv run play Mjlab-JumpKneeAnkle14-HalfHuphy \
  --checkpoint-file logs/rsl_rl/half_huphy_jump_knee_ankle14/<run>/model_29999.pt \
  --num-envs 1 --viewer native

# headless면 --viewer 생략 / null
uv run play Mjlab-Balance-HalfHuphy \
  --checkpoint-file <ckpt.pt> --num-envs 1
```

## 태스크 한줄 요약

| Task ID | 설명 |
|---------|------|
| `Mjlab-Balance-HalfHuphy` | 서기 / 밸런스 |
| `Mjlab-Jump-HalfHuphy` | 기본 홉 스케줄 + clearance curriculum |
| `Mjlab-JumpKnee-HalfHuphy` | + 무릎 crouch 40° / extend |
| `Mjlab-JumpKnee60-HalfHuphy` | 무릎 60° (학습 어려움) |
| `Mjlab-JumpKneeAnkle14-HalfHuphy` | JumpKnee + ankle ±14 Nm 등 |
| `Mjlab-JumpKneeAnkle14Torque-HalfHuphy` | Ankle14 + τ soft-limit + push×2 + μ DR |

Jump curriculum(개략): clearance 5→10→15→20 cm, stance 단축, push / motor DR 포함.
자세한 MDP는 `tasks_half_huphy/jump/mdp.py`, env 플래그는 `jump/env_cfgs.py`.

## IMU 좌표 (제로 포즈)

- **+Z** = up  
- **발가락 / forward ≈ −Y**  
- 정면 −Y 기준 **+X = left**, **−X = right**  
- X=발가락, Y=안쪽, Z=위로 붙이지 말 것.

## 체크포인트

`weights/` 에 태스크별 핵심 `.pt` 를 넣어 두었다. 목록·play 예시는 [`weights/WEIGHTS.md`](weights/WEIGHTS.md).

```bash
uv run play Mjlab-JumpKneeAnkle14-HalfHuphy \
  --checkpoint-file /path/to/HuphyChan-dev/mujoco-sim/half_huphy/weights/jump_knee_ankle14/model_29999.pt \
  --num-envs 1 --viewer native
```

## HuphyChan에서 수정할 때

1. 여기 `robots_half_huphy/` / `tasks_half_huphy/` 수정  
2. `bash sync_to_mjlab.sh ../mjlab` 로 로컬 mjlab에 반영  
3. HuphyChan에 commit (mjlab submodule tip은 동료에게 안 보임 — **이 폴더가 공유 소스**)
