"""Regression for a user-reported bug (2026-09-04): "L/R 각각 값을 넣으면 관절 양쪽이 같이
움직이는 버그가 있었다."

Reproduced by hand against the live viewer process first (curl, docs/121 section 9 has the
full transcript) before writing this as a pytest.  ``POST /target`` -> ``SimCore.set_target``
only ever writes ``self.target[i]`` for the named joint's own index - there is no shared
mutable state between joints in that path.  Two REAL, non-buggy effects can still look like
"the other leg moved too", and this file exists to tell them apart from an actual routing
defect and keep it that way:

  (a) ``base=fixed`` with ``ground=on`` at the bent-keyframe spawn height embeds both feet
      ~38.6 mm in the floor (docs/121 P0/P1 pitfall 4, ``keyframe_sole_penetration_m``).  Each
      leg's own floor-contact reaction perturbs ITS OWN tracking continuously and
      independently - two unrelated, simultaneously-drifting legs are easy to misread as one
      leg "following" the other.
  (b) any base mode OTHER than ``fixed`` (``free``/``pivot``/``string``) genuinely couples the
      two legs' ACTUAL q (never their ``target``) through the floating/suspended base's own
      reaction dynamics - real multi-body physics (Newton's third law through the shared
      trunk), not a bug.  Verified present in ``string`` mode and precisely absent in
      ``fixed`` mode by hand (a 0.3 rad ``R_hip_roll`` step measurably rocked
      ``L_hip_roll``/``L_hip_yaw`` under ``string``; the same step under ``fixed`` moved every
      other joint's q by < 1e-6 rad).

So the isolation claim this file makes is specifically for ``base=fixed`` + ``ground=off``
(no floor contact, no floating-base coupling) - the condition that actually isolates one
joint, and the condition the Joints tab's per-joint slider is meant to be used in.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from pygviewer import CACHE_DIR
from pygviewer.api import build_app
from pygviewer.contract import load_contract
from pygviewer.sim_core import SimCore

VARIANT = "LegOnly-AB"
SETTLE_S = 1.5


def _settle(core: SimCore, seconds: float = SETTLE_S) -> None:
  core.step_n(max(1, int(seconds / core.dt)))


def _isolated_reset(core: SimCore) -> None:
  """base=fixed, ground=off: no floor contact, no floating-base coupling - see module
  docstring (a)/(b)."""
  core.set_base(mode="fixed", ground=False)
  core.reset("knees_bent")
  _settle(core, 2.0)


@pytest.fixture
def rig():
  core = SimCore(load_contract(CACHE_DIR, VARIANT), realtime=False)
  _isolated_reset(core)
  app = build_app(core, core.c.freshness())
  try:
    yield TestClient(app), core
  finally:
    core.stop()


def test_each_joint_target_is_independent(rig):
  """Commanding any ONE of the 12 actuated joints through the real HTTP route must never
  change any OTHER joint's target (bit-exact, always - this is pure data routing) or the
  OPPOSITE LEG's actual q (beyond ordinary settling noise) - that second check is exactly
  the reported symptom, "L/R move together".

  Two joints on the SAME leg are deliberately NOT held to the q check: crank_A/crank_B share
  one closed loop (moving one mechanically moves the other's actual angle - that is the
  mechanism, not a bug) and hip/knee are serially connected by real inertia (a fast hip step
  measurably rocks the knee's tracking for a moment). Both were confirmed as expected same-leg
  physics while chasing this bug (docs/121 section 9, 2026-09-04) - conflating them with the
  cross-leg symptom would either mask the real bug behind noisy same-leg thresholds or turn
  ordinary mechanism/inertial coupling into false failures.
  """
  client, core = rig
  names = list(core.act_names)
  for probe in names:
    _isolated_reset(core)
    probe_side = probe.split("_")[0]
    base_targets = [float(x) for x in core.target]
    base_q = {n: float(core.d.qpos[core.a_q[i]]) for i, n in enumerate(names)}

    lo, hi = core.c.clip(probe)
    d0 = core.c.default_q(probe)
    step = min(0.1, 0.3 * (hi - lo))  # a moderate slider nudge, not a full-range jump
    new_val = float(np.clip(d0 + step, lo, hi))
    r = client.post("/target", json={"values": {probe: new_val}})
    assert r.status_code == 200, r.text
    _settle(core)

    for i, n in enumerate(names):
      if n == probe:
        continue
      dt = abs(core.target[i] - base_targets[i])
      assert dt < 1e-6, f"commanding {probe} changed {n}'s target by {dt:.3e} rad"
      if n.split("_")[0] != probe_side:  # opposite leg: the reported bug's actual symptom
        dq = abs(float(core.d.qpos[core.a_q[i]]) - base_q[n])
        assert dq < 0.01, f"commanding {probe} moved OPPOSITE-LEG {n}'s q by {dq:.5f} rad"


def test_ankle_foot_space_command_is_per_side(rig):
  """AB only: POST /ankle side=L must never move a R crank (or vice versa)."""
  client, core = rig
  if core.ankle_inverse is None:
    pytest.skip(f"{VARIANT} drives the ankle directly; no /ankle route")
  for side, other in (("L", "R"), ("R", "L")):
    _isolated_reset(core)
    other_names = [n for n in core.act_names if n.startswith(f"{other}_crank")]
    before = {n: float(core.d.qpos[core.a_q[core.act_names.index(n)]]) for n in other_names}
    before_target = {n: float(core.target[core.act_names.index(n)]) for n in other_names}

    r = client.post("/ankle", json={"side": side, "pitch": 0.2, "roll": 0.1})
    assert r.status_code == 200, r.text
    _settle(core)

    for n in other_names:
      i = core.act_names.index(n)
      dt = abs(core.target[i] - before_target[n])
      assert dt < 1e-6, f"{side} ankle command changed {other} crank {n}'s target by {dt:.3e} rad"
      dq = abs(float(core.d.qpos[core.a_q[i]]) - before[n])
      assert dq < 0.01, f"{side} ankle command moved {other} crank {n} by {dq:.5f} rad"
