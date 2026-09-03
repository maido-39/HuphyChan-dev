"""ONNX must be the same function as the .pt it was exported from, and it must refuse to
drive a model it was not trained on.

The parity set is 32 random observations run through the loaded .pt at bake time.  The bar
is 1e-4; the export is float32, so anything materially larger means the export path changed
something (a normalizer left out, a different head, the wrong policy loaded).
"""

import glob
import json

import numpy as np
import pytest

from pygviewer import CACHE_DIR
from pygviewer.contract import load_contract
from pygviewer.policy import OnnxPolicy, PolicyContractMismatch, action_to_target, check_compatible

POLICIES = sorted(glob.glob(f"{CACHE_DIR}/*.policy_contract.json"))
pytestmark = pytest.mark.skipif(not POLICIES, reason="no policy baked yet")


@pytest.fixture(scope="module", params=POLICIES, ids=lambda p: p.split("/")[-1][:40])
def baked(request):
  pc = json.loads(open(request.param).read())
  return pc, load_contract(CACHE_DIR, pc["variant"]), np.load(pc["parity_npz"])


def test_onnx_matches_the_torch_policy(baked):
  pc, _, par = baked
  pol = OnnxPolicy(pc["onnx"], pc)
  worst = max(
    float(np.abs(pol(par["obs"][i]) - par["action"][i]).max())
    for i in range(par["obs"].shape[0])
  )
  assert worst < 1e-4, f"ONNX and .pt differ by {worst:.3e} on the parity set"


def test_onnx_io_shape_matches_the_contract(baked):
  pc, mc, _ = baked
  pol = OnnxPolicy(pc["onnx"], pc)
  assert pol.obs_dim == pc["obs_dim"]
  assert pol.action_dim == pc["action_dim"] == len(mc.raw["action_joint_names"])


def test_compatible_policy_is_accepted(baked):
  pc, mc, _ = baked
  check_compatible(pc, mc)


def test_wrong_model_is_refused(baked):
  pc, mc, _ = baked
  bad = dict(pc, model_contract_sha="0" * 64)
  with pytest.raises(PolicyContractMismatch):
    check_compatible(bad, mc)


def test_shifted_default_pose_is_refused(baked):
  """The default pose IS the action offset, so a mismatch biases every joint target."""
  pc, mc, _ = baked
  j = mc.raw["action_joint_names"][0]
  bad = dict(pc, default_q=dict(pc["default_q"], **{j: pc["default_q"][j] + 0.01}))
  with pytest.raises(PolicyContractMismatch):
    check_compatible(bad, mc)


def test_action_to_target_is_the_trainer_expression(baked):
  pc, mc, _ = baked
  names = mc.raw["action_joint_names"]
  default = np.array([mc.default_q(n) for n in names])
  scale = np.array([mc.raw["action_scale"][n] for n in names])
  lo = np.array([mc.clip(n)[0] for n in names])
  hi = np.array([mc.clip(n)[1] for n in names])
  a = np.zeros(len(names))
  _, t = action_to_target(a, default, scale, lo, hi, pc["clip_actions"])
  assert np.allclose(t, np.clip(default, lo, hi)), "action 0 must mean the default pose"
  a = np.full(len(names), 1e6)
  raw, t = action_to_target(a, default, scale, lo, hi, pc["clip_actions"])
  if pc["clip_actions"] is not None:
    assert np.allclose(raw, pc["clip_actions"])
  assert np.all(t <= hi + 1e-9) and np.all(t >= lo - 1e-9), "target left the safe clip"
