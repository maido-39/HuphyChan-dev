# 102. 재구축 인계 문서 — CAD에서 학습 가능한 로봇까지, 검증 중심 (2026-08-25)

**대상**: 이 파이프라인을 **처음부터 다시** 만들려는 사람. 기존 산출물을 믿지 말고 **직접 검증**하라는 전제로 썼다.
그래서 각 단계는 "무엇을 실행하는가"보다 **"그 결과가 맞는지 어떤 독립 도구로 어떻게 확인하는가"**에 무게를 둔다.

**먼저 읽을 것**: [[90_urdf_mjcf_pipeline_and_dr]](파이프라인 본문·함정 19건·교차검증), [[87_robot_model_v2]](모델 개정 이력),
[[44_joint_param_creation_pipeline]](관절 파라미터 출처), [[62_policy_reward_design_review]](학습 쪽 확정 원칙 12).

---

## 0. ★ 따라가면 안 되는 문서 (죽은 경로)
| 문서 | 왜 죽었나 |
|---|---|
| [[02_asset_conversion]] | MJCF → **USD** 변환. IsaacLab 시대 산물이고 지금 스택(mjlab)은 MJCF를 직접 읽는다. USD는 만들 필요가 없다. |
| [[20_fusion360_isaaclab]] | 같은 이유(파이프라인 끝이 Isaac Lab). §"함정" 목록만 아직 읽을 값어치가 있다. |
| `pygmalion_locomotion/` 아래 IsaacLab 학습 스크립트 | 현행 학습은 전부 `mujoco-sim/mjlab`. `pygmalion_locomotion`은 에셋 보관과 옛 도구용으로만 남아 있다. |

현행 스택: **Fusion 360(또는 STEP) → URDF + MJCF → mjlab 에셋 → rsl_rl PPO**.

---

## 1. 전제조건과 **경로 선택**

### 1a. 파이썬 환경 (여기서 대부분 막힌다)
모델 도구와 학습 모두 **mjlab 가상환경**으로 돌린다. 시스템 `python3`에는 mujoco/mjlab이 없어 크래시한다.
```bash
mujoco-sim/mjlab/.venv/bin/python3 tools/robot_model/<script>.py     # 어디서 실행하든 이 인터프리터
```
CPU 전용 측정은 `CUDA_VISIBLE_DEVICES="" .venv/bin/python3 ... --device cpu` (GPU 학습과 병렬 가능).

### 1b. 질량·관성 입력을 어디서 얻을지 — **두 경로 중 하나를 고른다**
| | **A. Fusion 라이브** (권장, 현행) | **B. STEP 파일** (대안) |
|---|---|---|
| 입력 | Windows PC의 살아있는 Fusion 문서를 MCP로 읽음 | `~/pyg_fea/steps/*.step` (`tools/fea/xcaf_links.py`가 STEP에서 추출) |
| 도구 | `tools/fusion/dump_bodies.py` → `massprops_fusion.py` | `tools/robot_model/massprops_step.py`, `meshes_step.py` |
| 장점 | 재질·전구상태·바디 구성이 CAD와 항상 일치 | Fusion·Windows·MCP 없이 리눅스만으로 완결 |
| 단점 | **Fusion MCP가 Windows PC에 있어야 하고 역터널이 필요** | STEP을 다시 내보내야 최신 CAD 반영 |
| 판단 | CAD를 계속 고치며 반복할 계획이면 A | 형상이 굳었고 재현만 하면 B |

**B 경로 주의**: 구입품은 카탈로그 질량으로 들어가고, 판단이 필요한 건 "각 솔리드가 어느 링크에 속하는가"뿐이다 —
그 배정은 파일로 출력되니 **반드시 사람이 검토**하라. 모터 자리표시자는 CAD 질량이 가짜라 형상만 쓰고 밀도를 카탈로그 질량으로 재스케일한다.

### 1c. 형상 입력 3종 (스크립트가 재생성하지 않는다 — 형상이 바뀔 때만 사람이 다시 만든다)
1. `rom_measured.json` ← `tools/robot_model/rom_check.py` (관절당 수십 분). **없으면 빌드가 assert로 멈춘다**(예전엔 구 MJCF 범위로 조용히 되돌아갔다 — 그 버그는 고쳐졌다).
2. 링크 메시 ← `meshes_step.py`(STEP) 또는 `upper_meshes_fusion.py`(Fusion).
3. `build_robot.py`의 `DESIGN_CAP` 표 — 설계상 하드스톱. ROM 측정치보다 우선한다.

---

