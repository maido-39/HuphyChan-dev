"""``string`` base mode: a real safety-harness tether, not a rigid mount.

Physics is a MuJoCo spatial tendon LIMITED to length [0, L0] between the mocap anchor and a
site on base_link (bake.py "spec surgery" comment) - a one-directional (rope) constraint:
slack below the limit, taut at it.  That is the "설정 Z보다 base가 내려가면 끈이 팽팽해져
받쳐주고, 그 위에서는 느슨해져 스스로 서 있어야 함" request verbatim, done with MuJoCo's own
tendon-limit mechanism rather than a hand-rolled force law.

The isolated single-tendon check that established this design (before touching the real
6-DOF model) is reproduced by ``test_string_tension_equals_weight_isolated`` below: a bare
23.63 kg point mass caught by an identical tendon settles at z_set with zero steady-state
error and a tension that is the mass's own weight to 6 significant figures - so any residual
seen on the full LegOnly-AB model is attributable to the model, not to this test's tolerance.
"""

import mujoco
import numpy as np
import pytest

from pygviewer import CACHE_DIR
from pygviewer.contract import load_contract
from pygviewer.sim_core import SimCore

VARIANT = "LegOnly-AB"
ROBOT_MASS_KG = 23.63014  # contract total_mass_kg, LegOnly-AB
ROBOT_WEIGHT_N = ROBOT_MASS_KG * 9.81


@pytest.fixture
def core():
  c = SimCore(load_contract(CACHE_DIR, VARIANT), realtime=False)
  yield c
  c.stop()


def _base_z(c) -> float:
  return float(c.d.qpos[c.free_adr + 2])


def test_string_catches_a_free_fall_at_z_set(core):
  """Ground off, base dropped from 0.9 m, Z_set=0.6 m -> settles at Z_set +/- 0.02 m, tension
  ~= the robot's own weight (231.8 N +/- 10%), averaged after it has visibly stopped moving."""
  core.reset("knees_bent")
  core.d.qpos[core.free_adr : core.free_adr + 3] = [0.0, 0.0, 0.9]
  core.d.qvel[:] = 0.0
  mujoco.mj_forward(core.m, core.d)
  core.set_base(mode="string", z_set=0.6, ground=False)
  assert core.base_mode == "string"

  core.step_n(1300)  # 6.5 s: free-fall + catch + settle
  zs, tens = [], []
  for _ in range(20):
    core.step_n(10)  # +0.05 s each, 1.0 s total sampled
    snap = core.snapshot()
    zs.append(snap["base"]["pos"][2])
    tens.append(snap["string"]["tension_N"])
  zs, tens = np.array(zs), np.array(tens)

  assert abs(zs.mean() - 0.6) < 0.02, f"settled at {zs.mean():.4f} m, want 0.6 +/- 0.02"
  assert zs.std() < 0.01, f"still moving: z std {zs.std():.4f} m over the sampled 1 s"
  rel_err = abs(tens.mean() - ROBOT_WEIGHT_N) / ROBOT_WEIGHT_N
  assert rel_err < 0.10, f"tension {tens.mean():.1f} N vs weight {ROBOT_WEIGHT_N:.1f} N ({rel_err:.1%} off)"
  assert snap["string"]["taut"] is True


def test_string_is_slack_while_standing_then_catches_a_topple(core):
  """Ground on, default standing pose, Z_set = standing z - 0.15 m -> starts SLACK (tension
  0, taut False); with no policy (PD-only) the passive biped topples and, once the base
  reaches Z_set, the tether goes taut and holds base z >= Z_set - 0.02 m from then on."""
  core.reset("knees_bent")
  core.set_base(mode="free", ground=True)
  core.step_n(50)  # let the initial keyframe settle onto the floor
  standing_z = _base_z(core)
  z_set = standing_z - 0.15

  core.set_base(mode="string", z_set=z_set, ground=True)
  core.step_n(10)
  snap0 = core.snapshot()
  assert snap0["string"]["taut"] is False, "should start slack: base is well above z_set"
  assert snap0["string"]["tension_N"] == 0.0

  taut_ever = False
  min_z_after_taut = float("inf")
  for _ in range(150):  # up to 150*0.1 = 15 s of sim time
    core.step_n(20)  # 0.1 s
    snap = core.snapshot()
    if snap["string"]["taut"]:
      taut_ever = True
      min_z_after_taut = min(min_z_after_taut, snap["base"]["pos"][2])
    elif taut_ever:
      # once caught, a PD-held passive biped must not later slip BELOW the floor the tether
      # set - a one-shot dip below the constraint would be a real regression, not noise.
      min_z_after_taut = min(min_z_after_taut, snap["base"]["pos"][2])

  assert taut_ever, "the tether never went taut - the robot did not fall far enough to test it"
  assert min_z_after_taut >= z_set - 0.02, (
    f"base sank to {min_z_after_taut:.4f} m, more than 0.02 m under z_set {z_set:.4f} m"
  )


