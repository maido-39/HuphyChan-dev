"""P2-P4 SKELETON - the run-mode state machine and the target-script player.

P0/P1 use only two of these and they live in ``SimCore.mode`` as a label; the machine below
is what P2+ grows into.

    idle ---> manual ---> policy_sim ---> policy_shadow
                 |                            |
                 +--> real_replay        (obs per-term sim|real; NEVER transmits)
                 +--> file_replay

``manual``       UI/API joint targets (implemented in P1 by SimCore.set_target).
``policy_sim``   the loaded policy drives, all observations from the simulator.       P2
``policy_shadow``observations per-term from sim or from the received real stream, with a
                 staleness guard; the action is displayed and plotted ONLY.           P4
``real_replay``  received q drives the sim joints kinematically, base fixed.  For AB the
                 cranks are PD-followed, never qpos-snapped, or the loop tears.        P3
``file_replay``  the same, from a recorded jsonl.gz.                                   P3

``TargetScript``: {"joint_names": [...], "rows": [[t_s, q...], ...]} played in ``manual`` and
tagged with a run_id so ``compare.py`` can overlay the sim run against the robot run driven
by the same file.                                                                      P4
"""

from __future__ import annotations

MODES = ("idle", "manual", "policy_sim", "policy_shadow", "real_replay", "file_replay")
IMPLEMENTED = ("idle", "manual")

# A shadow-mode action must never leave this process. This is a constant, not a setting,
# so that turning it on requires a code change and a review.
SHADOW_MAY_TRANSMIT = False


class ModeMachine:  # TODO(P2)
  def __init__(self, *_a, **_k):
    raise NotImplementedError("ModeMachine is P2 - see docs/121 section 6")


class TargetScript:  # TODO(P4)
  def __init__(self, *_a, **_k):
    raise NotImplementedError("TargetScript is P4 - see docs/121 section 6")
