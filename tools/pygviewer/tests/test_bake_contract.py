"""The six baked contracts must describe six real, self-consistent robots.

The window check is the one that matters most: ``legonly_ab_v1`` burned a whole training run
because the left knee's command window was 0 deg wide (one regex, a mirrored axis,
docs/reward_research/2026-09-03_stiff_knee_root_cause.md).  A contract that reproduces that
must fail here, not 700 iterations later.
"""

import json

import pytest

from pygviewer import CACHE_DIR, VARIANTS
from pygviewer.contract import load_contract

REQUIRED = (
  "joint_names", "action_joint_names", "obs_joint_names", "obs_layout", "default_q",
  "gains", "tn_curves", "dof_props", "decimation", "physics_dt", "step_dt", "sim_options",
  "spawn_base_z", "keyframes", "env_toggles", "safe_clip", "joint_contract", "xml_sha256",
  "constants_sha256", "mjlab_git", "bake_utc", "anchor_eq_ids", "floor_geom", "gravity",
)

MIN_WINDOW_RAD = 0.2
MIN_WINDOW_HARD_RAD = 0.02

# Known narrow windows, recorded rather than hidden.  Each entry is a FINDING about the
# model/config, not about this viewer, and the number is the measured headroom:
#   RP ankle_pitch: default +0.360 rad sits 0.094 rad below its own safe_clip ceiling
#   (+0.454 rad).  The joint's MJCF range is asymmetric ([-50, +30] deg) and the bent
#   keyframe parks it near the short end, so plantarflexion has 5.4 deg of command headroom
#   while dorsiflexion has 66.6.  Not the legonly_ab_v1 failure (that window was 0 deg wide),
#   but the same family, so it is asserted at its measured value: if it shrinks further this
#   test fails again.
KNOWN_NARROW = {
  ("RP", "L_ankle_pitch_joint"): 0.0938,
  ("RP", "R_ankle_pitch_joint"): 0.0938,
}


@pytest.fixture(scope="module", params=list(VARIANTS))
def contract(request):
  return load_contract(CACHE_DIR, request.param)


def test_required_fields(contract):
  missing = [k for k in REQUIRED if k not in contract.raw]
  assert not missing, f"{contract.variant}: contract is missing {missing}"


def test_sizes_agree(contract):
  r = contract.raw
  assert r["nu"] == len(r["action_joint_names"]) == 12
  assert len(r["joint_names"]) == r["n_dof"]
  assert set(r["action_joint_names"]) <= set(r["joint_names"])
  assert set(r["obs_joint_names"]) <= set(r["joint_names"])
  # order, not just membership: the action term's resolved order is the wire order
  assert r["action_joint_names"] == list(dict.fromkeys(r["action_joint_names"]))
  assert all(n in r["gains"] for n in r["action_joint_names"])
  assert all(n in r["safe_clip"] for n in r["action_joint_names"])


def test_ab_action_order_matches_docs_112(contract):
  if contract.ankle_mode != "AB":
    return
  assert contract.action_joint_names == [
    "L_hip_pitch_joint", "L_hip_roll_joint", "L_hip_yaw_joint", "L_knee_joint",
    "L_crank_A_joint", "L_crank_B_joint",
    "R_hip_pitch_joint", "R_hip_roll_joint", "R_hip_yaw_joint", "R_knee_joint",
    "R_crank_A_joint", "R_crank_B_joint",
  ]


def test_gravity_is_untouched(contract):
  assert contract.raw["gravity"] == pytest.approx([0.0, 0.0, -9.81], abs=1e-9)


def test_rates_match_training(contract):
  r = contract.raw
  assert r["physics_dt"] == pytest.approx(0.005), "physics must be the trainer's 200 Hz"
  assert r["step_dt"] == pytest.approx(r["physics_dt"] * r["decimation"])
  assert r["step_dt"] == pytest.approx(0.02), "control must be the trainer's 50 Hz"


def test_default_inside_its_own_range_and_clip(contract):
  r = contract.raw
  bad = []
  for n in contract.action_joint_names:
    d = contract.default_q(n)
    lo, hi = r["joint_contract"][n]["range"]
    clo, chi = contract.clip(n)
    if not (lo - 1e-9 <= d <= hi + 1e-9):
      bad.append((n, "outside MJCF range", d, (lo, hi)))
    if not (clo - 1e-9 <= d <= chi + 1e-9):
      bad.append((n, "outside safe_clip", d, (clo, chi)))
  assert not bad, bad


def test_command_window_on_both_sides_of_default(contract):
  """>= 0.2 rad of travel each way from the default, for every actuated joint."""
  narrow = []
  for n in contract.action_joint_names:
    d = contract.default_q(n)
    lo, hi = contract.clip(n)
    known = KNOWN_NARROW.get((contract.ankle_mode, n))
    lim = known - 1e-3 if known is not None else MIN_WINDOW_RAD
    if (d - lo) < lim or (hi - d) < lim:
      narrow.append((n, round(d - lo, 4), round(hi - d, 4)))
  assert not narrow, f"{contract.variant}: window < {MIN_WINDOW_RAD} rad on one side: {narrow}"


def test_no_window_is_effectively_zero(contract):
  """The legonly_ab_v1 failure mode itself: a joint pinned against a stop all episode."""
  dead = []
  for n in contract.action_joint_names:
    d = contract.default_q(n)
    lo, hi = contract.clip(n)
    if (d - lo) < MIN_WINDOW_HARD_RAD or (hi - d) < MIN_WINDOW_HARD_RAD:
      dead.append((n, round(d - lo, 5), round(hi - d, 5)))
  assert not dead, f"{contract.variant}: joint has no usable command window: {dead}"


def test_mirror_flags_are_detected_both_ways(contract):
  """A mirrored pair must be flagged by range OR by axis - a symmetric range hides it."""
  jc = contract.raw["joint_contract"]
  knees = [n for n in jc if n.endswith("_knee_joint")]
  if len(knees) == 2:
    assert all(jc[n]["range_mirrored"] for n in knees), "v30 knees are range-mirrored"
  rolls = [n for n in jc if n.endswith("_ankle_roll_joint")]
  if len(rolls) == 2 and contract.ankle_mode == "AB":
    assert all(jc[n]["axis_mirrored"] for n in rolls), (
      "ankle_roll has a symmetric range on both legs but mirrored axes; a range-only test "
      "calls it unmirrored and a caller then sends both legs the same signed tilt"
    )


def test_travel_sign_points_at_the_long_end(contract):
  jc = contract.raw["joint_contract"]
  for n, v in jc.items():
    if v["travel_sign"] is None:
      continue
    lo, hi = v["range"]
    if abs(abs(lo) - abs(hi)) < 1e-9:
      continue
    assert v["travel_sign"] == (-1.0 if abs(lo) > abs(hi) else 1.0), n


def test_files_are_present_and_fresh(contract):
  f = contract.freshness()
  assert not f["stale"], f"{contract.variant} is stale: {f['checks']}"


def test_contract_sha_is_stable(contract):
  raw = json.loads(contract.path.read_text())
  assert raw["contract_sha"] == contract.contract_sha


def test_ab_carries_an_ankle_inverse(contract):
  if contract.ankle_mode != "AB":
    assert contract.raw["ankle_inverse"] is None
    return
  ai = contract.raw["ankle_inverse"]
  assert ai["method"] in ("envelope", "linear")
  assert ai["worst_residual_rad"] is not None
  assert ai["worst_residual_rad"] < 0.05, (
    "the ankle-space inverse misses by more than 0.05 rad even after the sign fit"
  )
