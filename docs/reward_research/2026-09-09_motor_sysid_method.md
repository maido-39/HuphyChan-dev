# 모터 파라미터를 실측으로 알아내는 방법 — 사전 조사 (2026-09-09)

> 사용자 지시: "모터 파라미터 취득은 **믿을 수 있는 사전연구를 찾고, 그 방법을 따른다.**
> 시간은 문제없으니 충분한 시간을 들여 진행하라."
> 준 참고자료 3개: `github.com/robomotic/mujoco-motors`, "mujoco toolbox",
> `share.note.sx/nthdceuz` (암호화 노트).

## 조사 결과 요약

세 자료 중 **쓸 수 있는 방법은 세 번째 하나**입니다. 나머지 둘의 위치도 적어 둡니다.

| 자료 | 무엇인가 | 우리에게 쓸모 |
|---|---|---|
| `robomotic/mujoco-motors` | 모터 **제원 데이터베이스**(JSON). 저항·인덕턴스·토크상수·기어비·반사관성·정지/동마찰·열저항 등을 벤더별로 모아 둠 | **식별 절차 없음.** 실험도 피팅도 검증도 안 다룸. 초기값 출처로만 쓸 수 있음 |
| "mujoco toolbox" | 세 번째 자료가 가리키는 **MuJoCo 내장 `mujoco.sysid`** 를 말하는 것으로 보임 | **핵심 도구.** 우리 mujoco 3.10.0 에 이미 들어 있음(§3) |
| `share.note.sx/nthdceuz` | RobStride **RS02 QDD 모터**에 그 툴박스를 실제로 적용한 벤치 기록 | **이것이 따라야 할 방법.** 우리 모터와 같은 계열 |

세 번째는 일반적인 내려받기로는 403 이 납니다. 브라우저에서만 복호화되는 노트라서,
브라우저를 띄워 읽었습니다.

## 1. 따라야 할 방법 (원문 요지)

원문은 MuJoCo 에 최근 추가된 시스템 식별 툴박스(작성자가 `@kevin_zakka` 커밋으로 지목)를
자신의 **RobStride RS02**(최대 17 Nm, 기어비 7.75:1)에 적용한 기록입니다.

### 1-1. 왜 여러 주파수를 한꺼번에 넣는가 (원문 인용)

> High frequency: the motor reverses direction rapidly. The reflected rotor inertia
> (armature) resists these fast accelerations.
> Low frequency: the motor moves slowly, reversing direction gradually. inertia resistance
> diminishes, while friction becomes dominant.

즉 **빠른 흔들림은 관성을, 느린 흔들림은 마찰을** 드러냅니다. 사인 하나로는 한쪽만 보이므로
여러 주파수를 더해 한 번에 넣습니다.

### 1-2. 넣는 신호 (원문 그대로)

```
torque(t) = amp × (sin(2π·f·t) + 0.6·sin(2π·3.4f·t) + 0.3·sin(2π·7.4f·t))
```

> The frequencies are chosen at irrational ratios so they don't cancel each other out.
> Amplitudes decrease at higher frequencies.

배수를 3.4, 7.4 처럼 어중간하게 잡는 이유는 주기가 겹쳐 서로 지워지지 않게 하려는 것입니다.

진폭·기준주파수 고르기(원문):

> Too low freq or too high amp, and the motor builds up speed, hitting the torque-speed
> curve. Too high freq or too low amp and there's not enough motion for friction to be
> identifiable. The sweet spot for my RS02 was 4-5 Hz base with 2-3 Nm amplitude.

### 1-3. **순수 토크로 보낸다** (가장 중요한 조건, 원문)

> I send pure torque commands (kp=0, kd=0) so the motor applies the excitation signal
> without any internal PD controller masking the physics we're trying to identify.

모터 내부 PD 가 켜져 있으면 우리가 보려는 물리를 그 PD 가 가려 버립니다.

### 1-4. 기록

