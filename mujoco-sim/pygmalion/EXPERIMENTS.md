# Pygmalion 학습 실험 기록

---

## v1 — 기본 설정 (baseline)

**태스크 ID:** `Mjlab-Velocity-Flat-Pygmalion` / `Mjlab-Velocity-Rough-Pygmalion`

**설정 파일:** `robot/task_velocity_pygmalion/env_cfgs.py` → `pygmalion_flat/rough_env_cfg()`

### 주요 보상 설정

| 항목 | 함수 | weight | 파라미터 |
|------|------|--------|---------|
| foot_clearance | `mdp.feet_clearance` | **−2.0** | target_height=0.10 m, deviation×vel_norm 패널티 |
| foot_swing_height | `mdp.feet_swing_height` | −0.25 | target_height=0.10 m, 착지 시 peak height 편차 |
| foot_slip | `mdp.feet_slip` | −0.1 | — |

### 액션 스케일

관절별 상이 (`PYG_ACTION_SCALE = 0.25 × effort_limit / stiffness`):

| 관절 | scale |
|------|-------|
| ankle_roll | 1.773 |
| hip_pitch / hip_roll / knee | 1.086 |
| hip_yaw / ankle_pitch | 0.760 |

### 체크포인트

- `weights/run1_0-30000/model_{6000~30000}.pt`
- `weights/run2_30000plus/model_{36000~51700}.pt`

---

## v2 — Gaussian clearance reward + 균일 액션 스케일

**태스크 ID:** `Mjlab-Velocity-Flat-Pygmalion-v2` / `Mjlab-Velocity-Rough-Pygmalion-v2`

**설정 파일:** `robot/task_velocity_pygmalion/env_cfgs.py` → `pygmalion_flat/rough_env_cfg_v2()`

**날짜:** 2026-07-01

### v1 대비 변경 사항

#### 1. `foot_clearance`: 패널티 → 양의 보상 (형태 변경)

| | v1 | v2 |
|---|---|---|
| 함수 | `mdp.feet_clearance` | `mdp.feet_clearance_reward` (신규 추가) |
| weight | **−2.0** | **+1.0** |
| 수식 | `Σ \|height − target\| × vel_norm` (패널티) | `Σ exp(−error²/std²) × tanh(2×vel)` (Gaussian 보상) |
| target_height | 0.10 m | **0.13 m** |
| std | — | 0.05 |

**변경 이유:**
- 패널티 방식은 목표 높이에서 벗어난 정도를 선형으로 감산 → 어느 방향이든 나쁨
- Gaussian 보상은 목표 높이 근방에서만 강한 양의 신호 → 정밀한 발 높이 제어 유도 (G1과 동일 방식)
- target_height 10 → 13 cm: 다리가 약 78 cm인 Pygmalion에서 좀 더 명확한 clearance 확보

#### 2. `foot_swing_height`: 제거

**제거 이유:**
- `foot_clearance`와 역할 중복:
  - `foot_clearance`: 매 스텝, swing 중 현재 발 높이 평가
  - `foot_swing_height`: 착지 시, swing 중 최고 높이 평가
- 같은 목표(10 cm 발 들기)를 두 신호가 동시에 강제 → 신호 간섭 가능성
- `foot_clearance`가 더 즉각적이고 dense한 피드백이므로 이쪽만 유지

#### 3. 액션 스케일: 관절별 → 균일 0.25

| | v1 | v2 |
|---|---|---|
| ankle_roll | 1.773 | **0.25** |
| hip_pitch / roll / knee | 1.086 | **0.25** |
| hip_yaw / ankle_pitch | 0.760 | **0.25** |

**변경 이유:**
- v1의 per-joint scale은 `effort_limit / stiffness` 비율 기반으로 모터 특성을 반영하지만,
  신경망 출력 분포가 관절마다 달라져 학습이 불균일해질 수 있음
- G1과 동일한 0.25 균일 스케일로 맞춰 학습 안정성 비교

### 변경되지 않은 설정

v1과 동일: PPO 하이퍼파라미터, 네트워크 구조, 관측 공간, 커맨드, DR, pose 보상 std 등

### 실행 커맨드

```bash
# flat
uv run train Mjlab-Velocity-Flat-Pygmalion-v2 --env.scene.num-envs 4096

# rough
uv run train Mjlab-Velocity-Rough-Pygmalion-v2 --env.scene.num-envs 4096
```

### 체크포인트

- `logs/rsl_rl/pygmalion_velocity/2026-07-01_22-07-24/model_9900.pt`

### 분석 결과 (60 s 롤아웃)

| 관절 | 한계 | max | p95 | >90% |
|------|------|-----|-----|------|
| L_ankle_pitch | 60 N·m | 8.8 | 4.5 | 0% |
| R_ankle_pitch | 60 N·m | 27.5 | 7.3 | 0% |
| L/R_hip_roll | 120 N·m | 86/98 | 73/63 | 0% |

