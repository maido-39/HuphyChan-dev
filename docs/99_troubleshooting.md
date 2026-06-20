# 99 · 트러블슈팅 로그

> 설치·실행 중 만난 문제와 해결을 누적 기록. (Obsidian 백링크로 관련 노트 연결)

---

## 환경/하드웨어
- **RTX 5060 Ti = Blackwell sm_120**: torch는 **2.7+cu128** 필요. cu118/121 빌드는 커널 없음 → 에러.
  → 검증 완료: `get_device_capability()==(12,0)`, GPU matmul OK. [[01_install]]
- **Isaac Sim 5.1/Lab 2.3 scenedb 크래시**: **595.xx 드라이버** 한정 회귀. 우리는 580.167 → 회피 기대.
  크래시 시 fallback: 드라이버 그대로 두고 Sim 5.0 유지, 또는 렌더러 옵션 조정.
- **RAM 9.7GB**: Isaac Sim 구동/학습 시 OOM 위험. 대응: `--headless`, `--num_envs` 축소(256~1024),
  사용자 RAM 확보. 첫 OOM 시 num_envs 절반으로.

## 자주 나는 증상 (예상 + 대응) — 실제 발생 시 갱신
| 증상 | 원인 | 대응 |
|---|---|---|
| `CUDA error: no kernel image` | torch가 sm_120 미지원 | cu128 휠 확인 |
| Isaac Sim 부팅 중 멈춤/크래시 | Blackwell 렌더 | 드라이버/버전 점검, headless 우선 |
| 스폰 직후 NaN/폭발 | 자기충돌/관성 | self_collision off, balanceinertia, init 자세 |
| 학습 reward 정체 | reward 불균형 | [[04_reward_experiments]] 레버 |
| body 이름 매칭 실패 | USD prim 이름 ≠ regex | USD 트리 확인 후 cfg 이름 수정 |
| OOM (학습 중) | num_envs 과다 | 절반으로, terrain rows/cols 축소 |

## 실제 발생 기록
- **rough 학습 중 Mean reward 폭발(−59만) + `PxGpuDynamicsMemoryConfig::collisionStackSize buffer overflow`**:
  **자기충돌(self_collision) + 거친지형 + 16384 env**가 PhysX GPU 충돌버퍼(기본 collision_stack 2²⁶, pairs 2²¹)를
  초과 → 일부 env 물리 폭발 → NaN/거대 −reward로 정책 오염. **toe 강성 문제 아님**(같은 toe로 평지는 정상).
  → 해결: env cfg `__post_init__`에서 `sim.physx.gpu_collision_stack_size=2**28`, `gpu_found_lost_pairs_capacity=2**23`,
  `gpu_total_aggregate_pairs_capacity=2**23`. + 자기충돌 무거운 rough는 num_envs 16384→8192로. (버퍼↑는 GPU 메모리↑)
- **editable 패키지 수정 후 `NameError`(이미 고친 함수명)가 계속 남음 — stale `__pycache__`**:
  `spec.py`를 고쳤는데 학습이 옛 함수(`get_mass_summary`) 에러를 계속 냄. 원인=오래된 `.pyc` 바이트코드 +
  여러 학습을 **동시/연속 실행**하며 캐시가 엉킴. 해결:
  ```bash
  find source -name "*.pyc" -delete; find source -name "__pycache__" -type d -exec rm -rf {} +
  export PYTHONDONTWRITEBYTECODE=1   # 디버깅 중 .pyc 안 쓰게
  ```
  + **한 번에 학습 하나만** 실행(동시 실행 금지). + 매 실행 전 이전 isaacsim PID `kill -9`.
- **GPU util 60%만 — num_envs↑ + CPU 도둑 정리**: [[10_gpu_perf_tuning]].
- **정책이 한 방향만/체중·마찰 DR 무효/발 교차**: command 범위·DR·feet_distance 수정 → [[04_reward_experiments]] 실험 #2.
- **간헐적 `[gpu.foundation.plugin] No device could be created` (Isaac Sim 부팅 실패)**:
  ⚠️ **좀비 Isaac Sim 프로세스가 GPU를 점유**해 발생. `timeout 300 python ...`로 돌려도 Isaac Sim 앱이
  SIGTERM을 무시하고 살아남아(예: spawn_check가 1h25m간 GPU 244MiB 점유) 다음 실행이 디바이스 생성 실패.
  → 해결: 실행 전 `nvidia-smi --query-compute-apps`로 잔존 PID 확인 후 `kill -9`. 향후엔
  `timeout --kill-after=20 -s TERM 300 python ...` 또는 스크립트에 확실한 종료 보장. 단일 Isaac Sim만 실행.
