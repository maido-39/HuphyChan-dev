"""P2 SKELETON - policy inference (ONNX + .pt), obs builder, obs source mux.

Nothing here runs yet.  The shape is fixed now so that P2 is an implementation job, not a
design job, and so that the failure modes we already know about are written down where the
implementer will read them.

Planned contents (docs/121 section 6, phase P2):

  * ``OnnxPolicy``  - onnxruntime CPU session; input name ``obs``, output = action.
  * ``TorchPolicy`` - lazy mjlab import (RslRlVecEnvWrapper + runner.load); costs ~25 s and
    ~1.3 GB, so the UI must warn before loading one.
  * ``ObsBuilder``  - builds the actor observation IN THE CONTRACT'S ORDER:
        [base_ang_vel(3), projected_gravity(3), q_rel(n_obs), qd(n_obs), last_action(n_act),
         cmd(3)]
    with ``q_rel = q[obs_joint_names] - default_q[obs_joint_names]``.  The order comes from
    ``contract.obs_joint_names``, which bake resolved from the env's own observation term -
    never from a regex over joint names.
  * ``ObsSourceMux`` - per observation TERM, sim or real, with a staleness guard (P4).
  * ``action_to_target(a) = default_q + action_scale * a`` then ``safe_target_clip``.

Hard rules for the implementer:
  * REFUSE to load a policy whose ``policy_contract.model_contract_sha`` does not equal the
    loaded model contract's sha.  Loading a v4 policy onto a v2 model already happened once.
  * ONNX and .pt must agree to |dq| < 1e-4 on the 32 saved observations in ``parity.npz``
    before the policy is allowed to drive anything.
  * The shadow mode must never transmit an action to hardware; that is hard-coded in
    ``modes.py``, not a setting.
"""

from __future__ import annotations


class PolicyNotImplemented(NotImplementedError):
  pass


class OnnxPolicy:  # TODO(P2)
  def __init__(self, *_a, **_k):
    raise PolicyNotImplemented("OnnxPolicy is P2 - see docs/121 section 6")


class TorchPolicy:  # TODO(P2)
  def __init__(self, *_a, **_k):
    raise PolicyNotImplemented("TorchPolicy is P2 - see docs/121 section 6")


class ObsBuilder:  # TODO(P2)
  def __init__(self, *_a, **_k):
    raise PolicyNotImplemented("ObsBuilder is P2 - see docs/121 section 6")


class ObsSourceMux:  # TODO(P4)
  def __init__(self, *_a, **_k):
    raise PolicyNotImplemented("ObsSourceMux is P4 - see docs/121 section 6")
