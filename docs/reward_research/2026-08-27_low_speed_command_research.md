# reward 연구 — 저속 명령 무시(0.25 m/s 달성률 0 %) 근본원인 (2026-08-27)

> 트리거: [[103_v2_training_plan]] V1 — fc 121-command·15 s dwell 격자 측정에서 **cmd 0.25 m/s → 달성률 0 %**(ankleAB·ankleRP 양쪽), cmd 1.6 m/s → 오차 ~0.14 m/s. V1 가설("보상 산수가 저속/정지를 못 벌게 만든다")의 **어느 항이 정확히 어떻게** 그 결과를 내는지 산수로 확정. 바꾸려는 reward: `stand_still_penalty`(cmd_deadband/rel_floor) 및/또는 `air_time`/`track_linear_velocity`의 저속 게이팅·σ. **아직 수정하지 않음** — 이 노트가 근거.

## 1. 직전 결과 분석 — 정확한 산수

관련 코드(모두 `mujoco-sim/mjlab/src/mjlab/tasks/velocity/`):
`velocity_env_cfg.py`(base rewards dict) · `config/pygmalion/env_cfgs.py`(pygmalion 오버라이드) · `mdp/rewards.py`(함수 본문) · `mdp/velocity_command.py`(명령 샘플링).

### 1a. cmd = 0.25 m/s(순수 전진)에서 속도-민감 항만 계산

$$\text{track\_linear\_velocity}(a_x) = 2.0\cdot\exp\!\left(-\frac{(0.25-a_x)^2}{0.75}\right),\qquad
\text{track\_lin\_vel\_progress}(a_x)=\mathrm{clamp}\!\left(\min\!\left(\frac{0.25\,a_x}{0.35},\,0.25\right),0\right)$$

(std² = 0.75는 `env_cfgs.py:200`의 고속-freeze 수정 오버라이드; progress항 eps=0.1은 `rewards.py:71`.)

| 행동 (actual $a_x$) | track_linear_velocity | track_lin_vel_progress | stand_still_penalty | air_time | **합** |
|---|---:|---:|---:|---:|---:|
| **정지** ($a_x=0$) | 1.8401 | 0.0000 | **0**(게이트 OFF, §1b) | **0**(게이트 OFF, §1b) | **1.8401** |
| **정확히 추종** ($a_x=0.25$) | 2.0000 | 0.1786 | 0 | 0 | **2.1786** |
| **과속 추종** ($a_x=0.8$) | 1.3362 | 0.2500(캡) | 0 | 0 | **1.5862** |

→ 정지 대비 정확 추종의 순이득은 **+0.338/step**(계산 근거만; 이 항들만으로는 과속(0.8)조차 정지보다 낮다 — 1.586 < 1.840). [[103_v2_training_plan]]이 인용한 "+0.41 이득 / −0.9 비용(절반 action_rate)"과 부호·자릿수가 일치(같은 산수를 가리킴, §2 참조 — 그 문서는 실측 롤아웃 기반 수치라 여기 정적 계산과 완전히 같은 수는 아님. **재확인 필요**: 다음 게이트 때 `Episode_Reward/action_rate_l2` at cmd≈0.25 실측 로그로 −0.9 자릿수를 검증할 것).

**이 좁은 +0.34 마진은 아래 비용 항 중 아무거나 하나에도 잡아먹힌다**:
- `action_rate_l2`(weight −0.1): 정지(정적 포즈)면 raw 델타 ≈0, 스텝을 밟으면 확실히 >0. doc103 실측 절반(~−0.45/step)이 이 항.
- `foot_clearance`(−2.0)·`foot_swing_height`(−0.25)·`foot_slip`(−0.1)·`soft_landing`/`foot_impact_velocity`: 전부 발속도·접촉전이에 **곱**해지므로 정지 시 정확히 0, 스텝을 밟는 순간부터만 비용 발생 — 즉 **이 항들 중 어느 것도 "제대로 걸음"에 대해 상쇄 보상을 주지 않는다**(전부 편도 비용).
- `thermal_effort`(−0.02): τ² 합, 정적 지지력만 낼 때가 스윙보다 낮음.

### 1b. 게이트 표 — 왜 정지가 "무비용"인가

