# -*- coding: utf-8 -*-
"""Human normative gait-cycle joint-angle reference, retargeted to our biped's ACTUATED joints.

Purpose: a per-phase reference trajectory for a DeepMimic-style phase-tracking reward (rsl_rl has no AMP, and
IsaacLab's AMP is skrl+direct = incompatible with our manager-based rsl_rl pipeline -> phase tracking is the
feasible path). The reward compares the policy's joint angles to ref_joint_pos(phase) and rewards the match, giving
a DENSE strong human-gait signal (the weak foot_flat/swing_height penalties plateaued -> couldn't beat tiptoe).

Reference curves = normative sagittal gait (Winter, "Biomechanics and Motor Control of Human Movement"; Perry,
"Gait Analysis") as keyframes over the % gait cycle (0 = heel strike, ~60% = toe-off). DRAFT numbers (typical
normative ranges) — to validate/refine against workflow w9d8ys8av (data finder).

Retargeting signs are FK-VERIFIED (docs/51_joint_sign_conventions.md):
  forward=+x; hip_pitch NEG=flexion; knee NEG=flexion; ankle_pitch POS=dorsiflexion / NEG=plantarflexion(toe-off).
  q_hip_pitch  = -deg2rad(hip_flexion)
  q_knee       = -deg2rad(knee_flexion)
  q_ankle_pitch= +deg2rad(ankle_dorsiflexion)
Frontal/transverse (hip_roll, hip_yaw, ankle_roll) kept ~0 (sagittal-dominant). Toe passive -> not in the target.

Right leg is the left leg phase-shifted by 0.5 (contralateral). Actuated joint order (BFS, toe excluded):
  [L_hip_pitch, R_hip_pitch, L_hip_roll, R_hip_roll, L_hip_yaw, R_hip_yaw,
   L_knee, R_knee, L_ankle_pitch, R_ankle_pitch, L_ankle_roll, R_ankle_roll]
    python -m pygmalion_locomotion.tasks.locomotion.gait_reference   # plots the retargeted reference for validation
"""
from __future__ import annotations
import numpy as np

# --- normative sagittal keyframes: (phase01, degrees). + = flexion (hip/knee), + = dorsiflexion (ankle). ---
# phase 0 = heel strike (initial contact), ~0.60 = toe-off.
_HIP_FLEX_KF = np.array([
    [0.00, 28], [0.10, 22], [0.20, 13], [0.30, 5], [0.40, -3], [0.50, -10],
    [0.55, -8], [0.60, 0], [0.70, 15], [0.80, 27], [0.90, 30], [1.00, 28],
])
_KNEE_FLEX_KF = np.array([
    [0.00, 5], [0.15, 18], [0.30, 10], [0.40, 4], [0.50, 10], [0.60, 38],
    [0.70, 58], [0.75, 62], [0.85, 35], [0.95, 8], [1.00, 5],
])
_ANKLE_DORSI_KF = np.array([
    [0.00, -2], [0.08, -5], [0.15, 0], [0.30, 5], [0.45, 10], [0.50, 8],
    [0.55, 0], [0.60, -15], [0.62, -18], [0.70, -8], [0.80, -2], [0.90, 0], [1.00, -2],
])
# MTP / toe (reference only; toe is PASSIVE, not tracked): dorsiflexes to ~+45deg at push-off (windlass).
_TOE_MTP_KF = np.array([
    [0.00, 18], [0.20, 12], [0.45, 20], [0.60, 45], [0.65, 40], [0.75, 5], [1.00, 18],
])

DEG = np.pi / 180.0


def _interp_deg(kf: np.ndarray, phase01):
    """Periodic linear interpolation of a keyframe table at phase in [0,1)."""
    p = np.mod(np.asarray(phase01, dtype=float), 1.0)
    return np.interp(p, kf[:, 0], kf[:, 1], period=1.0)


