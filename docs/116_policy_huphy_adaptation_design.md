# 116. Policy → HUPHY 배포 어댑테이션 설계

작성일: 2026-09-02 KST
대상 저장소: [Human-Pygmalion/HUPHY](https://github.com/Human-Pygmalion/HUPHY) (로컬 재클론, `src/huphy` 트리 기준)
성격: **설계 문서.** HUPHY 저장소에는 커밋/PR 하지 않았고, mjlab `env_cfgs.py`도 이 단계에서는 수정하지 않았다.

## 0. 이 문서가 새로 하는 일 / 기존 문서와의 관계

같은 날 앞서 작성된 [[114_huphy_proxyfix_rotation_dr_audit]]과 [[115_motor_flange_huphy_crosscheck]]가
이미 **AB(폐루프 크랭크) 12-action / actor 45D** 배포 계약과 모터 매핑, P0 수정 목록을 확정해 뒀다.
이 문서는 그 결론을 다시 만들지 않고 그대로 인용한다. 이 문서가 새로 더하는 것은 세 가지다.

1. HUPHY 코드를 실제로 줄 단위로 읽어 **OBS/Action 각 항목이 코드 레벨에서 존재하는지**를 표로 검증
   (114는 요약 문장 수준이었다).
2. `rp_policy_contract.json`(RP=직렬 발목 스트림, IsaacSim 교차엔진 검증에 쓰인 변환레이어 사양)과
   AB 스트림을 **나란히** 놓고, 무엇이 legacy이고 무엇이 실배포 대상인지 명시.
3. **projected_gravity 쿼터니언 공식을 mjlab의 `framezaxis` 센서 공식과 대수적으로 직접 대조** —
   "IMU 실측 세션"이 지적했다는 "쿼터니언 기반 projected gravity와 accelerometer 방향 불일치"가
   HUPHY 코드의 버그인지 코드 레벨에서 확인. 결론: **버그 아님** (§4c).

## ELI5

로봇이 걷는 법을 배우는 시뮬레이터(mjlab)와, 실제로 로봇을 움직이는 프로그램(HUPHY)은
서로 다른 팀이 다른 시점에 만든 별개의 소프트웨어다. 시뮬레이터가 "관절 12개짜리 몸 전체를 보고,
목표 속도까지 받아서, 발목 크랭크 모터 4개를 포함한 12개 모터에 명령을 내는" 정책을 학습하고 있는데,
HUPHY 쪽에 지금 붙어 있는 실행 코드는 **다리 하나(모터 6개)만 보고, 목표 속도 없이 균형을 잡거나
제자리 뛰기만 하는** 훨씬 단순한 정책을 위해 짜여 있다. 두 코드를 잇는 다리(어댑터)가 없으면
학습된 정책의 숫자 벡터가 엉뚱한 자리에 꽂힌다 — 값은 그럴듯해 보이는데 로봇이 이상하게 움직이는,
가장 찾기 어려운 종류의 버그다.

---

## 1. HUPHY 인터페이스 요약

### 1.1 지금 실제로 도는 것: 한쪽 다리 6관절 balance/hopping

`HUPHY:src/huphy/control/policy.py`가 정의하는 `JOINT_ORDER`는

```
hip_pitch, hip_roll, hip_yaw, knee, ankle_pitch, ankle_roll   (6개, 한쪽 다리)
```

이고 관찰 벡터는 (`observation_vector()`, 같은 파일 106-143행)

```
base_ang_vel(3) + projected_gravity(3) + joint_pos(6) + joint_vel(6) + actions(6) [+ hop_phase(2)]
   = balance 24D / hopping 26D
```

**속도·자세 명령(command) 채널이 아예 없다.** `BALANCE`/`HOPPING` 두 `PolicySpec`만 있고
(`action_scale` 0.25/0.5), 실행 진입점은 `huphy-run --limb right_leg --policy balance`
(`HUPHY:src/huphy/scripts/run.py`) — **처음부터 한쪽 다리만 골라 실행하는 구조**다.

`control/POLICY.md`(HUPHY 저장소 자체 문서, 5.2/5.4/5.5절)가 스스로 명시한 한계:
모터 부호·영점·IMU 부착 방향이 실물에서 확인된 적 없고, 발목 토크 명령에 한계 가드가 없고,
정책이 멈추거나 NaN을 내도 아무 대비가 없다. **"아직 실물에서 돌리면 안 됨"**이라고 자체 명시.

### 1.2 이미 합의된 실배포 목표: AB 12-action / actor 45D

114/115가 확정한 계약(재인용, 코드 대조는 §2에서):

```
actor 45D = base_ang_vel(3) + projected_gravity(3) + motor_pos_history[q(t-1),q(t)](24)
            + last_raw_action(12) + command(vx,vy,yaw_rate)(3)
output    = q_target = q_default + 0.25 * raw_action   (12개, L/R × hip_p/r/y·knee·crank_A/B)
주기      = policy 50 Hz / CAN·IMU 100 Hz
```

이는 mjlab의 `PYG_STUDENT_TEACHER=1` 옵트인 배선(`mujoco-sim/mjlab/src/mjlab/tasks/velocity/config/pygmalion/env_cfgs.py:154-182`)이
학습하는 정확한 45D 구성이다. **`PYG_STUDENT_TEACHER`가 꺼진 기본 학습 설정과는 구성이 다르다**(§2에서 구분).

### 1.3 데이터 흐름 (control/POLICY.md §0.3, 코드로 재확인)

```
scripts/run.py                       조립만
 ├─ config/loader.py                 robot.yaml
 ├─ scripts/bringup.py  build_leg    다리 조립 (Leg 객체 하나 = 다리 하나 = CAN 채널 하나)
 ├─ control/rsl_rl.py                .pt (torch 체크포인트) → numpy 4층 MLP+ELU 함수
 ├─ control/policy.py                모델함수 → Motion(obs vector 조립·정규화·역스케일)
 └─ control/loop.py     run(Motion)  50/100Hz 주기 실행
      매 주기: robots/leg.py.get_observation() → Motion(t,obs) → build_commands → send → collect
                 ├─ kinematics/ankle.py   발목 2모터 IK/FK/자코비안 토크
                 ├─ safety/guards.py      NaN 거부 → 한계 클립 → 점프(슬루) 클립
                 └─ motors/robstride/     MIT 프레임 인코딩
```

`Robot` 계약(`robots/base.py`)은 **다리 하나 단위**로 짜여 있다. `Leg`(`robots/leg.py`) 하나가
CAN 채널 하나, 관절 6개를 담당한다. 양다리를 하나의 관찰/행동 벡터로 묶는 상위 계층
(`WholeBodyABRobot` 같은 것)이 **코드에 존재하지 않는다** — 114가 P0 항목 1로 이미 지적한 것과 동일.

---

## 2. OBS 대조표

기준: mjlab `PYG_STUDENT_TEACHER=1` (`env_cfgs.py:154-182`)의 45D actor. "HUPHY 제공 가능?" 열은
**지금 코드에 존재하는 것만** PASS로 표기한다 (설계상 가능/향후 구현 예정은 별도 표기).

| # | mjlab 항목 (차원) | 정의 (env_cfgs.py) | HUPHY 제공 가능? | 근거/조치 |
|---|---|---|---|---|
| 1 | `base_ang_vel` (3) | `mdp.builtin_sensor("robot/imu_ang_vel")` = MJCF `<gyro>` (rad/s) | **PASS, 단위 변환 필요** | EBIMU `gyro_dps`가 **도/초**로 나옴(`sensors/base.py` 27행). `control/policy.py:122`가 이미 `math.radians()`로 변환하는 코드를 갖고 있음 — 다만 이는 **6관절 policy용**이라 그대로 재사용 가능(§5) |
| 2 | `projected_gravity` (3) | `envs_mdp.projected_gravity_from_sensor("robot/imu_upvector")` = `-framezaxis(world,site=imu_in_base)` | **PASS, 공식 대수적으로 일치 확인(§4c)** | `sensors/ebimu/protocol.py`의 `to_state()`가 `gravity_from_quat(quat)`을 이미 채워 냄(`ImuState.gravity`). 물리 부착 방향은 **미검증**(§6) |
| 3 | `motor_pos_history` [q(t-1),q(t)] (24) | `mdp.joint_pos_rel`, `history_length=2, flatten_history_dim=True`, 대상은 `PYG_MOTOR_OBS_JOINT_NAMES`(모터 12개, 크랭크 포함) | **부분 PASS — 재구성 필요** | `Leg.get_observation()`(`robots/leg.py:359-383`)은 **매 주기 최신값 한 개**만 낸다. 2-스텝 이력 버퍼가 없음 — 어댑터가 직접 쌓아야 함(§5). 또한 `Leg`는 다리당 6관절뿐이라 **양다리 12개를 합치는 계층이 없음**(§1.3) |
| 4 | `last_raw_action` (12) | `mdp.last_action` — **스케일 곱하기 전** 정책 raw 출력 | **PASS이나 6→12 확장 필요** | `control/policy.py:167-190`의 `policy_motion()`이 이미 `last_action`을 관리하는 클로저를 갖고 있음(6관절용). 12관절로 확장하고, POLICY.md 6.3이 지적한 "밖에서 0으로 리셋 못 함" 결함을 같이 고쳐야 함 |
| 5 | `command` (vx, vy, yaw_rate) (3) | `mdp.generated_commands("twist")` | **FAIL — 채널 자체 없음** | `observation_vector()`(`control/policy.py:106-143`)에 명령 입력 자리가 없다. §1.1에서 본 대로 HUPHY는 애초에 "명령 없는" 단일 행동(균형/제자리뛰기) 정책만 실행하도록 설계됨. **가장 큰 구조적 결손** — 조이스틱/상위 명령 채널을 새로 만들어야 함 |
| — | `base_lin_vel` (3, critic 전용) | `mdp.builtin_sensor("robot/imu_lin_vel")` | 해당 없음 | mjlab이 `del cfg.observations["actor"].terms["base_lin_vel"]`로 **actor에서 이미 제거**(env_cfgs.py:147, "실물 IMU에 대응값 없음"이라 명시). HUPHY 쪽에 대응 불필요 — 설계가 이미 정합 |
| — | `height_scan` 등 지형 스캔 (critic 전용) | rough terrain critic-only | 해당 없음 | actor에 없으므로 배포 대상 아님 |

### 참고: `PYG_STUDENT_TEACHER`가 꺼진 **기본** 학습 설정(같은 45D 총합, 다른 구성)

```
base_ang_vel(3, builtin_sensor) + projected_gravity(3, mdp.projected_gravity=ROOT BODY 진짜 orientation)
  + joint_pos(12, joint_pos_rel) + joint_vel(12, joint_vel_rel) + actions(12) + command(3)
```

이 기본 구성은 `projected_gravity`가 **시뮬레이터의 정답 root orientation**에서 오고
(`velocity_env_cfg.py:88-91`, `mdp.projected_gravity` — IMU 사이트도 노이즈도 아님), `base_ang_vel`도
`joint_vel`도 필터·지연 없는 이상값이다. **이 구성은 실물에 대응이 없다** — projected_gravity를 낼
실측 root orientation 센서가 없고, joint_vel은 HUPHY가 아예 관찰 필드로 안 내보낸다
(`Leg.observation_features`는 `.pos/.vel/.torque/.temp`를 모터별로 내지만, "관절 각속도"는 발목만
자코비안으로 역산하고 나머지 4관절은 애초에 `.vel`이 모터 속도 그대로임 — 이는 관절-모터가 1:1이라 문제
없음). **결론: 실배포는 반드시 `PYG_STUDENT_TEACHER=1` 계열이어야 하고, 기본 45D 구성으로 학습된
체크포인트는 이 어댑터로 배포할 수 없다.** 이 구분이 문서화된 적이 없어 여기 명시한다.

---

## 3. Action 대조표

| # | mjlab 산출 | 정의 | HUPHY 수신부 | 상태/조치 |
|---|---|---|---|---|
| 1 | `joint_pos` 액션 텀 (12) | `JointPositionActionCfg`, `scale=0.25`, `use_default_offset=True` → `q_target = q_default + 0.25·raw_action` (rad) | `Leg.build_commands(action)`가 관절 이름→모터 cal 목표 매핑, `raw_to_cal`/`cal_to_raw` 캘리브레이션 거침 | **좌표계는 맞으나 단위 변환 필요.** mjlab은 **rad**, HUPHY의 `Action`은 **도(cal 공간)**(`robots/base.py:47-48` 주석). `control/policy.py:146-160`의 `joint_targets()`가 이미 `math.degrees()`로 변환하는 코드가 있음(6관절판) — 12관절로 확장 |
| 2 | AB 모드: 크랭크 `crank_A`/`crank_B` 직접 출력 (mjlab 액션 자체가 크랭크 각) | `PYG_ANKLE_LOOP=1`/`ANKLE_MODE=AB` 시 정책의 ankle 두 채널 = 크랭크 힌지 목표각 그대로 | HUPHY의 `Leg.ankle_output`은 **관절(pitch/roll) 명령을 받아 내부에서 `kinematics/ankle.py`로 IK를 풀어 모터 두 개(a1,a2)를 계산**하는 구조 (`_motor_targets()`, `robots/leg.py:419-455`) | **역방향 불일치.** mjlab AB 정책은 크랭크각을 "출력"하는데 HUPHY `Leg`는 관절각을 "입력받아" 크랭크를 "계산"한다. 두 경로가 만나려면 (a) HUPHY의 IK 경로를 **완전히 우회**하고 크랭크 인코더값을 직접 motor 명령으로 보내거나, (b) mjlab 쪽에서 학습한 크랭크각을 관절 pitch/roll로 **역변환(FK)** 한 뒤 HUPHY IK에 넣어야 함 — 114 P0 §3이 이미 "(a) 방식(크랭크 직결)"을 권고 |
| 3 | RP 모드 (legacy, `rp_policy_contract.json`): `ankle_pitch`/`ankle_roll` 관절각 직접 출력, `gains_sw`(Kp 28.5/Kd 1.81)로 **관절 공간 PD** | `env_cfgs.py`의 `ANKLE_MODE=RP`, `AnkleRpTnActuatorCfg` — 정책이 관절 pitch/roll을 내면 액추에이터가 기구 자코비안으로 크랭크 토크로 변환(시뮬 내부) | 이 경로가 사실 HUPHY `Leg`의 기본 설계(§행 2)와 **방향이 맞는다** — `ANKLE_TORQUE` 모드로 두면 `kinematics/ankle.py`의 `mit_torque()`가 같은 일(관절 목표→자코비안→모터 토크)을 함 | **RP는 legacy이지만 코드 구조는 AB보다 HUPHY와 자연스럽게 맞는다.** 다만 배경 지침대로 실기는 AB로 결정됐으므로(`docs/experiments/2026-08-26_ankleAB_vs_RP_comparison.md`), 이 정합성은 참고용. AB로 갈 경우 §행2의 불일치를 반드시 해소해야 함 |
| 4 | 게인/토크 한계 (`rp_policy_contract.json.gains`/`forcerange`, 학습 시뮬레이터의 `BuiltinPositionActuatorCfg`) | hip_yaw ±60 N·m, hip/knee ±120 N·m, ankle ±110 N·m (joint space, RP 기준) | `config/robot_v1.0.yaml`의 `kp/kd`는 **튜닝 전 시작값**(10.0/1.0, 전 관절 동일) — 학습된 Kp 150(hip)/220(knee)/28.5(ankle)와 무관 | HUPHY yaml 주석 자체가 "튜닝 전 시작값"이라 명시. mjlab 학습 게인을 그대로 옮기면 안 됨 — 모터 모델(RS03 tmax 60 N·m, RS04 tmax 120 N·m, `motors/robstride/tables.py:98-99`)과 실측 링크 관성으로 **별도 게인 검증** 필요(114 P0 §7 clamp 순서도 이 문제와 연결) |
| 5 | 50 Hz 정책 스텝, `decimation=4`(`rp_policy_contract.json.decimation`), 물리 200 Hz | 학습 시 400 substep/s에서 4개마다 정책 갱신 | `control/loop.py`는 임의 `hz` 지원(`ControlLoop(hz=...)`), 현재 CAN/IMU 100Hz 예시 | mjlab 정책은 반드시 **정확히 50 Hz**로 불려야 함(`control/policy.py` 관찰 구성 자체가 그 가정 위에 있음은 아니지만, 학습된 정책의 시간 스케일이 50Hz 물리 스텝에 맞춰짐). 114 §2.2가 이미 "policy 50Hz / CAN·IMU 100Hz, 중간 tick zero-order hold"를 권고 — **정확한 50.0 Hz 유지가 게인 미스매치보다 먼저 검증돼야 함**(`control/loop.py`의 `precise_sleep`/`OVERRUN_RATIO` 메커니즘은 이미 존재, 이 목적에 재사용 가능) |
| 6 | 상체 5관절 (`PYG_UPPER_DOF`, 기본 OFF) | 기본적으로 용접 상태, 액션에 없음 | HUPHY `robot_v1.0.yaml`도 다리만 정의(허리·어깨 모터 없음) | **정합.** 12-action 목표와 HUPHY 하드웨어 스펙(다리만) 모두 상체 제외로 일치. 109가 이미 "불변 목표: Policy 출력 정확히 12개"로 확정 |

---

## 4. 좌표계·단위 불일치 리스트

### 4a. 각도 단위 — 이미 알려진 변환점, 위험은 "빠뜨리는 것"

| 값 | mjlab | HUPHY | 변환 위치(기존 코드) |
|---|---|---|---|
| 관절각 (obs 입력) | rad | 도(cal 공간) | `control/policy.py:129-130` `math.radians()` (6관절판 존재, 12관절로 확장 필요) |
| 관절 목표 (action 출력) | rad | 도 | `control/policy.py:158` `math.degrees()` |
| 각속도 | rad/s | 도/초 | `control/policy.py:122` `math.radians()` |

셋 다 **이미 6관절판에 정확히 구현돼 있다** — 새로 설계할 필요 없이 12관절/양다리로 넓히면 됨.
위험은 이 세 변환 중 하나를 어댑터 재작성 중 빠뜨리는 것 (POLICY.md 5.1이 스스로 경고하듯 "틀려도
에러가 안 남").

### 4b. 관절 순서 — 이름이 아니라 순서로만 식별됨

`control/policy.py:59-63` 주석: "모델은 이름을 모른다 — 순서만 본다. 여기가 어긋나면 값은 다 정상인데
로봇이 엉뚱하게 움직이고, 코드로는 안 잡힌다." mjlab의 학습 관절 순서(`rp_policy_contract.json.joint_names`,
L 다리 6개 → R 다리 6개, 다리 내부는 hip_pitch→roll→yaw→knee→ankle_pitch→ankle_roll)가 114의
"12-action → HUPHY 모터 매핑" 표와 **일치**함을 이미 확인했음(114 §2.1) — 이 문서는 그 표를 재검증하지
않고 그대로 신뢰한다. **다만 검증 방법은 사람이 눈으로 표를 대조하는 것뿐**이라, §5의 어댑터는
반드시 로드 시 golden test(114 P0 §5)로 관절 순서를 코드로 재확인해야 한다.

### 4c. IMU 좌표계 — projected_gravity 공식을 대수적으로 대조 (핵심 검증)

**mjlab 쪽 공식** (`envs_mdp.projected_gravity_from_sensor`, `mujoco-sim/mjlab/src/mjlab/envs/mdp/observations.py:109-123`):

```
sensor = <framezaxis objtype="body" objname="world" reftype="site" refname="imu_in_base">
       = 월드 Z축(0,0,1)을 IMU site 로컬 좌표로 표현한 벡터  (= "위" 방향, site 프레임 기준)
projected_gravity = -sensor.data
```

**HUPHY 쪽 공식** (`sensors/base.py:152-165` `gravity_from_quat`):

```
g = R^T (0, 0, -1),  R = 몸체→월드 회전행렬 (쿼터니언에서 유도)
  = ( 2(wy - xz),  -2(yz + wx),  2(x²+y²) - 1 )
```

두 식은 **같은 물리량의 같은 부호 규약**이다: `R^T(0,0,-1) = -R^T(0,0,1)`이고, `R^T(0,0,1)`은 정확히
"월드 Z축을 몸체(site) 좌표로 표현한 벡터" — mjlab의 `sensor.data`와 동일한 정의다. 항등원 검산으로도
확인됨: `w=1,x=y=z=0`(수평)일 때 HUPHY 공식은 `(0,0,-1)`을 내고, mjlab도 수평이면 `sensor.data=(0,0,1)`,
`-sensor.data=(0,0,-1)`로 일치한다.

**→ 두 공식은 수학적으로 동일하다. 쿼터니언→중력방향 변환 자체에는 부호/축서 버그가 없다.**

이 일치가 성립하려면 두 가지 **전제**가 맞아야 하는데, 둘 다 코드가 아니라 물리/설정의 문제이고
**아직 검증되지 않았다**:

1. **쿼터니언 회전 방향 관례** — EBIMU가 주는 쿼터니언이 "몸체→월드"(HUPHY 공식이 가정하는 것)인지
   확인 필요. `to_quaternion()`(`sensors/ebimu/protocol.py:112-118`)은 센서가 보내는 `(z,y,x,w)`를
   `(w,x,y,z)`로 재배열만 할 뿐 관례 자체는 바꾸지 않는다 — 벤더 매뉴얼 대조가 별도로 필요(레포에
   매뉴얼 없음, §6 미결).
2. **물리 부착 축 정렬** — HUPHY의 다리 좌표계 관례(`robots/leg.py` 6-16행: "오른손 좌표계, X 앞,
   Z 위, Y 왼쪽")와 mjlab MJCF의 `imu_in_base` site 로컬 축이 **같은 방향**으로 실제 부착됐는지.
   `control/POLICY.md` §5.3이 스스로 "그렇다고 **들었을 뿐**, 좌표 변환을 안 한다"고 명시 —
   미검증 가정.

### 4c-부록. "쿼터니언 projected gravity vs accelerometer 방향 불일치" 재현성 조사

배경에서 언급된 이전 세션의 발견("quaternion 기반 projected_gravity와 accelerometer 방향 불일치")에
해당하는 기록을 `docs/`, `docs/experiments/`, 실시간 브리핑에서 찾지 못했다(스크래치패드가 세션 간
삭제되는 것은 알려진 제약, [[feedback-scratchpad-is-ephemeral]]). 대신 HUPHY 자체가 이 정확한 대조를
수행하는 코드를 이미 갖고 있어, 그 코드를 근거로 다음을 확인했다.

`sensors/ebimu/commissioning.py`의 `check_mount()`(246-276행)는 **가속도계가 정지 시 재는 중력방향과
자세(쿼터니언)에서 계산한 중력방향을 대조하는데, 부호가 반대로 나올 수 있음을 이미 알고 두 부호를 다
계산해 가까운 쪽을 자동으로 고른다** — 그 이유를 코드 주석이 명시:

> "가속도계 부호 규약을 모르므로 두 부호를 다 계산해 가까운 쪽을 고른다. 벤더마다 다르다 —
> 정지 상태에서 '센서에 작용하는 힘'을 재느냐 '센서가 받는 반작용'을 재느냐임."

즉 **가속도계 raw 값과 `gravity` 필드를 부호 보정 없이 직접 비교하면 언제나 "불일치"로 보일 수 있는
알려진 모호성**이고, 이는 HUPHY 코드의 결함이 아니라 가속도계의 근본적인 부호 관례 문제이며 HUPHY는
이미 이를 자동 검출하도록 설계돼 있다(`accel_sign: +1/-1` 필드로 결과에 명시적으로 남김).

**결론**: 이전 세션이 관찰했다는 "불일치"가 이 부호 모호성을 보정 없이 비교한 결과였을 가능성이 높다.
단, `check_mount()`를 실제로 실물에서 실행한 로그가 없어 **물리적 부착 방향 자체의 오류 가능성은
배제할 수 없다** — 이는 §4c의 전제 2와 동일한 미결 항목으로 수렴한다. **코드 버그는 발견되지
않았다.**

### 4d. 가속도 단위 — 참고 (정책 obs에는 안 씀)

`accel_mps2`는 텔레메트리 전용이고 정책 입력이 아니다 (`sensors/base.py:111-117`). `G_TO_MPS2` 변환이
이미 있음 (`protocol.py:49`). 조치 불필요.

---

## 5. 제안 어댑터 레이어 설계

### 5.1 새로 필요한 모듈 (기존 `control/policy.py`를 대체하지 말고 나란히 추가)

```
huphy/control/biped_policy.py        # 신규 — AB 12관절/45D 전용
huphy/robots/biped.py                # 신규 — 양다리(Leg 두 개)를 하나의 Robot으로 묶음
```

`control/policy.py`(6관절 balance/hopping)는 건드리지 않는다 — POLICY.md가 이미 "임시 상태,
브링업 검증용"으로 문서화했고, 앞으로도 단일 다리 시험에 계속 쓰일 수 있다.

### 5.2 `robots/biped.py` — 양다리 동기화 (114 P0 §1)

```python
class WholeBodyABRobot(Robot):
    """left_leg + right_leg를 하나의 tick barrier로 묶는다.

    Leg.build_commands()는 CAN을 쓰지 않는 순수 계산이므로, 두 다리의
    계산을 먼저 몰아둔 뒤 전송을 한 번에 하면 "왼쪽 계산→왼쪽 전송→
    오른쪽 계산→오른쪽 전송" 순서로 생기는 두 다리 사이의 미세한 시간차를
    없앨 수 있다 (robots/base.py 계약이 이미 build_commands/send/collect
    분리를 위해 이렇게 설계돼 있다고 명시함, 37행).
    """
    def __init__(self, left: Leg, right: Leg):
        self.left, self.right = left, right

    @property
    def joint_names(self):
        # AB 계약 순서: L(hip_p,hip_r,hip_y,knee,crank_A,crank_B)
        #             + R(같은 순서)
        return tuple(f"L_{j}" for j in self.left.joint_names) + \
               tuple(f"R_{j}" for j in self.right.joint_names)

    def build_commands(self, action: Action) -> dict[int, MitCommand]:
        left_action = {k[2:]: v for k, v in action.items() if k.startswith("L_")}
        right_action = {k[2:]: v for k, v in action.items() if k.startswith("R_")}
        cmds = {}
        cmds.update(self.left.build_commands(left_action))
        cmds.update(self.right.build_commands(right_action))
        return cmds   # 전송은 호출부가 한 번에 (can0/can1 동시)

    def get_observation(self) -> Observation:
        out = {f"L_{k}": v for k, v in self.left.get_observation().items()}
        out.update({f"R_{k}": v for k, v in self.right.get_observation().items()})
        return out
    # send/collect/refresh/connect/... 는 두 Leg에 위임 (생략)
```

크랭크(§3 행2) 문제를 풀려면 `Leg._motor_targets()`가 `ankle_pitch`/`ankle_roll`을 받아 IK를 도는
경로를 **AB 전용으로는 우회**해야 한다 — `Leg`에 크랭크 각을 직접 받는 새 메서드
(`set_crank_targets(a1_deg, a2_deg)`)를 추가하거나, `action` dict의 키를 `ankle_a`/`ankle_b`
(모터 이름, `ANKLE_MOTORS`와 동일)로 주면 `_motor_targets()`의 `SINGLE_JOINTS` 취급처럼 그대로
통과시키는 짧은 분기를 추가하는 편이 기존 코드 침습이 가장 적다.

### 5.3 `control/biped_policy.py` — 45D 벡터 조립 + 이력 버퍼

```python
JOINT_ORDER_AB = (  # 114 §2.1 그대로, L 다리 → R 다리
    "L_hip_pitch", "L_hip_roll", "L_hip_yaw", "L_knee", "L_crank_A", "L_crank_B",
    "R_hip_pitch", "R_hip_roll", "R_hip_yaw", "R_knee", "R_crank_A", "R_crank_B",
)  # 12개

class MotorHistory:
    """q(t-1), q(t) 2-스텝 이력. control/policy.py에는 없는 신규 구성요소."""
    def __init__(self, n=12):
        self._buf = [0.0] * (2 * n)   # [q(t-1)_0..11, q(t)_0..11]
        self.n = n

    def push(self, q_now_rad: Sequence[float]) -> None:
        self._buf = list(self._buf[self.n:]) + list(q_now_rad)

    def flat(self) -> list[float]:
        return list(self._buf)   # 이미 [t-1, t] 순서

def observation_vector_ab(observation, imu_state, history: MotorHistory,
                            last_raw_action, command_vxvyyaw) -> np.ndarray:
    out = []
    out.extend(math.radians(v) for v in imu_state.gyro_dps)          # 3
    out.extend(imu_state.gravity)                                    # 3  (이미 단위벡터, 변환 불필요)
    out.extend(history.flat())                                       # 24 (rad, push()가 매 주기 채움)
    out.extend(float(v) for v in last_raw_action)                    # 12 (스케일 곱하기 전)
    out.extend(float(v) for v in command_vxvyyaw)                    # 3
    assert len(out) == 45
    return np.asarray(out, dtype=np.float32)
```

`history.push()`는 매 주기 `get_observation()` 직후, 스케일 변환 **전에** 호출해야 한다 —
mjlab의 `motor_pos_history`가 액션 스케일과 무관한 순수 관절각(`joint_pos_rel`)이기 때문이다.

### 5.4 명령 채널 — 지금 아무것도 없음

`command_vxvyyaw`를 어디서 받을지가 §2 표 행5에서 지적한 "가장 큰 구조적 결손"이다. 최소 구현은
`control/loop.py`의 `Motion` 시그니처(`(t, observation) -> action`)에 명령을 얹을 자리가 없으므로,
`policy_motion()`처럼 클로저로 명령을 들고 있다가 조이스틱/상위 프로세스가 UDP나 공유 변수로
갱신하는 방식이 가장 침습이 적다. **상태 기계(POLICY.md §6)와 명령 채널은 같이 설계해야** command=0
(정지)가 안전한 기본값이 되도록 보장할 수 있다.

### 5.5 필수 안전 게이트 (114 P0 §6/§7과 동일, 이 어댑터에도 그대로 적용)

```
raw_action(모델 출력) → finite 검사(NaN/Inf 거부, 기존 safety/guards.py 재사용)
  → q_target = q_default + 0.25·raw_action
  → ROM 여유폭 클립 (calibration의 limits_deg, 기존 safety/limits.py)
  → 슬루(max_delta_deg) 클립 (기존)
  → 크랭크는 §5.2의 우회 경로 — 발목 토크 가드는 **신규 필요**(POLICY.md 5.4가 아직 없다고 명시)
```

---

## 6. 미결 항목

**즉시 불가능 / 추가 설계·검증 필요 항목 — 총 6건**

| # | 항목 | 종류 | 필요한 것 |
|---|---|---|---|
| 1 | 명령(command) 채널이 HUPHY에 전혀 없음 | 구조적 결손 (§2 표 행5) | §5.4 설계를 실제 구현, 조이스틱/상위 명령 소스 결정 |
| 2 | 양다리를 하나의 tick으로 묶는 계층 없음 | 구조적 결손 (§1.3, §5.2) | `WholeBodyABRobot` 구현 + can0/can1 동시 전송 검증 |
| 3 | AB 크랭크 액션 방향이 HUPHY의 IK 설계와 반대 | 구조적 결손 (§3 행2) | `Leg` 우회 경로 또는 크랭크 전용 메서드 추가, 114 P0 §3과 동일 결론 |
| 4 | 2-스텝 모터 위치 이력 버퍼 없음 | 신규 구현 (§5.3) | `MotorHistory` 구현 + push 타이밍(스케일 전) 검증 |
| 5 | 발목 토크 명령에 한계 가드 없음 | 안전 결손 (POLICY.md 5.4, 114 P0 §6) | `safety/guards.py`를 각도가 아닌 토크/야코비안 출력에도 적용하는 확장 |
| 6 | IMU 물리 부착 방향·쿼터니언 관례가 미검증 | 검증 필요, 코드는 정합 확인됨(§4c) | `check_mount()`를 실물에서 실행해 `accel_sign`/`error`/`tilted_enough` 로그 확보. EBIMU 벤더 매뉴얼로 쿼터니언 관례(몸체→월드 여부) 대조 |

**부가 미결 (114/115가 이미 추적 중, 여기서는 상태만 재확인)**

- 12개 모터 실측 sign/zero/limit (114 §6-2, 115 전체) — 이 문서의 설계는 그 값이 채워졌다고 가정한다.
- `raw action clip` 수치, RS03/RS04 전류·온도·전압 한계 (114 §7).
- `Leg.get_observation()`의 부호 처리가 position에만 적용되고 velocity/torque에는 안 됨 (114 P0 §2) —
  §5.3의 `history.push()`가 이 버그의 영향을 받는다: `sign=-1`인 모터의 위치 이력이 뒤집혀 들어가면
  45D 중 24D가 통째로 오염된다. **114 P0 §2를 이 어댑터보다 먼저 고쳐야 한다.**

---

## 부록: rp_policy_contract.json 요약 (참고용, legacy)

`/home/syaro/pyg_fea/work/rp_policy_contract.json` — RP(직렬 발목) 스트림의 IsaacSim 교차엔진
검증에 쓰인 변환레이어 사양. `joint_names` 12개(크랭크 아님, ankle_pitch/roll), `action_scale` 전
관절 0.25, `decimation=4`(물리 200Hz/정책 50Hz), `gains_sw`(관절공간 PD: hip 150/6, knee 220/6,
ankle 28.5/1.81), `dof_props`(실측 armature/damping/frictionloss, RS03/RS04), T-N 곡선(무부하
200rpm 포함). 실기가 AB로 결정된 이후 이 파일 자체는 배포에 쓰이지 않지만, "변환레이어 사양을
어떻게 기록하는가"의 선례로는 유효 — §5의 새 45D/AB 계약도 114가 이미 만든
`HUPHY_AB_deploy_contract_proxyfix.json`을 정본으로 삼아야 하며, 이 문서가 새 계약 파일을
만들지는 않는다.
