# -*- coding: utf-8 -*-
"""Offline analysis of a measurement run (no Isaac Sim needed).

Reads logs/measure/<tag>.npz, computes per-joint torque peak/RMS, per-link axial-force
(|Fx,Fy,Fz|) peak/RMS, and foot GRF peak; compares joint torque against the RobStride motor
ratings; writes figures (PNG) + a markdown summary that can be embedded in docs/.

    python scripts/analyze.py --npz logs/measure/rough_m1.0.npz --out docs/assets

Pure numpy + matplotlib -> runs in any env with those installed.
"""

from __future__ import annotations

import argparse
import json
import os
import re

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# motor peak / rated torque [N*m] by joint substring (output-shaft)
MOTOR_RATING = {
    "hip_pitch": (120.0, 40.0),
    "hip_roll": (120.0, 40.0),
    "hip_yaw": (60.0, 20.0),
    "knee": (360.0, 120.0),
    "ankle_pitch": (60.0, 20.0),
    "ankle_roll": (14.0, 5.0),
    "toe": (0.0, 0.0),
}


def rating_for(joint: str):
    for k, v in MOTOR_RATING.items():
        if k in joint:
            return v
    return (None, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", required=True)
    ap.add_argument("--out", default="docs/assets")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    tag = args.tag or os.path.splitext(os.path.basename(args.npz))[0]

    data = np.load(args.npz)
    cols = list(data.keys())
    t = data["time"] if "time" in cols else np.arange(len(data[cols[0]]))

    tau_cols = sorted(c for c in cols if c.startswith("tau_"))
    joints = [c[len("tau_"):] for c in tau_cols]
    grf_cols = sorted(c for c in cols if c.startswith("GRF_") and c.endswith("_mag"))

    # link axial force magnitude per body from Fx/Fy/Fz_<body>
    bodies = sorted({re.sub(r"^F[xyz]_", "", c) for c in cols if re.match(r"^F[xyz]_", c)})

    # ---- stats ----
    summary_rows = []
    for c, j in zip(tau_cols, joints):
        v = data[c]
        peak = float(np.max(np.abs(v)))
        rms = float(np.sqrt(np.mean(v ** 2)))
        pk_r, rt_r = rating_for(j)
        util = (peak / pk_r * 100.0) if pk_r else float("nan")
        summary_rows.append((j, peak, rms, pk_r, rt_r, util))

    link_rows = []
    for b in bodies:
        fx, fy, fz = data.get(f"Fx_{b}"), data.get(f"Fy_{b}"), data.get(f"Fz_{b}")
        if fx is None:
            continue
        mag = np.sqrt(fx ** 2 + fy ** 2 + fz ** 2)
        link_rows.append((b, float(np.max(mag)), float(np.sqrt(np.mean(mag ** 2))),
                          float(np.max(np.abs(fx))), float(np.max(np.abs(fy))), float(np.max(np.abs(fz)))))

    # ---- figure 1: joint torque time series ----
    fig, ax = plt.subplots(figsize=(11, 5))
    for c, j in zip(tau_cols, joints):
        ax.plot(t, data[c], lw=0.8, label=j)
    ax.set_xlabel("time [s]"); ax.set_ylabel("joint torque [N·m]")
    ax.set_title(f"Joint torque — {tag}")
    ax.legend(ncol=4, fontsize=7); ax.grid(alpha=0.3)
    f1 = os.path.join(args.out, f"{tag}_joint_torque.png")
    fig.tight_layout(); fig.savefig(f1, dpi=120); plt.close(fig)

    # ---- figure 2: peak torque vs motor rating ----
    fig, ax = plt.subplots(figsize=(11, 5))
    x = np.arange(len(joints))
    peaks = [r[1] for r in summary_rows]
    pk_ratings = [r[3] if r[3] else 0.0 for r in summary_rows]
    ax.bar(x - 0.2, peaks, 0.4, label="measured peak |τ|")
    ax.bar(x + 0.2, pk_ratings, 0.4, label="motor peak rating", alpha=0.6)
    ax.set_xticks(x); ax.set_xticklabels(joints, rotation=90, fontsize=7)
    ax.set_ylabel("torque [N·m]"); ax.set_title(f"Peak joint torque vs motor rating — {tag}")
    ax.legend(); ax.grid(alpha=0.3, axis="y")
    f2 = os.path.join(args.out, f"{tag}_torque_vs_rating.png")
    fig.tight_layout(); fig.savefig(f2, dpi=120); plt.close(fig)

    # ---- figure 3: link axial force peak ----
    if link_rows:
        fig, ax = plt.subplots(figsize=(11, 5))
        lb = [r[0] for r in link_rows]
        lx = np.arange(len(lb))
        ax.bar(lx, [r[1] for r in link_rows])
        ax.set_xticks(lx); ax.set_xticklabels(lb, rotation=90, fontsize=7)
        ax.set_ylabel("peak |F| [N]"); ax.set_title(f"Peak link reaction (axial) force — {tag}")
        ax.grid(alpha=0.3, axis="y")
        f3 = os.path.join(args.out, f"{tag}_link_force.png")
        fig.tight_layout(); fig.savefig(f3, dpi=120); plt.close(fig)
    else:
        f3 = None

    # ---- figure 4: foot GRF ----
    if grf_cols:
        fig, ax = plt.subplots(figsize=(11, 4))
        for c in grf_cols:
            ax.plot(t, data[c], lw=0.8, label=c.replace("GRF_", "").replace("_mag", ""))
        ax.set_xlabel("time [s]"); ax.set_ylabel("foot GRF |F| [N]")
        ax.set_title(f"Foot ground reaction force — {tag}")
        ax.legend(fontsize=8); ax.grid(alpha=0.3)
        f4 = os.path.join(args.out, f"{tag}_foot_grf.png")
        fig.tight_layout(); fig.savefig(f4, dpi=120); plt.close(fig)
    else:
        f4 = None

    # ---- markdown summary ----
    md = [f"# Measurement analysis — `{tag}`\n",
          f"- steps: {len(t)}, duration: {float(t[-1]) - float(t[0]):.2f} s\n",
          "\n## Joint torque vs motor rating\n",
          "| joint | peak |τ| [N·m] | RMS [N·m] | motor peak | motor rated | peak util % |",
          "|---|---|---|---|---|---|---|"]
    for j, peak, rms, pk_r, rt_r, util in summary_rows:
        md.append(f"| {j} | {peak:.1f} | {rms:.1f} | {pk_r} | {rt_r} | "
                  f"{util:.0f} |" if pk_r else f"| {j} | {peak:.1f} | {rms:.1f} | - | - | - |")
    md += ["\n## Link reaction (axial) force\n",
           "| link | peak |F| [N] | RMS [N] | peak|Fx| | peak|Fy| | peak|Fz| |",
           "|---|---|---|---|---|---|---|"]
    for b, pk, rms, fx, fy, fz in link_rows:
        md.append(f"| {b} | {pk:.0f} | {rms:.0f} | {fx:.0f} | {fy:.0f} | {fz:.0f} |")
    md += ["\n## Figures",
           f"![joint torque](./{os.path.basename(f1)})",
           f"![torque vs rating](./{os.path.basename(f2)})"]
    if f3:
        md.append(f"![link force](./{os.path.basename(f3)})")
    if f4:
        md.append(f"![foot grf](./{os.path.basename(f4)})")
    md_path = os.path.join(args.out, f"{tag}_analysis.md")
    with open(md_path, "w") as f:
        f.write("\n".join(md) + "\n")

    print(f"[analyze] figures + summary -> {args.out}")
    print(f"[analyze] markdown: {md_path}")
    # also dump machine-readable stats
    stats = {
        "tag": tag,
        "joint_torque": {j: {"peak": pk, "rms": rms, "motor_peak": pr, "util_pct": ut}
                         for j, pk, rms, pr, _, ut in summary_rows},
        "link_force": {b: {"peak": pk, "rms": rms} for b, pk, rms, *_ in link_rows},
    }
    with open(os.path.join(args.out, f"{tag}_stats.json"), "w") as f:
        json.dump(stats, f, indent=2)


if __name__ == "__main__":
    main()