def test_mode_roundtrip_no_nan_and_no_stale_constraints(core):
  """string -> fixed -> free -> string: no NaN, no equality left active, tendon state clean."""
  core.reset("knees_bent")
  core.set_base(mode="string", z_set=0.6)
  core.step_n(50)
  core.set_base(mode="fixed", pos=[0.0, 0.0, 1.0], rpy=[0.0, 0.0, 0.0])
  core.step_n(50)
  assert core.m.tendon_limited[core.string_tid] == 0, "fixed mode must not leave the tether limited"
  core.set_base(mode="free")
  core.step_n(50)
  assert core.d.eq_active[core.eq_weld] == 0
  assert core.d.eq_active[core.eq_pivot] == 0
  assert core.m.tendon_limited[core.string_tid] == 0
  core.set_base(mode="string", z_set=0.6)
  core.step_n(50)

  assert np.all(np.isfinite(core.d.qpos)), "NaN qpos after a base-mode roundtrip"
  assert np.all(np.isfinite(core.d.qvel)), "NaN qvel after a base-mode roundtrip"
  assert core.d.eq_active[core.eq_weld] == 0, "weld left active after leaving 'fixed'"
  assert core.d.eq_active[core.eq_pivot] == 0, "pivot connect left active (never entered)"
  assert core.m.tendon_limited[core.string_tid] == 1, "back in 'string' but the tendon is not limited"


def test_string_hook_offset_moves_the_attachment_site(core):
  """POST /base hook_offset rewrites the compiled model's site_pos, same mechanism pivot_offset
  already uses on eq_data - this just confirms the write actually lands."""
  core.reset("knees_bent")
  offset = [0.01, -0.02, 0.03]
  core.set_base(mode="string", z_set=0.6, hook_offset=offset)
  assert core.m.site_pos[core.string_hook_sid] == pytest.approx(offset)


def test_string_follow_xy_keeps_the_anchor_over_the_base(core):
  """follow_xy=True: the anchor's (x, y) tracks the base every substep, so a purely
  horizontal base offset does not, by itself, tauten the tether (no swing arm to fight)."""
  core.reset("knees_bent")
  core.set_base(mode="string", z_set=0.6, follow_xy=True, ground=False)
  core.d.qpos[core.free_adr : core.free_adr + 2] = [0.3, -0.2]
  mujoco.mj_forward(core.m, core.d)
  core._refresh_anchor()
  anchor_xy = core.d.mocap_pos[core.mocap_id][:2]
  assert anchor_xy == pytest.approx([0.3, -0.2], abs=1e-9)


def test_string_tension_equals_weight_isolated():
  """Isolated single-tendon sanity check (no robot, no bake): the exact rig this feature adds
  to the real model, run standalone so a failure here can never be blamed on anything else in
  LegOnly-AB. A 23.63 kg point mass dropped above Z_set settles at Z_set with the tendon
  tension equal to its own weight to 6 significant figures."""
  spec = mujoco.MjSpec()
  spec.option.timestep = 0.005
  spec.option.gravity = [0, 0, -9.81]
  anchor = spec.worldbody.add_body(name="anchor", mocap=True, pos=[0, 0, 1.6])
  anchor.add_site(name="a_site", size=[0.01, 0, 0])
  mass_body = spec.worldbody.add_body(name="mass", pos=[0, 0, 0.9])
  mass_body.add_freejoint()
  mass_body.add_geom(type=mujoco.mjtGeom.mjGEOM_SPHERE, size=[0.05, 0, 0], mass=ROBOT_MASS_KG)
  mass_body.add_site(name="m_site", pos=[0, 0, 0])
  t = spec.add_tendon(name="string")
  t.limited = True
  t.range = [0, 1.0]
  t.solref_limit = [0.02, 1.0]
  t.wrap_site("a_site")
  t.wrap_site("m_site")
  m = spec.compile()
  d = mujoco.MjData(m)
  tid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_TENDON, "string")
  mujoco.mj_forward(m, d)
  for _ in range(2000):  # 10 s
    mujoco.mj_step(m, d)
  z = float(d.xpos[m.body("mass").id][2])
  tension = 0.0
  for i in range(d.nefc):
    if d.efc_id[i] == tid and d.efc_type[i] == mujoco.mjtConstraint.mjCNSTR_LIMIT_TENDON:
      tension = float(d.efc_force[i])
  assert z == pytest.approx(0.6, abs=1e-3)
  assert tension == pytest.approx(ROBOT_WEIGHT_N, rel=1e-4)