## 2. 빌드 — 한 줄, 6단계
```bash
bash tools/robot_model/make_printed_robot.sh pygmalion_v3_printed
```
| # | 단계 | 산출물 | 이 단계에서 의심할 것 |
|---|---|---|---|
| 1 | `dump_bodies.py --expect=...` | `bodies_<tag>.json` | 활성 문서 이름이 다르면 **아무것도 쓰지 않고 멈춘다**. 옛 버전은 먼저 쓰고 나중에 확인했다 |
| 2 | `massprops_fusion.py` | `robot_massprops_<tag>.json` | 모터 카탈로그 질량 assert, 대체분기 제외 규칙 |
| 3 | `motor_proxies_fusion.py` | `motor_proxies_<tag>.json` | **같은 덤프**에서 만들어야 한다(§4 함정 1) |
| 4 | `build_robot.py` | `<tag>.urdf`, `<tag>.xml` | 프레임 변환·관절·충돌체·센서 |
| 5 | `validate_robot.py` | 검증 출력 + 그림 | 질량 대조·치수·L/R 규약·관절 스윕·관성 readback |
| 6 | `mass_dr.py` | `mass_dr.json`, `docs/img/mass_dr_ranges.png` | 질량 불확실성 → DR 범위 |

---

## 3. ★ 검증 — 내 결과를 믿지 말고 여기부터 하라

### 3a. URDF ↔ MJCF 교차검증 (독립 파서)
우리 emitter가 아니라 **MuJoCo 자체 URDF 로더**로 `.urdf`를 읽어 `.xml`과 대조한다.
```bash
mujoco-sim/mjlab/.venv/bin/python3 tools/robot_model/urdf_crosscheck.py --tag=pygmalion_v3_printed
```
| 검사 | 기준 | 우리 결과 (재현되어야 함) |
|---|---|---|
| 관절 집합 | 이름 일치 | 17/17 |
| 관절 축·앵커·범위(영점) | <0.01°, <0.05 mm, <1e-5 rad | 0.0000°, 0.0000 mm, 4.9e-6 |
| 관절별 범위 스윕(16점) → 전 링크 | <0.05 mm, <0.01° | 0.0000 mm, 2.4e-6° |
| 랜덤 자세 200개 | 동일 | 0.0000 mm, 0.0000° |
| 링크별 질량·COM·관성 | <1e-4 kg, <0.05 mm, <1e-5 kg·m² | 17링크 전부 통과 |
| 루프 모델(`--tag=..._loop`) | | 29/29 관절, URDF 전용 더미 4개만 차이 |
**알려진 정상 차이**: URDF 로더가 base_link를 월드에 병합한다(로더 관례). 컬리전은 **MJCF만 권위** — URDF는 hull 메시다(URDF에 캡슐이 없다).

### 3b. 폐루프 발목 (AB 모델을 쓸 때만)
```bash
mujoco-sim/mjlab/.venv/bin/python3 tools/robot_model/loop_ankle_verify.py     # plain MuJoCo, dt 1 ms, fp64
```
[[91_closed_loop_ankle_rl]] §4에 통과 기준. 구속 강성 `solimp`은 [[94_loop_constraint_stiffness]]에서 **0.999 유지**로 결론났다(전례 조사 + 5단계 스윕: 단단할수록 오히려 토크가 덜 튄다, 기본값은 8 mm 처짐).

### 3c. 실물 대조
[[81_rl_model_vs_cad_mass]], [[82_final_design_mass_review]]에 CAD vs RL 모델 질량 대조가 있다.
★ **모터 질량은 2026-08-25에 실측으로 갱신됐다**: RS04 **1.5144 kg(케이블 한쪽 포함)**, RS03 **0.9195 kg(모터 단품)** — 이전 카탈로그값 1.42/0.88 대비 로봇 전체 +0.898 kg(+2.54 %). **케이블·다수의 미체결 나사는 모델에 없다 → DR이 떠안는다**([[90_urdf_mjcf_pipeline_and_dr]] §2d).

### 3d. 부호 규약
[[51_joint_sign_conventions]]. 미러 규약은 F(−1,1,1)/M(1,−1,−1), 모멘트 기준점은 **로봇 CoM**(`subtree_com[body_rootid]`)이지 링크 COM이 아니다 — 검증법은 앵커 모멘트의 관절축 성분 vs 모터 토크 상관 1.000.

---

## 4. 실제로 우리를 물었던 함정 (전체는 [[90_urdf_mjcf_pipeline_and_dr]] §4, 레드팀 확정 19건)
1. **모터 원통이 옛 덤프를 봤다** — 힙 피치 RS04가 75.6 mm 옮겨졌는데 질량은 새 위치, 그림은 옛 위치였다. → 원통·질량을 **같은 덤프**에서 생성하도록 고침.
2. **Fusion 커넥터는 4 KiB 초과 스크립트를 실행하지 않고 `success: true`를 돌려준다**(3777 B 실행 / 4289 B 무시). 조용한 실패다.
3. 예외로 끝나는 Fusion 스크립트는 **문서 편집을 롤백**한다. 읽기는 예외 채널, 쓰기는 정상 종료로.
4. 파일명의 "v21"이 버전이 아니라 **저장 시각**이었다.
5. **전구(가시성) 꺼짐 ≠ 억제** — 골반 나사 69개를 놓쳤다.
6. 순회 스크립트에서 자식 오커런스를 스택에 안 넣으면 루트만 돌고 "성공 0건".
7. **자리표시자는 bbox·바디구성을 먼저 실측하라** — JS06은 로드엔드가 아니라 인서트였고, RS04는 축소가 아니라 중공이었다. 카탈로그만 믿고 넣으면 오적용된다.
8. `.nfs*` 파일: NFS 마운트에서 삭제된 열린 파일. 무시해도 된다.

