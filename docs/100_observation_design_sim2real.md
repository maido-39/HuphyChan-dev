# 100. 관측 설계 — 비대칭 actor-critic과 배포 가능한 obs (2026-08-24)

사용자: "비대칭 Student-Teacher 구조로, IMU에서 못받는거는 Student 에서 빼고 Teacher 에 넣어야겠는데. 선례 연구해서 정리해. observation 을 실제 deploy 할 폴리시에 어떻게 넣는지."

원자료: [[2026-08-24_asymmetric_actor_critic]](코드베이스 9종·논문 13편), [[2026-08-24_deployed_policy_observation]](실기 배포 스택 4종 줄 단위).

## 0. 결론 — 우리는 이미 맞게 가고 있고, 구멍은 4개다
| 항목 | 우리 현재 | 선례 | 판정 |
|---|---|---|---|
| `base_lin_vel` actor에서 제거 | ✅ 2026-07-04 적용 | 하드웨어 튜닝된 휴머노이드 **9개 중 5개가 critic 전용**(unitree G1/H1·humanoid-gym·Booster T1·HumanoidVerse `wolinvel`). Unitree SDK엔 **선속도 필드 자체가 없다** | ✅ 표준. 오히려 공개 mjlab(actor에 velocimeter+노이즈 유지)보다 엄격 |
| 접촉·발높이·air_time critic 전용 | ✅ | humanoid-gym(`stance_mask`,`contact_mask`), mjlab 동일 | ✅ |
| height_scan critic 전용 | ✅(flat이라 아예 제거) | humanoid-gym critic 전용 | ✅ |
| **DR 파라미터(마찰·질량·CoM·push)를 critic에 안 넣음** | ❌ 양쪽 모두 없음 | humanoid-gym `env_frictions·body_mass·rand_push_force/torque`, Booster `base_mass_scaled·pushing_forces/torques` = **critic 전용** | ⬜ **구멍 1** |
| **`projected_gravity`가 IMU를 안 거침** | ❌ 바디 쿼터니언(`projected_gravity_b`) | 실기 3개 스택 **전부** IMU 자세→중력벡터로 변환해서 넣는다 | ⬜ **구멍 2** |
| **관측 히스토리 없음**(단일 프레임) | ❌ | ASAP 전 항목 4프레임, humanoid-gym actor 15프레임/critic 3프레임, RMA 50스텝. 단 unitree·Booster는 히스토리 없음 | ⬜ **구멍 3**(선택) |
| **AB 발목 FK 의존성** | actor가 ankle 각을 봄(크랭크에서 FK 필요) | Booster T1이 **병렬 발목을 실제로 배포**: 정책의 위치 액션을 직렬 엔코더 기반 **계산 토크**로 변환 | ⬜ **구멍 4**(배포 설계) |

## 1. 배포되는 정책이 실제로 읽는 것 (실기 코드 기준)
unitree_rl_gym(G1/H1, DDS 50 Hz) · Booster T1(SDK, 500 Hz 스레드 + 50 Hz 정책) · ASAP(ROS2 rclpy 50 Hz, ONNX) 셋을 줄 단위로 확인한 결과 **관측 조립은 사실상 한 가지 형태로 수렴**한다:

```
obs = [ base_ang_vel(gyro) * scale,      # IMU 각속도, raw (소프트웨어 LPF 없음)
        projected_gravity,               # IMU 자세 → 본체 프레임 중력벡터 3성분
        command(vx, vy, wz),
        (q − q_default) * scale,
        dq * scale,
        previous_action,
        (gait phase sin/cos)  ]          # 클록을 쓰는 스택만
```
- **가속도계는 아무도 안 쓴다.** Unitree IDL에 `accelerometer[3]`가 있지만 세 스택 어디서도 읽지 않는다.
- **자세는 쿼터니언·RPY 원본이 아니라 항상 중력벡터 3성분**으로 넣는다(경로만 다름: `get_gravity_orientation(quat)` / `rotate_vector_inverse_rpy` / `quat_rotate_inverse`).
- **바이어스·드리프트 보정 코드가 없다** — 벤더 온보드 EKF를 그대로 신뢰. Booster는 대신 `|roll|>1.0 or |pitch|>1.0 → 정지` 안전 트립을 둔다.
- **base 선속도**: Unitree엔 필드가 없고, Booster는 그 슬롯에 **조이스틱 명령값**을 넣으며, ASAP은 슬롯을 0으로 둔다.

## 2. 특권 정보를 쓰는 두 갈래
- **(A) 순수 비대칭 PPO** — critic obs = actor obs ∪ 특권항. unitree G1/H1, humanoid-gym, Booster, mjlab. 단순하고 우리가 지금 하는 것.
- **(B) teacher-student / 추정기** — actor는 **sim에서도** 특권값을 못 보고, 지도학습으로 특권 타깃을 회귀하는 추정기 출력을 받는다. walk-these-ways(adaptation module), Lee 2020, RMA, Miki 2022, DreamWaQ(CENet), DWL(GRU denoising).
  - **DreamWaQ**는 정확히 우리 문제를 푼다: `base_lin_vel`을 고유수용 히스토리에서 회귀해 **actor에 넣는다** → 밀기 회복 0.511→1.121 m/s(2.2×), 생존율 20.5→95.2 %.
  - **DWL** 실기: 계단오름 100 vs 20 %, IMU 드리프트 −87 %.
