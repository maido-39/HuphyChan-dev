"""Recovering a motor that has cut out, without an ssh session.

2026-09-08, user: "모터 Kill 된 경우에 리셋하는 버튼은?" - there was none.

A RobStride motor that latches a fault stops producing torque and keeps refusing commands
until the latch is cleared. The only thing in this system that ever cleared one was the robot
bridge's own STARTUP sequence (`clear_fault()` then `enable()`), so recovering meant opening an
ssh session and restarting a torque-carrying process - for a condition the operator can already
see on the screen in front of them.

Two properties decide whether this is safe to have at all, and both are asserted here:

* **It cannot move anything.** The command carries no target and the robot applies none. It
  makes a motor able to listen again; going somewhere still requires the ordinary arm and
  dead-man path.
* **It is no easier to send than a movement.** Same socket, same destination, same arm token,
  checked the same way. A recovery action that re-enables torque must not be the one message
  with weaker authorisation than the rest.

It is deliberately allowed while DISARMED and is not gated on the sync or the mode: a latched
motor is exactly the situation where arming is impossible, so requiring an arm first would make
this useless precisely when it is needed.
"""

from __future__ import annotations

import re
import socket
from pathlib import Path

import pytest

from pygviewer import CACHE_DIR
from pygviewer.contract import load_contract
from pygviewer.schema import RobotCommand, from_jsonl, to_jsonl
from pygviewer.tx import TxNotAllowed, TxState

VARIANT = "LegOnly-AB"
DASHBOARD_JS = Path(__file__).resolve().parents[1] / "pygviewer" / "static" / "dashboard.js"
REMOTE_MOTION = Path(__file__).resolve().parents[1] / "pygviewer" / "bridge" / "huphy_remote_motion.py"


def _contract():
  try:
    return load_contract(CACHE_DIR, VARIANT)
  except FileNotFoundError:
    pytest.skip(f"no baked contract for {VARIANT}")


# ------------------------------------------------------------------- the message itself
def test_the_command_carries_no_target():
  """The property that makes this safe. A recovery action that could also move a joint would
  be a movement command with a different name."""
  msg = RobotCommand(t_ns=1, op="clear_fault", arm_token="t")
  fields = msg.model_dump()
  for forbidden in ("q_target", "kp", "kd", "tau_ff", "joint_names"):
    assert forbidden not in fields, f"a recovery command must not carry {forbidden}"


def test_it_survives_the_wire():
  msg = RobotCommand(t_ns=1, op="clear_fault", arm_token="t", reason="bench test")
  back = from_jsonl(to_jsonl(msg))
  assert back.type == "RobotCommand" and back.op == "clear_fault" and back.reason == "bench test"


# ------------------------------------------------------------------- the sending side
def _tx_pointing_at(port):
  c = _contract()
  tx = TxState(list(c.action_joint_names), c)
  tx.configure("127.0.0.1", port, [c.action_joint_names[0]])
  return tx


def test_sending_needs_a_configured_destination():
  """Without a config there is no robot address to send to, and inventing one would be the
  same class of mistake as the 127.0.0.1 default that cost a bench session (docs/127)."""
  c = _contract()
  tx = TxState(list(c.action_joint_names), c)
  with pytest.raises(TxNotAllowed) as e:
    tx.send_command("clear_fault")
  assert "tx/config" in str(e.value)


def test_it_sends_while_disarmed_and_actually_reaches_the_wire():
  """Disarmed is the normal state for this: a cut-out motor cannot be armed."""
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  sock.bind(("127.0.0.1", 0))
  sock.settimeout(2.0)
  port = sock.getsockname()[1]
  tx = _tx_pointing_at(port)
  assert tx.armed is False
  out = tx.send_command("clear_fault", reason="unit test")
  assert out["sent"] == "clear_fault"
  data, _ = sock.recvfrom(4096)
  sock.close()
  msg = from_jsonl(data.decode())
  assert msg.type == "RobotCommand"
  assert msg.op == "clear_fault"
  assert msg.reason == "unit test"
  assert msg.arm_token == tx.arm_token, "the same secret a movement command carries"


