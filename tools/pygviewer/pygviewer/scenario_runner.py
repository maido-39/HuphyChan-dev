"""시나리오를 단추 하나로 실행한다. 순서와 중단 조건을 이 파일이 전부 가진다.

2026-09-08, 사용자 지적: "지금 내가 시킨 시나리오 하나하나 실행을 위한 버튼을 내가 순서대로
눌러도 동작 제대로 안한다고. ... 지금 단계가 너무 많아서 실행 불가능해."

맞는 지적이었다. 그때까지 ``scenario.py`` 는 지금 상태에 **이름을 붙이는** 물건이었고,
``POST /scenario/apply`` 는 모드 바꾸기와 무장 해제 두 가지만 했다. 실제로 필요한 순서 -
정책 불러오기, 전송 설정, 좌표 맞춤, 실물을 시작 자세로 옮기기, 몸통 고정과 해제, 무장 -
는 ``scripts/run_policy_drive.py`` 라는 명령줄 스크립트 안에만 있었고, 화면에는 그 순서가
적혀 있지도 않았다. 그러니 화면의 단추를 순서대로 눌러도 될 리가 없었다.

이 파일이 그 순서를 가진다. 화면은 누르고 지켜보기만 한다.

두 마당으로 나뉘는 이유
-----------------------
사람이 스페이스를 누르고 있는 동안에만 패킷이 나간다(``tx.TxState.on_control_tick``).
그 장치는 **사람이 지금 보고 있다**는 것을 확인하려고 있는 것이므로, 실행기가 대신 눌러
주면 안 된다. 그래서 단계를 성질로 갈랐다:

* **1마당 - 실물로 아무것도 안 나가는 단계.** 전부 자동으로 한다.
* **멈춤 - 실물이 어디로 얼마나 움직일지 숫자로 보여주고 사람의 확인을 받는다.**
* **2마당 - 실물이 움직이는 단계.** 스페이스가 눌린 상태에서만 한 걸음씩 나아가고,
  손을 떼면 그 자리에서 멈춘다.

안전 검토에서 나온, 양보하지 않는 것들 (각각 시험이 있다)
---------------------------------------------------------
1. **2마당의 어느 단계도 스페이스가 안 눌린 상태에서는 진행하지 않는다.** 이 실행기는
   심장박동을 스스로 만들지 않는다. 오래된 것을 보면 그 자리에서 멈춘다.
2. **``allow_jump`` 를 실행기가 켜지 않는다.** 그것은 "이만큼 움직여도 좋다"는 사람의
   판단이고, 재시도를 빨리 끝내려고 켜는 순간 관문이 있으나 마나가 된다.
3. **실물이 갈 자리를 먼저 보여주고 확인을 받는다.** 사람이 고르지 않은 목적지로 실물을
   움직이는 단계이므로, 숫자(지금 각도, 갈 각도, 이동량)를 보여준 뒤에만 간다.
4. **어디서 실패하든 되돌린다.** 무장을 풀고 몸통을 다시 붙잡는다. 그 순서로.
5. **무장 재시도에는 시계 기준 상한이 있다.** 정책 목표는 걸음 주기를 따라 오르내리므로
   기다리면 관문이 열리지만, 안 열리는 경우가 있고 그동안 모터는 힘이 들어간 채 서 있다.
6. **높은 수준의 동작만 쓴다.** 전송 객체를 직접 만들지 않는다. 그래야 ``configure`` 의
   거부(정책 허용에는 걸음당 상한이 반드시 있어야 함)와 매 틱 모드 검사가 그대로 살아 있다.

의존성이 없다(``hw_sync.py`` 와 같은 이유). 실제 동작은 전부 ``actions`` 로 주입받으므로
모형이나 통신 없이 시험할 수 있다.
"""

from __future__ import annotations

import dataclasses
import threading
import time
from typing import Callable

ARM_WAIT_S = 6.0
"""무장이 열리기를 기다리는 시계 기준 상한.

정책 목표는 걸음 주기를 따라 오르내리므로 실물과 가까워지는 순간이 주기마다 돌아온다.
6초면 흔한 걸음 주기(1초 안팎)가 여러 번 지나간다. 이보다 오래 기다리는 것은 '곧 열린다'가
아니라 '안 열린다'이고, 그동안 모터는 힘이 들어간 채 서 있다."""