초당 1000회, 1 Mbps CAN. 매 밀리초마다 토크 지령(8바이트 + 29비트 확장 ID)을 보내고
약 100 마이크로초 뒤 모터가 위치·속도·추정토크·온도를 답합니다. 왕복 약 300 마이크로초.
한 번에 10초 = 10,000 표본.

### 1-5. 맞추기 (회색상자 식별)

최소 모형 — **경첩 하나 + 토크 액추에이터**. 모르는 값 세 개를 지정:

| 이름 | 뜻 |
|---|---|
| `armature` | 기어를 지나 반사된 회전자 관성 |
| `frictionloss` | 쿨롱 마찰. 운동을 거스르는 일정한 토크 |
| `damping` | 점성 마찰. 속도에 비례 |

같은 토크 지령을 시뮬에 다시 넣고, 예측 위치·속도와 실측을 비교해 차이를 줄이도록
반복합니다.

### 1-6. 원문의 결과 (RS02)

| 값 | 처음 | 맞춘 뒤 |
|---|---|---|
| `armature` | 0.0042 | **0.0143** |
| `frictionloss` | 0.1 | **0.163** |
| `damping` | 0 | 거의 0 |

잔차 52.7 → 0.036, 16회 반복. 원문의 해석:

> armature: much higher than the initial value. **Our sim motor was accelerating too fast.**

원문이 스스로 붙인 단서(그대로 옮김):

> It's important to remember these are not absolute physical ground truths: these are just
> values that better satisfy the specific model I was using.

### 1-7. 검증은 **따로 뽑은 시험**으로

식별에 쓰지 않은 별도 자료로 확인합니다. 무작위 위치 명령을 PD(kp=8, kd=0.5)로 추종시키며
초당 1000회로 10초 기록(±π 라디안 사이 무작위 목표). 같은 명령을 MuJoCo 에 넣어
**맞추기 전 / 맞춘 뒤**를 나란히 봅니다.

> before sysid, the sim overshoots the real motor at each step, arriving at its targets too
> quickly. **The low inertia makes the simulated motor too responsive.** After sysid, sim and
> real are nearly indistinguishable.

★ 이 문장이 우리 관찰과 정확히 닮았습니다 — 우리도 "화면 속 모형이 더 튄다"였습니다.
다만 우리 경우는 이득 사슬(7.3배)이 먼저 걸려 있었으므로(§아래), 관성만으로 설명하면
안 됩니다.

## 2. 우리 조건과 다른 점 — 그대로 따라 할 수 없는 것

| 항목 | 원문 | 우리 |
|---|---|---|
| 지령 주기 | 초당 1000회, CAN 직결 | 화면에서 초당 50회, 그물망 경유 |
| 지령 종류 | 순수 토크 (kp=0, kd=0) | 위치 + 이득 (토크 지령 경로가 화면 쪽엔 배선 안 됨) |
| 명령 지연 | CAN 왕복 약 0.3 밀리초 | **80 밀리초 사구간**(2026-09-09 실측) |
| 모터 | RS02 (17 Nm, 기어 7.75:1) | 무릎 RS04 (120 Nm), 엉덩이회전 RS03 (60 Nm) |
| 관절 한계 | — | **로봇 설정이 `enforce_limits: false`** — 보정 전이라 한계값이 전부 비어 있음 |

**결론: 화면(초당 50회)에서 넣으면 안 됩니다.** 기준주파수 4~5 Hz 에 7.4배 성분이면
30~37 Hz 인데, 초당 50회 지령의 이론 한계(25 Hz)를 넘습니다. 게다가 80 밀리초 사구간이
관성과 뒤섞여 구분이 안 됩니다.

**그래서 원문과 같이 로봇 위에서 직접 돌립니다.** HUPHY 가 순수 토크 지령을 이미 지원합니다
(`robots/leg.py`: `torque  q=0  kp=0  kd=0  tau_ff=tau  모터는 시킨 토크만 냄`).

## 3. 도구는 이미 우리 안에 있다

