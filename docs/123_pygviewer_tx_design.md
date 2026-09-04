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

## 5. 구현 결과 (2026-09-04, 코더)

**범위**: `tools/pygviewer/pygviewer/bridge/`(신규 5파일) + `schema.py`(JointTarget 필드 추가) +
`tools/pygviewer/deploy/README_robot_host.md`. 대시보드/`api.py`/`ui.py`는 다른 코더가 동시 편집
중이라 손대지 않음 — 뷰어 UI에서 이 `tx_client.py`를 실제로 연결하는 배선은 별도 작업.

### 파일
- `pygviewer/schema.py` — `JointTarget`에 `arm_token`(필수, 빈 문자열 거부) · `origin: Literal["manual","script"]`(타입 자체가 `"policy"`를 생성 시점에 거부) · `tau_ff` 추가, `q_target`/`kp`/`kd`/`tau_ff`의 NaN/inf 거부 검증기.
- `bridge/tx_map.py` — sim rad → HUPHY cal-deg 역변환(`huphy_udp.py` 정변환의 정확한 역), `JointTargetMapper`(같은 `joint_map_huphy.json`·contract travel_sign 재사용, AB 크랭크 A/B→ankle_a/b 직접 테이블 매핑), `clamp_gain` 공용 헬퍼. huphy import 없음.
- `bridge/remote_target.py` — `LatestOnly`(seq 역행/중복 무시, arm_token 불일치, contract_hash 불일치 각각 카운트+거부) + `DeadmanFilter`(0.2s 데드맨→hold→3s 선형 슬루 복귀, enable 목록으로 모든 단계 제한). huphy import 없음, 가짜 시계로 결정론적 테스트.
- `bridge/dummy_rx.py` — huphy 없이 동작하는 로컬 왕복 대상: UDP:9872 수신 → 1차 PD 모터 모델(관성·감쇠) → HUPHY UDP 텔레메트리 포맷(:9870)으로 재전송.
- `bridge/huphy_remote_motion.py` — 로봇 측 스크립트. 순수 헬퍼(관절명 변환·enable 파싱·게인 계획)는 huphy 없이 임포트·테스트 가능; `run_real()`만 huphy를 함수 내부에서 지연 임포트. `--dry-run`은 huphy도 CAN도 안 씀(순간추종 가정 텔레메트리 에코).
- `bridge/tx_client.py` — 뷰어 측 송신 라이브러리(50 Hz, arm/disarm, `mode=` 인자로 policy_sim/policy_shadow 차단, safe_clip+슬루+kp/kd 상한 사전클램프, `ttl_ms` 노출·기본 250ms).
- `deploy/README_robot_host.md` — SSH→Python 확인→HUPHY clone→`pip install -e .[imu]`+python-can→CAN 인터페이스→`huphy-commission`(캘리브 null=제어차단은 정상)→스크립트 배치(`rsync`)→`--dry-run`→벤치 1모터 arm/정지 절차.

### 검증 수치
- pytest: 이번 작업으로 **89개 신규 테스트**(`test_schema_tx.py` 12·`test_tx_map.py` 12·`test_tx_client.py` 22·`test_remote_target.py` 17·`test_dummy_rx.py` 5·`test_remote_motion.py` 17·`test_bridge_roundtrip.py` 4) 추가, 기존 스위트 전체 **333 passed, ~30s**(`tools/pygviewer` 전체, mjlab venv).
- 부호·단위 순수 변환 왕복: **1e-9**(`test_tx_map.py`, 양무릎 +30°→L +0.5236/-0.5236 rad→역변환 30.0°/30.0° 확인).
- **★정밀도 정정**: 과제 문구의 "왕복 1e-6"은 순수 변환식 기준(위 1e-9로 이미 충족)이고, **실제 UDP 와이어를 통한 왕복**은 HUPHY 자체 텔레메트리 관례(cal-deg 소수 둘째 자리 반올림, `huphy_udp.py` 모듈독스트링)에 막혀 **~1.75e-4 rad**(0.01°) 이하로는 못 내려감. `test_bridge_roundtrip.py`는 이 한계의 3배 마진(~5.2e-4 rad)으로 검증 — 1e-6을 조용히 낮춰 잡지 않고 이 문서에 그 이유를 남김.
- 데드맨 발동 시각: 가짜 시계 유닛테스트로 경계(0.2s 직전/직후) 정확히 확정(`test_remote_target.py`) + **실제 벽시계**로 재측정(`test_bridge_roundtrip.py::test_deadman_trigger_timing_is_0_2s_plus_minus_0_05s`) — 마지막 송신 후 0.15~0.25s 범위 내 트리거 확인.
- enable 밖 모터: 명령을 아예 안 받고 자기 default를 유지(`test_dummy_rx.py`/`test_bridge_roundtrip.py`).
- `origin="policy"`: `JointTarget` 생성 시점(pydantic `ValidationError`) + `TxClient` 생성 시점(`RuntimeError`) 이중 거부 확인.