- **이론 주의**: Baisero & Amato(AAMAS'22) — 부분관측에서 **순수 "상태" critic은 정의가 이상하고 편향**될 수 있다(history aliasing). 8개 POMDP·20시드에서 상태 critic이 붕괴. Lambrechts(ICML'25)는 **특권 입력이 history-sufficient면 안전**하다고 정리. ⇒ critic에 히스토리 또는 충분통계를 주는 편이 이론적으로 안전하다.
- **반례**: Radosavovic — 특권도 distillation도 없이 causal transformer + 히스토리로 in-context 적응. 지배적이지만 유일한 길은 아니다.

## 3. 우리 처방 (다음 세대, [[98_scratch_training_plan]]에 반영)
### 3a. Actor (배포 가능한 것만) — 지금 유지 + 2가지 수정
```
projected_gravity   ← ★IMU 센서에서(`projected_gravity_from_sensor`, 사이트 `imu_in_base`)   [구멍 2]
base_ang_vel        ← imu_ang_vel (gyro), 노이즈 ±0.2                                    유지
joint_pos − default ← AB: hip3+knee+crank2+ankle2 / RP: hip3+knee+ankle2, 노이즈 ±0.01    유지
joint_vel           ← 노이즈 ±1.5                                                        유지
last action, command                                                                     유지
(선택) 위 항목의 4프레임 히스토리                                                          [구멍 3]
✗ base_lin_vel  ✗ height_scan  ✗ foot contact/force                                      유지(제거 상태)
```
### 3b. Critic (특권, 배포 비용 0) — 지금 것 + DR 파라미터 추가
```
actor 전 항목(노이즈 제거) + base_lin_vel + foot_height/air_time/contact/contact_forces   유지
★ 추가: foot_friction, base mass scale, base CoM offset, push force/torque               [구멍 1]
   근거: humanoid-gym `env_frictions·body_mass·rand_push_force/torque`, Booster `base_mass_scaled·pushing_*`
   비용: 0(학습 전용). 지금 DR은 걸어놓고 critic이 못 보는 상태 = 가치함수가 DR을 잡음으로만 인식
관절 토크는 넣지 않는다 — 조사한 어느 코드베이스에도 없음
```
### 3c. 2단계 옵션 (여유 있으면)
`base_lin_vel` 추정기(CENet/DreamWaQ형): actor 히스토리 → `v̂`를 회귀해 actor에 주입. 히스토리(3a 선택항목)가 선행 조건. **먼저 (A)로 완주하고, 실기 밀기 회복이 부족할 때 착수**.

## 4. 배포 시 반드시 지킬 것 (실기 코드에서 확인된 함정)
1. **obs 순서는 로봇 속성이 아니라 체크포인트 계약**이다. 같은 레포 안에서도 Go2와 G1의 순서가 다르다(unitree issue #32). 우리는 ONNX와 함께 **obs 스펙(순서·스케일·default 자세)을 JSON으로 동봉**한다.
2. **관절 순서**는 URDF 선언순(Isaac Gym) vs BFS(Isaac Sim)가 다르다(PR #98 `doc/dof_order.md`). mjlab/MuJoCo 순서를 기준으로 배포측 매핑표를 만든다.
3. **IMU 장착 프레임**: H1은 IMU가 몸통이라 배포 코드가 `transform_imu_data(waist_yaw, …)`로 골반 프레임으로 되돌린다. 우리 site는 `base_link` 기준 `(0.004, 0, 0.241)` — **CAD 실측과 일치하는지 확인**하고, 다르면 같은 보정을 넣는다. (URDF에는 IMU가 아예 없다 → 추가 필요)
4. **AB(2-RSU) 발목**: 정책이 보는 ankle 각은 크랭크 엔코더에서 FK로 풀어야 하고, 정책이 내는 ankle 위치 지령은 IK로 크랭크 지령이 된다. Booster T1은 같은 상황에서 **위치 대신 계산 토크**로 보낸다(`# Use series-parallel conversion for torque to avoid non-linearity`). RP는 이 부담이 없다 — **배포 비용 비교([[93_ankle_ab_rp_comparison_plan]] stage 3)의 핵심 항목**.
5. **지연 보상 코드는 세 스택 모두 없다.** 우리는 학습에서 지연 DR을 넣을 계획이므로(docs/70 §5.3) 그쪽이 오히려 앞선다.
6. **액션 클립**이 스택마다 다르다(Booster 1.0 / ASAP ±100+관절한계 / unitree 없음). 우리 clip 값을 배포 스펙에 명시.
7. 제어 주기 50 Hz는 표준과 일치.