PARK_TOLERANCE_DEG = 2.0
"""실물이 시작 자세에 도착했다고 볼 오차. 넘으면 실패다 - 여기서 느슨하게 봐주면 어긋난
자리에서 무장 재시도로 넘어가는데, 그게 안전 검토에서 가장 위험하다고 지목된 조합이다."""

PARK_TIMEOUT_S = 8.0


class StepFailed(RuntimeError):
  """단계가 실패했다. 메시지는 사람에게 그대로 보여진다."""


class OperatorGone(StepFailed):
  """스페이스에서 손을 뗐다. 실패가 아니라 멈춤에 가깝지만, 되돌리기는 똑같이 한다."""


@dataclasses.dataclass
class Step:
  key: str
  label: str
  """화면에 그대로 나가는 말. 전문용어를 쓰지 않는다."""
  sends: bool
  """참이면 이 단계에서 실물이 움직인다 - 스페이스가 눌려 있어야 하고, 화면에 표시가 다르다."""
  run: Callable[[], str | None]
  """성공하면 사람에게 보여줄 한 줄(또는 None), 실패하면 :class:`StepFailed`."""


@dataclasses.dataclass
class StepResult:
  key: str
  label: str
  sends: bool
  state: str  # "pending" | "running" | "done" | "failed" | "skipped"
  detail: str | None = None


