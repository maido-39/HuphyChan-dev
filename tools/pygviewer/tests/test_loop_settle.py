"""The AB closed loop must stay closed, and the ankle-space command must land.

Reference for the transmission magnitude: ``tools/robot_model/loop_ankle_verify.json``
(pitch 1.210 deg per common crank deg, roll 1.418 deg per differential crank deg).  That
file was produced on ``pygmalion_v3_printed_loop`` with only the shin welded, so it is a
magnitude cross-check, NOT a sign spec: the v30 generator re-signed crank_B's joint axis, so
what is "common" in v3 joint-q is "opposed" here.  The test asserts the magnitudes agree to
5 % and lets the signs be whatever the model says.
"""

import json

import numpy as np
import pytest

from pygviewer import CACHE_DIR, REPO
from pygviewer.contract import load_contract
from pygviewer.sim_core import SimCore

VARIANT = "LegOnly-AB"
REF = json.load(open(f"{REPO}/tools/robot_model/loop_ankle_verify.json"))


@pytest.fixture(scope="module")
def core():
  c = SimCore(load_contract(CACHE_DIR, VARIANT), realtime=False)
  c.set_base(mode="fixed", pos=[0.0, 0.0, 1.0], rpy=[0.0, 0.0, 0.0])
  c.step_n(200)
  yield c
  c.stop()


def test_closure_holds_at_rest(core):
  assert core.closure_mm() < 0.01, f"loop already open at rest: {core.closure_mm()} mm"


@pytest.mark.parametrize("pitch,roll", [(0.0, 0.0), (-0.35, 0.0), (0.17, 0.0), (0.0, 0.17),
                                        (0.0, -0.17), (-0.2, 0.1)])
def test_ankle_space_command_lands_and_the_loop_stays_closed(core, pitch, roll):
  core.reset("home")
  core.set_base(mode="fixed", pos=[0.0, 0.0, 1.0], rpy=[0.0, 0.0, 0.0])
  for s in ("L", "R"):
    core.set_ankle(s, pitch, roll)
  core.step_n(1200)  # 6 s of PD ramp + settle; crank targets are NEVER qpos-snapped
  assert core.closure_mm() < 0.01, f"loop opened to {core.closure_mm()} mm"
  snap = core.snapshot()
  for s, v in snap["ankle_derived"].items():
    assert abs(v["pitch"] - pitch) < 0.05, f"{s} pitch {v['pitch']:.4f} vs {pitch}"
    assert abs(v["roll"] - roll) < 0.05, f"{s} roll {v['roll']:.4f} vs {roll}"


def test_transmission_magnitude_matches_the_v3_reference(core):
  t = core.c.raw["loop_transmission"]
  ref_pitch = abs(REF["pitch_per_crank_deg"])
  ref_roll = abs(REF["roll_per_crank_diff_deg"])
  for s in ("L", "R"):
    # v3's "per common crank" moved BOTH cranks, so it equals the sum of this model's two
    # columns; the mode that is common in v3 q-space is the opposed one here.
    got_pitch = abs(t[s]["pitch_per_crank_opposed_deg"]) * 2.0
    got_roll = abs(t[s]["roll_per_crank_common_deg"]) * 2.0
    assert got_pitch == pytest.approx(ref_pitch, rel=0.05), f"{s} pitch lever {got_pitch:.3f}"
    assert got_roll == pytest.approx(ref_roll, rel=0.05), f"{s} roll lever {got_roll:.3f}"


def test_the_two_cranks_of_one_leg_have_opposite_axes(core):
  """The trap this whole module exists for, asserted so it cannot silently go away."""
  jc = core.c.raw["joint_contract"]
  a = np.asarray(jc["L_crank_A_joint"]["axis"])
  b = np.asarray(jc["L_crank_B_joint"]["axis"])
  assert np.allclose(a, -b), (
    "L_crank_A and L_crank_B no longer have opposite joint axes; the envelope sign map "
    "fitted at bake time and the 'opposed = pitch' reading in this file both need redoing"
  )


def test_rp_variant_drives_the_ankle_directly():
  c = SimCore(load_contract(CACHE_DIR, "LegOnly-RP"), realtime=False)
  try:
    assert c.ankle_inverse is None
    assert "L_ankle_pitch_joint" in c.act_names
    c.set_base(mode="fixed", pos=[0.0, 0.0, 1.0])
    c.set_target({"L_ankle_pitch_joint": -0.3, "R_ankle_pitch_joint": -0.3})
    c.step_n(600)
    q = c.snapshot()["q"][c.names.index("L_ankle_pitch_joint")]
    assert abs(q - (-0.3)) < 0.05, f"RP ankle did not track: {q:.4f}"
  finally:
    c.stop()