- **2026-06-20 설치 중 동시 pip 금지**: 같은 conda env에 isaacsim 설치가 도는 도중 `pip install matplotlib`를
  돌렸더니 numpy가 재작성 중이라 `numpy.typing` 일시 오류. → **한 env에 동시 pip 설치 금지**. 한 작업이 끝난 뒤 다음.
- **`isaaclab.sh --install` 후 core `isaaclab`만 누락**: assets/tasks/rl/mimic는 깔렸는데 core `isaaclab`은
  egg-info만 있고 pip 미등록(+gymnasium 등 deps 미설치). 원인은 아래 setuptools 문제로 core 설치 sub-step 실패.
  → 해결: `pip install -e sim/IsaacLab/source/isaaclab` 로 core를 deps 포함 재설치.
- **`ModuleNotFoundError: No module named 'pkg_resources'` (flatdict 빌드 실패 → 전체 설치 중단)**:
  Isaac Sim 5.0 설치가 **setuptools 82.0.1**로 올렸는데 setuptools **81+는 `pkg_resources`를 제거**함.
  legacy 빌드(flatdict==4.0.1)와 다수 omni/isaac 런타임이 pkg_resources를 import → 깨짐.
  → 해결: `pip install "setuptools<81"`(pkg_resources 복구) 후 isaaclab deps 재설치.
- **wheel 0.47 vs packaging 23.0 경고**: `wheel requires packaging>=24` 경고는 비치명적(무시 가능).
  필요 시 `pip install "packaging>=24"`.
- **`Failed to find a single articulation ... Found multiple [worldBody, base_link/base_link]`**:
  MJCF→USD 변환 시 importer가 **빈 `worldBody` Xform에 ArticulationRootAPI를 잘못 남김** → 루트가 2개
  (worldBody + 진짜 base_link). env 생성 실패. CPU 빌드 검증(`check_env.py`)으로 발견.
  → 해결: 변환 후 `worldBody`를 `SetActive(False)`로 비활성화(우리 `spec.py::_strip_spurious_worldbody_root`,
  isaaclab 무수정). USD 실제 구조: `/robot/base_link/{base_link(root), L/R_*_link...}` + `/robot/joints/*` + (잉여)`worldBody`.
- **`ContactSensor ... could not find any bodies with contact reporter API`** (깨끗한 device=cpu에서도 일관):
  MJCF→USD가 모든 rigid body를 **컨테이너 한 단계 아래**에 둠 → 실제 경로 `/Robot/base_link/<body>`
  (표준 로봇은 `/Robot/<body>`). Isaac Lab prim regex `.*`는 **한 세그먼트만** 매칭하므로 base env의
  `contact_forces` prim_path `"/Robot/.*"`가 컨테이너만 잡고 body를 놓침.
  → 해결: env `__post_init__`에서 `contact_forces.prim_path="{ENV_REGEX_NS}/Robot/base_link/.*"`,
  `height_scanner.prim_path="{ENV_REGEX_NS}/Robot/base_link/base_link"`. (body_names 기반 reward/termination은
  센서가 잡은 body 이름으로 해석되므로 그대로 동작.)
- **device=cpu는 env 초기화가 행이 아니라 정상 진행** (단, PhysX는 CPU라 학습은 매우 느림). cuda:0+CPU폴백 경로가
  env init에서 멈추던 것과 대비 → CPU 검증/소규모 학습은 `--device cpu`로.
- **`'Articulation' object has no attribute '_root_physx_view'`**: 위 articulation 초기화 실패의 2차 증상
  (physx view가 안 만들어져 startup 물리 이벤트가 접근 실패). 루트 문제 해결 시 함께 사라짐.
- **Isaac Sim 첫 실행이 EULA 입력에서 멈춤 (`EOFError: ... input("Do you accept the EULA?")`)**:
  Omniverse Kit 최초 구동은 대화형 EULA 동의를 요구 → 비대화형(스크립트)에선 EOFError로 죽음.
  → 해결: 환경변수 `OMNI_KIT_ACCEPT_EULA=YES`. 영구화: `conda env config vars set OMNI_KIT_ACCEPT_EULA=YES -n pygmalion`
  (이후 모든 Isaac Sim 스크립트가 자동 통과). **이건 Blackwell 크래시가 아님** — 단순 동의 프롬프트.