---

## 5. MJCF → mjlab 학습 에셋
모델을 학습에 쓰려면 `mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/pygmalion_constants.py`가 관문이다. 여기서 정하는 것:
- **액추에이터**: 관절별 Kp/Kd/effort, 실측 모터 파라미터(J·b·tc), **T-N 곡선 클램프**(`tn_actuator.py`, 구동 사분면만), 폐루프는 크랭크 액추에이터 + `AnkleRpTnActuator`.
- **action scale 0.25 rad**(전 관절 공통), `use_default_offset=True`.
- **관측 관절 집합** `OBS_JOINT_NAMES` — 폐루프에서 로드 유니버설 8개는 제외(엔코더가 없고 크랭크의 결정론적 함수), 발목 힌지는 **유지**(하드웨어가 크랭크 엔코더로 FK 계산 가능).
- **`PYG_*` 토글** 전부: `PYG_V2`, `PYG_INIT_BENT`, `PYG_ARM_ABD_DEG`, `PYG_ANKLE_MODE`, `PYG_MOTOR_MEAS`, `PYG_TN`, `PYG_SOFT_LANDING`, `PYG_INERTIAL_DR`, `PYG_CMD_VY_STAGES`, `PYG_CMD_NORM_CAP`, `PYG_NO_DR`, `PYG_DR_STARTUP`.
  ★ **측정·재생·렌더도 학습과 같은 토글을 줘야 한다** — 다르면 다른 로봇을 재생하게 된다.

정확한 차원·게인·리워드 표는 [[101_policy_spec_and_final_plan]] §1–2. 학습 세팅 근거는 [[92_ankle_ab_rp_training_setup]].
**학습 실행 방법이 두 갈래라 혼동하기 쉽다**:
- `pygmalion_locomotion/scripts/run_training.sh` — **IsaacLab 시대 런처**(영상 2종 + 리포트 자동화). PreToolUse 훅이 `train.py` 직접 호출을 막는 것도 이 경로 기준이다.
- 현행 mjlab 학습은 `mujoco-sim/mjlab/analysis/train_wandb_video.py`로 띄운다. 실제 c3 런의 인자·환경은 `mujoco-sim/mjlab/analysis/out/watchdog_runs.json`에 그대로 기록돼 있으니 **재현할 때 그 JSON을 정본으로 보라**(와치독이 죽은 런을 되살릴 때도 이 스펙을 쓴다).
- 감시 인프라: `analysis/watchdog.sh`(자동 resume + RAM 가드, crontab */5 자기복구), `analysis/gate_watch.sh`(iter 마일스톤·시간 하트비트), `analysis/snapshot_review.py`(런 노트에 판정행 추가), `analysis/review_loop.sh`(1시간마다 자동 기록).

---

## 6. 아직 검증되지 않은 것 (믿지 말 것)
- **실물 대조 0건**: 이 모델은 어떤 실기 데이터와도 맞춰본 적이 없다. 관성·마찰·지연 전부 CAD/데이터시트/벤치 값이다.
- **모터 벤치는 무부하 단품 기준**(motor-id 127, 출력축 가정). 조립 상태의 마찰·백래시는 미측정.
- **RS00 상전류 저항 미공개** → ankle_roll 동손 추정이 근사.
- **η_drive 0.80** 이 전력 추정 최대 오차원(±15–20 %). CoT 절대값보다 arm 간 비를 믿을 것.
- **RP(직렬 발목)는 실물이 아니다** — 통제 비교용 가상 구성이고, 토크 한계는 루프에서 유도한 포락의 중심자세 선형화다.
- **컬리전은 볼록 근사**. 자기충돌 판정이 실제보다 보수적일 수 있다.
- **단일 시드**. 지금까지 모든 A/B가 시드 1개다.

---

## 7. 다시 만든다면 순서
1. §1 경로 선택 → 환경 확인(`.venv/bin/python3`).
2. `rom_check.py`로 ROM 실측(형상이 우리 것과 다르면 필수).
3. `make_printed_robot.sh` 1회전 → **§3a 교차검증부터** 돌려 숫자가 위 표와 같은지 확인.
4. 다르면 §4 함정 목록을 위에서부터 대조.
5. mjlab 등록(§5) → 1024 env·1,500 iter 스모크 런.
6. 본 학습 계획은 [[98_scratch_training_plan]](게이트형 커리큘럼·entropy 어닐링·T-N 토크 항 포함).
