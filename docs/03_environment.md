# 03 · 학습 환경 구성 (Velocity Locomotion Env)

> [!abstract] 목표
> Isaac Lab의 검증된 velocity-locomotion 환경(H1/G1 휴머노이드 레시피)을 **상속**해
> 우리 하반신 이족에 맞춘 `Pygmalion-Velocity-*` 태스크를 만든다. **Isaac Lab 원본은 수정하지 않는다.**

---

## 왜 (Why) — 바닥부터 안 짜는 이유
Isaac Lab엔 이미 `manager_based.locomotion.velocity`에 다음이 다 들어있다:
- 지형 생성(평지/계단/울퉁불퉁/경사), cmd_vel 명령, 외란 push, 도메인 랜덤화,
- 이족 보행 reward(속도추종, feet_air_time, feet_slide, 자세), 종료/커리큘럼.

→ 우리는 이걸 **상속(subclass)** 하고 **body/joint 이름만 우리 로봇으로 매핑**하면 된다.
바닥부터 짜는 것보다 안전·빠르고, 원본 무수정 원칙도 지킨다.

> [!tip] 이름은 spec에서 (하드코딩 없음)
> env의 body/joint 이름(base/foot/undesired/action_joints/target_height)은 모두 [[08_robot_hotswap]]의
> spec(`ROLES`)에서 읽는다. 로봇을 바꾸면 spec만 고치면 env가 따라온다.

## 무엇을 / 어디서 (What / Where)
- `tasks/locomotion/velocity_env_cfg.py` → `BipedRoughEnvCfg` (계단·울퉁불퉁·경사) + `BipedRewards`
- `tasks/locomotion/flat_env_cfg.py` → `BipedFlatEnvCfg` (평지)
- `tasks/locomotion/__init__.py` → Gym 등록 (`Pygmalion-Velocity-{Flat,Rough}[-Play]-v0`)
- 베이스: `isaaclab_tasks...velocity.velocity_env_cfg.LocomotionVelocityRoughEnvCfg`

## 어떻게 (How) — G1 → 우리 로봇 이름 매핑
| 용도 | G1 | 우리 (robot.xml) |
|---|---|---|
| 베이스/몸통 body | `torso_link` | `base_link` |
| 발 body (GRF/air-time/slide) | `.*_ankle_roll_link` | `.*_foot_link` |
| height_scanner anchor | `/Robot/torso_link` | `/Robot/base_link` |
| 낙상 종료 contact | `torso_link` | `base_link` |
| 토크/가속 페널티 관절 | `.*_hip_.* .*_knee` | 동일 + `.*_ankle_*` |
| 액션 관절 | 전 관절 | **12개 (toe 제외, 패시브)** |
| 상체/팔/손가락 deviation | 있음 | **제거** (상체 없음) |

### 관측 (Observation = policy 입력) — 현재 스펙
| 관측항 | 차원 | 노이즈(Unoise) | 분류 |
|---|---|---|---|
| `base_lin_vel` | 3 | ±0.1 | proprioception |
| `base_ang_vel` | 3 | ±0.2 | proprioception |
| `projected_gravity` | 3 | ±0.05 | proprioception(자세) |
| `velocity_commands` | 3 | — | 명령(cmd_vel vx,vy,wz) |
| `joint_pos` (기본자세 상대) | 12~14 | ±0.01 | proprioception |
| `joint_vel` | 12~14 | ±1.5 | proprioception |
| `last_action` | 12 | — | proprioception |
| `height_scan` (rough만) | ~187 | ±0.1 | 외수용(지형) |
> `enable_corruption=True` → **관측 노이즈 주입**(센서 DR, sim2real). ⚠️ **질량·마찰·외력은 관측에 없음** =
> 정책이 못 보고 **DR로 강건하게**(blind robustness; privileged/asymmetric critic은 미사용). 키보드 cmd_vel이 관측에 포함됨.

### 액션 (Action)
`JointPositionActionCfg(scale=0.5, use_default_offset=True)` — 정책이 12개 관절의 **목표각**을 출력,
PD 제어기가 토크로 변환. toe는 패시브로 제외.

### Reward 구성 (사람다움 = 여러 항의 합)
| 항 | 가중치(초기) | 의미 |
|---|---|---|
| track_lin_vel_xy / track_ang_vel_z | +1.0 / +2.0 | cmd_vel 추종 (핵심 과제) |
| feet_air_time_positive_biped | +0.25 | 한 발씩 들며 보폭 확보 (이족 single-stance) |
| feet_slide | −0.1 | 발 미끄럼 방지 (접지 중 수평속도) |
| flat_orientation_l2 / upright | −1.0 / +0.5 | 몸통 직립 |
| base_height_l2 | −1.0 | 주저앉음 방지(목표 0.85 m) |
| feet_distance_l1 | −0.5 | 다리 꼬임/과도한 벌림 방지 |
| no_flight_phase | −0.5 | 양발 동시 비행(점프) 방지 → 걷기 |
| dof_torques/acc/action_rate | 작은 − | 부드럽고 에너지 효율적 동작 |
| joint_deviation_hip, dof_pos_limits | − | 자연 자세·한계 보호 |
| termination_penalty | −200 | 낙상 강한 페널티 |

> 가중치는 **시작점**이며 [[04_reward_experiments]]에서 trial-and-error로 조정한다.

### 도메인 랜덤화 (DR) — 현재 스펙 ★ (각 env 독립 샘플)
학습 env의 16384개 로봇이 **각자 다른** 값을 받음 → 강건성 + `--video` 조망에 다양성으로 보임.
| DR 항목 | 이벤트 | 범위 | 시점 |
|---|---|---|---|
| **cmd_vel 방향·속도** | UniformVelocityCommand | vx **(−1,1)**·vy (−0.6,0.6)·wz (−1,1) **omnidirectional** | 주기 리샘플 |
| **체중(질량)** | `add_base_mass` | base_link **±5 kg** | startup |
| COM | `base_com` | x/y ±5cm, z ±1cm | startup |
| **마찰** | `physics_material` | static (0.4,1.25)·dynamic (0.3,1.0) | startup |
| **외력(reset push)** | `base_external_force_torque` | reset 시 | reset |
| reset 자세·속도 | `reset_base` | pose ±0.4m·yaw 전방위 + vel ±0.3 | reset |
| 초기 관절각 | `reset_robot_joints` | 기본 ×(0.7,1.3) | reset |
| **주기 외란 push** | `push_robot` | **6–11초마다 ±0.8 m/s** | interval |
| 관측 노이즈 | enable_corruption | 위 관측표 참고 | 매 스텝 |
> 측정/Play env(`*-Play-v0`)는 **DR 끔**(결정론적) — 질량은 `measure.py --base_mass/--mass_scale`로 의도적 스윕. [[05_sensing_logging]]
> ⚠️ `apply_robot_physics`(spec 질량 오버라이드)는 **측정 전용** — 학습 땐 끄고 `add_base_mass` DR이 질량 담당.

### 저RAM 대응
- rough terrain grid 8×8(기본 10×20 축소), Play는 5×5/num_envs 32.
- 학습 `--num_envs 256~1024`, `--headless`.

## 검증 포인트
- `python -c "import gymnasium, pygmalion_locomotion; print('Pygmalion-Velocity-Flat-v0' in gymnasium.registry)"`
- 짧은 학습이 OOM 없이 reward 상승. [[04_reward_experiments]]

## 다음 노트
- [[04_reward_experiments]] · [[05_sensing_logging]]