### 작업 중 발견·수정한 버그(내 코드, HUPHY 아님)
1. **테스트 하네스 라이브레이스**: dummy_rx는 ~200 pkt/s로 무한 스트리밍하는데, 수신측 "큐가 빌 때까지 드레인"(`while True`) 패턴은 절대 안 비어서 라이브록; "최대 64개 드레인"(유한 루프였지만 캡이 큼)은 살아있는 스트림을 상대로 "64개가 더 도착할 때까지 기다림"이 되어 **호출당 ~300ms** 소모 — 호출부(테스트 자신의 송신 루프) 틱 간격을 100ms ttl_ms보다 크게 벌려 데드맨을 오발동시킴. 캡을 8, 타임아웃을 10ms로 낮춰 해결(`test_dummy_rx.py`, `test_bridge_roundtrip.py`).
2. **`TxClient`에 `ttl_ms` 노출 누락**: 스키마 기본값(100ms)이 표준 데드맨 기본값(200ms)보다 타이트해서, `deadman_s=0.2`로 설정해도 실제로는 `min(0.2, 0.1)=0.1s`에서 발동(로직 자체는 맞음, 사용자 기대와 어긋남). `ttl_ms` 생성자 인자 추가, 기본 250ms.
3. **테스트 어서션 취약점**: LegOnly-AB의 default_q가 0이 아니라 무릎 약 20°(bent-knee 키프레임)라서 "pos > 5°"류 임계값이 커맨드 이전부터 참 — 실제 목표각 대비 비교로 교체.

### HUPHY 인터페이스 갭 (버그가 아니라 "이렇게 생겼음" 기록 — 코드 수정 없음)
- **`Leg.build_commands`는 발목을 pitch/roll(IK)로만 받고, 모터 레벨(a1/a2 = ankle_a/ankle_b)을 직접 받는 경로가 없다.** 우리 sim의 canonical 표현은 크랭크 각(모터와 1:1)이라, `huphy_remote_motion.py`는 크랭크 목표를 `AnkleKinematics.solve_fk`로 pitch/roll로 바꾼 뒤 `build_commands`에 넘기고, 그 안에서 다시 `solve_ik`로 a1/a2를 복원한다 — FK(뉴턴 반복)→IK(닫힌해) 왕복이 매 틱 발생. 실측(벤치)에서 이 왕복의 수치오차가 실사용에 문제되는지는 미확인(로컬에 CAN이 없어 실행 자체를 못 해봄). **제안**: `Leg`에 "모터 레벨 목표(ankle_a_deg, ankle_b_deg)를 가드까지 통과시키는" 저수준 경로가 있으면 원격/재생 브리지처럼 pitch/roll 의미가 필요 없는 호출자에게 더 정확하고 간단함.
- **게인은 `LimbConfig`(생성자 시점에 고정)에서만 읽고, `action` 딕셔너리로는 못 준다.** 메시지별 kp/kd를 실제로 반영하려면 매 틱 `leg.config`를 `dataclasses.replace`로 재구성해야 했음(`bringup.build_leg`가 생성 시점에 쓰는 것과 같은 패턴을 틱 단위로 확장) — 동작은 하지만 `Leg`가 원래 "설정은 시작할 때 한 번 읽고 안 바뀐다"고 명시한 불변식(설정 파일 docstring)을 어기는 사용법이라 조심스럽다. **제안**: `build_commands(action, gains_override=None)`처럼 틱 단위 게인 오버라이드를 1급으로 지원하면 이런 우회가 필요 없어짐.
- **§3의 "0.2s 데드맨 → hold → 3s 후 default로 슬루 복귀" 문구는 두 가지로 읽힌다**: (a) 0.2s간 고정 유지 후 (별도 속도로) 슬루 시작, (b) 0.2s에 데드맨이 걸리고 그 순간부터 3s에 걸쳐 선형 보간. CLI에 타이밍 노브가 `--default-return-s` 하나뿐이라 (b)로 구현(`remote_target.py` 모듈 독스트링에 근거 명시). 사용자가 (a)를 의도했다면 `--hold-s`류 별도 플래그가 필요.
- **로컬 검증 한계**: `huphy_remote_motion.py`의 `run_real()`/`RemoteMotion`(huphy 임포트가 실제로 일어나는 유일한 경로)은 이 개발 머신에 huphy 미설치·CAN 미연결이라 **한 번도 실행되지 않았다** — 순수 헬퍼(관절명 변환·게인 계획·CLI 파싱)와 `--dry-run` 경로만 검증됨. 배포 README §9의 벤치 1모터 단계가 이 파일에 대한 첫 실제 실행이 된다.

### 브리핑
`docs/000.Real-time Brefing.md`에 `add pygviewer-tx`→`done` 기록(수치·용어 동일하게 반영, 손편집 아님).
