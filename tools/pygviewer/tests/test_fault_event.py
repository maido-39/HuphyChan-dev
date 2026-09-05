"""A fault must be recorded when it happens, not once per packet forever.

Bench, 2026-09-05: the robot's telemetry buffer keeps the last value of every field, so an
unchanged fault word arrives with every packet. Recording one violation per packet turned a
single stale reading - from two motors that were never even connected - into 10,516 records
in 25 s and an all-time counter of 11.3 million. A genuine fault would have been one line in
that flood, which is the opposite of what fault reporting is for.
"""
from pygviewer.telemetry import RealState
from pygviewer.violations import ViolationLog
from pygviewer.schema import JointState

NAMES = ["L_knee_joint", "L_hip_yaw_joint"]


def feed(rs, fault_le, n=1):
  for i in range(n):
    rs.ingest_joint_state(JointState(
      t_ns=i * 20_000_000, seq=i, joint_names=NAMES, q=[0.1, 0.2], qd=[0.0, 0.0],
      tau_est=[0.0, 0.0], fault_le=fault_le, fault_be=fault_le,
    ))


def counts(log):
  return sum(v.get("fault", 0) for v in log.counts_by_joint().values())


def make():
  log = ViolationLog()
  rs = RealState(act_names=NAMES, joint_ranges={n: (-3.0, 3.0) for n in NAMES},
                 contract_sha="test", violations=log)
  return rs, log


def test_an_unchanged_fault_is_recorded_once_not_once_per_packet():
  rs, log = make()
  feed(rs, [0x08, None], n=500)
  assert counts(log) == 1, "500 identical packets must not be 500 faults"


def test_a_fault_that_changes_is_recorded_again():
  """A different fault word is different news."""
  rs, log = make()
  feed(rs, [0x08, None], n=50)
  feed(rs, [0x01, None], n=50)
  assert counts(log) == 2


def test_a_fault_that_clears_and_returns_is_recorded_again():
  rs, log = make()
  feed(rs, [0x08, None], n=20)
  feed(rs, [0x00, None], n=20)
  feed(rs, [0x08, None], n=20)
  assert counts(log) == 2, "it came back - that is news again"


def test_no_fault_records_nothing():
  rs, log = make()
  feed(rs, [0x00, 0x00], n=200)
  assert counts(log) == 0


def test_each_joint_is_counted_on_its_own():
  rs, log = make()
  feed(rs, [0x08, 0x02], n=100)
  by = log.counts_by_joint()
  assert by["L_knee_joint"]["fault"] == 1
  assert by["L_hip_yaw_joint"]["fault"] == 1
