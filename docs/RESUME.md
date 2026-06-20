# ▶ RESUME — 현재 상태 & 재개 지점 (드라이버 업데이트/재부팅 대비)

> 세션이 끊겨도(예: 드라이버 재설치+재부팅) 이 문서로 정확히 이어간다.

## 환경 (설치 완료, 검증됨)
- conda: `sim/miniforge3`, env **`pygmalion`** (Python 3.11). 활성화:
  `source sim/miniforge3/etc/profile.d/conda.sh && conda activate pygmalion`
- **torch 2.7.0+cu128** — Blackwell sm_120 GPU 연산 검증 ✅
- **Isaac Sim 5.0.0** (pip), **Isaac Lab 2.2** (`sim/IsaacLab`, editable) + 우리 패키지 `pygmalion_locomotion`(editable) 설치 완료
- 환경변수: `OMNI_KIT_ACCEPT_EULA=YES` (conda env에 영구 설정 + run.sh에 export)
- 설치 트러블슈팅 해결 기록: [[99_troubleshooting]] (core isaaclab 누락, setuptools<81/pkg_resources, EULA, MJCF 확장)

## 코드 (작성·문법검증 완료)
- 로봇 핫스왑 spec 시스템: `assets/robot_specs/robstride_biped.yaml` + `robots/spec.py` (검증 통과)
- env: `Pygmalion-Velocity-{Flat,Rough}[-Play]-v0`, 사람형 reward, toe=passive_spring, 발목=직결모터
- 센싱/로깅/HUD/질량조정/측정/분석 스크립트 전부 작성

## 산출물 진행
- ✅ **MJCF→USD 변환 완료**: `usd/biped_lower_body.usd` (+configuration 레이어). 재실행: `python scripts/convert_asset.py`
- ✅ **USD articulation 루트 버그 수정**: MJCF 컨버터가 남긴 잉여 `worldBody` 루트 → `spec.py`가 비활성화
  (env가 articulation 생성 통과 확인됨). [[99_troubleshooting]]
- ✅ **MuJoCo 로봇 뷰잉**: `python scripts/view_mujoco.py --hold` ('stand' 키프레임 시작). 오프스크린 렌더 4뷰 = `docs/assets/02_robot_*.png`
- ✅ **GPU 렌더 안정화**: 간헐 "No device created"는 **좀비 Isaac Sim 프로세스의 GPU 점유**가 원인 → 정리하면 정상.
- ✅ **contact sensor 중첩 prim_path 버그 수정**: `/Robot/base_link/.*` (MJCF 중첩) → env 빌드 차단 해소. [[99_troubleshooting]]
- ✅ **env 전체 빌드+센싱 검증 성공 (device=cpu)**: obs(52)·act(12)·15 bodies·14 joints, reward 전 항목 바인딩,
  reset+step OK, **센싱 shape 확인** — applied_torque(14), body_incoming_wrench_b(15,6=Fx,Fy,Fz,Tx,Ty,Tz), GRF(15,3).
  → **코드 스택 전체 정합성 확정.** (`python scripts/check_env.py --device cpu`)
- ⚠️ **device=cuda:0는 PhysX GPU 폴백으로 env init이 느림/행**; **device=cpu는 정상 빌드·스텝**(단 학습 느림).
  최종 빠른 학습은 GPU 드라이버 수정 후 `--device cuda:0`.

> [!important] 실행 전후 체크 (좀비 방지)
> Isaac Sim은 SIGTERM/timeout으로 안 죽고 GPU를 잡고 있음. 매 실행 전후:
> `nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader` 로 잔존 PID 확인 → `kill -9 <pid>`.

## ⚠️ 미해결: Isaac Sim PhysX GPU 파이프라인 (드라이버 이슈)
- **GPU 연산 자체는 정상**: torch ✅, 단독 warp ✅ (`cuda:0 RTX 5060 Ti sm_120`).
- **Isaac Sim 내부 PhysX GPU 실패 → CPU 폴백**: `PhysX warning: GPU solver pipeline failed, switching to software`,
  `omni.physx handle on CUDA lib is (nil)`. + Isaac Sim 번들 warp의 `cuDeviceGetUuid` 경고.
- **원인**: Isaac Sim 5.0 PhysX/warp = CUDA 12.8 빌드 ↔ 드라이버 **580.167.08 (Open Kernel, CUDA 13.0)** 간
  `cuGetProcAddress` 불일치 (알려진 Blackwell+R580 이슈, IsaacLab #3477). CPU PhysX는 다수 env 학습에 부적합.
- **조치(사용자 선택)**: 드라이버를 **Latest Production Branch (Open Kernel Module 필수, Blackwell)** 로 업데이트.

### ★ 드라이버 정답 (검증 완료): **570.195.03 open kernel** — [[09_gpu_driver_fix]]
공식 supportedchips.html에서 RTX 5060 Ti(2D04) 지원 확인, CUDA 12.8(PhysX 일치), open kernel. 설치 가이드 docs/09.

### 재부팅 후 재개 절차 (570.195.03 설치+재부팅 후)
1. `nvidia-smi` → Driver 570.195.03 확인.
2. PhysX GPU 테스트: `cd pygmalion_locomotion && OMNI_KIT_ACCEPT_EULA=YES python /tmp/physx_gpu5.py`
   → kit 로그에 `GPU solver pipeline failed`가 **안 뜨면 성공**.
3. 성공 시:
   - **학습 이어가기(GPU)**: `python scripts/train.py --task Pygmalion-Velocity-Flat-v0 --device cuda:0 --num_envs 4096 --headless --resume --load_run 2026-06-20_16-28-54 --checkpoint model_300.pt`
   - reward trial-and-error([[04_reward_experiments]] #0: 균형OK, error_vel_xy 0.9 개선 필요)
   - **진화 영상**: `python scripts/record_progress.py --run logs/rsl_rl/pygmalion_flat/<run> --device cuda:0`
   - **측정**: `measure.py` → `analyze.py`(검증됨 — [[07_measurement]] 예시 그래프)
   - **키보드**: `play_keyboard.py`
4. 실패 시: 드라이버 fallback 580.95.05.

### 현재 진척 (CPU로 검증된 것)
- env 빌드+센싱(토크/6축반력/GRF) ✅, PPO 학습 ✅(model_300, episode length 60→814, Mean reward +7.76)
- analyze.py 하드웨어분석 파이프라인 ✅(모터정격 대비 util%, 링크축력 표+그래프)

## 다음 단계 (GPU PhysX 해결 후)
`spawn_check.py` → `train.py --task Pygmalion-Velocity-Flat-v0 --headless --num_envs 1024` →
reward trial-and-error([[04_reward_experiments]]) → `play_keyboard.py` → `measure.py`+`analyze.py`.