class ScenarioRunner:
  """한 번에 하나만 돈다. 상태는 :meth:`status` 하나로 전부 읽힌다."""

  def __init__(self, heartbeat_fresh: Callable[[], bool], recover: Callable[[], None],
               now: Callable[[], float] = time.monotonic):
    self.heartbeat_fresh = heartbeat_fresh
    """지금 사람이 스페이스를 누르고 있는가. 2마당의 매 단계 앞에서 묻는다."""
    self.recover = recover
    """실패하거나 중단했을 때 되돌리는 동작 - 무장 해제 후 몸통 고정, 그 순서."""
    self._now = now
    self._lock = threading.Lock()
    self._thread: threading.Thread | None = None
    self.reset()

  # ------------------------------------------------------------------ 상태
  def reset(self) -> None:
    with self._lock:
      self.key: str | None = None
      self.state = "idle"  # idle | running | waiting | done | failed | aborted
      self.results: list[StepResult] = []
      self.message: str | None = None
      self.confirm: dict | None = None
      self._abort = False
      self._continue = False
      self._needs_key = False

  def status(self) -> dict:
    with self._lock:
      return {
        "key": self.key,
        "state": self.state,
        "message": self.message,
        "confirm": self.confirm,
        "steps": [dataclasses.asdict(r) for r in self.results],
        "running": self.state in ("running", "waiting"),
      }

  # ------------------------------------------------------------------ 조작
  def start(self, key: str, phase_a: list[Step], phase_b: list[Step],
            confirm_fn: Callable[[], dict]) -> dict:
    """1마당을 돌리고, 확인 화면에서 멈춘다. 2마당은 :meth:`proceed` 가 이어서 돌린다.

    ``confirm_fn`` 은 1마당이 끝난 뒤에 불린다 - 실물이 어디로 얼마나 움직일지를 그때의
    실제 값으로 재야 하기 때문이다.
    """
    with self._lock:
      if self.state in ("running", "waiting"):
        raise StepFailed(f"이미 '{self.key}' 를 실행하는 중입니다 - 먼저 중단하세요")
    self.reset()
    with self._lock:
      self.key = key
      self.state = "running"
      self.results = [StepResult(s.key, s.label, s.sends, "pending")
                      for s in phase_a + phase_b]
      self._needs_key = any(s.sends for s in phase_b)
    self._thread = threading.Thread(
      target=self._run, args=(phase_a, phase_b, confirm_fn), daemon=True,
      name=f"scenario-{key}")
    self._thread.start()
    return self.status()

  def proceed(self) -> dict:
    """사람이 스페이스를 누른 채 '계속' 을 눌렀다."""
    with self._lock:
      if self.state != "waiting":
        raise StepFailed("지금은 기다리는 중이 아닙니다")
    # 열쇠를 요구하는 것은 **실제로 실물이 움직이는 단계가 남아 있을 때만**이다. 아무것도
    # 안 나가는 실행(시뮬만 돌리기 등)에까지 요구하면, 지킬 이유가 없는 요구를 하게 되고
    # 그런 요구는 곧 무시된다.
    with self._lock:
      needs_key = self._needs_key
    if needs_key and not self.heartbeat_fresh():
      raise StepFailed(
        "스페이스를 누른 채로 눌러 주세요 - 여기서부터 실물이 움직이고, 손을 떼면 "
        "그 자리에서 멈춥니다"
      )
    with self._lock:
      self._continue = True
    return self.status()

  def abort(self) -> dict:
    with self._lock:
      self._abort = True
    return self.status()

  # ------------------------------------------------------------------ 내부
  def _mark(self, key: str, state: str, detail: str | None = None) -> None:
    with self._lock:
      for r in self.results:
        if r.key == key:
          r.state = state
          if detail is not None:
            r.detail = detail
          return

  def _aborted(self) -> bool:
    with self._lock:
      return self._abort

  def _run_phase(self, steps: list[Step]) -> None:
    for s in steps:
      if self._aborted():
        raise StepFailed("사람이 중단했습니다")
      # 실물이 움직이는 단계 앞에서 묻는다. 실행기가 심장박동을 만들지 않는다는 규칙이
      # 지켜지는 자리가 바로 여기다. 단계의 성질을 보고 묻지, 마당을 보고 묻지 않는다 -
      # 안 나가는 단계에까지 열쇠를 요구하면 그 요구가 값싸진다.
      if s.sends and not self.heartbeat_fresh():
        raise OperatorGone("스페이스에서 손을 뗐습니다 - 그 자리에서 멈췄습니다")
      self._mark(s.key, "running")
      try:
        detail = s.run()
      except StepFailed:
        raise
      except Exception as exc:  # 어떤 오류든 그 단계 이름과 함께 보여야 한다
        raise StepFailed(f"{s.label}: {exc}") from exc
      self._mark(s.key, "done", detail)

  def _run(self, phase_a: list[Step], phase_b: list[Step],
           confirm_fn: Callable[[], dict]) -> None:
    try:
      self._run_phase(phase_a)
      if phase_b:
        info = confirm_fn()
        with self._lock:
          self.confirm = info
          self.state = "waiting"
          self.message = info.get("message")
        # 사람을 기다린다. 여기서 기다리는 동안에는 실물로 아무것도 나가지 않는다.
        deadline = self._now() + 300.0
        while True:
          with self._lock:
            go, stop = self._continue, self._abort
          if go:
            break
          if stop:
            raise StepFailed("사람이 중단했습니다")
          if self._now() > deadline:
            raise StepFailed("5분 동안 확인이 없어 그만뒀습니다")
          time.sleep(0.05)
        with self._lock:
          self.state = "running"
          self.confirm = None
        self._run_phase(phase_b)
      with self._lock:
        self.state = "done"
        self.message = "끝났습니다. 스페이스를 누르고 있는 동안 실물이 정책을 따라갑니다."
    except StepFailed as exc:
      self._fail(str(exc))
    except Exception as exc:
      self._fail(f"뜻밖의 오류: {exc}")

  def _fail(self, reason: str) -> None:
    # 먼저 되돌린다. 상태를 적는 것보다 이게 먼저다 - 무장된 채로 남는 것이 제일 나쁘다.
    recover_note = ""
    try:
      self.recover()
    except Exception as exc:
      recover_note = f" (되돌리기도 실패했습니다: {exc} - 직접 무장을 해제하세요)"
    with self._lock:
      self.state = "failed"
      self.message = reason + recover_note
      for r in self.results:
        if r.state == "running":
          r.state = "failed"
          r.detail = reason
        elif r.state == "pending":
          r.state = "skipped"
