"""ROM clip enforcement task (2026-09-04): the receive-side hard-range clip at the qpos-snap
point in ``sim_core.py``, and the send-side honesty/NaN-rejection in ``schema.py``/``api.py``.

Motivation (docs/121 section 3, real measurement): a real_replay direct-drive joint driven
straight from telemetry with no bound at all produced ``range_violations L_knee 1373`` -
an uncalibrated/multi-turn real value landing in ``qpos`` completely unclipped. These cases
are the hard guarantee that can no longer happen:

  (a) a direct-drive joint (hip/knee/RP-ankle) fed an out-of-hard-range real value never
      gets that value snapped into qpos - it lands clipped to the model's own MJCF range,
      finite, and counted, while the RAW telemetry value stays untouched (the truth for
      plots/violation counts lives in ``RealState.q``, only the DRIVE is clamped). A NaN/inf
      sample is a separate case: treated exactly like "no data this tick", never snapped.
  (b) the AB closed-loop crank, fed an out-of-hard-range pair, keeps its PD target inside
      the tighter soft ``safe_clip`` window (unchanged pre-existing behaviour) and the
      closed loop stays closed - a hard-range violation on the crank is still counted even
      though the applied target never gets that far.
  (c) ``POST /target`` with an out-of-range value returns an honest
      ``{requested, applied, clip_range}`` - ``applied`` sits at the clip boundary and
      differs from ``requested``.
  (d) ``POST /target`` with a NaN/inf value is rejected (422), never silently clipped/passed
      through to the PD math.

All 7 cases share ONE ``SimCore`` (module-scoped fixture) rather than one per test: this
suite already runs ``test_sim_rate.py``'s ``ru_maxrss`` (process-lifetime peak RSS, never
decreases) against a 600 MB budget in the same pytest session, and a SimCore per test here
was measured to push that over budget purely from the extra instantiations - each test
still does its own explicit ``reset``/``set_base``/``mode`` transition, so sharing the
object does not weaken any assertion, it only avoids re-paying MuJoCo model/allocator
overhead seven times in one process.
"""

import json as jsonlib
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from pygviewer import CACHE_DIR
from pygviewer.api import build_app
from pygviewer.contract import load_contract
from pygviewer.schema import JointState
from pygviewer.sim_core import SimCore

VARIANT = "LegOnly-AB"


@pytest.fixture(scope="module")
def core():
  try:
    c = load_contract(CACHE_DIR, VARIANT)
  except FileNotFoundError:
    pytest.skip(f"no baked contract for {VARIANT}")
  core = SimCore(c, realtime=False)
  yield core
  core.stop()


@pytest.fixture(scope="module")
def http(core):
  app = build_app(core, core.c.freshness())
  return TestClient(app)


def _quiesce(core: SimCore) -> None:
  """Return the shared core to a known-clean state before a test's own setup: idle mode (so
  no earlier test's replay/manual driving is still active) and the standard reset pose."""
  core._apply_cmd({"op": "mode", "value": "idle"})
  core.reset("knees_bent")


# --------------------------------------------------------------- (a) direct-drive hard clip
def test_direct_drive_joint_is_hard_range_clipped_before_snapping_into_qpos(core):
  _quiesce(core)
  core.set_base(mode="free")
  core.submit({"op": "mode", "value": "real_replay"})
  core.step_n(core.decimation)
  assert core.mode == "real_replay"

  i = core.act_names.index("L_knee_joint")
  lo, hi = float(core.range_lo[i]), float(core.range_hi[i])
  out_of_range = hi + 5.0  # matches the real incident: a multi-turn/uncalibrated value
  assert out_of_range > hi

  msg = JointState(t_ns=1, seq=1, src="dummy", joint_names=["L_knee_joint"], q=[out_of_range])
  core.real.ingest_joint_state(msg)
  core.step_n(core.decimation * 5)

  q = float(core.d.qpos[core.a_q[i]])
  assert math.isfinite(q), "qpos went non-finite - the exact failure this task closes"
  assert lo - 1e-6 <= q <= hi + 1e-6, f"qpos {q} outside hard range [{lo}, {hi}]"
  assert q == pytest.approx(hi, abs=1e-6), "an out-of-hi value should clip to the hi bound"

  assert core.replay_clamp_count["L_knee_joint"] > 0
  assert core.replay_clamped_now["L_knee_joint"] is True

  # the RAW telemetry value is untouched - the truth stays in RealState, only the drive clamps
  assert core.real.q["L_knee_joint"] == pytest.approx(out_of_range, abs=1e-9)


def test_nonfinite_direct_drive_value_is_treated_as_no_data_never_snapped(core):
  """NaN/inf must never reach qpos - treated exactly like "no data this tick" (design item
  6: no data holds default, never guessed, never snapped as NaN). Differential test, same
  reasoning as test_record.py::test_real_replay_with_no_telemetry_is_identical_to_manual_mode:
  this leg is still gently settling under gravity even with an unchanged target, so "moved a
  little" is not itself a failure signal - what must hold is that a NaN sample produces the
  BIT-IDENTICAL trajectory to no telemetry at all (both dispatch to the same "no data" code
  path, by construction)."""
  _quiesce(core)
  core.set_base(mode="fixed")
  core._apply_cmd({"op": "mode", "value": "real_replay"})
  core.step_n(200)
  qpos0, qvel0, target0 = core.d.qpos.copy(), core.d.qvel.copy(), core.target.copy()

  core.step_n(core.decimation * 10)
  no_data_traj = core.d.qpos.copy()

  core.d.qpos[:], core.d.qvel[:], core.target[:] = qpos0, qvel0, target0
  msg = JointState(t_ns=1, seq=1, src="dummy", joint_names=["L_hip_pitch_joint"], q=[float("nan")])
  core.real.ingest_joint_state(msg)
  core.step_n(core.decimation * 10)
  nan_traj = core.d.qpos.copy()

  assert all(math.isfinite(x) for x in nan_traj), "qpos went non-finite from a NaN telemetry sample"
  assert np.allclose(nan_traj, no_data_traj, atol=1e-9), "NaN telemetry diverged from no-data-at-all"
  assert core.replay_clamped_now["L_hip_pitch_joint"] is False