각 항이 저속(0.25)에서 켜지는지, 코드에 박힌 임계값과 함께:

| 항 | weight | 명령 게이트 임계값 | 0.25에서 활성? | 근거 |
|---|---:|---:|---|---|
| `track_linear_velocity` | +2.0 | 없음(항상) | 예 | `rewards.py:28` |
| `track_lin_vel_progress` | +1.0 | `cmd_mag>eps=0.1`이면 활성 | 예(0.25>0.1) | `rewards.py:48,71` |
| **`stand_still_penalty`** | **−1.0** | **`cmd_deadband=0.3`** — `cmd_mag>0.3` 여야 발동 | **아니오**(0.25<0.3, 구조적 OFF) | `rewards.py:77-118`, 기본값 미오버라이드 |
| **`air_time`**(스텝 보상) | **+1.0** | **`command_threshold=0.5`** | **아니오**(0.25<0.5) | `velocity_env_cfg.py:318-328`, base 미변경 |
| `foot_clearance`/`swing_height`/`slip`/`soft_landing`/`foot_impact_velocity`/`stance_knee_extension` | −2.0/−0.25/−0.1/−1.0/−2.0 | `command_threshold=0.05` | 예(비용만, §1a) | `env_cfgs.py` 각 항목 |
| `pose`(variable_posture) | +1.0 | `walking_threshold=0.05` (커맨드 기준, 실제속도 아님) | walking 레짐(느슨한 std)이지만 기본자세=정지자세라 정지 쪽이 오차 작음 | `rewards.py:832-913` |

**결론(1차)**: 0.25 m/s는 "걷기 시작"(0.05) 임계는 넘었지만 "정지 금지"(0.3)·"스텝 보상"(0.5) 두 임계 모두 못 넘는 **사각지대**다. 이 사각지대에서 로봇은 걷기의 모든 편도 비용을 물지만 걷기에 대한 보상은 거의 없다(추종 오차 축소분 0.34만). `air_time`(0.5)은 **의도적으로** 높게 잡혀 있었다(§2, "정지 친화적" 설계) — 버그가 아니라 트레이드오프. `stand_still_penalty`(0.3)는 §2에서 보듯 **완전히 다른 속도대(0.7–2.5)의 병리**를 잡으려고 캘리브레이션된 상수이며 <0.3 구간은 애초에 검증 대상이 아니었다.

### 1c. 왜 이게 "산수의 필연"이기도 한가 — 지수 커널의 구조적 성질

`track_linear_velocity`의 exp(−error²/σ²) 커널은 명령이 작을수록 정지가 "덜 틀린" 것으로 보인다: 정지가 받는 최대보상 대비 비율은 cmd=0.25에서 **92 %**(1.840/2.0), cmd=0.7(2026-07-11 H1 사례, 아래)에서는 **52 %**(1.041/2.0)다. 즉 **명령이 0에 가까울수록 "서 있어도 거의 만점"** — 이건 σ 튜닝으로 없앨 수 없는 가우시안 커널 자체의 성질이다(에러가 작으니까). 그래서 industry 관행(§3)은 이 문제를 커널 자체로 풀지 않고 **명령 자체를 죽이거나(deadband) 명시적 모드 스위치**로 우회한다.

### 1d. 명령 분포 — 저속 명령이 얼마나 나오나

`velocity_command.py`: `rel_standing_envs=0.1`(정확히 0으로 세팅, 문제 대역 아님), `rel_forward_envs=0.2`(전진고정, `abs().clamp(min=0.3)` — **0.3 미만은 이 경로에서 나올 수 없음**), 나머지 ~70 %는 vx·vy 독립 균일분포(박스). 최종 커리큘럼 단계(S4, iter 16000+, `env_cfgs.py:322-328`)는 vx∈[−2.0,2.5]·vy∈[−1,1](박스 면적 9.0 m²/s²); |v_xy|<0.3인 원의 면적은 π·0.09=0.283 → 일반 70 % 중 **3.1 %**, 전체의 **~2.2 %**만 "정지벌점 OFF"대역에 걸린다. |v_xy|<0.5(에어타임도 OFF)는 원면적 0.785 → 일반의 8.7 %, 전체의 **~6–8 %**(+forward_env가 [0.3,0.5)로 떨어지는 몇 %). **초기 단계(S0, vx∈[−0.8,0.8])는 박스가 3.2 m²로 훨씬 작아 같은 원이 전체의 ~17 %를 차지** — 즉 **문제 대역은 학습 초반에 가장 크게 노출되고, 커리큘럼이 넓어질수록 비중이 줄어든다**. 커리큘럼이 "고쳐주는" 게 아니라 그 대역을 점점 안 보이게 만들 뿐이라는 뜻 — 정지 우위가 강화되면 강화됐지 스스로 없어질 이유가 없다(수치는 코드 기반 추정, 실측 텔레메트리 대조 필요 — 캐비어트 참조).

