# 123. pygviewer → 실물(HUPHY) 송신 설계 — 3안 비교 (2026-09-04, 결정 대기)

사용자 요청(09-04 10:40): "지금은 조인트 각을 텔레메트리로 받아오기만 하는데, HUPHY 구조를 파악해 적절한 형태로
송신도 할 수 있도록 하라. 안 3개, 모호한 부분은 질문."  (수신 경로는 docs/121 §3 스키마 v1 + `bridge/huphy_udp.py` 완료.)

## 0. HUPHY 구조 사실 (`~/external_repos/HUPHY` @133855f, 읽기 전용 조사)
- **제어 루프**: `control/loop.py` `ControlLoop(robot, hz=100, mode, telemetry)`; 매 주기 `Motion = Callable[[t, observation], Action|None]`이
  목표를 내고 루프는 주기·안전만 담당(설계 원칙 "루프는 무엇을 시킬지 모름"). `run()`이 루프, `step()`이 1주기.
- **명령 경로**: `robots/leg.py` `Leg._motor_targets(action)`(발목 IK: 관절각→ankle_a/b) → `build_commands(action)` → 안전 가드
  (`safety/guards.py` `is_finite`·`clamp_jump`(max_delta_deg 50=슬루)·`limits.clamp`(command_margin_deg 3, enforce_limits)) → `cal_to_raw` →
  `bus.send_mit()`(`MitCommand(position_deg, velocity_deg_s, kp, kd, torque_nm)`, 펌웨어 PD τ=kp(q_des−q)+kd(dq_des−dq)+τ_ff). `send/collect/refresh` 분리.
- **단위·프레임**: HUPHY 상위는 **도(deg)·cal 공간**(`cal = sign·raw + offset`, ±180 wrap), 관절명 `hip_pitch, hip_roll, hip_yaw, knee, ankle_a, ankle_b`
  (+ 파생 `ankle_pitch/roll`), limb `left`(can0, id 1–6) / `right`(can1, id 7–12). 캘리브레이션 JSON은 전부 sign=1/offset=0/limits=null(**미측정** → `Motor.is_configured=False`면 제어 진입 차단).
- **게인**: `config/robot_v1.0.yaml` 전 모터 kp 10 / kd 1(튜닝 전 시작값), RS03/RS04 인코딩 범위 0~5000/0~100(133855f).
- **네트워크**: 송신만 있음 — `telemetry/udp.py UdpSink`(JSON 1행/주기, 9870, PlotJuggler용). **인바운드 명령 API 없음**(socket 수신 코드 0건).
- **범위**: 현재 **한 다리(6모터)** 전용(`--limb`), 두 다리 집계 계층 없음(docs/116 §5.2 `WholeBodyABRobot` 제안만). 진입점 `huphy-run/bringup/commission/imu/test`.
- **안전 자산**: `safety/guards.apply()`(NaN 거부→한계 클립→슬루), `Leg.hold()`(마지막 명령 유지), `last_sent`. 타임아웃/데드맨은 없음(추가 필요).

## 1. 세 가지 안

### 안 A — "원격 Motion": HUPHY 안에 `RemoteTargetMotion` + UDP 수신 (최소 변경, 텔레메트리와 대칭)
- **구조**: 뷰어가 `JointTarget`(스키마 v1: sim 관절명·rad·kp/kd 선택·ttl_ms·seq·t_ns·contract_hash)을 **UDP :9872**로 50 Hz 송신(HUPHY UdpSink의 거울).
  HUPHY 측에 `huphy/remote/udp_target.py`(수신 스레드, latest-only) + `RemoteTargetMotion(t, obs) → Action`(sim 관절명→limb/모터명·rad→deg·부호맵 역변환 = `joint_map_huphy.json`의 역) 추가, `huphy-run --motion remote --listen 0.0.0.0:9872`.
  기존 `build_commands` 가드(NaN·한계·슬루) 그대로 통과 + **신규 데드맨**: ttl 초과/seq 정체 시 `hold()` → N초 후 default 자세로 서서히 복귀(옵션).
