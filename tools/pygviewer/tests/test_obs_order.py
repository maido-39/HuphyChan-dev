"""The observation the viewer builds must BE the observation the trainer builds.

Not "look like": ``bake policy`` records 40 consecutive control steps of the real mjlab env -
the ingredients (motor angles, gyro, up-vector, previous raw action, command) next to the
45-D vector its own ObservationManager produced from them.  This test feeds the ingredients
to ``ObsBuilder`` and demands the same numbers back.  That is what pins term order, the
2-frame history direction ([q(t-1), q(t)], not the reverse) and the sign of projected
gravity, none of which are visible in a plot until the gait is quietly wrong.
"""

import glob
import json

import numpy as np
import pytest

from pygviewer import CACHE_DIR
from pygviewer.contract import load_contract
from pygviewer.policy import ObsBuilder

POLICIES = sorted(glob.glob(f"{CACHE_DIR}/*.policy_contract.json"))
pytestmark = pytest.mark.skipif(not POLICIES, reason="no policy baked yet")


@pytest.fixture(scope="module", params=POLICIES, ids=lambda p: p.split("/")[-1][:40])
def baked(request):
  pc = json.loads(open(request.param).read())
  mc = load_contract(CACHE_DIR, pc["variant"])
  rec = np.load(pc["obs_parity_npz"], allow_pickle=True)
  return pc, mc, rec


def _sensor_vector(mc, rec, k):
  adr = {kk.split("/")[-1]: (v["adr"], v["dim"]) for kk, v in mc.raw["sensors"].items()}
  sd = np.zeros(max(a + d for a, d in adr.values()))
  a, d = adr["imu_ang_vel"]
  sd[a : a + d] = rec["gyro"][k]
  a, d = adr["imu_upvector"]
  sd[a : a + d] = rec["upvector"][k]
  return sd


def test_layout_matches_the_contract(baked):
  pc, mc, _ = baked
  b = ObsBuilder(mc, pc)
  dims = b.describe()
  assert sum(d["dim"] for d in dims) == pc["obs_dim"]
  assert [d["name"] for d in dims] == [t["name"] for t in pc["obs_terms"]]


def test_obs_dim_is_45_for_the_student_actor(baked):
  pc, _, _ = baked
  if pc["env_toggles"].get("PYG_STUDENT_TEACHER"):
    assert pc["obs_dim"] == 45, (
      "student/teacher actor = 3 gyro + 3 gravity + 24 (12 motors x 2 frames) + 12 actions "
      f"+ 3 command; got {pc['obs_dim']}"
    )


def test_builder_reproduces_the_env_observation(baked):
  pc, mc, rec = baked
  b = ObsBuilder(mc, pc)
  jn = list(mc.raw["joint_names"])
  on = [str(x) for x in rec["obs_joint_names"]]
  idx = [jn.index(n) for n in on]
  worst = 0.0
  for k in range(1, rec["env_obs"].shape[0]):
    now = np.zeros(len(jn))
    now[idx] = rec["motor_q"][k]
    prev = np.zeros(len(jn))
    prev[idx] = rec["motor_q"][k - 1]
    obs = b.build(
      [prev, now], np.zeros(len(jn)), _sensor_vector(mc, rec, k), rec["last_action"][k],
      rec["cmd"][k],
    )
    worst = max(worst, float(np.abs(obs - rec["env_obs"][k]).max()))
  assert worst < 1e-4, f"observation differs from the env's by {worst:.3e}"


def test_history_direction_is_oldest_first(baked):
  """Swap the two frames: the test above must then FAIL. Proves it has teeth."""
  pc, mc, rec = baked
  b = ObsBuilder(mc, pc)
  if b.history_length < 2:
    pytest.skip("no history in this observation")
  jn = list(mc.raw["joint_names"])
  on = [str(x) for x in rec["obs_joint_names"]]
  idx = [jn.index(n) for n in on]
  k = 10
  now = np.zeros(len(jn))
  now[idx] = rec["motor_q"][k]
  prev = np.zeros(len(jn))
  prev[idx] = rec["motor_q"][k - 1]
  ok = b.build([prev, now], np.zeros(len(jn)), _sensor_vector(mc, rec, k),
               rec["last_action"][k], rec["cmd"][k])
  swapped = b.build([now, prev], np.zeros(len(jn)), _sensor_vector(mc, rec, k),
                    rec["last_action"][k], rec["cmd"][k])
  assert np.abs(ok - rec["env_obs"][k]).max() < 1e-4
  assert np.abs(swapped - rec["env_obs"][k]).max() > 1e-4, (
    "swapping the history frames changed nothing - the two frames are identical here, so "
    "this sample cannot prove the direction; pick a moving step"
  )


def test_projected_gravity_is_the_negated_up_vector(baked):
  pc, mc, rec = baked
  b = ObsBuilder(mc, pc)
  off = {d["name"]: (d["offset"], d["dim"]) for d in b.describe()}
  if "projected_gravity" not in off:
    pytest.skip("no projected_gravity term")
  o, d = off["projected_gravity"]
  k = 5
  assert np.allclose(rec["env_obs"][k][o : o + d], -rec["upvector"][k], atol=1e-6)
