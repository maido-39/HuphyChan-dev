"""The real IMU's attitude, and why it is checked rather than trusted.

2026-09-08, user: "IMU (body frame) -> 이거 아직도 IMU 실물은 축 시각화 안보여."

The dashboard draws the real sensor's body axes translucently beside the sim's, but they
never appeared, because ``parse_imu`` deliberately dropped the quaternion:

    # HUPHY has already reordered its sensor's native (z,y,x,w) quaternion ...
    # quat is left null unless a future need requires it.
    quat_wxyz=None,

That was a reasonable call at the time - re-deriving an attitude risks a second, independent
reordering bug - and it named its own expiry condition. The need arrived: gravity alone fixes
only two of the three degrees of freedom (there is no yaw in it), so the axes cannot be drawn
from it.

The risk is now handled by measuring instead of trusting. HUPHY computes gravity from this
same quaternion in ``sensors/base.py::gravity_from_quat`` and sends BOTH on the same packet,
so re-deriving one from the other is a free, per-packet check on the component order.

That check is not ceremonial. The first attempt at it used the third COLUMN of the rotation
matrix instead of the third ROW and disagreed on X by 0.59 - which reads exactly like a sensor
sign fault, and is not one. The formula below is HUPHY's, verified against 40 live packets
from this bench (worst component difference 0.008, the wire's own two-decimal rounding).
"""

from __future__ import annotations

import math

import pytest

from pygviewer import CACHE_DIR
from pygviewer.bridge.huphy_udp import HuphyBridge
from pygviewer.contract import load_contract

VARIANT = "LegOnly-AB"

# One real packet off this bench, quaternion and gravity together.
LIVE = {"qw": 0.62, "qx": 0.0, "qy": 0.24, "qz": 0.75,
        "grav_x": 0.29, "grav_y": -0.36, "grav_z": -0.88}


def _bridge():
  try:
    return HuphyBridge(load_contract(CACHE_DIR, VARIANT))
  except FileNotFoundError:
    pytest.skip(f"no baked contract for {VARIANT}")


def _packet(**over):
  d = dict(LIVE); d.update(over)
  return {f"imu/main/{k}": v for k, v in d.items()}


def huphy_gravity(w, x, y, z):
  """HUPHY's own formula (sensors/base.py::gravity_from_quat): minus the third ROW of the
  standard (w,x,y,z) body-to-world rotation."""
  return (2.0*(w*y - x*z), -2.0*(y*z + w*x), 2.0*(x*x + y*y) - 1.0)


def test_the_live_packet_is_self_consistent():
  """The measurement the whole change rests on: this sensor's quaternion and its gravity
  agree to the wire's rounding, so the component order is right."""
  g = huphy_gravity(LIVE["qw"], LIVE["qx"], LIVE["qy"], LIVE["qz"])
  sent = (LIVE["grav_x"], LIVE["grav_y"], LIVE["grav_z"])
  worst = max(abs(a-b) for a, b in zip(g, sent))
  assert worst < 0.02, f"worst component difference {worst:.4f}"


def test_the_third_column_mistake_would_be_caught():
  """The wrong derivation that looked like a hardware fault. Kept as a test so the next
  person to 'simplify' the formula finds out immediately."""
  w, x, y, z = (LIVE[k] for k in ("qw", "qx", "qy", "qz"))
  third_column = (-2.0*(x*z + w*y), -2.0*(y*z - w*x), 2.0*(x*x + y*y) - 1.0)
  sent = (LIVE["grav_x"], LIVE["grav_y"], LIVE["grav_z"])
  worst = max(abs(a-b) for a, b in zip(third_column, sent))
  assert worst > 0.5, "the column/row mix-up must be far outside tolerance, not marginal"


def test_a_consistent_quaternion_is_passed_through():
  msg = _bridge().parse_imu(_packet())
  assert msg is not None
  assert msg.quat_wxyz == pytest.approx([0.62, 0.0, 0.24, 0.75])
  assert msg.gravity_b == pytest.approx([0.29, -0.36, -0.88])


def test_a_reordered_quaternion_is_rejected_not_drawn():
  """The exact failure the old comment feared. Swapping two components leaves a perfectly
  valid unit quaternion that describes a different attitude - only the gravity cross-check
  can tell, and the result must be null rather than a confidently wrong picture."""
  b = _bridge()
  msg = b.parse_imu(_packet(qx=LIVE["qy"], qy=LIVE["qx"]))
  assert msg is not None, "the rest of the IMU packet must still come through"
  assert msg.quat_wxyz is None
  assert msg.gravity_b is not None, "gravity is HUPHY's own and stays trustworthy"
  assert b.imu_quat_rejects == 1
  assert any("disagrees with the reported gravity" in w for w in b.warnings)


def test_a_sign_flip_is_rejected():
  b = _bridge()
  assert b.parse_imu(_packet(qy=-LIVE["qy"])).quat_wxyz is None


def test_a_non_unit_quaternion_is_rejected():
  b = _bridge()
  msg = b.parse_imu(_packet(qw=0.1, qx=0.1, qy=0.1, qz=0.1))
  assert msg.quat_wxyz is None
  assert any("unit quaternion" in w for w in b.warnings)


def test_a_packet_without_gravity_still_yields_the_quaternion():
  """Nothing to check against, but the fields are named on the wire, so they are taken.
  Refusing here would lose the attitude for a sender that simply reports less."""
  b = _bridge()
  p = {f"imu/main/{k}": v for k, v in LIVE.items() if not k.startswith("grav")}
  msg = b.parse_imu(p)
  assert msg.quat_wxyz == pytest.approx([0.62, 0.0, 0.24, 0.75])


def test_a_packet_without_a_quaternion_is_unaffected():
  """Senders that never carried one must behave exactly as before."""
  b = _bridge()
  p = {f"imu/main/{k}": v for k, v in LIVE.items() if k.startswith("grav")}
  msg = b.parse_imu(p)
  assert msg is not None and msg.quat_wxyz is None
  assert b.imu_quat_rejects == 0, "absence is not a disagreement"


def test_rejections_warn_once_not_every_packet():
  b = _bridge()
  for _ in range(50):
    b.parse_imu(_packet(qx=LIVE["qy"], qy=LIVE["qx"]))
  assert b.imu_quat_rejects == 50
  assert sum("disagrees" in w for w in b.warnings) == 1, "one warning, not a flood"
