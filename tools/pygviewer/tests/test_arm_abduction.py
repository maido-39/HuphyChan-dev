"""Both arms must flare OUTWARD at the welded default pose, on every baked variant that has
arms - a physical acceptance check on the real baked model, complementing the mjlab-side
forward-kinematics probe (``mujoco-sim/mjlab/tests/test_pygmalion_arm_abduction.py``) that
found and fixed the underlying sign bug in ``pygmalion_constants.get_spec()``.

Before the fix, one arm abducted (moved away from the body) and the other ADDUCTED (folded
toward/across the body) - a single hardcoded sign applied to both sides, on a model whose
shoulder_roll RANGE is mirrored between the two arms. This test would have failed on the
pre-fix bake (verified manually while writing it): only one of the two ``assert`` lines
below passed.
"""

import pytest

from pygviewer import CACHE_DIR
from pygviewer.contract import load_contract
from pygviewer.sim_core import SimCore

ARM_VARIANTS = ("FullDoF-AB", "FullDoF-RP", "SemiFullDoF-AB", "SemiFullDoF-RP")


@pytest.fixture(scope="module", params=ARM_VARIANTS)
def core(request):
  c = SimCore(load_contract(CACHE_DIR, request.param), realtime=False)
  yield c
  c.stop()


def test_both_arms_abduct_at_the_welded_default_pose(core):
  """mj_forward at the reset (default) pose: each arm-link collision geom's world Y must
  sit FURTHER from the centreline (Y=0) than its own shoulder - the same forward-kinematics
  check that caught the sign bug, run here on the actual baked model pygviewer serves."""
  m, d = core.m, core.d
  offsets = {}
  for side in ("L", "R"):
    sh_id = m.body(f"robot/{side}_shoulder_pitch_link").id
    g_id = m.geom(f"robot/{side}_arm_link_collision").id
    shoulder_y = float(d.xpos[sh_id][1])
    arm_y = float(d.geom_xpos[g_id][1])
    offsets[side] = (shoulder_y, arm_y - shoulder_y)

  for side, (shoulder_y, rel_y) in offsets.items():
    # abduction = moving further in the direction the shoulder already sits away from the
    # centreline: rel_y must have the SAME sign as the shoulder's own Y.
    assert shoulder_y * rel_y > 0, (
      f"{core.c.variant}: {side} arm did NOT abduct at the default pose "
      f"(shoulder_y={shoulder_y:+.4f}, arm rel_y={rel_y:+.4f} - opposite signs means it "
      f"folded IN instead of flaring OUT)"
    )

  l_mag, r_mag = abs(offsets["L"][1]), abs(offsets["R"][1])
  assert abs(l_mag - r_mag) < 0.002, (
    f"{core.c.variant}: arms flare by different amounts (L {l_mag:.4f} m, R {r_mag:.4f} m) "
    "- should be mirror-symmetric"
  )
  assert 0.08 < l_mag < 0.13, f"{core.c.variant}: unexpected flare magnitude {l_mag:.4f} m"
