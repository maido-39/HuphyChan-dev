#!/usr/bin/env python3
"""RobStride 모터에 **직접** 명령한다. 안전장치도, 우리 통신 코드도 거치지 않는다.

2026-09-09, 사용자 지시: "지금은 모터 ID 중이니까 Safety 나 우리 코드 우회해서,
System_ID Workspace 로 폴더 자체를 새로 만들고, 거기서 작업해."

우회하는 것과 우회하지 않는 것
------------------------------
**우회한다.** 관절 한계·속도 제한·점프 제한(HUPHY ``safety/guards``), 다리 조립과
운동학(``robots/leg``·``robots/biped``), 보정 파일, 그리고 화면에서 로봇까지 가는 우리
통신 경로 전부. 파라미터를 재는 동안 그것들이 끼면 **재려는 물리가 가려진다** — 우리가 어제
잰 80 밀리초 지연도, 7배로 깎이던 이득도 전부 그 경로가 만든 것이었다.

**우회하지 않는다.** 전선에 실리는 프레임 형식(``huphy.motors.robstride.codec.mit``)과
모델별 부호화 범위(``tables.MIT_ENCODING``). 이건 안전장치가 아니라 **모터가 알아듣는
언어**다. 손으로 다시 유도하면 조용히 틀리고, 그 결과는 HUPHY 주석이 적어 둔 그대로다 —
"kp 자리에 위치가 들어가면 모터가 전력으로 튐". 게다가 게인 범위는 모델마다 다르다:
RS03·RS04 는 kp 0~5000 / kd 0~100 인데 RS00·RS02 는 0~500 / 0~5 라, 표를 잘못 쓰면
같은 숫자가 10배로 들어간다.

즉 **판단하는 층은 전부 걷어내고, 번역하는 층만 남긴다.**

여전히 남는 것 — 실험 자신의 중단 조건
--------------------------------------
이건 "안전장치"라기보다 **측정 도구의 일부**다. 순수 토크에는 위치 되먹임이 없어서 모터가
자기 위치를 신경쓰지 않고, 이 벤치는 ``enforce_limits: false`` 라 로봇 쪽에도 위치를 막을
것이 없다. 표류가 시작되면 알아차릴 방법이 **이것뿐**이고, 표류한 자료는 애초에 쓸 수도 없다.

    from rs_direct import Motor
    with Motor(channel="can0", motor_id=4, model="RS04") as m:
        st = m.read()                      # 힘을 전혀 안 쓰고 상태만
        m.enable()
        m.torque(0.3)                       # 순수 토크 (kp=kd=0)
        m.hold(st.position_deg, kp=8, kd=0.6)
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass

HUPHY_SRC = "/home/syaro/Human-Pygmalion/HUPHY/src"
if HUPHY_SRC not in sys.path:
  sys.path.insert(0, HUPHY_SRC)

import can  # noqa: E402
from huphy.motors.robstride import tables  # noqa: E402
from huphy.motors.robstride.codec import mit  # noqa: E402


@dataclass
class State:
  """모터가 한 응답에 실어 보낸 것 전부. 각도는 모터 자신의 raw 공간이다."""

  motor_id: int
  position_deg: float
  velocity_deg_s: float
  torque_nm: float
  temp_c: float
  stamp: float
  mode: int
  """0 Reset / 1 Cali / **2 Motor**. 토크가 정말 켜졌는지는 이 값으로 확인한다 —
  보낸 명령이 아니라 모터가 스스로 보고하는 값이다."""
  fault: bool
  warn: bool


class Motor:
  """모터 한 대. 한 번에 한 대만 다룬다 — 파라미터를 재는 동안 다른 모터가 같은 버스에서
  말하면 응답을 골라내야 하고, 그 과정에서 시각이 흐트러진다."""

  def __init__(self, channel: str = "can0", motor_id: int = 4, model: str = "RS04",
               bitrate: int = 1_000_000, interface: str = "socketcan"):
    self.channel = channel
    self.motor_id = int(motor_id)
    self.enc = tables.MIT_ENCODING[tables.Model(model)]
    self.model = model
    self._bus = can.interface.Bus(channel=channel, interface=interface, bitrate=bitrate)
    self._enabled = False

  # ----------------------------------------------------------------- 열고 닫기
  def __enter__(self):
    return self

  def __exit__(self, *exc):
    self.close()
    return False

  def close(self) -> None:
    """**힘을 먼저 빼고** 채널을 닫는다. 순서가 반대면 정지 명령을 보낼 길이 사라지고,
    모터는 마지막 명령을 계속 붙들고 있는다 — 사람이 전원을 뽑을 때까지."""
    try:
      # 여러 번 보낸다. 한 프레임이 유실돼도 토크는 반드시 꺼져야 한다.
      for _ in range(5):
        self.disable()
        time.sleep(0.01)
    except Exception as exc:            # 여기서 예외가 새면 채널만 닫히고 토크가 남는다
      print(f"[rs_direct] 토크 끄기 실패: {exc} — 전원을 확인하세요", flush=True)
    finally:
      self._bus.shutdown()

  # ----------------------------------------------------------------- 보내기
  def _send_frame(self, data: bytes, tries: int = 40) -> bool:
    """보낸다. 송신 큐가 차 있으면 비기를 기다렸다가 다시 보낸다.

    이 어댑터는 시리얼 방식(CANable/slcan)이고 커널 송신 큐가 10프레임뿐이라, 조금만 빨리
    밀어 넣어도 "No buffer space available" 이 난다. 그 자체는 흔한 일이지만 **한 곳에서만은
    절대 예외가 되면 안 된다** - 토크를 끄는 명령이다. 2026-09-09 실제로 그 예외가
    `close()` 안에서 나서 토크가 켜진 채 끝날 뻔했다(다행히 모터는 꺼져 있었다).
    """
    for _ in range(tries):
      try:
        self._bus.send(can.Message(arbitration_id=self.motor_id, is_extended_id=False,
                                   data=data))
        return True
      except can.CanOperationError:
        time.sleep(0.002)
    return False

  # ----------------------------------------------------------------- 제어 명령
  def _cmd(self, command: int, f_cmd: int = tables.F_CMD_DEFAULT) -> None:
    self._send_frame(bytes([0xFF] * 6 + [f_cmd & 0xFF, command & 0xFF]))

  def enable(self) -> None:
    self._cmd(tables.CMD_ENABLE)
    self._enabled = True

  def disable(self) -> None:
    self._cmd(tables.CMD_STOP)
    self._enabled = False

  def clear_fault(self) -> None:
    self._cmd(tables.CMD_FAULT)

  # ----------------------------------------------------------------- MIT 명령
  def send(self, position_deg: float = 0.0, velocity_deg_s: float = 0.0,
           kp: float = 0.0, kd: float = 0.0, torque_nm: float = 0.0) -> None:
    """모터 펌웨어가 계산하는 식은 이것이다:

        tau = kp*(position_deg - 현재각) + kd*(velocity_deg_s - 현재속도) + torque_nm

    따라서 kp=kd=0 이면 position_deg 가 무엇이든 무시되고 torque_nm 만 남는다.
    """
    self._send_frame(mit.pack_command(
      position_deg=position_deg, velocity_deg_s=velocity_deg_s,
      kp=kp, kd=kd, torque_nm=torque_nm, enc=self.enc))

  def torque(self, tau_nm: float) -> None:
    """순수 토크. 위치 되먹임 없음 — 모터는 시킨 토크만 낸다."""
    self.send(torque_nm=tau_nm)

  def hold(self, position_deg: float, kp: float = 8.0, kd: float = 0.6) -> None:
    """위치 유지. 실험을 **끝낸 뒤** 내려오는 데만 쓴다 — 실험 중에 켜면 내부 PD 가
    우리가 재려는 물리를 가린다."""
    self.send(position_deg=position_deg, kp=kp, kd=kd)

  # ----------------------------------------------------------------- 응답
  def recv(self, timeout_s: float = 0.005) -> State | None:
    """도착한 응답 하나를 읽는다. 우리 모터 것이 아니면 계속 기다린다."""
    deadline = time.monotonic() + timeout_s
    while True:
      left = deadline - time.monotonic()
      if left <= 0:
        return None
      msg = self._bus.recv(timeout=left)
      if msg is None:
        return None
      try:
        mid, pos, vel, tau, temp = mit.decode_state(bytes(msg.data), enc=self.enc)
      except (ValueError, KeyError):
        continue
      if mid != self.motor_id:
        continue
      fl = mit.decode_flags(bytes(msg.data))
      return State(motor_id=mid, position_deg=pos, velocity_deg_s=vel, torque_nm=tau,
                   temp_c=temp, stamp=time.monotonic(),
                   mode=fl.mode, fault=bool(fl.fault), warn=bool(fl.warning))

  def read(self, tries: int = 20) -> State | None:
    """힘을 전혀 쓰지 않고 상태만 얻는다.

    MIT 모드에는 읽기 전용 명령이 없다 — 모터는 **명령을 받아야** 답한다. 그래서 이득도
    토크도 0인 명령을 보내고 그 응답을 받는다. 아무 일도 일어나지 않는다.
    """
    for _ in range(tries):
      self.send()
      st = self.recv(timeout_s=0.01)
      if st is not None:
        return st
    return None
