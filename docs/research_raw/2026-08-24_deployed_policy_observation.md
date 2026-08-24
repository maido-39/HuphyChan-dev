# 원자료 — 실제 배포 스택이 IMU에서 무엇을 읽어 관측을 조립하는가 (2026-08-24, Sonnet 서브에이전트)

조사 지시: 학습 코드 말고 **실기 배포 코드**를 줄 단위로. SDK에서 읽는 양·프레임·주기·obs 패킹 순서, IMU 표현, base 선속도 처리, sim2real 함정, 히스토리.

## 스택 비교
| 스택 | 로봇 | 전송 | 제어주기 | obs 크기 | 히스토리 | IMU 표현 | base 선속도 |
|---|---|---|---|---|---|---|---|
| unitree_rl_gym `deploy/deploy_real/deploy_real.py` | G1/H1 | Unitree DDS(CycloneDDS) | `control_dt=0.02` 50 Hz | 47 | 없음(단일 프레임) | 쿼터니언 → **projected gravity** | **LowState_에 필드 자체가 없음** |
| Booster Gym `deploy/deploy.py` | T1 | Booster SDK | 500 Hz 상태/명령 스레드, `decimation=10` → 50 Hz 정책 | 47 | 없음 | **RPY** → projected gravity | SDK에서 안 읽음; obs의 속도 슬롯엔 **조이스틱 명령값**을 넣음 |
| ASAP (LeCAR/CMU, RSS'25) `sim2real/` | G1 29dof | **ROS2 rclpy** | `create_rate(50)` | 47~100+ | **있음, 전 항목 4프레임** | 쿼터니언 → projected gravity | 슬롯은 있으나 **한 번도 채우지 않음(0 고정)**, 대신 명령속도 사용 |
| humanoid-gym (XBot-L) | — | *sim2sim만 공개* | `dt=0.001`·dec 10 → **100 Hz** | 47×frame_stack | **frame_stack deque** | **raw 오일러각 + raw 각속도** (예외) | sim에서 계산하되 **obs에 안 넣음** |

## 코드 인용
- unitree_rl_gym: `quat = low_state.imu_state.quaternion` / `ang_vel = imu_state.gyroscope` → `get_gravity_orientation(quat)`; obs = `[ang_vel, gravity, cmd, (q−default), dq, prev_action, sin_phase, cos_phase]`. `g1.yaml`: `control_dt 0.02, ang_vel_scale 0.25, dof_pos_scale 1.0, dof_vel_scale 0.05, action_scale 0.25, num_obs 47`.
- ★ **IMU 장착 프레임 보정**: H1/H1_2는 IMU가 **몸통**에 있고 정책은 골반 프레임 가정 → `transform_imu_data(waist_yaw, waist_yaw_omega, quat, ang_vel)`로 쿼터니언·각속도를 골반 프레임으로 되돌린다.
- Booster: `projected_gravity = rotate_vector_inverse_rpy(rpy[0],rpy[1],rpy[2], [0,0,-1])`, `base_ang_vel = imu_state.gyro`. **IMU 기울기 안전정지**: `abs(rpy[0])>1.0 or abs(rpy[1])>1.0 → running=False`. 500 Hz 발행 스레드에서 `filtered = filtered*0.8 + target*0.2` EMA.
- ★ **Booster의 병렬 발목 처리**: `# Use series-parallel conversion for torque to avoid non-linearity` — 병렬 기구 관절(`parallel_mech_indexes`)은 정책의 위치 액션을 **직렬 엔코더 기반 계산 토크**로 변환해 보낸다(학습측 액추에이터 모델엔 대응물 없음).
- ASAP: `state_processor.py`에서 `q[0:3]=0`(베이스 위치 미사용), `q[3:7]=imu.quaternion`, `dq[3:6]=imu.gyroscope`, **`dq[0:3]`(베이스 선속도)는 한 번도 쓰지 않음**. 정책은 ONNX(`onnxruntime`)로 로드. `history_config`: 전 항목 길이 4.

## 판정
1. **IMU 표현**: 실기에 도달한 3개 스택 모두 자세를 **본체 프레임 중력벡터 3성분**으로 변환해 넣는다(쿼터니언·RPY 원본 아님). humanoid-gym sim2sim만 오일러각 사용(실기 코드 미공개).
2. **가속도계는 아무도 안 쓴다** — Unitree IDL에 `accelerometer[3]`가 있지만 세 스택 어디서도 읽지 않는다. gyro + 벤더 EKF가 만든 쿼터니언/RPY만 사용.
3. **각속도는 raw**(소프트웨어 LPF 없음), 스케일만 곱한다(0.25 또는 1.0).
4. **바이어스/드리프트 보정 코드 없음** — 벤더 온보드 추정기를 그대로 신뢰.
5. **base 선속도는 실기에서 안 쓴다**: Unitree LowState에 필드 자체가 없고, Booster·ASAP은 슬롯에 **명령값**을 넣거나 0으로 둔다. 학습 YAML에는 `base_lin_vel: 3, scale 2.0`가 남아 있어 **특권(critic) 항으로만 존재**함을 시사.
6. 학습된 상태추정 네트워크나 가속도 적분은 이 3개 스택에 **없다**(문헌엔 존재).

## sim2real 함정 (이슈 인용)
- **obs 순서는 체크포인트 계약**: 같은 프레임워크 안에서 Go2는 `(lin_vel, ang_vel, gravity, cmd, q, dq, act)`, G1/H1 배포는 `(ang_vel, gravity, cmd, q, dq, act, sin, cos)` — 섞으면 "얼추 동작하다 실패"(issue #32).
- **관절 순서**: `default_joint_angles` 딕셔너리 순서는 의미 없음; URDF 선언 순서(Isaac Gym) vs BFS 순회(Isaac Sim)가 **다르다** → 같은 URDF라도 학습 시뮬레이터에 따라 순서가 달라진다(issue #43, PR #98 `doc/dof_order.md`).
- **obs 스케일·구성 미문서화 시 조용한 실패**: 77차원 체크포인트를 JIT 그래프만 보고 복원 불가(issue #95).
- **지연 보상 코드 없음**(3개 스택 모두). Booster의 500 Hz EMA가 부수적 지연을 만들 뿐.
- **액션 클립이 스택마다 다름**: Booster 1.0으로 클립 / ASAP ±100(NaN 가드) + 관절한계 클립 / unitree_rl_gym **클립 없음**.
- **제어 주기**: 50 Hz가 표준(우리와 동일), humanoid-gym만 100 Hz.

## 출처
- https://github.com/unitreerobotics/unitree_rl_gym (`deploy/deploy_real/deploy_real.py`, `common/rotation_helper.py`, `common/command_helper.py`, `configs/g1.yaml`), issues #26·#32·#43·#95, PR #98
- https://github.com/unitreerobotics/unitree_sdk2_python (`idl/unitree_{go,hg}/msg/dds_/_IMUState_.py`, `_LowState_.py`)
- https://github.com/BoosterRobotics/booster_gym (`deploy/deploy.py`, `utils/policy.py`, `utils/rotate.py`, `configs/T1.yaml`)
- https://github.com/LeCAR-Lab/ASAP (`sim2real/rl_policy/*.py`, `utils/{state_processor,command_sender,history_handler}.py`, `config/g1_29dof_hist.yaml`)
- https://github.com/roboterax/humanoid-gym (`scripts/sim2sim.py`), arXiv:2404.05695