def sagittal_deg(phase01):
    """(hip_flexion, knee_flexion, ankle_dorsiflexion) in degrees at phase01."""
    return (_interp_deg(_HIP_FLEX_KF, phase01),
            _interp_deg(_KNEE_FLEX_KF, phase01),
            _interp_deg(_ANKLE_DORSI_KF, phase01))


def leg_targets_rad(phase01):
    """Retargeted (hip_pitch, hip_roll, hip_yaw, knee, ankle_pitch, ankle_roll) in rad for ONE leg at phase01."""
    hip_f, knee_f, ank_d = sagittal_deg(phase01)
    return np.array([
        -hip_f * DEG,   # hip_pitch: q = -human_flexion
        0.0,            # hip_roll  (frontal, ~0)
        0.0,            # hip_yaw   (transverse, ~0)
        -knee_f * DEG,  # knee: q = -human_flexion
        +ank_d * DEG,   # ankle_pitch: q = +human_dorsiflexion
        0.0,            # ankle_roll (frontal, ~0)
    ])


# index order within one leg
_LEG = ["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll"]
# full actuated order (BFS, L/R interleaved per joint type)
ACTUATED_ORDER = [f"{s}_{j}" for j in _LEG for s in ("L", "R")]


def ref_joint_pos(phase01, rl_offset: float = 0.5):
    """Full 12-vector of actuated joint targets [rad] in BFS order at gait phase01.
    Left leg at phase01, right leg at phase01 + rl_offset (contralateral). Accepts scalar or array (-> shape [...,12])."""
    phase01 = np.asarray(phase01, dtype=float)
    L = leg_targets_rad(phase01)                 # [...,6]
    R = leg_targets_rad(phase01 + rl_offset)     # [...,6]
    # interleave L/R per joint type -> [L_hip_pitch,R_hip_pitch, L_hip_roll,R_hip_roll, ...]
    out = np.stack([L, R], axis=-1).reshape(*np.shape(phase01), 12) if np.ndim(phase01) else \
          np.stack([L, R], axis=-1).reshape(12)
    return out


if __name__ == "__main__":
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ph = np.linspace(0, 1, 101)
    hip_f, knee_f, ank_d = sagittal_deg(ph)
    toe = _interp_deg(_TOE_MTP_KF, ph)
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.5), dpi=130)
    # (a) human normative (degrees)
    ax[0].plot(ph * 100, hip_f, label="hip flexion(+)")
    ax[0].plot(ph * 100, knee_f, label="knee flexion(+)")
    ax[0].plot(ph * 100, ank_d, label="ankle dorsiflex(+)")
    ax[0].plot(ph * 100, toe, "--", label="MTP/toe (passive, ref only)")
    ax[0].axvline(60, color="gray", ls=":", label="toe-off ~60%")
    ax[0].set_title("Human normative sagittal gait (Winter/Perry, draft)")
    ax[0].set_xlabel("gait cycle [%]"); ax[0].set_ylabel("angle [deg]"); ax[0].legend(fontsize=8); ax[0].grid(alpha=0.3)
    # (b) retargeted robot joint targets (rad), L leg
    tg = np.array([leg_targets_rad(p) for p in ph])
    for i, nm in enumerate(_LEG):
        if nm in ("hip_roll", "hip_yaw", "ankle_roll"):
            continue
        ax[1].plot(ph * 100, tg[:, i], label=f"q_{nm}")
    ax[1].axvline(60, color="gray", ls=":")
    ax[1].set_title("Retargeted robot reference (L leg, FK-verified signs)")
    ax[1].set_xlabel("gait cycle [%]"); ax[1].set_ylabel("joint target [rad]"); ax[1].legend(fontsize=8); ax[1].grid(alpha=0.3)
    fig.tight_layout()
    out = "/tmp/gait_reference_preview.png"
    fig.savefig(out)
    print(f"[gait_reference] saved {out}")
    print(f"[gait_reference] ref_joint_pos(0.0) = {np.round(ref_joint_pos(0.0), 3)}")
    print(f"[gait_reference] ref_joint_pos(0.3) = {np.round(ref_joint_pos(0.3), 3)}")
