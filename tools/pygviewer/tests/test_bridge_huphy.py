"""P3 item 8: the HUPHY UDP adapter's unit/sign/name conversion, checked against the model
contract's own ``travel_sign`` - the exact synthetic case named in the task brief:
a physical +30 deg knee flexion on BOTH legs must land as sim ``L_knee +0.5236`` /
``R_knee -0.5236`` rad (contract travel_sign +1 / -1), to 1e-6.
"""

import math

import pytest

from pygviewer import CACHE_DIR
from pygviewer.bridge.huphy_udp import (
  DEFAULT_MAP_PATH,
  HuphyBridge,
  JointMap,
  huphy_deg_s_to_sim_rad_s,
  huphy_deg_to_sim_rad,
  huphy_torque_to_sim,
)
from pygviewer.contract import load_contract

VARIANT = "LegOnly-AB"


def _contract():
  try:
    return load_contract(CACHE_DIR, VARIANT)
  except FileNotFoundError:
    pytest.skip(f"no baked contract for {VARIANT}")


def test_joint_map_has_exactly_twelve_motor_rows_and_is_unverified_by_default():
  jmap = JointMap(DEFAULT_MAP_PATH)
  assert len(jmap.motors) == 12
  assert jmap.side_mapping_verified is False
  for limb in ("left", "right"):
    for motor in ("hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_a", "ankle_b"):
      row = jmap.sim_joint(limb, motor)
      assert row["sim_joint"].endswith("_joint")


def test_unknown_limb_motor_pair_is_a_hard_failure_not_a_guess():
  jmap = JointMap(DEFAULT_MAP_PATH)
  with pytest.raises(KeyError):
    jmap.sim_joint("left", "elbow")
  with pytest.raises(KeyError):
    jmap.sim_joint("middle", "knee")


def test_pure_conversion_matches_the_task_briefs_synthetic_case():
  """Both knees physically flexed +30 deg; map default sign=1/offset=0; travel_sign from the
  contract is +1 (L) / -1 (R) (verified directly against the contract in the test below)."""
  l_rad = huphy_deg_to_sim_rad(30.0, sign=1, offset_rad=0.0, travel_sign=1.0)
  r_rad = huphy_deg_to_sim_rad(30.0, sign=1, offset_rad=0.0, travel_sign=-1.0)
  assert l_rad == pytest.approx(0.5235988, abs=1e-6)
  assert r_rad == pytest.approx(-0.5235988, abs=1e-6)


def test_bridge_end_to_end_both_knees_plus_30_deg():
  c = _contract()
  bridge = HuphyBridge(c)
  assert bridge.travel_sign["L_knee_joint"] == pytest.approx(1.0)
  assert bridge.travel_sign["R_knee_joint"] == pytest.approx(-1.0)

  payload = {"t": 0.0, "loop_dt": 10.0, "left/knee/pos": 30.0, "right/knee/pos": 30.0}
  msg = bridge.parse_fast(payload)
  assert msg is not None
  by_name = dict(zip(msg.joint_names, msg.q))
  assert by_name["L_knee_joint"] == pytest.approx(0.5235988, abs=1e-6)
  assert by_name["R_knee_joint"] == pytest.approx(-0.5235988, abs=1e-6)
  # every other joint in this packet is untouched -> null, never a guessed 0.0
  for n, v in by_name.items():
    if n not in ("L_knee_joint", "R_knee_joint"):
      assert v is None


def test_bridge_converts_velocity_and_torque_with_the_same_sign(monkeypatch=None):
  c = _contract()
  bridge = HuphyBridge(c)
  payload = {"t": 0.0, "left/knee/vel": 90.0, "right/knee/vel": 90.0,
             "left/knee/tau": 5.0, "right/knee/tau": 5.0}
  msg = bridge.parse_fast(payload)
  by_name_qd = dict(zip(msg.joint_names, msg.qd))
  by_name_tau = dict(zip(msg.joint_names, msg.tau_est))
  assert by_name_qd["L_knee_joint"] == pytest.approx(math.radians(90.0), abs=1e-6)
  assert by_name_qd["R_knee_joint"] == pytest.approx(-math.radians(90.0), abs=1e-6)
  assert by_name_tau["L_knee_joint"] == pytest.approx(5.0, abs=1e-6)
  assert by_name_tau["R_knee_joint"] == pytest.approx(-5.0, abs=1e-6)


def test_minus_one_sentinel_becomes_null_and_warns_after_three():
  c = _contract()
  bridge = HuphyBridge(c)
  for _ in range(3):
    msg = bridge.parse_fast({"t": 0.0, "left/knee/pos": -1})
  assert dict(zip(msg.joint_names, msg.q))["L_knee_joint"] is None
  assert any("3 packets in a row" in w for w in bridge.warnings)


def test_ankle_derived_is_separate_from_the_canonical_actuated_joints():
  c = _contract()
  bridge = HuphyBridge(c)
  payload = {"t": 0.0, "left/ankle_pitch/pos": 10.0, "left/ankle_roll/pos": -5.0}
  msg = bridge.parse_fast(payload)
  assert msg.ankle_derived is not None
  assert msg.ankle_derived["L"]["pitch"] == pytest.approx(math.radians(10.0), abs=1e-6)
  assert msg.ankle_derived["L"]["roll"] == pytest.approx(math.radians(-5.0), abs=1e-6)
  assert "L_crank_A_joint" in msg.joint_names
  assert all(v is None for v in msg.q)  # the FAST packet only carried ankle-joint fields


def test_diag_and_can_fields_are_ignored_not_hard_failures():
  c = _contract()
  bridge = HuphyBridge(c)
  payload = {"t": 0.0, "left/knee/temp": 42.0, "left/guard/clip_limit": 1.0,
             "left/can/tx_errors": 0.0, "missing": 0.0}
  assert bridge.parse_fast(payload) is None  # nothing recognised as a fast joint field


def test_imu_packet_prefers_gravity_over_reconstructing_a_quaternion():
  c = _contract()
  bridge = HuphyBridge(c)
  payload = {
    "t": 0.0, "imu/base/gx": 1.0, "imu/base/gy": 0.0, "imu/base/gz": 0.0,
    "imu/base/ax": 0.0, "imu/base/ay": 0.0, "imu/base/az": -9.81,
    "imu/base/grav_x": 0.0, "imu/base/grav_y": 0.0, "imu/base/grav_z": -1.0,
    "imu/base/age": 5.0,
  }
  msg = bridge.parse_imu(payload)
  assert msg is not None
  assert msg.quat_wxyz is None
  assert msg.gravity_b == pytest.approx([0.0, 0.0, -1.0])
  assert msg.gyro_rad_s[0] == pytest.approx(math.radians(1.0))
  assert msg.age_s == pytest.approx(0.005)


def test_huphy_rate_and_torque_helpers_apply_travel_sign_only():
  assert huphy_deg_s_to_sim_rad_s(180.0, sign=1, travel_sign=-1.0) == pytest.approx(-math.pi)
  assert huphy_torque_to_sim(10.0, sign=-1, travel_sign=1.0) == pytest.approx(-10.0)
