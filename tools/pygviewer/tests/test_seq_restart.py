"""The sequence gate must drop reordered packets and still survive a sender restart.

Bench, 2026-09-05: reconfiguring TX rebuilt the client with its counter back at 0, the robot
kept rejecting everything below its high-water mark, and an entire measurement run silently
did nothing (accepted=843 / rejected_seq=5823) while every health indicator stayed green.
"""
import os

import pytest

from pygviewer.bridge.remote_target import LatestOnly
from pygviewer.schema import JointTarget

TOKEN = "tok"


def msg(seq, q=0.1):
  return JointTarget(t_ns=seq * 20_000_000, seq=seq, arm_token=TOKEN,
                     joint_names=["L_knee_joint"], q_target=[q], ttl_ms=250, origin="manual")


def fresh():
  return LatestOnly(expected_arm_token=TOKEN)


def test_accepts_increasing_sequence():
  lo = fresh()
  assert all(lo.put(msg(i)) for i in range(1, 6))
  assert lo.stats.accepted == 5


def test_drops_a_reordered_packet_without_re_baselining():
  """One or two stale packets must NOT look like a restart."""
  lo = fresh()
  for i in (1, 2, 3, 4, 5):
    lo.put(msg(i))
  assert not lo.put(msg(3))        # reordered duplicate
  assert not lo.put(msg(4))
  assert lo.put(msg(6))            # the next in-order packet still lands
  assert lo.stats.rejected_seq == 2
  assert lo.stats.seq_restarts == 0


def test_a_reorder_burst_shorter_than_the_run_never_re_baselines():
  lo = fresh()
  for i in range(1, 200):
    lo.put(msg(i))
  for i in range(1, LatestOnly.SEQ_RESTART_RUN):     # one short of the threshold
    assert not lo.put(msg(i))
  assert lo.stats.seq_restarts == 0
  assert lo.put(msg(500))                            # in-order traffic resumes normally
  assert lo.stats.seq_restarts == 0


def test_recovers_when_the_sender_restarts_its_counter():
  """A restarted viewer begins at 0. Without this the robot ignores it forever."""
  lo = fresh()
  for i in range(1, 6000):
    lo.put(msg(i))
  before = lo.stats.accepted
  accepted_after_restart = sum(1 for i in range(1, 200) if lo.put(msg(i, q=0.2)))
  assert lo.stats.seq_restarts == 1
  assert accepted_after_restart > 100, "should be commanding again well inside 200 packets"
  assert lo.stats.accepted > before
  got, _age = lo.get()
  assert got.q_target == [0.2], "the NEW sender's target must be the one in effect"


def test_restart_costs_at_most_one_second_of_commands():
  """SEQ_RESTART_RUN is the whole cost of a restart: 50 packets at 50 Hz."""
  lo = fresh()
  for i in range(1, 1000):
    lo.put(msg(i))
  dropped = 0
  for i in range(1, 100):
    if not lo.put(msg(i)):
      dropped += 1
    else:
      break
  assert dropped == LatestOnly.SEQ_RESTART_RUN - 1


def test_after_re_baselining_the_old_high_numbers_are_gone():
  """Once re-baselined onto the new sender, stale high-numbered packets from the OLD one
  must not be able to take control back."""
  lo = fresh()
  for i in range(1, 1000):
    lo.put(msg(i))
  for i in range(1, 200):
    lo.put(msg(i, q=0.2))
  assert lo.put(msg(5000, q=0.9)), "a genuinely newer packet is still accepted"


def _make_tx(contract=None):
  from pygviewer.tx import TxState
  return TxState(act_names=["L_knee_joint"], contract=contract)


def test_arm_token_can_be_pinned_so_a_viewer_restart_does_not_kill_the_robot(monkeypatch):
  """A fresh random token each start means restarting the viewer silently mutes the robot -
  the receiver keeps checking the old one and drops every command as rejected_arm_token,
  with nothing on screen to say so (bench, twice on 2026-09-05)."""
  monkeypatch.setenv("PYG_ARM_TOKEN", "  pinned-secret  ")
  a = _make_tx()
  assert a.arm_token == "pinned-secret", "surrounding whitespace must not become part of it"
  assert a.arm_token_pinned is True
  # a second process started the same way must land on the SAME token
  assert _make_tx().arm_token == a.arm_token


def test_arm_token_is_random_when_not_pinned(monkeypatch):
  """Unpinned is still the default - a token must never have a guessable built-in value."""
  monkeypatch.delenv("PYG_ARM_TOKEN", raising=False)
  a, b = _make_tx(), _make_tx()
  assert a.arm_token != b.arm_token
  assert len(a.arm_token) >= 16
  assert a.arm_token_pinned is False


def test_blank_pin_falls_back_to_random(monkeypatch):
  """An empty or whitespace-only value is an unset value, not a token of its own - an empty
  shared secret would match a receiver that was never configured."""
  monkeypatch.setenv("PYG_ARM_TOKEN", "   ")
  a = _make_tx()
  assert a.arm_token.strip()
  assert a.arm_token_pinned is False
