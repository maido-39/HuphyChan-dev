# 01 · 설치 (Install: conda + Isaac Sim 5.0 + Isaac Lab 2.2)

> [!abstract] 목표
> `sim/` 아래에 **격리된 conda 환경**과 **Blackwell(sm_120) 호환** Isaac Sim 5.0 / Isaac Lab 2.2를 설치.
> 시스템 Python을 건드리지 않고, Isaac Lab 원본은 참조·러너로만 둔다.

---

## 왜 이 버전 조합인가 (Why)
RTX 5060 Ti = **Blackwell, sm_120**. 이 아키텍처는 빌드 타깃이 새로워서 구버전 스택이 안 돈다.

| 스택 | sm_120 | 결론 |
|---|---|---|
| Isaac Sim 4.5 (torch cu118/121) | ❌ "CUDA compute capability" 에러 보고 다수 | 사용 불가 |
| **Isaac Sim 5.0 GA + Isaac Lab 2.2** | ✅ Python 3.11 + **torch 2.7 cu128** | **채택** |
| Isaac Sim 5.1 + Isaac Lab 2.3 | ⚠️ scenedb 크래시 = **595 드라이버 한정** 회귀 | fallback (우리는 580) |

> torch는 sm_120을 **2.7+cu128**부터 정식 포함. 그래서 torch를 **먼저** 고정 설치한 뒤 Isaac Sim을 얹는다.

## 무엇을 / 어디서 (What / Where)
- conda: `sim/miniforge3` (Miniforge, conda-forge 기본)
- env: `pygmalion` (Python 3.11)
- Isaac Sim 5.0: env 내 pip 패키지 (`isaacsim[all,extscache]`)
- Isaac Lab 2.2: `sim/IsaacLab` 소스 클론 (수정 금지, `isaaclab.sh` 러너 제공)

---

## 어떻게 (How) — 재현 절차

### 1) Miniforge 설치 (시스템 미오염)
```bash
curl -fsSL -o /tmp/Miniforge3.sh \
  https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash /tmp/Miniforge3.sh -b -p <repo>/sim/miniforge3
source <repo>/sim/miniforge3/etc/profile.d/conda.sh
```
> 결과: conda 26.3.2 ✅

### 2) conda 환경
```bash
conda create -y -n pygmalion python=3.11
conda activate pygmalion
```
> 결과: Python 3.11.15 ✅

### 3) PyTorch (Blackwell) — **먼저**
```bash
pip install torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128
```
검증:
```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_capability())"
# 기대: 2.7.0+cu128 True (12, 0)   <- (12,0) == sm_120 == Blackwell
```
> [!success] 결과 (2026-06-20 검증 완료)
> - `torch 2.7.0+cu128`, `cuda available: True`, device `NVIDIA GeForce RTX 5060 Ti`, **capability (12, 0)** ✅
> - 실제 GPU matmul(4096²) 커널 실행 OK → **Blackwell + PyTorch 완전 동작 확인**. RL/torch 쪽 sm_120 리스크 해소.
> - 동반 설치: nvidia-cublas-cu12 12.8.x, cudnn 9.7.x, nccl 2.26, triton 3.3.0, numpy 2.4.4.

### 4) Isaac Sim 5.0 (pip)
```bash
pip install 'isaacsim[all,extscache]==5.0.0' --extra-index-url https://pypi.nvidia.com
```

### 5) Isaac Lab 2.2 (소스, 수정 금지)
```bash
cd <repo>/sim
git clone --branch v2.2.0 https://github.com/isaac-sim/IsaacLab.git
cd IsaacLab
./isaaclab.sh --install rsl_rl      # isaaclab 패키지 editable + rsl_rl RL 라이브러리
```

### 6) [체크포인트] Isaac Sim 헤드리스 스모크
> [!warning] RAM
> Isaac Sim 최초 구동은 메모리 부하가 크다. **실행 직전 사용자에게 RAM 확보를 요청**한 뒤 진행한다.
```bash
# Blackwell 렌더/PhysX GPU 파이프라인이 크래시 없이 기동되는지 최소 확인
python -c "from isaacsim.simulation_app import SimulationApp; app=SimulationApp({'headless':True}); app.close(); print('OK')"
```

---

## ★ 전체 재현 순서 (실제로 통한 것 + 함정 모두 — 이대로 따라하면 됨)
```bash
# 0) Miniforge → conda env (py3.11)
bash Miniforge3-Linux-x86_64.sh -b -p <repo>/sim/miniforge3
source <repo>/sim/miniforge3/etc/profile.d/conda.sh
conda create -y -n pygmalion python=3.11 && conda activate pygmalion

# 1) torch FIRST (Blackwell sm_120 = cu128)
pip install torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128
python -c "import torch; print(torch.cuda.get_device_capability())"   # (12,0) 확인

# 2) Isaac Sim 5.0 (pip)  ※ 이게 setuptools를 82로 올려 pkg_resources를 깨뜨림(아래 4에서 복구)
pip install 'isaacsim[all,extscache]==5.0.0' --extra-index-url https://pypi.nvidia.com

# 3) Isaac Lab 2.2 (source) — ★함정: isaaclab.sh가 core 'isaaclab'을 빼먹음 → 수동 설치 필요
git clone --depth 1 --branch v2.2.0 https://github.com/isaac-sim/IsaacLab.git sim/IsaacLab
cd sim/IsaacLab && ./isaaclab.sh --install rsl_rl ; cd -
pip install "setuptools<81"                                  # ★pkg_resources 복구 (81+에서 제거됨)
pip install -e sim/IsaacLab/source/isaaclab                  # ★core isaaclab + 의존성(gymnasium 등)

# 4) 우리 패키지
cd pygmalion_locomotion && pip install -e . --no-deps ; cd -

# 5) EULA 영구 수락 (대화형 프롬프트가 헤드리스에서 EOFError 내는 것 방지)
conda env config vars set OMNI_KIT_ACCEPT_EULA=YES -n pygmalion

# 6) 에셋 변환 (MjcfConverter가 확장 자동활성화 안 함 → spec.py가 대신 enable; worldBody 잉여루트 비활성화)
python pygmalion_locomotion/scripts/convert_asset.py --force

# 7) (Blackwell GPU) 드라이버 — Isaac Sim PhysX(CUDA12.8)가 CUDA13 드라이버(580)와 불일치 → 570.x로
#    → [[09_gpu_driver_fix]] : 570.195.03 open kernel
```
각 단계의 **왜/함정**은 [[99_troubleshooting]]에 상세.

## 트러블슈팅 로그
- 위 순서의 ★표가 실제로 막혔던 지점. 전부 [[99_troubleshooting]]에 원인·해결 기록됨.

## 다음 노트
- [[02_asset_conversion]] — MJCF→USD · [[09_gpu_driver_fix]] — 드라이버