## 2. 이전 이력 — 이 사각지대는 "새 버그"가 아니라 기존 결정들의 경계다

- [[2026-07-10_highspeed_freeze_progress_reward]]: 고속(≥2.0) 프리즈 해소를 위해 `track_linear_velocity` std² **0.25→0.75**(σ 0.5→0.866) 확대 + `track_lin_vel_progress` 신설. **이 확대가 저속에서 "서 있어도 보상 잔존"을 만든 원인 그 자체**(§1c).
- [[2026-07-11_midspeed_stall_overshoot]] (H1 가설, 15 s dwell 실측): cmd 0.7에서 정지 시 `exp(-0.49/0.75)=0.52`을 받는다고 **이미 계산해 기록**했다 — 지금 0.25에서 하는 계산(§1a)과 **동일한 메커니즘**을 5주 전 다른 속도점에서 발견한 것. 이 노트는 σ 축소를 "고속 프리즈 재발 위험"으로 **기각**하고 대신 command-gated 정지벌점을 채택했다.
- [[2026-07-12_gen2_bundle]]: `stand_still_penalty` 최초 도입. **`cmd_deadband=0.3`은 0.7 m/s stall을 잡기 위한 값이었다** — 0.25는 설계 사거리 밖.
- [[2026-07-13_stall_relative_threshold]]: 절대속도임계(0.15)→상대임계(`rel_floor=0.3·|cmd|`)로 교체. **0.3 선정 근거는 cmd 1.5–2.5 구간의 creep-게이밍 실측(달성률 0.56–0.57)** — 역시 저속과 무관.
- [[2026-07-05_periodic_contact_removal]]: 지금 죽어있는 `mdp.periodic_contact`(`rewards.py:550-599`) 함수 안에 **이미 "정지 모드 스위치" 구현이 존재한다** — `standing = total_command <= command_threshold(0.05)`일 때 `stand_rew = exp(-k_v·foot_vel).mean()`(양발 조용히)로 바꿔치기하는 분기(`rewards.py:592-598`). 이건 외부 문헌(§3)이 권장하는 "명령-조건 리워드 라우팅"을 우리가 **한 번 만들었다가 껐다**는 뜻. 제거 사유는 이 분기 자체가 아니라 **고정주기 클럭 관측(`gait_clock`)이 게이트 없이 항상 순환**해 v=0에서도 스텝을 강요한 것(그 노트 §2(b)) — 이번에 제안하는 수정(§4)은 클럭을 재도입하지 않으므로 이 전례가 기각 사유는 아니지만, **격리 실험 없이 재도입 금지**(캐비어트).
- 같은 노트가 명시: "표준 command-gated `feet_air_time`/`clearance`는 정지 친화적(threshold **0.5/0.05**)이 설계 의도" — 즉 `air_time`의 0.5는 처음부터 **의도적** 고임계(사소한 헛디딤을 진짜 보행처럼 보상하지 않으려는 안티게이밍)였다. §4의 제안은 이 의도를 무시하는 게 아니라 트레이드오프를 재계량하자는 것.

## 3. 학술/자료조사 (출처 하이퍼링크)

