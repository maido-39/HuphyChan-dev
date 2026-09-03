# LegOnly AB 미러축 버그픽스 검증 스모크 `legonly_ab_v2_smoke` (2026-09-03)

> **한 줄 판정:** v30 모델의 좌우 미러 축과 mjlab 단일 정규식 설정이 충돌해 왼쪽 무릎의
> 사용 가능 창이 0°였던 버그([[../reward_research/2026-09-03_stiff_knee_root_cause]])를
> 설정/코드 레이어에서 고친 뒤, 같은 오케스트레이션이 여전히 완주하는지와 **양 무릎이 실제로
> 명령을 받는지**를 확인하는 인프라 시험이다. **보행 성능을 판정하는 런이 아니다.**

| 항목 | 값 |
|---|---|
| 상태 | ✅ **완주 — 인프라 PASS + 무릎 액션창 열림 확인** (P1 iter 200 settled, P2 iter 399 DONE, 17분 01초, 크래시 0). 보행 성능 판정 대상 아님 |
| 대상 버그 | 모델-설정 좌우 부호 불일치 3건 (default pose / action clip / 폐루프 발목 bent 키프레임) |
| 로봇 | `LegOnly_prototype-tempmass-motormeasured-armfix_v30_proxyfix_loop.xml` (**모델 무수정**) |
| 모델 질량 | 23.630 kg (1 BW = 231.8 N) |
| 질량 DR | `mass_dr_legonly_fastener50_prototype-tempmass.json` (본런 `legonly_ab_v1`과 동일 = fastener50 권위본) |
| 직전 스모크 | [[2026-09-03_legonly_ab_smoke_test]] (동일 오케스트레이션, 구 DR JSON, 버그 잔존 상태에서 완주) |
| 중단된 본런 | [[2026-09-03_legonly_ab_v1]] — 이 버그로 iter 5,700에서 보수적 중단 |
| 정량 근거 | [[2026-09-03_legonly_gait_kinematics]] (L_knee qtarget 진폭 0.00°, 스톱 상시 21.8 N·m) |

---

## §1 재현 조건

### §1a 실행 명령

```bash
cd mujoco-sim/mjlab
nohup .venv/bin/python3 analysis/run_v2_scratch.py --smoke \
  --run legonly_ab_v2_smoke --ankle AB --logger tensorboard \
  --env PYG_MODEL_TAG=LegOnly_prototype-tempmass-motormeasured-armfix_v30_proxyfix \
  --env PYG_MASS_DR_JSON=<repo>/tools/robot_model/fusion_snapshots/v30_inspection/mass_dr_legonly_fastener50_prototype-tempmass.json \
  > analysis/out/legonly_ab_v2_smoke.out 2>&1 &
```

- 스모크 규격은 런처 기본값 그대로: `num_envs=1024`, P1 cap 400 iter, P2 = ramp 120 + digest 80
  = 200 iter, 게이트 완화(`min_dwell 20 / max_dwell 60 / window 20 / fell_max 1.0 /
  err_ratio 100`), `settle_hold 3`.
- 직전 스모크와 다른 점은 **두 가지뿐**: (1) 이번 픽스가 들어간 설정 코드, (2) 질량 DR JSON을
  본런과 같은 fastener50 권위본으로 교체(직전 스모크는 구 round4 서브셋).
- 권위 원장: `analysis/out/v2_scratch_legonly_ab_v2_smoke.json`.

### §1b 이번 런에서 바뀐 것 (버그픽스, 리워드 변경 0건)

리워드 가중치·항 구성은 `legonly_ab_v1`과 **완전히 동일**하다. 바뀐 것은 부호 유도 방식뿐이다.

| # | 위치 | 이전 | 이후 |
|---|---|---|---|
| 1 | `pygmalion_constants._bent_joint_pos` | `{".*_hip_pitch_joint": -0.175, ".*_knee_joint": -0.35}` 단일 정규식 | `signed_pose({"hip_pitch": 0.175, "knee": 0.35})` — **굽힘 크기**만 적고 부호는 각 관절의 MJCF range 장축 방향에서 유도 |
| 2 | `env_cfgs.py` `PYG_SAFE_TARGET_CLIP` | 손으로 적은 7행 정규식 표(무릎 `(-114°, -6°)` 등) | `safe_target_clip()` — 관절별로 자기 range의 중심 ±90 % 로 계산 |
| 3 | `pygmalion_constants._reexpress_loop_pose` (신규) | v3 기하로 푼 bent 키프레임 크랭크/로드 각을 v30에 그대로 대입 | 기준 모델과 축을 비교해 축이 뒤집힌 힌지의 각도만 부호 반전 |
| 4 | `assert_unmirrored()` (신규) | — | 단일 정규식으로 남겨둔 관절(`ankle_pitch`)의 좌우 range가 갈라지면 **import 시점에 실패** |
| 5 | `analysis/preflight_action_window.py` (신규) + `run_v2_scratch.py` 훅 | — | 발사 전 전 액추에이터 관절의 `default ∈ range` 와 `명령대역 ∩ range ≥ max(15°, range의 30 %)` 검사, 실패 시 발사 거부 |

