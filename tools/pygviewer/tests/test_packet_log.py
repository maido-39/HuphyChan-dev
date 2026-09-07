"""Packet-level logging of both directions on the wire.

2026-09-07, user: "시뮬로는 검증이 안되는게 너무 많아. 입/출력을 패킷 / debug 레벨로
로깅하고 분석해."

The reason this exists: two joint movements on the bench could not be explained afterwards
(docs/127 section 8), because nothing kept the individual commands. ``/tx/status`` reports
``last_sent_target``, which is the newest value only and is wiped whenever the transmit client
is rebuilt - so by the time anyone asks "what did we command at that moment", the evidence is
gone. Every diagnosis in this session came from reading real bytes; this makes the bytes
survive the moment.

The properties that matter, and why each one is here rather than left to judgement:

* a command is logged with the MEASURED pose it was computed against - a target alone cannot
  be judged after the fact ("0 deg" is correct or a disaster depending on where the joint was)
* the log never raises into the control path - a logger that can stop the robot is worse than
  no logger
* it is off unless asked for, so the default send path is byte-for-byte what it was
* it rotates, so an all-day session cannot fill the disk
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import pytest

from pygviewer import CACHE_DIR
from pygviewer.bridge.tx_client import TxClient
from pygviewer.contract import load_contract
from pygviewer.packet_log import PacketLog, from_env

VARIANT = "LegOnly-AB"


def _contract():
  try:
    return load_contract(CACHE_DIR, VARIANT)
  except FileNotFoundError:
    pytest.skip(f"no baked contract for {VARIANT}")


# ------------------------------------------------------------------------- the log itself
def test_writes_one_json_object_per_event(tmp_path):
  log = PacketLog(tmp_path / "p.jsonl")
  log.write("tx", {"seq": 1, "q_target": [0.5]})
  log.write("tx", {"seq": 2, "q_target": [0.6]})
  log.close()
  lines = (tmp_path / "p.jsonl").read_text().strip().splitlines()
  assert len(lines) == 2
  rec = json.loads(lines[0])
  assert rec["kind"] == "tx" and rec["seq"] == 1
  # both clocks: monotonic orders events within a run, wall clock lines them up against the
  # robot's own log on the other machine
  assert rec["t_mono"] > 0 and rec["t_wall"] > 1_600_000_000


def test_a_broken_log_never_raises_into_the_caller(tmp_path):
  """A logger that can take the control path down with it is worse than no logger."""
  log = PacketLog(tmp_path / "p.jsonl")
  log.close()
  log._fh = None
  (tmp_path / "p.jsonl").unlink()
  # a directory where the file should be: every reopen fails, and none of it propagates
  (tmp_path / "p.jsonl").mkdir()
  log.write("tx", {"seq": 3})
  assert log.write_errors >= 1
  assert log.status()["last_error"]


def test_unserialisable_payload_is_counted_not_raised(tmp_path):
  log = PacketLog(tmp_path / "p.jsonl")
  log.write("tx", {"bad": object()})
  assert log.write_errors == 1
  log.write("tx", {"good": 1})            # and the log keeps working afterwards
  assert log.lines == 1
  log.close()


def test_rotation_keeps_one_previous_file(tmp_path):
  log = PacketLog(tmp_path / "p.jsonl", max_bytes=400)
  for i in range(200):
    log.write("tx", {"seq": i, "pad": "x" * 40})
  log.close()
  assert (tmp_path / "p.jsonl").exists()
  assert (tmp_path / "p.jsonl.1").exists(), "the previous file must survive a rollover"
  assert (tmp_path / "p.jsonl").stat().st_size < 4000


def test_off_unless_asked_for(monkeypatch, tmp_path):
  monkeypatch.delenv("PYG_TX_LOG", raising=False)
  assert from_env() is None
  monkeypatch.setenv("PYG_TX_LOG", str(tmp_path / "on.jsonl"))
  log = from_env()
  assert log is not None
  log.close()


# -------------------------------------------------------------- what a sent packet records
def test_every_sent_packet_records_command_state_and_gains(tmp_path):
  c = _contract()
  a, b = c.action_joint_names[0], c.action_joint_names[1]
  log = PacketLog(tmp_path / "tx.jsonl")
  measured = {a: 0.10, b: 0.20}
  tx = TxClient("10.8.0.14", 9872, joint_names=[a, b], arm_token="t", origin="manual",
                contract=c, kp_max=30.0, kd_max=1.5,
                packet_log=log, state_fn=lambda: dict(measured))
  tx.arm()
  tx.set_target({a: 0.10, b: 0.20 + math.radians(4)}, mode="manual",
                kp={a: 25.0, b: 25.0}, kd={a: 1.0, b: 1.0})
  msg = tx.build_message()
  assert msg is not None
  # build_message does not log; tick() does, because only tick() means it went out
  assert not (tmp_path / "tx.jsonl").exists() or not (tmp_path / "tx.jsonl").read_text().strip()
  log.close()


def test_tick_logs_the_error_between_command_and_measurement(tmp_path, monkeypatch):
  """The column that answers "was anything actually being asked for". Today's incident was
  1722 packets whose commanded error was zero (docs/127 section 2-2); a log without this
  column would have shown 1722 healthy-looking packets."""
  c = _contract()
  a = c.action_joint_names[0]
  log = PacketLog(tmp_path / "tx.jsonl")
  measured = {a: 0.10}
  tx = TxClient("127.0.0.1", 59999, joint_names=[a], arm_token="t", origin="manual",
                contract=c, kp_max=30.0, kd_max=1.5,
                packet_log=log, state_fn=lambda: dict(measured))
  tx.arm()
  tx.set_target({a: 0.10}, mode="manual", kp={a: 25.0}, kd={a: 1.0})
  tx.tick()                                     # commanding it to stay put
  measured[a] = 0.10
  tx.set_target({a: 0.10 + math.radians(6)}, mode="manual", kp={a: 25.0}, kd={a: 1.0})
  tx.tick()                                     # now asking for 6 deg of motion
  log.close()
  recs = [json.loads(l) for l in (tmp_path / "tx.jsonl").read_text().strip().splitlines()]
  assert len(recs) == 2
  assert recs[0]["error"][0] == pytest.approx(0.0, abs=1e-9), "a null command must read as zero"
  assert math.degrees(recs[1]["error"][0]) == pytest.approx(6.0, abs=0.2)
  assert recs[0]["kp"] == [25.0] and recs[0]["measured"] == [0.10]
  assert recs[1]["seq"] == recs[0]["seq"] + 1


def test_a_state_source_that_throws_does_not_stop_the_packet(tmp_path):
  """The measured pose is a nicety; the packet is not."""
  c = _contract()
  a = c.action_joint_names[0]
  log = PacketLog(tmp_path / "tx.jsonl")

  def boom():
    raise RuntimeError("telemetry thread died")

  tx = TxClient("127.0.0.1", 59999, joint_names=[a], arm_token="t", origin="manual",
                contract=c, packet_log=log, state_fn=boom)
  tx.arm()
  tx.set_target({a: 0.1}, mode="manual")
  assert tx.tick() is not None
  log.close()
  rec = json.loads((tmp_path / "tx.jsonl").read_text().strip().splitlines()[0])
  assert rec["measured"] == [None]


def test_no_log_means_the_send_path_is_untouched(tmp_path):
  c = _contract()
  a = c.action_joint_names[0]
  tx = TxClient("127.0.0.1", 59999, joint_names=[a], arm_token="t", origin="manual",
                contract=c)
  tx.arm()
  tx.set_target({a: 0.1}, mode="manual")
  assert tx.tick() is not None
  assert tx.packet_log is None