- **[legged_robot.py](https://github.com/leggedrobotics/legged_gym/blob/master/legged_gym/envs/base/legged_robot.py)**(leggedrobotics/legged_gym, ANYmal 계열 표준 레퍼런스): 두 메커니즘이 동시에 있다 — ① `_resample_commands`가 **`norm(cmd_xy) > 0.2`가 아니면 명령을 정확히 0으로 자른다**("set small commands to zero"), ② `_reward_stand_still = Σ|dof_pos − default| · 1[cmd_mag<0.1]`. 즉 **레퍼런스 구현은 0.2 m/s 미만 명령을 애초에 존재하지 않게 만든다** — pygmalion처럼 "0.25 m/s를 실제로 추종해야 할 목표"로 두지 않는다.
- **[legged_robot_config.py](https://github.com/leggedrobotics/legged_gym/blob/master/legged_gym/envs/base/legged_robot_config.py)**: `tracking_sigma=0.25`(σ²=0.25, exp(−error²/σ) 표기라 σ 자체가 우리 std²와 동일 스케일) — pygmalion의 원래(고속수정 前) 값과 정확히 같다. 지금 우리는 이 표준값의 **3배(0.75)**를 쓴다.
- **[IsaacLab issue #458](https://github.com/isaac-sim/IsaacLab/issues/458)**("Legged robots stand still despite tracking rewards"): 커뮤니티 답변(KyleM73)이 두 가지를 지목 — (a) **"action-rate/acceleration 페널티 weight를 낮춰라, 그렇게 크면 안 된다"**(우리 doc103의 "비용의 절반이 action_rate"와 정확히 같은 병리를 다른 사람이 다른 로봇에서 겪음), (b) **"추종 std를 오히려 작게 하라 — 기본값은 너무 관대해서 큰 오차도 보상해버린다"**(우리가 한 것과 **반대** 방향 — 고속을 풀려고 넓힌 σ가 저속엔 정반대 부작용).
- **[Gait-Conditioned RL with Multi-Phase Curriculum](https://arxiv.org/abs/2505.20619)**(2025, 이미 [[2026-08-26_human_landing_bundle]]에서 straight-knee 항의 출처로 인용된 논문): one-hot **gait-ID**를 관측에 붙여 액터/크리틱을 조건화하고, **"gait mask가 현재 gait에 맞는 보상 항만 선택 활성화"**. Standing 모드는 **`‖v_cmd‖<0.1 m/s`이고 double-support 1.5 s 지속** 시 진입(walk→stand 전이), 모드별 보상표(Table IV)에 Standing 전용 `Stillness bonus`(+2.0)·`Contact(standing)`(+2.5)·`Base motion(standing)`(+2.5) 등 **독립 가중치**를 둔다. Walking 카테고리엔 `Straight knee` +0.1(우리가 이미 차용). → **필드 표준 임계는 0.1**, 우리 `stand_still_penalty`의 0.3보다 3배 낮다.
- **[MuJoCo Playground](https://arxiv.org/html/2502.08844v1)**(DeepMind, G1/H1/T1/Berkeley Humanoid 조이스틱 태스크 포함): 정지-특화 페널티 항이 명시적으로 존재(`r_standstill`류, 명령이 0에 가까운데 관절이 움직이면 벌점 — 정확한 수식은 PDF 파싱이 불완전해 **자릿수·상수 확인 불가, 저신뢰**로 표기). Air-time/게이트류 항이 커맨드 크기로 조건화된다는 서술은 있으나 수치는 확보 못함 — **후속 확인 필요**.
- **[Booster Gym](https://arxiv.org/html/2506.15132v1)**(2025 실기체 프레임워크): "일정 확률로 명령을 'stand still'로 설정해 정지↔보행 전이를 학습시킨다"는 것이 명시적 서술 — legged_gym과 동일하게 **연속값이 아니라 이산 모드 샘플링**으로 정지를 다룬다(우리처럼 "0.25 m/s를 걸어야 하는 값"으로 두지 않음).
- 자사 선행 코드(§2의 `periodic_contact`)도 근본적으로 같은 패턴(명령 임계 이하 → 별도 정지-리워드 분기)이라 이 자료조사 결과는 **우리가 한 번 검증했던 접근과 외부 필드가 수렴**함을 보여준다.

## 4. 원인·문제 규명

**근본 원인은 doc103의 가설("보상 산수가 저속을 못 벌게 만든다")이 맞고, 정확한 메커니즘은 다음 세 가지의 결합이다.**

1. **게이트 불일치(구조적 사각지대)**: `stand_still_penalty`(deadband 0.3)와 `air_time`(command_threshold 0.5)이 코드베이스 나머지 8곳(0.05 컨벤션)보다 훨씬 높게 설정돼 있고, 그 값들은 **각각 다른 속도대(0.7–2.5)의 병리를 잡으려고 캘리브레이션**됐을 뿐 0.25 근방은 한 번도 검증 대상이 아니었다(§2). 그 결과 0.05–0.3 m/s 대역은 "걷기 비용은 다 물지만 정지금지도 스텝보상도 없는" 무주지다.
2. **고속수정의 부작용**: 2026-07-10 std² 0.25→0.75 확대가 저속에서 정지의 보상 잔존율을 92 %까지 올려놓았다(§1c) — 이건 이미 7월에 H1으로 진단됐지만 "회귀 위험"으로 미수정 상태로 남아 있었다(§2).
3. **비대칭 비용구조**: 걷기에 관련된 발-궤적 항(clearance/swing/slip/soft-landing/impact) 전부가 "정지 시 정확히 0"인 **편도 비용**이라 저속 대역에서 걷기를 상쇄할 보상원이 track 항 +0.34/step 하나뿐이다 — action_rate_l2 하나만으로도 역전된다(doc103 실측, §1a에서 재확인 필요 표시).

세 가지 다 "버그"가 아니라 **각각 독립적으로 합리적이었던 이전 결정들이 서로 겹치지 않는 속도대를 가정**한 결과다. 외부 필드(legged_gym/Booster Gym/2505.20619)가 이 문제를 원천적으로 피하는 방법은 우리와 다르다: **연속 커널이 알아서 저속을 처리하게 두지 않고, 저속을 아예 명령 샘플링 단계에서 없애거나(deadband) 이산 모드로 분리한다**(§1c의 구조적 이유와 정합).

## 5. 제안 (우선순위 — reward 변경 전 §6 위험 검토와 함께 읽을 것)

| # | 항/변경 | 정확한 정식화 | 기대 효과 | 근거 |
|---|---|---|---|---|
| **P1** | `stand_still_penalty.cmd_deadband` 0.3→**0.05** (rel_floor 0.3은 유지 — 그건 creep 게이밍 대응이라 별개 축) | 코드 1줄, 기존 함수 그대로 | 0.25 m/s부터 "정지=−1.0 flat cost"가 걸려 §1a의 +0.34 마진이 최소 +1.34로 벌어짐(2026-07-11 H1 계산의 cmd 0.7 사례와 동일 크기) | 코드베이스 자체 컨벤션(0.05가 7곳에서 이미 표준, §1b) + [[2026-07-05_periodic_contact_removal]]의 "표준 임계 0.05" 명시 |
| **P2** | `air_time.command_threshold` 0.5→**0.05**(또는 최소 0.15) — **단독 A/B, 헛디딤 게이밍 감시** | `feet_air_time` params 오버라이드 한 줄 | 0.05–0.5 대역에서 스텝에 대한 유일한 양(+)의 보상이 켜져, "밟았다가 서는" 국소해의 스텝-비용을 상쇄 | 0.5는 [[2026-07-05_periodic_contact_removal]]에서 **의도적으로** "정지 친화적"으로 설정된 값 — 낮추면 그 트레이드오프(사소한 헛디딤 과대보상)가 재발할 수 있다는 걸 알고 진행. legged_gym 관행(정지는 명령 자체를 0으로 자름, P3 참조)과는 다른 절충 |
| **P3 (아키텍처, 검토용)** | 명령 샘플링에 **legged_gym식 deadband** 추가: `velocity_command.py`의 `_resample_command`에서 `‖(vx,vy)‖<0.15~0.2`면 명령을 정확히 0으로 스냅(현재 `rel_standing_envs=0.1`과 별개로, 일반 샘플의 저속 꼬리에도 적용) | `xy *= (norm>θ)` (legged_gym 원본과 동일 형태) | 0.25 m/s를 "추종해야 할 목표"에서 원천 제거 — 단, **fc 121-command 격자에서 0.25를 계속 실제 목표로 측정하고 싶다면 이 옵션은 측정 프로토콜과 상충**하므로 채택 전 목적 재확인 필요(§6 캐비어트) |
| **P4** | `track_linear_velocity`의 σ를 **속도-의존**으로 분리: 저속 대역(|cmd|<0.5)은 σ²≈0.25(레퍼런스 표준, [[2026-07-10_highspeed_freeze_progress_reward]] 이전 값)로 되돌리고, 고속은 현행 0.75(진행보상이 고속 gradient를 이미 담당하므로 저속만 좁혀도 고속 회귀 위험 낮음) | `std = std_lo if cmd_mag<0.5 else std_hi` 형태로 `track_linear_velocity`에 파라미터 추가 | §1a 재계산 시 저속 마진이 0.34→약 0.6대로 확대(§1c의 92%→약 78% 잔존율) | [[2026-07-11_midspeed_stall_overshoot]] H1(σ 축소를 "회귀위험"으로 전면 기각했던 것과 달리 **저속 전용 분리**라 고속 회귀 없이 그 우려를 해소) + IsaacLab #458(KyleM73: "std를 작게 하라") |
| **P5 (구조적, 장기)** | `periodic_contact`(`rewards.py:550-599`)의 **정지 분기만** 살려 재사용: 고정 클럭(위상 스케줄)은 재도입하지 않고, `standing = total_command <= θ`일 때 `foot_clearance/swing/slip/air_time` 전체를 "조용한 양발 지지" 단일 보상으로 스위치하는 명시적 모드 라우팅 도입 | Gait-ID 원-핫 관측 + 모드별 보상 마스킹([[arXiv:2505.20619]] Table IV 패턴) | P1–P4보다 근본적으로 사각지대 자체를 없앰(연속 커널에 의존하지 않음) | [[2026-07-05_periodic_contact_removal]](자사 선행 구현) + arXiv:2505.20619 + legged_gym 이산 모드 샘플링 |
| P6 | `action_rate_l2` 저속 전용 완화(weight 그대로 두되 저속에서만 절반) | `weight *= 0.5 if cmd_mag<0.5` 류 | doc103 실측상 비용의 절반을 차지하는 항을 저속에서만 완화 — 부작용(떨림 증가) 위험 커서 P1–P2 이후 잔여 갭이 있을 때만 | IsaacLab #458(action-rate 과대가 "정지 선호"의 공통 원인) — **§1a의 "재확인 필요" 실측 전에는 저우선** |

**권장 순서**: P1(무위험, 0.05는 이미 코드베이스 표준) 단독 +800 iter 격리 실험 → 게이트: teleop cmd=0 정지 유지 + fc 0.25/0.5 달성률. 안 풀리면 P2 추가(헛디딤 게이밍 감시, `Episode_Reward/air_time` 로그로 V15 규칙 확인). 그래도 부족하면 P4(σ 분리). P3/P5는 아키텍처 변경이라 사용자 결정 필요(§6).

## 6. 캐비어트 (≤5)

1. §1a의 "+0.41/−0.9" 숫자는 doc103에 출처 노트 없이 인용돼 있다 — 본 노트의 +0.338은 **정적 산수**(실제 롤아웃 없이 track/progress 항만 계산)이고 부호·자릿수는 일치하나 정확히 같은 수는 아니다. reward edit 전 `Episode_Reward/action_rate_l2`(cmd≈0.25 구간) 실측으로 −0.9/−0.45 자릿수를 검증할 것.
2. §1d의 명령 분포 비율(2–8 %)은 커리큘럼 코드에서 **역산한 추정치**이며 실제 학습 텔레메트리(명령 히스토그램)로 대조하지 않았다.
3. P2(air_time 임계 완화)는 [[2026-07-05_periodic_contact_removal]]에서 **의도적으로** 정지 친화적으로 잡은 값을 되돌리는 것이라, 헛디딤 과대보상(게이밍) 재발을 반드시 단독 ablation으로 감시해야 한다.
4. P3(명령 자체 deadband)는 "0.25 m/s를 실제 걷기 목표로 유지"라는 fc 측정 프로토콜의 전제와 상충할 수 있다 — 채택 전 "0.25는 추종 대상인가, 정지 대상인가"를 사용자와 확정할 것.
5. 외부 자료 중 MuJoCo Playground의 `r_standstill` 수식은 PDF 파싱이 불완전해 **자릿수 확인이 안 된 저신뢰 인용**이다(§3에 명시); 정식 채택 전 원문 HTML/코드로 재검증 필요.