**문제점:** L_hip_roll qpos 범위 -0.792~-0.787 rad (범위 0.005 rad, 거의 한계에 고착).
base_z mean=0.365 m, min=0.328 m — 앉는 자세(local minimum)로 수렴.

---

## v3 — 로컬미니멈 대응 (얼리 터미네이션 + 느린 커리큘럼)

**태스크 ID:** `Mjlab-Velocity-Flat-Pygmalion-v3` / `Mjlab-Velocity-Rough-Pygmalion-v3`

**설정 파일:** `mjlab/src/mjlab/tasks/velocity/config/pygmalion/env_cfgs.py` → `pygmalion_flat/rough_env_cfg_v3()`

**날짜:** 2026-07-02

### v2 대비 변경 사항

#### 1. 얼리 터미네이션: `low_base_height`

| | v1/v2 | v3 |
|---|---|---|
| 추가 터미네이션 | 없음 | `low_base_height(min_height=0.59 m)` |
| 조건 | — | `base_z - terrain_z < 0.59 m` 이면 에피소드 종료 (패널티) |

**임계값 근거 (v1/v2 60 s 롤아웃 측정):**

| | base_link mean | base_link min | base_link p5 |
|---|---|---|---|
| v1 정상 보행 | 0.816 m | 0.792 m | 0.804 m |
| v2 squatting | 0.364 m | 0.345 m | 0.350 m |

- 두 분포가 완전히 분리됨 (간격 ~45 cm)
- 임계값 **0.59 m** = v1 p5(0.804 m)와 v2 p95(0.381 m)의 중간점
- v1 정상 보행: 절대 안 잡힘 (최솟값 0.792 m >> 0.59 m)
- v2 squatting: 항상 잡힘 (최댓값 0.389 m << 0.59 m)
- `time_out=False` → 에피소드 종료 + 보상 없음 → 앉기 행동 억제

#### 2. 커리큘럼: 초기 속도 범위 낮춤 + 증가 타이밍 2배 지연

| 단계 | v1/v2 | v3 |
|------|-------|-----|
| step 0 | (-1.0, 1.0) m/s, ω: ±0.5 | **(-0.5, 0.8) m/s, ω: ±0.3** |
| step 120k (5000×24) | (-1.5, 2.0) m/s, ω: ±0.7 | (-1.0, 1.5) m/s, ω: ±0.5 |
| step 240k (10000×24) | (-2.0, 3.0) m/s | (-1.5, 2.0) m/s, ω: ±0.7 |
| step 480k (20000×24) | — | (-1.5, 2.0) m/s (최종) |

**근거:**
- 초기 커맨드가 너무 크면 기본 보행 학습 전에 direction-matching local minimum에 빠질 수 있음
- 낮은 속도부터 시작해 균형·보행 기초를 먼저 학습한 뒤 속도 증가

### 실행 커맨드

```bash
# flat
uv run train Mjlab-Velocity-Flat-Pygmalion-v3 --env.scene.num-envs 4096

# rough
uv run train Mjlab-Velocity-Rough-Pygmalion-v3 --env.scene.num-envs 4096
```

### 체크포인트

- `wandb/run-20260702_091002-28cx4dzk/files` (Flat, model_9900)

---

## v4: v3 + Foot Contact Force Penalty

**태스크:** `Mjlab-Velocity-Flat-Pygmalion-v4`, `Mjlab-Velocity-Rough-Pygmalion-v4`

### v3 대비 변경 사항

#### 추가: `foot_contact_force` 패널티

| 항목 | 값 |
|---|---|
| 함수 | `foot_contact_force_penalty` |
| 수식 | ∑_foot max(\|F_c\| − 500 N, 0) |
| weight | **−0.005** |
| 센서 | `feet_ground_contact` (net force, global frame) |

**근거 (v3 측정값 기반):**

| 지표 | v3 selftest (2000 steps) |
|---|---|
| Left foot Fz max | **2126 N** |
| Right foot Fz max | **2069 N** |
| Left foot Fz mean | 257.9 N |
| Right foot Fz mean | 253.3 N |
| 피그말리온 추정 체중 | ~50 kg → 정적 단발 하중 ≈ 490 N |

- 임계값 500 N ≈ 체중×1.0: 정적 하중과 동일한 기준, 동적 충격만 억제
- 피크 2000+ N은 ~7.5/step 패널티 → 충격 착지 강하게 억제
- `soft_landing`(착지 순간만)과 달리 이 패널티는 **지속적으로 높은 힘도 억제**

#### 나머지 설정 (v3 동일)

- `low_base_height` 얼리 터미네이션 (min_height=0.59 m)
- 커리큘럼: 초기 ±0.5 m/s, 단계적 증가

### 실행 커맨드

```bash
# flat
uv run train Mjlab-Velocity-Flat-Pygmalion-v4 --env.scene.num-envs 4096

# rough
uv run train Mjlab-Velocity-Rough-Pygmalion-v4 --env.scene.num-envs 4096
```

### 체크포인트

- (학습 예정)

---

## v5: v4 + High-Gain PD

