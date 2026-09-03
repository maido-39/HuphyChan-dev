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

import json
from pathlib import Path

MODES = ("idle", "manual", "policy_sim", "policy_shadow", "real_replay", "file_replay")
IMPLEMENTED = MODES

# A shadow-mode action must never leave this process. This is a constant, not a setting,
# so that turning it on requires a code change and a review.
SHADOW_MAY_TRANSMIT = False


class ModeMachine:  # every mode is `SimCore.mode`, see the module docstring - kept only so an
  def __init__(self, *_a, **_k):  # import of this name fails loudly rather than silently.
    raise NotImplementedError(
      "there is no separate ModeMachine object - every mode is SimCore.mode, dispatched in "
      "SimCore._apply_cmd / _on_control_tick / _substep. See this module's docstring."
    )


class TargetScript:
  """Same-target-sequence player: ``{"joint_names": [...], "rows": [[t_s, q...], ...],
  "loop": bool}`` linearly interpolated by elapsed sim time since ``start()``.

  Used by ``SimCore`` in ``manual`` mode (``POST /script/run``); the same file, played
  through the robot's own bridge (not this process - the viewer never transmits), produces a
  comparable recording that ``compare.py`` overlays against the sim run tagged with the same
  ``run_id`` (design doc item 2, verification protocol steps 5/6).
  """

  def __init__(self, path: str | Path):
    self.path = Path(path)
    d = json.loads(self.path.read_text())
    self.joint_names: list[str] = list(d["joint_names"])
    self.rows: list[list[float]] = [list(r) for r in d["rows"]]
    if not self.rows:
      raise ValueError(f"{self.path}: no rows")
    if any(len(r) != 1 + len(self.joint_names) for r in self.rows):
      raise ValueError(f"{self.path}: every row must be [t_s, q...] with one q per joint_name")
    self.rows.sort(key=lambda r: r[0])
    self.loop = bool(d.get("loop", False))
    self.t0 = float(self.rows[0][0])
    self.duration_s = max(float(self.rows[-1][0]) - self.t0, 0.0)
    self._t_ref: float | None = None

  def start(self, sim_time_s: float) -> None:
    self._t_ref = sim_time_s

  def stop(self) -> None:
    self._t_ref = None

  @property
  def active(self) -> bool:
    return self._t_ref is not None

  def at(self, sim_time_s: float) -> dict[str, float] | None:
    """Interpolated joint targets at the current sim time, or ``None`` before ``start()``."""
    if self._t_ref is None:
      return None
    elapsed = sim_time_s - self._t_ref
    tm = self.t0 + ((elapsed % self.duration_s) if (self.loop and self.duration_s > 0) else min(elapsed, self.duration_s))
    if tm <= self.rows[0][0]:
      return dict(zip(self.joint_names, self.rows[0][1:]))
    if tm >= self.rows[-1][0]:
      return dict(zip(self.joint_names, self.rows[-1][1:]))
    lo, hi = 0, len(self.rows) - 1
    while lo + 1 < hi:
      mid = (lo + hi) // 2
      if self.rows[mid][0] <= tm:
        lo = mid
      else:
        hi = mid
    t0, t1 = self.rows[lo][0], self.rows[hi][0]
    frac = 0.0 if t1 <= t0 else (tm - t0) / (t1 - t0)
    q0, q1 = self.rows[lo][1:], self.rows[hi][1:]
    return dict(zip(self.joint_names, (a + frac * (b - a) for a, b in zip(q0, q1))))

  def is_finished(self, sim_time_s: float) -> bool:
    if self.loop or self._t_ref is None:
      return False
    return (sim_time_s - self._t_ref) >= self.duration_s

  def progress(self, sim_time_s: float) -> dict:
    if self._t_ref is None:
      return dict(active=False)
    elapsed = sim_time_s - self._t_ref
    frac = 1.0 if self.duration_s <= 0 else min(elapsed / self.duration_s, 1.0)
    return dict(
      active=True, path=str(self.path), elapsed_s=round(elapsed, 3),
      duration_s=round(self.duration_s, 3), frac=round(frac, 3), loop=self.loop,
    )