### §1c 프리플라이트 게이트: 수정 전 FAIL / 수정 후 PASS

동일 명령(`analysis/preflight_action_window.py`), 동일 환경변수, 코드만 교체.

**수정 전 (= `legonly_ab_v1`이 돌던 설정):**

| joint | range [°] | clip [°] | 사용 가능 창 [°] | 폭 | 필요 | default | 판정 |
|---|---|---|---|---|---|---|---|
| L_knee_joint | [0.00, 120.00] | [−114.00, −6.00] | **없음** | **0.00** | 36.00 | −20.05 | **FAIL** default-outside-range + window-too-narrow |
| R_hip_pitch_joint | [−25.00, 120.00] | [−112.75, 17.75] | [−25.00, 17.75] | **42.75** | 43.50 | −10.03 | **FAIL** window-too-narrow |
| L_hip_roll_joint | [−25.00, 85.00] | [−79.50, 19.50] | [−25.00, 19.50] | 44.50 | 33.00 | 0.00 | ok (통과하지만 오른쪽의 45 %) |
| (나머지 9개) | — | — | — | — | — | — | ok |

→ `[preflight] FAIL: 2 joint(s) cannot be commanded` (exit 1), 실행시간 약 1 초.

**수정 후:**

| joint | range [°] | clip [°] | 사용 가능 창 [°] | 폭 | 필요 | default | 판정 |
|---|---|---|---|---|---|---|---|
| L_knee_joint | [0.00, 120.00] | [6.00, 114.00] | [6.00, 114.00] | **108.00** | 36.00 | **+20.05** | ok |
| R_knee_joint | [−120.00, 0.00] | [−114.00, −6.00] | [−114.00, −6.00] | 108.00 | 36.00 | −20.05 | ok |
| L_hip_pitch_joint | [−120.00, 25.00] | [−112.75, 17.75] | [−112.75, 17.75] | 130.50 | 43.50 | −10.03 | ok |
| R_hip_pitch_joint | [−25.00, 120.00] | [−17.75, 112.75] | [−17.75, 112.75] | **130.50** | 43.50 | **+10.03** | ok |
| L_hip_roll_joint | [−25.00, 85.00] | [−19.50, 79.50] | [−19.50, 79.50] | **99.00** | 33.00 | 0.00 | ok |
| R_hip_roll_joint | [−85.00, 25.00] | [−79.50, 19.50] | [−79.50, 19.50] | 99.00 | 33.00 | 0.00 | ok |
| L/R_hip_yaw_joint | [−45.00, 45.00] | [−40.50, 40.50] | [−40.50, 40.50] | 81.00 | 27.00 | 0.00 | ok |
| L/R_crank_A/B_joint | [−68.75, 68.75] | [−61.88, 61.88] | [−61.88, 61.88] | 123.76 | 41.25 | ±17.1 | ok |

→ `[preflight] PASS (0 warning(s))`. **좌우 12관절의 사용 가능 창이 처음으로 완전히 대칭**이다.

### §1d 폐루프 발목 초기자세 (부수 발견, 같은 유형의 세 번째 버그)

bent 키프레임의 크랭크/로드 각은 v3 기하에서 푼 값인데(`pygmalion_v3_printed_loop_bent.json`,
closure 0.001 mm), v30은 `L_crank_A`와 `R_crank_B`의 축이 뒤집혀 있다. 그대로 넣으면 매 리셋이
**로드 끝과 발 볼조인트가 어긋난 상태**에서 시작하고 equality 구속이 그 간격을 튕겨 닫는다.

| 모델 | 수정 전 최대 closure | 수정 후 최대 closure |
|---|---|---|
| `pygmalion_v3_printed_loop` | 0.001 mm | 0.001 mm (불변) |
| `pygmalion_v4_printed_loop` | 0.001 mm | 0.001 mm (불변) |
| `LegOnly_..._v30_proxyfix_loop` | **37.270 mm** (L rod A) / 36.347 mm (R rod B) | **0.001 mm** |
| `FullDoF_..._v30_proxyfix_loop` | 동일 유형 | **0.001 mm** |

