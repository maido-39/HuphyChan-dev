"""The three base modes must mean what the panel says they mean.

``fixed``  the base does not move at all - the number to beat is 1e-6 m of drift over 2 s.
           MuJoCo's DEFAULT equality softness gives 1.9e-4 m here, i.e. a 23 kg robot slowly
           sinking through its own "fixed" mount, so this test is what keeps the stiff
           solref/solimp in bake.py from being "simplified" away.
``pivot``  the chosen point stays put (< 1e-4 m) while the orientation is free to fall.
``free``   normal dynamics: with the ground on, the robot stands rather than sinking.
"""

import numpy as np
import pytest

from pygviewer import CACHE_DIR
from pygviewer.contract import load_contract
from pygviewer.sim_core import SimCore

VARIANT = "LegOnly-AB"


@pytest.fixture(scope="module")
def core():
  c = SimCore(load_contract(CACHE_DIR, VARIANT), realtime=False)
  yield c
  c.stop()


def _base_pos(c):
  return c.d.qpos[c.free_adr : c.free_adr + 3].copy()


def _base_quat(c):
  return c.d.qpos[c.free_adr + 3 : c.free_adr + 7].copy()


def test_fixed_does_not_drift(core):
  core.reset("knees_bent")
  core.set_base(mode="fixed", pos=[0.2, -0.1, 1.05], rpy=[0.0, 0.1, 0.3])
  core.step_n(400)  # 2 s of settling
  p0, q0 = _base_pos(core), _base_quat(core)
  core.step_n(400)  # the 2 s under test
  drift = float(np.linalg.norm(_base_pos(core) - p0))
  rot = float(np.linalg.norm(_base_quat(core) - q0))
  assert drift < 1e-6, f"fixed base drifted {drift:.3e} m in 2 s"
  assert rot < 1e-5, f"fixed base rotated {rot:.3e} (quat norm) in 2 s"


def test_fixed_lands_on_the_commanded_pose(core):
  core.reset("knees_bent")
  want = np.array([0.05, 0.02, 1.10])
  core.set_base(mode="fixed", pos=want, rpy=[0.0, 0.0, 0.0])
  core.step_n(400)
  err = float(np.linalg.norm(_base_pos(core) - want))
  assert err < 1e-5, f"welded base sits {err:.3e} m from the anchor"


def test_pivot_holds_the_point_and_frees_the_rotation(core):
  core.reset("knees_bent")
  offset = np.array([0.0, 0.0, 0.06])
  pivot = np.array([0.0, 0.0, 1.10])
  core.set_base(mode="pivot", pos=pivot, pivot_offset=offset, rpy=[0.0, 0.05, 0.0])
  core.step_n(1000)  # 5 s under gravity
  R = np.zeros(9)
  import mujoco

  mujoco.mju_quat2Mat(R, _base_quat(core))
  world_pivot = core.d.xpos[core.base_bid] + R.reshape(3, 3) @ offset
  err = float(np.linalg.norm(world_pivot - pivot))
  assert err < 1e-4, f"pivot point moved {err:.3e} m"
  dq = float(np.linalg.norm(_base_quat(core) - np.array([1.0, 0.0, 0.0, 0.0])))
  assert dq > 1e-3, "pivot mode did not let the base rotate at all - it is welded, not pivoted"


def test_free_is_supported_by_the_ground():
  """With the ground on the robot is held up by contact, not by anything in this viewer.

  It is NOT asked to stay standing: nothing balances it in P1 (targets are held at the
  default pose, there is no policy), and a passive biped topples in a couple of seconds.
  What must be true is that contact CARRIES it - it does not sink or fall through.  Fresh
  core, because how far a toppling robot has got by a given instant depends on what the
  previous test left behind.
  """
  c = SimCore(load_contract(CACHE_DIR, VARIANT), realtime=False)
  try:
    c.set_base(mode="free", ground=True)
    c.reset("knees_bent")
    z0 = float(_base_pos(c)[2])
    c.step_n(100)  # 0.5 s
    z1 = float(_base_pos(c)[2])
    assert c.d.ncon > 0, "ground on but no contacts at all"
    assert z1 > 0.8, f"free base sank from {z0:.3f} to {z1:.3f} m in 0.5 s with the ground on"
  finally:
    c.stop()


def test_the_trainer_keyframe_starts_with_the_soles_below_the_floor(core):
  """A recorded FINDING, not a viewer behaviour - see contract.keyframe_sole_penetration_m.

  pygmalion_constants._v2_standing_z() takes `standing_base_z` from the pygmalion_v2
  validation file; the v30 build is a different robot, so the bent keyframe's base z (0.868)
  is ~39 mm lower than the height that puts the soles on the plane (0.907).  Every training
  reset therefore begins with the feet buried and the solver pushing them out.  The viewer
  reproduces the trainer exactly rather than silently correcting it; this test pins the
  number so a future model change that fixes (or worsens) it is visible.
  """
  pen = core.c.raw["keyframe_sole_penetration_m"]
  assert pen == pytest.approx(0.0386, abs=0.002), f"keyframe sole penetration is now {pen} m"


def test_ground_toggle_actually_removes_contact(core):
  core.reset("knees_bent")
  core.set_base(mode="free", ground=False)
  z0 = float(_base_pos(core)[2])
  core.step_n(200)  # 1 s of free fall
  z1 = float(_base_pos(core)[2])
  drop = z0 - z1
  assert drop > 0.5 * 9.81 * 1.0**2 * 0.5, f"ground off but the robot only fell {drop:.3f} m"
  core.set_base(ground=True)
  assert core.m.geom_contype[core.floor_gid] != 0


def test_gravity_is_never_modified(core):
  assert list(core.m.opt.gravity) == pytest.approx([0.0, 0.0, -9.81], abs=1e-9)