def test_sending_does_not_disturb_the_movement_stream():
  """It shares the socket, so it must touch none of the stream's state - no sequence number
  consumed, no slew anchor moved, no arming."""
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  sock.bind(("127.0.0.1", 0))
  port = sock.getsockname()[1]
  tx = _tx_pointing_at(port)
  before_seq = tx._client.last_seq
  before_sent = dict(tx._client.last_sent)
  tx.send_command("clear_fault")
  assert tx._client.last_seq == before_seq
  assert dict(tx._client.last_sent) == before_sent
  assert tx.armed is False
  sock.close()


# ------------------------------------------------------------------- the receiving side
def test_the_receiver_checks_the_same_secret():
  src = REMOTE_MOTION.read_text()
  m = re.search(r"def _handle_command\(self, msg\).*?(?=\nclass |\n\nclass )", src, re.S)
  assert m, "_handle_command() not found"
  body = m.group(0)
  assert "msg.arm_token != self.latest.expected_arm_token" in body
  assert "commands_refused" in body


def test_the_receiver_refuses_what_it_cannot_do():
  """A receiver with no way to act on a command must say so rather than accept it - an
  accepted command that did nothing would read as a successful recovery."""
  src = REMOTE_MOTION.read_text()
  assert "cannot act " in src and "self.on_command is None" in src


def test_the_recovery_clears_before_it_enables():
  """Order is load-bearing: enable_torque on a still-latched motor silently does nothing, and
  the result is a motor that reports healthy and produces no torque (docs/123 section 10.1)."""
  src = REMOTE_MOTION.read_text()
  m = re.search(r"def _do_command\(op: str\).*?flush=True\)", src, re.S)
  assert m, "_do_command() not found"
  body = m.group(0)
  assert body.index("clear_fault()") < body.index("biped.enable()")
  assert "No target" in body, "the comment must state that nothing moves"


def test_a_recovery_failure_does_not_kill_the_receive_thread():
  src = REMOTE_MOTION.read_text()
  m = re.search(r"def _handle_command\(self, msg\).*?(?=\nclass |\n\nclass )", src, re.S)
  assert "except Exception" in m.group(0)


# ------------------------------------------------------------------- the panel
def test_the_button_appears_only_when_something_is_faulted():
  """An always-visible "re-enable torque" button is an invitation."""
  js = DASHBOARD_JS.read_text()
  assert 'id="btn-tx-clearfault"' in js
  assert 'recRow.style.display = faulted.length ? "" : "none"' in js


def test_the_button_asks_first_and_says_nothing_will_move():
  js = DASHBOARD_JS.read_text()
  m = re.search(r'el\("btn-tx-clearfault"\)\.onclick.*?\n  \};', js, re.S)
  assert m, "the handler was not found"
  body = m.group(0)
  assert "confirm(" in body
  assert "Nothing moves" in body, "the confirmation must say what it does NOT do"
  assert "Reported by:" in body, "and name what is actually complaining"


def test_faulted_joints_are_read_from_the_fault_line_not_the_link_verdict():
  """A motor can answer every packet and still have cut its own torque - the ok/warn/dead
  verdict is about the link, `fault_reason` is about the motor."""
  js = DASHBOARD_JS.read_text()
  m = re.search(r"function faultedJoints\(st\)\s*\{.*?\n\}", js, re.S)
  assert m
  assert "fault_reason" in m.group(0)
  assert '"dead"' not in m.group(0)


