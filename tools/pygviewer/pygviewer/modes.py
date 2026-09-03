"""Run-mode reference + the P4 target-script player skeleton.

There is no separate ``ModeMachine`` object: every mode below lives as the plain string
``SimCore.mode``, dispatched in ``SimCore._apply_cmd``/``_on_control_tick``/``_substep`` -
the same pattern P2 used for ``policy_sim`` before P3 added the two replay modes the same
way. This module is the reference table plus the one thing that genuinely has nothing to
attach to yet: the P4 script player.

    idle ---> manual ---> policy_sim ---> policy_shadow
                 |                            |
                 +--> real_replay        (obs per-term sim|real; NEVER transmits)
                 +--> file_replay

``manual``       UI/API joint targets (P1, ``SimCore.set_target``).
``policy_sim``   the loaded policy drives, all observations from the simulator.       P2
``policy_shadow``observations per-term from sim or from the received real stream, with a
                 staleness guard (``policy.ObsBuilder.build_shadow``); the action is
                 displayed/plotted/recorded ONLY unless ``--shadow-follow`` is set, in which
                 case it also steps the LOCAL sim - never a real robot.               P4
``real_replay``  received q drives the sim joints kinematically, base FORCED fixed on
                 entry.  Direct-drive joints (everything but an AB crank) are snapped
                 exactly, per control tick, when data was received that tick - with no
                 data they get an ordinary PD hold (never torque-free).  Cranks are always
                 PD-tracked, never qpos-snapped, or the closed loop tears (QACC NaN,
                 documented in ``sim_core.py`` and ``tools/viewer/mjcf_joint_viewer.py``).
                 ``SimCore._update_replay_targets``/``_apply_replay_drive``.          P3
``file_replay``  the same drive split, sourced from a loaded ``record.Replayer`` instead
                 of ``core.real``.                                                     P3

``TargetScript``: {"joint_names": [...], "rows": [[t_s, q...], ...]} played in ``manual`` and
tagged with a run_id so ``compare.py`` can overlay the sim run against the robot run driven
by the same file.                                                                      P4
"""

from __future__ import annotations

MODES = ("idle", "manual", "policy_sim", "policy_shadow", "real_replay", "file_replay")
IMPLEMENTED = MODES

# A shadow-mode action must never leave this process. This is a constant, not a setting,
# so that turning it on requires a code change and a review.
SHADOW_MAY_TRANSMIT = False


class ModeMachine:  # TODO(P2)
  def __init__(self, *_a, **_k):
    raise NotImplementedError("ModeMachine is P2 - see docs/121 section 6")


class TargetScript:  # TODO(P4)
  def __init__(self, *_a, **_k):
    raise NotImplementedError("TargetScript is P4 - see docs/121 section 6")
