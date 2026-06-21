# -*- coding: utf-8 -*-
"""Motor SPEED + torque-speed envelope analysis (complements analyze_motor_util's torque-only view).

A motor has BOTH a torque limit AND a speed limit, joined by its torque-SPEED curve (it cannot deliver
peak torque at high speed). Using the logged joint velocity (omega) this reports, per joint:
  * peak / RMS |omega| -> % of the joint-side velocity limit (the 'max speed' check)
  * peak mechanical power |tau*omega| [W]
  * a torque-SPEED scatter of every operating point vs the (peak-torque x max-speed) box envelope
    -> points hugging the top-right corner are where a real torque-speed curve would cut them off.

Joint-side limits (after gear; spec robstride_biped.yaml velocity_limit_rpm): hip pitch/roll 200,
hip_yaw 220, knee (RS04 1:3 belt) 66.7, ankle_pitch 220, ankle_roll 315 rpm. Peak torque from the
motor table (analyze_motor_util).

Usage: python scripts/analyze_motor_speed.py --npz logs/measure/<tag>.npz --tag <name> --title "..." --out ../docs/assets
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RAD2RPM = 60.0 / (2.0 * np.pi)
# joint substring -> (peak_torque N*m, joint-side velocity limit rpm)
MOTOR = {
    "hip_pitch": (120.0, 200.0), "hip_roll": (120.0, 200.0), "hip_yaw": (60.0, 200.0),
    "knee": (360.0, 66.7), "ankle_pitch": (60.0, 200.0), "ankle_roll": (14.0, 315.0),
}
ORDER = ["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll"]


def motor_for(j):
    for k, v in MOTOR.items():
        if k in j:
            return k, v
    return None, (None, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", required=True)
    ap.add_argument("--tag", default="motor_speed")
    ap.add_argument("--title", default=None)
    ap.add_argument("--out", default="../docs/assets")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    title = args.title or args.tag
    d = np.load(args.npz)
    joints = [c[len("omega_"):] for c in d.keys() if c.startswith("omega_") and motor_for(c[len("omega_"):])[0]]
    joints = sorted(joints, key=lambda j: (ORDER.index(motor_for(j)[0]), 0 if j.startswith("L") else 1))

    rows = []
    for j in joints:
        omega = d[f"omega_{j}"]
        tau = d[f"tau_{j}"]
        _, (pk, vlim) = motor_for(j)
        rpm = np.abs(omega) * RAD2RPM
        power = np.abs(tau * omega)
        rows.append({"joint": j, "peak_rpm": float(rpm.max()), "rms_rpm": float(np.sqrt(np.mean(rpm**2))),
                     "vlim_rpm": vlim, "pct_speed": float(100 * rpm.max() / vlim),
                     "peak_tau": float(np.abs(tau).max()), "peak_torque": pk,
                     "peak_W": float(power.max()), "rms_W": float(np.sqrt(np.mean(power**2)))})

    # --- torque-speed scatter grid (one per motor family, L+R overlaid) ---
    fams = ORDER
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for ax, fam in zip(axes.flat, fams):
        pk, vlim = MOTOR[fam]
        for j in [jj for jj in joints if fam in jj]:
            ax.scatter(np.abs(d[f"omega_{j}"]) * RAD2RPM, np.abs(d[f"tau_{j}"]), s=2, alpha=0.3,
                       label=("L" if j.startswith("L") else "R"))
        ax.add_patch(plt.Rectangle((0, 0), vlim, pk, fill=False, ls="--", ec="#c0392b", lw=1.5))
        ax.set_xlim(0, vlim * 1.15); ax.set_ylim(0, pk * 1.15)
        ax.set_title(f"{fam}  (box={vlim:.0f}rpm x {pk:.0f}N*m)", fontsize=9)
        ax.set_xlabel("|speed| [rpm]", fontsize=8); ax.set_ylabel("|tau| [N*m]", fontsize=8)
        ax.legend(fontsize=6, markerscale=3); ax.grid(alpha=.3)
    fig.suptitle(f"Torque-speed operating points vs envelope — {title}", fontsize=12)
    fig.tight_layout(); png = os.path.join(args.out, f"{args.tag}_torque_speed.png")
    fig.savefig(png, dpi=95); plt.close(fig)

    md = [f"# Motor speed + torque-speed — {title}", "",
          "| joint | peak rpm | RMS rpm | limit rpm | **% speed** | peak \\|tau\\| | peak W | RMS W |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['joint']} | {r['peak_rpm']:.0f} | {r['rms_rpm']:.0f} | {r['vlim_rpm']:.0f} | "
                  f"{r['pct_speed']:.0f}% | {r['peak_tau']:.0f}/{r['peak_torque']:.0f} | {r['peak_W']:.0f} | {r['rms_W']:.0f} |")
    open(os.path.join(args.out, f"{args.tag}_motor_speed.md"), "w").write("\n".join(md) + "\n")
    json.dump({"title": title, "rows": rows}, open(os.path.join(args.out, f"{args.tag}_motor_speed.json"), "w"), indent=2)
    print(f"[motor_speed] wrote {png} + .md + .json")
    print("\n".join(md))


if __name__ == "__main__":
    main()