수정 후 네 모델 모두 리셋 시 발목 피치 각이 **+20.60° / +20.63°** 로 동일 — 물리적으로 같은
자세임이 확인된다.

### §1e 회귀 안전성 (기존 정책 계통 불변 검증)

컴파일된 모델의 관절 순서로 런타임이 실제로 계산하는 두 벡터(`default_joint_pos` =
`resolve_expr`, action clip = `resolve_matching_names_values`)를 **픽스 전/후 코드로 각각 덤프해
수치 비교**했다.

| 모델 | 관절/액션 집합·스케일 | max Δ default | max Δ clip | 바뀐 default |
|---|---|---|---|---|
| v4 printed loop (AB) | 동일 | **0.0000e+00°** | 2.67e−04° | 없음 |
| v3 printed serial (RP) | 동일 | **0.0000e+00°** | 2.67e−04° | 없음 |
| v3 printed loop (AB) | 동일 | **0.0000e+00°** | 2.67e−04° | 없음 |
| v30 LegOnly loop (AB) | 동일 | 4.01e+01° | 1.20e+02° | L_knee, R_hip_pitch, L_crank_A, R_crank_B, L_rod_A_u1/u2, R_rod_B_u1/u2 (=고쳐야 했던 8개) |

clip의 2.67e−04° (= 4.7 µrad)는 **도→라디안 왕복 오차**다: 이전 표는 도 단위로 손으로 적은
값(`math.radians(-112.75)`)이고 새 유도는 MJCF의 라디안을 직접 읽는다. 인코더 분해능보다 4자리
아래이며, 회귀 검사(`--legacy-equivalence`)가 이 편차의 최대값을 항상 출력한다.

## §2 결과

### §2a 오케스트레이션 (인프라 판정)

**✅ 완주.** 12:07:24 launch → 12:24:25 ALL PHASES DONE, **17분 1초**, 크래시 0건.

| 판정 항목 | 결과 |
|---|---|
| 프리플라이트 게이트 | **PASS**(12관절 전부 ok, 경고 0). 발사 로그에 표가 그대로 기록됨 |
| P1 | 게이트 top stage(4) 도달 → **iter 154 settle**(err_steady 0.6256 vs baseline 1.0760, streak 15/3, fell 0.0000) → iter 200 종료. stage 0→1만 `FORCED`(MAX-DWELL, iter 60) — zero-command 워밍업이라 err가 NaN인 **스모크 정상 경로**(직전 스모크와 동일) |
| P2 | P1 실측 종료 iter 200에서 `PYG_DR_START_ITER=200`/`END=320` 계산 → full-resume, `dr_factor` 0→**1.000**(iter 324) 도달 후 iter 399까지 유지 |
| 질량 DR (fastener50 권위본) | 바디명 해석 실패 없음, pseudo-inertia 이벤트 7종 정상 등록(`inertial_dr_pelvis/hip_pitch_link/hip_roll_link/thigh/shin/ankle_pitch_link/foot`) |
| 낙상 | 전 구간 `fell_over` **0.0000** |

**최종 지표(iter 399)**: reward 21.37(50avg 21.5), ep_len 500.6, `error_vel_xy` 0.797,
`error_vel_xy_steady` 0.659, `error_vel_yaw` 1.375, `thermal_effort_mean` 2.73,
`stance_knee_deg` 8.11°, `foot_impact_vel_max` 1.99, `dr_factor` 1.000.

> ⚠ 이 숫자들은 **성능 판정이 아니다**(1024 env, 399 iter, 단일 시드). 프로젝트 판정 규칙은
> 평가기 32-ep 통계 또는 200 Hz 멀티환경 프로브다.

### §2b 무릎 액션창 열림 확인 (이 스모크의 본론)

`analysis/gait_kinematics_probe.py`를 P2 체크포인트(`model_399.pt`)에 돌려 **명령 대역이 실제로
열렸는지**만 확인했다. 노미널 로봇(DR 이벤트 7종 제거), 17 s 기록 중 앞 2 s 과도구간 제외 =
15 s 분석, 50 Hz, num_envs=1, CPU. 원자료
`analysis/out/legonly_ab_v2_smoke_399_vx{0.6,1.2}.npz`.

