# Human-Pygmalion — 하반신 이족 로봇 사람형 보행 학습 + 하중 측정

RobStride 모터 구동 **하반신 14-DOF 이족 로봇**을 Isaac Lab에서 "사람처럼 걷도록" 학습시키고,
키보드 조작·실시간 **관절 토크/링크 축력(x,y,z 반력)/발 GRF** 로깅으로 **하드웨어 설계용 하중 데이터**를 얻는다.

## 구조
```
Human-Pygmalion/
├── sim/                    # 격리 환경 (시스템 미오염)
│   ├── miniforge3/         # conda (env: pygmalion, Python 3.11)
│   ├── IsaacLab/           # Isaac Lab 2.2 소스 (참조·러너, 무수정)
│   └── (Isaac Sim 5.0 = env 내 pip)
├── pygmalion_locomotion/   # ★ 학습 워크스페이스 (외부 프로젝트; Isaac Lab을 import만)
│   ├── assets/robot_specs/ # ★ robstride_biped.yaml = 로봇 단일 진실원
│   ├── source/.../         # robots(spec) / tasks(env·reward) / sensors(로깅·질량) / ui(HUD)
│   ├── scripts/            # convert_asset · train · play_keyboard · measure · analyze · spawn_check
│   └── logs/ usd/
├── docs/                   # Obsidian 노트 (00~08 + 99) + assets 스크린샷
└── robot_files/            # 입력 (불변): robot.xml, biped_cfg.py, mjcf.zip
```

## 빠른 시작
```bash
source sim/miniforge3/etc/profile.d/conda.sh && conda activate pygmalion
cd pygmalion_locomotion && pip install -e .

python scripts/convert_asset.py                 # MJCF/URDF → USD (spec 기반)
python scripts/train.py --task Pygmalion-Velocity-Flat-v0 --headless --num_envs 512
python scripts/play_keyboard.py --task Pygmalion-Velocity-Flat-Play-v0 --checkpoint <ckpt>
python scripts/measure.py --task Pygmalion-Velocity-Rough-Play-v0 --headless --checkpoint <ckpt> --tag run1
python scripts/analyze.py --npz logs/measure/run1.npz --out ../docs/assets
```

## 핵심 기능
- **사람형 보행 학습**: 속도추종 + 보행 쉐이핑 reward (이후 AMP 단계 옵션)
- **지형**: 평지 / 계단 / 울퉁불퉁 / 경사 + cmd_vel + 외란(push)
- **센싱**: 관절 토크 · 링크 6축 반력(Fx,Fy,Fz,Tx,Ty,Tz) · 발 GRF → 실시간 HUD + CSV/npz
- **로봇 핫스왑**: YAML 한 파일로 질량/관성/COM/관절구조 교체 → 1커맨드 변환+재학습 ([[docs/08_robot_hotswap]])
- **toe = 패시브 스프링, 발목 = 직결 모터**

## 하드웨어 제약 (검증됨)
RTX 5060 Ti(Blackwell sm_120) → torch 2.7+cu128 ✅ / Isaac Sim 5.0 + Isaac Lab 2.2 / RAM 9.7GB → headless·num_envs 축소.

자세한 내용·이유는 [docs/](docs/README.md) 참조.