**태스크:** `Mjlab-Velocity-Flat-Pygmalion-v5`, `Mjlab-Velocity-Rough-Pygmalion-v5`

**파일:** `pygmalion_constants_hg.py` (신규, 기존 constants.py 유지)

### v4 대비 변경 사항: Kp/Kd 상향

| 관절 | 모터 | 기존 Kp | 기존 Kd | **v5 Kp** | **v5 Kd** | G1 Kp | G1 Kd |
|---|---|---|---|---|---|---|---|
| hip_pitch/roll | RS04 | 27.6 | 1.76 | **100** | **2.0** | 100 | 2 |
| knee | RS04 | 27.6 | 1.76 | **150** | **4.0** | 150 | 4 |
| hip_yaw | RS03 | 19.7 | 1.26 | **40** | **2.0** | 40 | 2 |
| ankle_pitch | RS03 | 19.7 | 1.26 | **40** | **2.0** | 40 | 2 |
| ankle_roll | RS00 | 2.0 | 0.13 | **14** | **0.5** | 40 | 2 |

- ankle_roll(RS00)은 피크 토크 14 N·m 한계로 인해 G1 수준(40)이 아닌 보수적인 14로 설정
- 나머지 v4 설정 동일 (low_base_height 터미네이션, 커리큘럼, contact force 패널티 500 N)

### 실행 커맨드

```bash
uv run train Mjlab-Velocity-Flat-Pygmalion-v5 --env.scene.num-envs 4096
```

### 체크포인트

- (학습 예정)

---

## v6: v5 - contact_force + ankle_deviation + ankle_roll 60 N·m

**태스크:** `Mjlab-Velocity-Flat-Pygmalion-v6`, `Mjlab-Velocity-Rough-Pygmalion-v6`

### v5 대비 변경 사항

| 항목 | v5 | v6 |
|---|---|---|
| `foot_contact_force` 패널티 | weight=-0.005 (500 N 초과) | **제거** |
| `ankle_deviation` 패널티 | 없음 | **추가, weight=-0.02** |
| ankle_roll effort_limit | 14 N·m | **60 N·m** |
| ankle_roll Kp/Kd | 14 / 0.5 | 14 / 0.5 (동일) |

수식: `∑|q_ankle_rp - q_default|` (L1 norm, L/R pitch+roll 4관절)

### 실행 커맨드

```bash
uv run train Mjlab-Velocity-Flat-Pygmalion-v6 --env.scene.num-envs 4096
```

### 체크포인트

- (학습 예정)

---

## v8: v7 + 박스 발판 + 앞뒤 균형 보상 + 토크 한계 패널티

### 변경 사항 (v7 대비)

#### 1. 발 충돌 형상 변경 (XML)
- 각 발을 **앞판(foot1) + 뒤판(foot2)** 2개 박스로 단순화
  - `foot1_collision`: 앞판(발끝), `pos Y=-0.122`, `size 10×12.2×2 cm`
  - `foot2_collision`: 뒤판(뒤꿈치), `pos Y=+0.001`, `size 10×12.2×2 cm`
  - 원래 캡슐 대비 **+2cm 후방** (heel 방향) 이동
- 적용 파일: `pygmalion.xml`, `pygmalion_ab.xml`

#### 2. 신규 리워드: `foot_plate_balance` (+0.3)

**발판 geom에서 직접 측정한 접촉력** 기반의 균등 분포 리워드.

전용 ContactSensor(`foot_plate_contact`, `mode="geom"`) 를 scene에 추가해  
L_foot1, L_foot2, R_foot1, R_foot2 geom 각각의 net vertical force를 측정.

```
balance = min(F_front, F_rear) / (max(F_front, F_rear) + 1)  — 발당
reward  = balance_L × contact_L + balance_R × contact_R
```
- 1.0 = 앞·뒤판 완전 균등, 0.0 = 한쪽 판에만 하중
- 접지 중(F_front + F_rear > 5 N)일 때만 활성 / 양발 합산 최대 +2.0

#### 3. 신규 패널티: `joint_torque_excess` (-3.0)
```
Σ_j max(|τ_j| / τ_limit_j − 0.9, 0)   — 정규화 초과분 합산
```
- 관절 토크가 한계의 90% 초과 시 강한 패널티
- 12관절 모두 한계 시 최대 -3.6/step ≈ 추적 보상의 ~2.4배

### 리워드 구성 (v8 신규 항목)

| 항목 | weight | 비고 |
|------|--------|------|
| `foot_plate_balance` | +0.3 | per-geom Fz 직접 측정, balance ratio |
| `joint_torque_excess` | -3.0 | 정규화 초과분, threshold=0.9 |

### 실행 커맨드

```bash
uv run train Mjlab-Velocity-Flat-Pygmalion-v8 \
  --env.scene.num-envs 4096 --logger wandb --wandb-project HuphyChan

uv run train Mjlab-Velocity-Rough-Pygmalion-v8 \
  --env.scene.num-envs 4096 --logger wandb --wandb-project HuphyChan
```

### 체크포인트

- (학습 예정)
