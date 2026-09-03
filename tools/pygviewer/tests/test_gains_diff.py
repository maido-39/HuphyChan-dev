"""P4/R7: the gains table gains a REAL column once hardware telemetry reports gains, with a
>5% ratio flagged - a sim<->real response overlay is meaningless if the gains do not match."""

from pygviewer import CACHE_DIR
from pygviewer.contract import load_contract
from pygviewer.schema import JointState
from pygviewer.sim_core import SimCore

VARIANT = "LegOnly-AB"


def _core():
  c = SimCore(load_contract(CACHE_DIR, VARIANT), realtime=False)
  c.reset("knees_bent")
  return c


def test_gains_table_has_no_real_columns_before_telemetry():
  c = _core()
  try:
    t = c.gains_table()
    n = "L_knee_joint"
    assert "real_kp" not in t[n]
    assert t[n]["motor"] == c.c.raw["joint_family"][n]
  finally:
    c.stop()


def test_gains_table_flags_a_mismatched_real_kp():
  c = _core()
  try:
    n = "L_knee_joint"
    sim_kp = c.kp[c.act_names.index(n)]
    # 20% high on kp (should be flagged), kd matching (should not be flagged)
    c.real.ingest_joint_state(
      JointState(
        t_ns=0, seq=1, src="dummy", contract_hash=c.c.contract_sha,
        joint_names=[n], q=[0.0], gains={n: {"kp": float(sim_kp) * 1.2, "kd": float(c.kd[c.act_names.index(n)])}},
      )
    )
    t = c.gains_table()
    assert t[n]["real_flag_kp"] is True
    assert t[n]["real_ratio_kp"] > 1.15
    assert t[n].get("real_flag_kd") is not True
  finally:
    c.stop()


def test_gains_table_within_5pct_is_not_flagged():
  c = _core()
  try:
    n = "R_hip_pitch_joint"
    i = c.act_names.index(n)
    c.real.ingest_joint_state(
      JointState(
        t_ns=0, seq=1, src="dummy", contract_hash=c.c.contract_sha,
        joint_names=[n], q=[0.0],
        gains={n: {"kp": float(c.kp[i]) * 1.02, "kd": float(c.kd[i]) * 0.98}},
      )
    )
    t = c.gains_table()
    assert t[n].get("real_flag_kp") is not True
    assert t[n].get("real_flag_kd") is not True
  finally:
    c.stop()