- **장점**: HUPHY 설계 원칙(Motion 교체)과 정확히 일치, 코드 최소(~200줄), UDP라 제어 루프 비차단, PlotJuggler 경로와 대칭이라 디버깅 쉬움.
- **단점**: 무연결(패킷 손실 시 슬루가 대신 완충), 계약/매핑 검증이 시작 시 1회뿐(런타임 불일치는 contract_hash 비교로 거부), 한 다리 = 프로세스 1개(두 다리는 2 프로세스 or B 필요).

### 안 B — "세션형 원격제어": WebSocket 양방향 세션 + `huphy-remote` 서비스 (상태·핸드셰이크·arm/disarm)
- **구조**: HUPHY 측 별도 서비스 `huphy-remote`(ControlLoop을 감싸는 얇은 데몬)가 WS 서버(:9873). 세션 절차: ① `hello`(contract_hash·매핑표 sha·모터 기종·캘리브 상태 교환, 불일치 거부) ② `arm`(뷰어 UI의 명시적 arm 버튼 + 하트비트 200 ms) ③ `JointTarget` 스트림(50 Hz) ④ `disarm`/하트비트 끊김 → 즉시 hold→default 복귀. 상태(rx/age/가드 클립 횟수/arm)가 응답으로 돌아와 뷰어 배지에 표시.
  **두 다리** 동시: 서비스가 limb 2개(`Leg`×2, can0/can1)를 소유하고 `send/collect` 배리어로 동기(HUPHY가 이미 분리해 둔 이유).
- **장점**: 명시적 안전 상태기계(arm/deadman/거부 사유 가시화), 매핑·계약 불일치를 **연결 시점**에 잡음, 두 다리 집계 계층을 이 서비스가 제공(docs/116 §5.2 실현), 뷰어 UI에 "왜 안 움직이는지"가 보임.
- **단점**: HUPHY에 새 서비스·상태기계(~600줄) — 변경 폭 큼, WS/TCP는 막힘 가능(수신 스레드+latest-only로 루프 비차단 설계 필요).

### 안 C — "정책은 로봇에서": 뷰어는 감독만(cmd·게인·모드), HUPHY가 ONNX 정책 실행
- **구조**: docs/116 어댑터 경로 완성 — HUPHY에 `PolicyMotion`(ONNX+45D obs 빌더+history+action→cal deg, docs/110 계약) 추가. 뷰어는 `PolicySupervise{cmd vx vy wz, gains preset, mode: hold|pose|policy}`만 저속(10 Hz)으로 송신하고 관절값은 텔레메트리로 받아 표시. 슬라이더 목표는 `pose` 모드에서만(관절별 목표 = A와 같은 경로).
- **장점**: 관절 목표가 LAN 지연·지터를 타지 않음(정책 루프가 로봇 로컬 100 Hz) → **sim2real 실험의 정석**; 뷰어는 안전하게 "무엇을 시켰나"만 봄.
- **단점**: HUPHY에 정책 러너·obs 계약 이식(작업 큼, docs/116 §6의 속도 부호 버그·명령 채널·두 다리 집계 선결), 뷰어 슬라이더 실험은 결국 A/B 경로가 필요 → C는 A 또는 B 위에 얹는 **2단계**.

### 비교
| | A UDP+RemoteMotion | B WS 세션+huphy-remote | C 정책 온보드(+A/B) |
|---|---|---|---|
| HUPHY 변경 | 소(파일 2개) | 중~대(서비스) | 대(정책 러너) |
| 안전장치 | 기존 가드 + 데드맨 추가 | arm/하트비트/거부사유 | 로컬 루프(지연 무관) |
| 두 다리 | 프로세스 2개 | 서비스 1개가 집계 | B에 의존 |
| 슬라이더→실물 | ○ | ○ | pose 모드로 |
| 정책→실물 | 뷰어에서 계산해 송신(지연 탐) | 동일 | 로봇 로컬 |
| 권장 | **1단계로 권장**(빠른 벤치 검증) | 실물 상시 실험 단계 | 보행 sim2real 본게임 |