| 무릎 | 조건 | qtarget 진폭 | qtarget p5..p95 [°] | 클립 경계 고착률 | q 사용 ROM | \|τ\| RMS [N·m] |
|---|---|---|---|---|---|---|
| **L_knee** (전, v1 model_5600) | 0.6 / 1.2 | **0.00° / 0.00°** | [−6.00, −6.00] (도달불가) | 100 % / 100 % | 0.21° / 0.37° | 21.79 / 21.87 |
| **L_knee** (후, smoke model_399) | 0.6 / 1.2 | **27.45° / 32.84°** | [6.00, 31.18] / [6.00, 36.93] | 58.5 % / 54.8 % | **30.14° / 37.21°** | **6.36 / 10.18** |
| **R_knee** (전) | 0.6 / 1.2 | 0.00° / 0.00° | [−6.00, −6.00] | 100 % / 100 % | 8.77° / 11.29° | 12.25 / 13.13 |
| **R_knee** (후) | 0.6 / 1.2 | 3.95° / 5.97° | [−7.17, −6.00] / [−6.53, −6.00] | 92.7 % / 93.5 % | 9.16° / 10.02° | 9.67 / 9.77 |

**판정: 통과.** 기준(양 무릎 qtarget 진폭 > 0 **AND** q 사용 ROM > 5°)을 두 속도 모두 충족한다.
왼무릎의 **상시 하드스톱 밀기(21.8 N·m 상수 토크)가 사라졌고**(6.4~10.2 N·m, 그것도 이제 변동),
목표각이 15초 내내 상수였던 것이 27~33° 진폭으로 바뀌었다.

⚠ **정직한 단서 두 가지**:
1. 오른무릎은 여전히 **명령의 93 %를 클립 상한(−6°, 최대 신전)에 붙여** 둔다. 이건 액션창
   버그가 아니라 근본원인 노트 §1의 **2순위(swing 무릎을 요구하는 리워드 항이 0개)** 그대로다.
   이번 픽스는 그걸 고치지 않았고(고칠 계획도 아니었다), 판단은 v2 본런 완주 후로 미룬다.
2. 좌우가 아직 비대칭이다(L 30~37° vs R 9~10°). 다만 **399 iter 정책의 비대칭을 5600 iter
   정책과 비교하는 것 자체가 like-for-like가 아니며**, 이 표는 "창이 열렸는가"만 답한다.

### §3b 영상

![[accum_legonly_ab_v2_smoke_p2.mp4]]

학습경과 accumulate 영상(런처 자동 생성, 2클립). **실시간 검증**: 1,000 스텝 × 50 Hz = 20.0 s
시뮬레이션, 파일 604 frames / 30 fps = **20.13 s** (`ffprobe`) → fps = rate/downsample =
50/1.667 = 30, 배속 없음.

최종정책 loadviz 시연 영상은 **만들지 않았다**: 399 iter 스모크 정책의 부하 시각화는 판정
가치가 없고, 직전 스모크([[2026-09-03_legonly_ab_smoke_test]])도 같은 이유로 생략했다.
본런 `legonly_ab_v2`는 두 영상 모두 필수다.

## §3 다음 단계

- 스모크 PASS + 양 무릎 창 열림 확인 시: 본런 `legonly_ab_v2`(16384 env, 32k, fastener50 DR,
  `--vy-stages`) 발사 판단은 **계획자 몫**. 이 노트는 발사하지 않는다.
- swing 무릎 리워드 항(근본원인 노트 §2의 2순위, Booster T1 knee-height)은 **별도 트랙**이며
  이번 픽스에 번들하지 않는다 — v2에서 자연 해소될 수 있고, 2026-08-24 규칙상 신규 항은
  +800 iter warm-start 단독 A/B로 시험한다.

## §2c 학습 중 리뷰 (게이트마다 스냅샷, docs/27 체크리스트)

![progress](mujoco/assets/legonly_ab_v2_smoke_p1_progress.png)

| 시각 | iter | reward | ep_len | noise σ | value loss | entropy | surrogate / LR | fell / low_base | err_vel xy / yaw | dr_factor / vx_max | thermal | 판정(docs/27) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 09-03 12:13 | 210 | 12.9 (50avg 9.3) | 306 | 0.417 | 0.0719 | 6.31 | -0.0079 / 1.1e-04 | 0.000 / 2.952 | 0.533 / 0.784 | 0.00 / 2.5 | 1.93 | P1 phase-end: review before P2 |
| 09-03 12:24 | 399 | 21.4 (50avg 21.5) | 501 | 0.382 | 0.126 | 5.14 | -0.0093 / 1.1e-04 | 0.000 / 2.000 | 0.797 / 1.375 | 1.00 / 2.5 | 2.73 | P2 phase-end: final smoke/training health review |