# ------------------------------------------------------------------- recovering mid-drive
# 2026-09-08, second pass. The button above was written for the case an operator is most
# likely to notice: a motor cuts out while nothing much is happening, they press the button,
# they carry on. The dangerous case is the other one - a motor cuts out while a POLICY is
# driving it.
#
# Nothing upstream notices a dead joint. The policy keeps walking and the viewer keeps
# sending, so the command marches on while the joint stays exactly where it died. Every rate
# limit between them is anchored to the PREVIOUS COMMAND (this side's `_prev_sent` slew, the
# robot's `clamp_rate`), which advanced right along with it - so not one of them can see the
# gap that opened. Torque comes back against a command that is a whole gait cycle away:
# measured 2026-09-08, the knee swings 16.1 -> 54.6 deg, so up to 38.5 deg delivered in one
# step against kp.
#
# The two checks that ARE anchored to the real joint both live in the arm path (`TxClient.arm`
# re-seeds the slew ramp from the measured position; `hw_sync.check_arm_ready` refuses a
# target more than 10 deg from it). So clearing a fault has to send the operator back through
# it, which means disarming.
def test_clearing_a_fault_while_armed_disarms():
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  sock.bind(("127.0.0.1", 0))
  port = sock.getsockname()[1]
  tx = _tx_pointing_at(port)
  tx.set_enabled(True)
  tx.arm("manual")
  assert tx.armed is True

  out = tx.send_command("clear_fault")

  assert tx.armed is False, "torque must not come back under a command nothing re-checked"
  assert out["disarmed"] is True, "and the caller has to be told, or the UI still says armed"
  assert "re-arm" in (tx.disarm_reason or ""), \
    f"the reason has to say what to do next, got {tx.disarm_reason!r}"
  sock.close()


def test_clearing_a_fault_while_disarmed_reports_no_disarm():
  """The ordinary case, and the reply must not claim a state change that did not happen."""
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  sock.bind(("127.0.0.1", 0))
  port = sock.getsockname()[1]
  tx = _tx_pointing_at(port)
  out = tx.send_command("clear_fault")
  assert out["disarmed"] is False
  assert tx.armed is False
  sock.close()


def test_the_clear_still_reaches_the_robot_when_it_disarms():
  """Disarming is a local consequence, not a substitute for the action. If the packet stopped
  going out, the button would silently become a disarm button."""
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  sock.bind(("127.0.0.1", 0))
  sock.settimeout(2.0)
  port = sock.getsockname()[1]
  tx = _tx_pointing_at(port)
  tx.set_enabled(True)
  tx.arm("manual")
  tx.send_command("clear_fault", reason="mid-drive")
  data, _ = sock.recvfrom(4096)
  sock.close()
  msg = from_jsonl(data.decode())
  assert msg.op == "clear_fault"
  assert msg.reason == "mid-drive"


def test_re_arming_after_the_clear_goes_through_the_position_check():
  """What makes the disarm worth anything: the next arm re-seeds the slew ramp from where the
  joint actually IS, instead of resuming from the command that ran away without it."""
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  sock.bind(("127.0.0.1", 0))
  port = sock.getsockname()[1]
  c = _contract()
  joint = c.action_joint_names[0]
  measured = {joint: 0.20}
  tx = TxState(list(c.action_joint_names), c, state_fn=lambda: dict(measured))
  tx.configure("127.0.0.1", port, [joint], max_step_deg=4.0)
  tx.set_enabled(True)
  tx.arm("manual")
  # the command runs away from the joint while it is dead
  tx._client._prev_sent[joint] = 0.90
  tx.send_command("clear_fault")
  tx.arm("manual")
  assert abs(tx._client._prev_sent[joint] - 0.20) < 1e-9, \
    "the re-arm must anchor to the measured joint, not the command that left it behind"
  sock.close()


def test_the_button_tells_the_operator_it_disarmed():
  """A silent disarm is its own failure: the panel would read "armed" while the keep-alive
  409s in the background and nothing is being sent."""
  js = DASHBOARD_JS.read_text()
  m = re.search(r'el\("btn-tx-clearfault"\)\.onclick.*?\n  \};', js, re.S)
  assert m
  body = m.group(0)
  assert "r.disarmed" in body, "the reply's disarmed flag has to be read"
  assert "stopTxDeadman()" in body, "the held-key keep-alive has to stop too"
  assert "DISARM" in body.upper(), "and the operator has to be told, in words"