## 2. 공통 사항(어느 안이든)
- **송신 스키마**: `JointTarget` v1(docs/121 §3 "문서만"이던 것을 구현): `{v,type:"JointTarget",t_ns,seq,src:"viewer",frame:"model_v30",contract_hash, joint_names[], q_target[rad], kp[]?, kd[]?, tau_ff[]?, ttl_ms, arm_token}`. 단위 rad·sim 관절명 고정, 변환은 **로봇 측 브리지**(수신과 대칭).
- **뷰어 측 안전**: 송신은 기본 OFF, UI **arm 버튼(2단: 활성화→arm)** + 데드맨(마우스/키 유지 또는 하트비트), ROM·슬루 사전 클램프(계약 safe_clip + `max_delta`), 계약/매핑 UNVERIFIED면 arm 거부(프로토콜 ②③ 통과 전엔 **벤치 단일 모터**만 허용 옵션).
- **테스트**: 더미 수신기(HUPHY 없이 스키마 검증) → 벤치 모터 1개(RS03, 저게인 kp≤5) → 한 다리 → 두 다리 순.

## 3. 사용자 결정 (09-04 1차 답변)
- HUPHY 코드는 **건드리지 않고 별도 스크립트로 동작**(우리 리포 `tools/pygviewer/bridge/`, 로봇 호스트에서 `huphy`를 임포트해 실행; 통합은 나중에 검토; HUPHY 버그는 버그리포트로 작성).
- 안전: UI 2단 arm(활성화 토글+arm 버튼) + 하트비트 데드맨(끊기면 hold→default 복귀) + **키보드 데드맨**(키 누른 동안만 송신) + **모터별 구동 허용 토글**.
- 첫 실험: **벤치 모터 1개(RS03, kp≤5)** 슬라이더 목표→응답 확인. 안 선택은 ELI5 재설명 후 결정(§3b).

## 3b. 세 안을 쉽게 — "로봇에게 명령을 어떻게 전달할 것인가"
공통: 뷰어는 "관절별 목표각(rad)" 편지를 씁니다. 다른 점은 **편지를 어떻게 부치고, 누가 읽어서 모터에 넣느냐**입니다.

**안 A — 엽서(UDP) + 로봇 옆에 앉은 '읽어주는 사람'(외부 스크립트)**
- 비유: 뷰어가 초당 50장 엽서를 우체통에 넣기만 하고(답장 안 기다림), 로봇 옆 스크립트가 최신 엽서 한 장만 읽어 모터에 넣음. 엽서가 몇 장 빠져도 다음 엽서로 이어짐. 엽서가 0.2초 이상 안 오면(데드맨) "제자리 유지→천천히 기본자세".
- 예시 구현: 로봇 호스트에서 `python bridge/huphy_remote_motion.py --listen 0.0.0.0:9872 --limb left --enable hip_pitch --kp 5 --kd 0.5`
  ```python
  # bridge/huphy_remote_motion.py (핵심만)
  latest = LatestOnly()                      # UDP 스레드가 JSON 한 줄씩 받아 최신만 보관
  def motion(t, obs):                        # HUPHY ControlLoop이 100 Hz로 호출하는 함수
      msg = latest.get(max_age_s=0.2)        # 0.2 s 이상 오래되면 None → 데드맨
      if msg is None or not armed(msg):      # arm 토큰/하트비트 없으면
          return hold_then_default()         #   마지막 목표 유지 → 3 s 후 기본자세로 서서히
      return to_cal_deg(msg, joint_map)      # sim 관절명·rad → HUPHY limb/motor·deg (부호·영점 표 역변환), 허용 모터만
  ControlLoop(Leg(...), hz=100).run(motion)  # HUPHY의 기존 안전가드(NaN·한계·슬루)가 그대로 적용됨
  ```
- 뷰어 쪽: `POST /tx/arm`, 50 Hz로 `JointTarget` UDP 송신, 키를 누른 동안만 송신(키보드 데드맨), 모터별 enable 체크박스.
- 좋은 점: 가장 단순(스크립트 1개 ~200줄), 제어 루프가 절대 안 막힘, 벤치 검증 최속. 아쉬운 점: "잘 받았는지"를 뷰어가 직접 모름(텔레메트리로 간접 확인).