# ------------------------------------------------------------------- (b) AB crank hard clip
def test_ab_crank_out_of_hard_range_stays_inside_soft_clip_and_loop_stays_closed(core):
  _quiesce(core)
  core.set_base(mode="fixed")
  core.submit({"op": "mode", "value": "manual"})
  core.step_n(core.decimation)
  core.step_n(200)  # settle the post-reset loop-closure transient before commanding
  assert core.closure_mm() < 0.1, f"loop already open before the test: {core.closure_mm()} mm"

  (pl, ph), (rl, rh) = core.ankle_inverse.bounds()
  a, b = core.ankle_inverse("L", 0.5 * (pl + ph), 0.5 * (rl + rh))
  iA = core.act_names.index("L_crank_A_joint")
  iB = core.act_names.index("L_crank_B_joint")
  hi_a, hi_b = float(core.range_hi[iA]), float(core.range_hi[iB])
  # scale the mechanically-valid pair up until at least one member is past its hard range -
  # preserves the pair's ratio (unlike picking two independent extreme values, which the
  # mechanism can jam on - see test_record.py's own crank test docstring) while still
  # exercising the hard-range clamp path.
  scale = 1.0
  for candidate in (2.0, 3.0, 5.0, 10.0):
    if abs(a * candidate) > hi_a or abs(b * candidate) > hi_b:
      scale = candidate
      break
  a_out, b_out = a * scale, b * scale
  assert abs(a_out) > hi_a or abs(b_out) > hi_b

  core.submit({"op": "mode", "value": "real_replay"})
  core.step_n(core.decimation)
  msg = JointState(
    t_ns=1, seq=1, src="dummy",
    joint_names=["L_crank_A_joint", "L_crank_B_joint"], q=[a_out, b_out],
  )
  core.real.ingest_joint_state(msg)
  core.step_n(core.decimation)  # one control tick is enough to route the target

  clip_a = core.c.clip("L_crank_A_joint")
  clip_b = core.c.clip("L_crank_B_joint")
  assert clip_a[0] - 1e-9 <= core.target[iA] <= clip_a[1] + 1e-9
  assert clip_b[0] - 1e-9 <= core.target[iB] <= clip_b[1] + 1e-9
  assert core.replay_clamp_count["L_crank_A_joint"] > 0 or core.replay_clamp_count["L_crank_B_joint"] > 0

  core.step_n(core.decimation * 20)  # let the PD actually chase the (clamped) target
  assert math.isfinite(core.closure_mm())
  assert core.closure_mm() < 1.0, f"loop opened to {core.closure_mm()} mm under a clamped target"


# --------------------------------------------------------------------- (c)/(d) API honesty
def test_post_target_out_of_range_reports_requested_ne_applied(core, http):
  _quiesce(core)
  lo, hi = core.c.clip("L_knee_joint")
  requested = hi + 3.0
  r = http.post("/target", json={"values": {"L_knee_joint": requested}})
  assert r.status_code == 200, r.text
  body = r.json()
  assert body["requested"]["L_knee_joint"] == pytest.approx(requested)
  assert body["applied"]["L_knee_joint"] == pytest.approx(hi, abs=1e-9)
  assert body["applied"]["L_knee_joint"] != body["requested"]["L_knee_joint"]
  assert body["clip_range"]["L_knee_joint"] == pytest.approx([lo, hi])


def test_post_target_in_range_reports_requested_eq_applied(core, http):
  _quiesce(core)
  lo, hi = core.c.clip("L_knee_joint")
  mid = 0.5 * (lo + hi)
  r = http.post("/target", json={"values": {"L_knee_joint": mid}})
  assert r.status_code == 200, r.text
  body = r.json()
  assert body["applied"]["L_knee_joint"] == pytest.approx(body["requested"]["L_knee_joint"])


def _post_raw_json(http, path, obj):
  """httpx's own ``json=`` kwarg calls ``json.dumps(..., allow_nan=False)`` and raises a
  local ``ValueError`` before a request is even built - so a NaN/inf test has to build the
  wire bytes itself (CPython's ``json.dumps`` default IS ``allow_nan=True``, emitting the
  literal ``NaN``/``Infinity`` tokens; a real misbehaving client could send exactly this)."""
  body = jsonlib.dumps(obj).encode("utf-8")
  return http.post(path, content=body, headers={"content-type": "application/json"})


def test_post_target_nan_is_rejected_not_silently_clipped(core, http):
  r = _post_raw_json(http, "/target", {"values": {"L_knee_joint": float("nan")}})
  assert r.status_code == 422, r.text


def test_post_target_inf_is_rejected(core, http):
  r = _post_raw_json(http, "/target", {"values": {"L_knee_joint": float("inf")}})
  assert r.status_code == 422, r.text
