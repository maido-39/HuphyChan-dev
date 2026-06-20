# pygmalion_locomotion

휴머노이드(하반신 이족, RobStride 구동) **사람형 보행 학습 워크스페이스**.
Isaac Lab을 **import만** 하는 외부 프로젝트입니다 (Isaac Lab 원본 무수정).

## 구성
```
source/pygmalion_locomotion/
  robots/biped_cfg.py            # ArticulationCfg (모터/관성/한계) + get_biped_cfg()
  tasks/locomotion/
    velocity_env_cfg.py          # BipedRoughEnvCfg (평지/계단/울퉁불퉁/경사) + rewards
    flat_env_cfg.py              # BipedFlatEnvCfg (평지)
    mdp/rewards.py               # 사람다움 보강 reward (base_height/upright/feet_distance/no_flight)
    agents/rsl_rl_ppo_cfg.py     # PPO 러너 cfg
  sensors/wrench_logger.py       # 관절토크/링크반력(6축)/발GRF → CSV·npz
  sensors/mass_utils.py          # 질량/관성 런타임 조정 (mass_scale, set_base_mass)
  ui/hud.py                      # 인-시뮬 HUD 오버레이 + GRF 화살표
scripts/
  convert_asset.py               # MJCF → USD
  train.py / play.py             # Isaac Lab rsl_rl 러너 사본 (+우리 태스크 등록 import)
  play_keyboard.py               # 키보드 텔레오프 + HUD + 로깅 (★ 핵심 산출물)
  measure.py                     # 측정 캠페인 (명령/질량 스윕 → 로깅)
  analyze.py                     # 오프라인 분석/플롯 (Isaac Sim 불필요)
usd/                             # 변환된 USD
logs/                            # 체크포인트 / tensorboard / 측정 CSV·npz
```

## 등록된 Gym 태스크
- `Pygmalion-Velocity-Flat-v0` / `-Flat-Play-v0`
- `Pygmalion-Velocity-Rough-v0` / `-Rough-Play-v0` (계단·울퉁불퉁·경사 포함)

## 빠른 사용 (conda env `pygmalion`)
```bash
source ../sim/miniforge3/etc/profile.d/conda.sh && conda activate pygmalion
cd /home/syaro/MikuchanRemote/Human-Pygmalion/pygmalion_locomotion

# 0) (최초 1회) 에셋 변환 + 패키지 설치
python scripts/convert_asset.py
pip install -e .

# 1) 학습 (headless, 저RAM이면 num_envs 축소)
python scripts/train.py --task Pygmalion-Velocity-Flat-v0 --headless --num_envs 512

# 2) 키보드 조작 + 실시간 토크/축력 HUD + 로깅
python scripts/play_keyboard.py --task Pygmalion-Velocity-Flat-Play-v0 \
    --checkpoint logs/rsl_rl/pygmalion_flat/<run>/model_xxx.pt --mass_scale 1.0

# 3) 측정 캠페인 + 분석
python scripts/measure.py --task Pygmalion-Velocity-Rough-Play-v0 --headless \
    --checkpoint <ckpt> --mass_scale 1.2 --push --tag rough_m1.2
python scripts/analyze.py --npz logs/measure/rough_m1.2.npz --out ../docs/assets
```

## MuJoCo로 로봇 보기 (CPU, GPU 드라이버 무관)
```bash
python scripts/view_mujoco.py --hold      # 'stand' 자세 고정, 회전/줌하며 관찰 (★추천)
python scripts/view_mujoco.py             # 'stand'에서 시작 → 정책 없어 주저앉음
python scripts/render_robot.py --out ../docs/assets   # 오프스크린 PNG 4뷰 생성
```
> ⚠️ `python -m mujoco.viewer --mjcf=scene.xml`는 기본자세(base z=0)로 시작해 다리가 바닥을 뚫고
> 튕겨 날아가 안 보임 → 반드시 위 런처(또는 뷰어에서 'stand' 키프레임 Load Key) 사용.

자세한 배경/이유는 `../docs/` 참조.