**안 B — 전화 통화(WebSocket 세션) + 로봇 쪽 '교환원' 서비스(외부 스크립트)**
- 비유: 먼저 전화를 걸어 "너 누구니? 내 모델 계약 해시는 이거, 매핑표는 이거" 인사를 나누고(불일치면 끊음), "arm"이라고 말한 뒤에만 명령을 보냄. 0.2초마다 "살아있니?" 확인, 전화가 끊기면 즉시 제자리 유지→기본자세. 로봇이 "이 명령은 한계 때문에 잘랐어"라고 답장해 뷰어 화면에 배지로 뜸.
- 예시 구현: `python bridge/huphy_remote_service.py --ws 0.0.0.0:9873 --limbs left,right` (두 다리를 한 프로세스가 send/collect 배리어로 동기)
  ```python
  async def session(ws):
      hello = await ws.recv(); check_contract(hello)      # 계약·매핑 sha 불일치 → 거부
      state = "connected"
      async for msg in ws:                                  # arm / heartbeat / JointTarget / disarm
          if msg.type == "arm": state = "armed"
          elif msg.type == "JointTarget" and state == "armed": latest.put(msg)
          await ws.send(status(rx_age, clipped_count, state))  # 뷰어 배지용 답장
  # motion(t, obs)는 A와 동일, latest+데드맨
  ```
- 좋은 점: "왜 안 움직이는지"가 화면에 보임, 연결 시점에 매핑 오류를 잡음, 두 다리 집계. 아쉬운 점: 코드 2~3배, TCP라 수신 스레드 분리 필수.

**안 C — 로봇이 스스로 판단(정책을 로봇에서 실행), 뷰어는 리모컨**
- 비유: 뷰어는 "앞으로 0.5 m/s로 걸어" 같은 리모컨 신호만 보내고, 관절 목표는 로봇 안의 정책(ONNX)이 100 Hz로 직접 계산. 슬라이더로 관절을 하나씩 움직이는 실험은 "pose 모드"로 전환해서(=A 경로) 함.
- 예시 구현: `python bridge/huphy_policy_runner.py --onnx legonly_v2.onnx --contract policy_contract.json` (obs 45D 빌더 = docs/110 계약, HUPHY IMU·관절값→obs, action→cal deg), 뷰어는 `PolicySupervise{cmd, mode}` 10 Hz.
- 좋은 점: 보행 sim2real의 정석(LAN 지연이 관절 명령에 안 섞임). 아쉬운 점: 작업량 최대(정책 러너·두 다리 집계·docs/116 §6 선결), 벤치 슬라이더 실험엔 결국 A가 필요.

**추천 경로**: A로 벤치 모터 1개 검증(스키마·부호·단위·데드맨) → 한 다리 → 필요 시 B(세션·두 다리) → C(보행).

## 4. 확정 (09-04 11:00, 사용자 2차 답변)
- **안 A 채택.** 용도 = "모터에 같은 입력을 넣었을 때 sim과 실물 응답이 맞는지 관절마다 움직여 보는 것".
- **★정책 출력은 절대 로봇으로 보내지 않는다** — "Policy 출력은 항상 로봇에서만 돈다"(향후 C). 뷰어 송신은 **manual/script 모드의 관절 목표만**; policy_sim/policy_shadow 모드에서는 송신 경로가 코드 수준에서 차단(arm 불가).
- 벤치 환경: 로봇 호스트에 **HUPHY 설치부터 필요**, 호스트는 **원격지일 수 있음** → 배포 절차(HUPHY GitHub 설치·의존성·CAN 설정·스크립트 배치·실행)를 README에 단계별로, 로컬에서는 더미 수신기(huphy 없이)로 스키마·데드맨 검증.
- 안전(§3): 2단 arm + 하트비트 데드맨 + 키보드 데드맨 + 모터별 enable 토글 + 뷰어 측 사전 클램프(safe_clip·슬루·kp/kd 상한 kp≤5 기본).