`mujoco 3.10.0` 에 `mujoco.sysid` 가 포함되어 있습니다. 처음엔 불러오기가 실패했는데
빠진 것은 표시용 꾸러미 셋뿐이었습니다(`colorama`, `tabulate`, `plotly` — 계산에는 무관).
설치 후 정상 동작합니다.

우리에게 중요한 기능:

| 이름 | 무엇 |
|---|---|
| `Parameter` / `ParameterDict` | 모르는 값과 그 상·하한 |
| `build_residual_fn` / `optimize` | 실측과 예측의 차이를 줄이도록 반복 |
| `apply_delay` / `SignalTransform.delay` | **지연도 파라미터로 식별 가능** ← 우리 80 밀리초 문제와 직결 |
| `calculate_intervals` | 최적점의 야코비안에서 **신뢰구간** — 값만이 아니라 얼마나 믿을 수 있는지 |
| `default_report` / `save_results` | 결과 저장 |

`calculate_intervals` 가 있다는 것이 중요합니다. 프로젝트 규칙상 값마다 얼마나 믿을 수
있는지를 함께 적어야 하는데, 이 도구가 그 숫자를 직접 줍니다.

## 4. 우리가 할 순서

1. **로봇 위에서 순수 토크 다중사인**을 넣고 초당 1000회로 기록. 원문의 신호식을 그대로 쓰되
   진폭은 아주 작게 시작해 올린다.
2. 같은 토크를 **모터만 있는 최소 MuJoCo 모형**(경첩 하나 + 토크 액추에이터)에 넣고
   `armature` / `frictionloss` / `damping` 을 맞춘다.
3. **식별에 쓰지 않은 별도 자료**(위치 계단 추종)로 검증한다.
4. 맞춘 값을 지금 로봇 모형이 쓰는 값(무릎 armature 0.01633 / damping 0.0095 /
   frictionloss 0.2695)과 대조한다.

## 5. 안전 — 이 실험이 지금까지와 다른 점

**순수 토크는 위치 되먹임이 전혀 없습니다.** 모터는 시킨 토크만 내고 어디 있는지 신경쓰지
않습니다. 여기에 로봇 설정이 `enforce_limits: false`(보정 전이라 한계값 없음)이므로
**로봇 쪽에 위치를 막아 줄 장치가 하나도 없습니다.**

다중사인은 설계상 평균이 0이지만, 마찰의 좌우 비대칭이나 미세한 치우침이 있으면 위치가
서서히 흘러갑니다. 그래서 **막는 일은 전부 실험 스크립트가 직접** 해야 합니다:

* 시작 위치에서 정해진 각도 이상 벗어나면 **즉시 위치 유지로 전환하고 중단**
* 온도가 45도에 닿으면 중단 (끊는 값 50도보다 낮게)
* 한 번에 10초를 넘기지 않음
* 진폭은 아주 작은 값부터 시작해 표류를 확인하며 올림

또 하나: 이 스크립트가 도는 동안에는 **지금 돌고 있는 로봇 프로그램을 멈춰야 합니다**(통신
버스를 한 프로그램만 쓸 수 있음). 멈추면 화면과의 연결이 끊기고 토크가 빠집니다 — 그 자체는
안전한 쪽입니다.

## 출처

* [MuJoCo motor system identification toolbox 적용기 (RobStride RS02)](https://share.note.sx/nthdceuz#tXE+MIsRlKXy6k3WHkvLiJfHEy/VOquGRR9rknifjdM)
  — 이 문서의 §1 은 전부 여기서 왔습니다. 읽은 날짜 2026-09-09.
* [robomotic/mujoco-motors](https://github.com/robomotic/mujoco-motors) — 모터 제원
  데이터베이스. 식별 절차는 없음.
* `mujoco.sysid` — 우리 `mujoco 3.10.0` 설치본에 포함.
* HUPHY `src/huphy/robots/leg.py` (로봇 위) — 순수 토크 지령 지원 근거.
* 우리 실측 배경: [[2026-09-09_sim_vs_real_sine_sweep]]
