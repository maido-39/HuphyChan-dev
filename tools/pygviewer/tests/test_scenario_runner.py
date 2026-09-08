"""시나리오를 단추 하나로 실행하는 물건의 성질.

2026-09-08. 사용자: "시나리오 하나하나 실행을 위한 버튼을 순서대로 눌러도 동작 제대로
안한다... 단계가 너무 많아서 실행 불가능해."

여기서 지키는 것은 "순서대로 돈다"가 아니다. 그건 쉬운 쪽이다. 어려운 쪽은 **자동으로 도는
동안에도 사람이 문 앞에 서 있어야 한다**는 것이고, 안전 검토가 짚은 것도 그것이었다. 사람이
9단계를 손으로 하던 시절에는 '사람이 지금 보고 있다'가 절차 자체에 들어 있었는데, 단추 하나로
바꾸면 그게 사라진다.

그래서 시험의 대부분은 "안 하는 것"에 대한 것이다.
"""

from __future__ import annotations

import time

import pytest

from pygviewer.scenario_runner import (
  OperatorGone,
  ScenarioRunner,
  Step,
  StepFailed,
)


def _wait(runner, *states, timeout=3.0):
  t0 = time.monotonic()
  while time.monotonic() - t0 < timeout:
    st = runner.status()
    if st["state"] in states:
      return st
    time.sleep(0.01)
  raise AssertionError(f"상태가 {states} 가 되지 않았습니다: {runner.status()}")


class Recorder:
  """무엇이 어떤 순서로 불렸는지."""

  def __init__(self):
    self.calls: list[str] = []
    self.held = True   # 사람이 스페이스를 누르고 있는가
    self.recovered = 0

  def step(self, name, sends=False, fail=None):
    def run():
      self.calls.append(name)
      if fail:
        raise StepFailed(fail)
      return f"{name} 완료"
    return Step(key=name, label=name, sends=sends, run=run)

  def runner(self):
    def recover():
      self.recovered += 1
      self.calls.append("되돌리기")
    return ScenarioRunner(heartbeat_fresh=lambda: self.held, recover=recover)


def _confirm(msg="이만큼 움직입니다"):
  return lambda: {"message": msg}


# ------------------------------------------------------------------ 순서와 보고
def test_steps_run_in_order_and_are_reported_one_by_one():
  """화면이 '어디까지 갔는지'를 보여줄 수 있어야 한다. 끝나고 결과만 알려주면, 실패했을 때
  어느 단계에서 막혔는지가 다시 사라진다."""
  r = Recorder()
  run = r.runner()
  a = [r.step("하나"), r.step("둘")]
  run.start("t", a, [], _confirm())
  st = _wait(run, "done")
  assert r.calls == ["하나", "둘"]
  assert [s["state"] for s in st["steps"]] == ["done", "done"]
  assert st["steps"][0]["detail"] == "하나 완료"


def test_a_failed_step_names_itself_and_the_rest_are_not_run():
  r = Recorder()
  run = r.runner()
  a = [r.step("하나"), r.step("둘", fail="장치가 대답하지 않습니다"), r.step("셋")]
  run.start("t", a, [], _confirm())
  st = _wait(run, "failed")
  assert "셋" not in r.calls, "실패한 뒤 계속 진행하면 안 된다"
  states = {s["key"]: s["state"] for s in st["steps"]}
  assert states == {"하나": "done", "둘": "failed", "셋": "skipped"}
  assert "장치가 대답하지 않습니다" in st["message"]


def test_an_unexpected_error_still_names_the_step():
  """뜻밖의 오류가 나도 '어디서' 는 남아야 한다. 그게 이 화면의 존재 이유다."""
  r = Recorder()
  run = r.runner()

  def boom():
    raise ValueError("널 참조")

  run.start("t", [Step("터짐", "무언가 하는 중", False, boom)], [], _confirm())
  st = _wait(run, "failed")
  assert "무언가 하는 중" in st["message"] and "널 참조" in st["message"]


# ------------------------------------------------------------------ 사람이 문 앞에 있는가
def test_the_runner_stops_before_anything_reaches_the_hardware():
  """1마당과 2마당 사이에서 반드시 멈춘다. 실물이 움직이기 전에 사람이 한 번 본다."""
  r = Recorder()
  run = r.runner()
  run.start("t", [r.step("준비")], [r.step("실물이동", sends=True)],
            _confirm("무릎이 27.9도로 25.1도 움직입니다"))
  st = _wait(run, "waiting")
  assert "실물이동" not in r.calls, "확인 전에 실물이 움직이면 안 된다"
  assert st["confirm"]["message"] == "무릎이 27.9도로 25.1도 움직입니다"


def test_it_will_not_proceed_when_the_operator_is_not_holding_the_key():
  """스페이스는 '사람이 지금 보고 있다'는 뜻이다. 실행기가 대신 눌러 줄 수 없다."""
  r = Recorder()
  run = r.runner()
  run.start("t", [r.step("준비")], [r.step("실물이동", sends=True)], _confirm())
  _wait(run, "waiting")
  r.held = False
  with pytest.raises(StepFailed) as e:
    run.proceed()
  assert "스페이스" in str(e.value)
  assert "실물이동" not in r.calls


def test_letting_go_mid_sequence_stops_it_where_it_is():
  r = Recorder()
  run = r.runner()
  b = [r.step("첫이동", sends=True), r.step("둘째이동", sends=True)]

  # 첫 이동 도중에 손을 뗀다
  first = b[0].run
  def release_then_run():
    out = first()
    r.held = False
    return out
  b[0] = Step(b[0].key, b[0].label, True, release_then_run)

  run.start("t", [r.step("준비")], b, _confirm())
  _wait(run, "waiting")
  run.proceed()
  st = _wait(run, "failed")
  assert "둘째이동" not in r.calls, "손을 뗀 뒤에도 다음 단계로 가면 안 된다"
  assert "손을 뗐" in st["message"]


def test_every_failure_puts_it_back_and_in_that_order():
  """무장된 채로 남는 것이 제일 나쁘다. 어디서 실패하든 되돌린다."""
  r = Recorder()
  run = r.runner()
  run.start("t", [r.step("하나"), r.step("둘", fail="안 됨")], [], _confirm())
  _wait(run, "failed")
  assert r.recovered == 1
  assert r.calls[-1] == "되돌리기"


def test_a_failing_recovery_is_reported_not_hidden():
  """되돌리기까지 실패하면 사람이 직접 해야 한다. 그 말을 반드시 해야 한다."""
  def recover():
    raise RuntimeError("통신 끊김")
  run = ScenarioRunner(heartbeat_fresh=lambda: True, recover=recover)
  run.start("t", [Step("x", "x", False, lambda: (_ for _ in ()).throw(StepFailed("실패")))],
            [], _confirm())
  st = _wait(run, "failed")
  assert "직접 무장을 해제" in st["message"]


def test_aborting_stops_it_and_puts_it_back():
  r = Recorder()
  run = r.runner()
  run.start("t", [r.step("준비")], [r.step("실물이동", sends=True)], _confirm())
  _wait(run, "waiting")
  run.abort()
  st = _wait(run, "failed")
  assert "실물이동" not in r.calls
  assert r.recovered == 1
  assert "중단" in st["message"]


def test_two_runs_at_once_are_refused():
  """두 개가 겹치면 서로의 순서를 밟는다."""
  r = Recorder()
  run = r.runner()
  run.start("t", [r.step("준비")], [r.step("이동", sends=True)], _confirm())
  _wait(run, "waiting")
  with pytest.raises(StepFailed) as e:
    run.start("t2", [r.step("다른준비")], [], _confirm())
  assert "이미" in str(e.value)


def test_steps_say_which_ones_touch_the_hardware():
  """화면이 '여기부터 실물이 움직인다'를 표시할 수 있어야 한다."""
  r = Recorder()
  run = r.runner()
  run.start("t", [r.step("준비")], [r.step("이동", sends=True)], _confirm())
  st = _wait(run, "waiting")
  sends = {s["key"]: s["sends"] for s in st["steps"]}
  assert sends == {"준비": False, "이동": True}


def test_the_key_is_only_demanded_when_something_actually_moves():
  """아무것도 안 나가는 실행에까지 열쇠를 요구하면, 지킬 이유 없는 요구가 되고 그런 요구는
  곧 무시된다. 요구는 실물이 움직이는 단계가 남아 있을 때만."""
  r = Recorder()
  r.held = False              # 아무도 스페이스를 누르고 있지 않다
  run = r.runner()
  run.start("t", [r.step("준비")], [r.step("놓기", sends=False)], _confirm())
  _wait(run, "waiting")
  run.proceed()               # 막히면 안 된다
  st = _wait(run, "done")
  assert "놓기" in r.calls
  assert st["state"] == "done"
