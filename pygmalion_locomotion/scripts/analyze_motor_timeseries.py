# -*- coding: utf-8 -*-
"""VISUAL motor analysis — make the loads readable, not text-only.

For the measured robot (env-0 time-series in the measurement npz: tau_<joint>, omega_<joint>) produces:
  <tag>_torque.png     : per-joint avg+max |tau| bars WITH rated(nominal)+peak spec lines | %peak saturation
  <tag>_speed.png      : per-joint avg+max |omega|(rpm) bars WITH speed-limit line       | %limit saturation
  <tag>_torque_ts.png  : per joint-type grid — L/R |tau| OVER TIME + rated/peak lines (how torque is used)
  <tag>_speed_ts.png   : per joint-type grid — L/R rpm OVER TIME + speed-limit line       (how speed is used)
These are meant to be EMBEDDED in the run's analysis note. Usage:
  python scripts/analyze_motor_timeseries.py --npz <clip.npz> --tag <tag> --title "..." --out ../docs/assets
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RAD2RPM = 60.0 / (2.0 * np.pi)
# joint substring -> (PEAK N*m, RATED/nominal N*m, speed-limit rpm)  [robstride_biped.yaml]
SPEC = {
    "hip_pitch": (120.0, 40.0, 200.0), "hip_roll": (120.0, 40.0, 200.0), "hip_yaw": (60.0, 20.0, 220.0),
    "knee": (360.0, 120.0, 66.7), "ankle_pitch": (60.0, 20.0, 220.0), "ankle_roll": (14.0, 5.0, 315.0),
}
TYPES = ["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll", "toe"]


def spec_for(j):
    for k, v in SPEC.items():
        if k in j:
            return v
    return None  # toe = passive -> no motor spec


def jtype(j):
    for t in TYPES:
        if t in j:
            return t
    return j


def zone(pct):
    return "#40c040" if pct < 33.3 else "#d0c000" if pct < 80 else "#f09010" if pct < 100 else "#e03030"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", required=True)
    ap.add_argument("--tag", default="motor")
    ap.add_argument("--title", default=None)
    ap.add_argument("--out", default="../docs/assets")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    title = args.title or args.tag
    d = np.load(args.npz, allow_pickle=True)
    files = set(d.files)
    joints = sorted([k[4:] for k in files if k.startswith("tau_")],
                    key=lambda n: (TYPES.index(jtype(n)) if jtype(n) in TYPES else 99, 0 if n.startswith("L_") else 1, n))
    act = [j for j in joints if spec_for(j) is not None]                      # 12 actuated (have a motor)
    t = d["time"] if "time" in files else np.arange(len(d["tau_" + joints[0]]))
    have_w = all("omega_" + j in files for j in act)
    out = {}

    def tau(j):
        return np.abs(d["tau_" + j])

    def rpm(j):
        return np.abs(d["omega_" + j]) * RAD2RPM

    lbl = [j.replace("_joint", "") for j in act]
    x = np.arange(len(act))

    def bars(getter, spec_idx, unit, ttl, sat_ttl, fname, rated_idx=None):
        fig, ax = plt.subplots(1, 2, figsize=(16, 6))
        avg = [getter(j).mean() for j in act]
        mx = [getter(j).max() for j in act]
        ax[0].bar(x - 0.2, avg, 0.4, label="avg", color="#9bbbd6")
        ax[0].bar(x + 0.2, mx, 0.4, label="max", color="#2980b9")
        for i, j in enumerate(act):
            sp = spec_for(j)
            ax[0].plot([i - 0.45, i + 0.45], [sp[spec_idx], sp[spec_idx]], color="#c0392b", lw=1.6, ls="--")
            if rated_idx is not None:
                ax[0].plot([i - 0.45, i + 0.45], [sp[rated_idx], sp[rated_idx]], color="#e67e22", lw=1.4)
        ax[0].plot([], [], color="#c0392b", lw=1.6, ls="--", label="peak/limit")
        if rated_idx is not None:
            ax[0].plot([], [], color="#e67e22", lw=1.4, label="rated (nominal)")
        ax[0].set_xticks(x); ax[0].set_xticklabels(lbl, rotation=60, ha="right", fontsize=7)
        ax[0].set_ylabel(unit); ax[0].set_title(ttl); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3, axis="y")
        sat_mx = [100 * getter(j).max() / spec_for(j)[spec_idx] for j in act]
        sat_av = [100 * getter(j).mean() / spec_for(j)[spec_idx] for j in act]
        ax[1].bar(x, sat_mx, color=[zone(s) for s in sat_mx], label="max %")
        ax[1].scatter(x, sat_av, color="k", marker="_", s=220, zorder=5, label="avg %")
        ax[1].axhline(100, color="#c0392b", ls="--", lw=1); ax[1].axhline(80, color="#f09010", ls=":", lw=1)
        for i, s in enumerate(sat_mx):
            ax[1].text(i, s + 1, f"{s:.0f}", ha="center", fontsize=6)
        ax[1].set_xticks(x); ax[1].set_xticklabels(lbl, rotation=60, ha="right", fontsize=7)
        ax[1].set_ylabel("% of " + ("peak" if rated_idx is not None else "limit")); ax[1].set_title(sat_ttl)
        ax[1].legend(fontsize=8); ax[1].grid(alpha=.3, axis="y")
        fig.suptitle(f"{ttl.split('(')[0].strip()} — {title}", fontsize=13); fig.tight_layout(rect=[0, 0, 1, .96])
        p = os.path.join(args.out, fname); fig.savefig(p, dpi=95); plt.close(fig)
        return p, sat_mx

    out["torque"], sat_t = bars(tau, 0, "torque [N*m]", "Joint torque  avg/max vs spec (rated/peak)",
                                "Torque saturation  (% of peak; 100%=limit)", f"{args.tag}_torque.png", rated_idx=1)
    if have_w:
        out["speed"], sat_s = bars(rpm, 2, "speed [rpm]", "Joint speed  avg/max vs spec (speed limit)",
                                   "Speed saturation  (% of limit)", f"{args.tag}_speed.png")

    # time-series grids
    present = [ty for ty in TYPES if any(jtype(j) == ty for j in joints)]

    def grid(getter, spec_idx, unit, sup, fname, rated_idx=None):
        cols = 4; rows = (len(present) + cols - 1) // cols
        fig, axs = plt.subplots(rows, cols, figsize=(4.3 * cols, 2.9 * rows), squeeze=False)
        for idx, ty in enumerate(present):
            a = axs[idx // cols][idx % cols]
            for side, c in [("L", "#2980b9"), ("R", "#e67e22")]:
                j = f"{side}_{ty}_joint"
                if "tau_" + j in files:
                    a.plot(t, getter(j), color=c, lw=.6, label=side)
            sp = spec_for(f"L_{ty}_joint")
            if sp is not None:
                a.axhline(sp[spec_idx], color="#c0392b", ls="--", lw=1)
                if rated_idx is not None:
                    a.axhline(sp[rated_idx], color="#e67e22", ls=":", lw=1)
            a.set_title(ty + ("" if sp else " (passive)"), fontsize=9); a.grid(alpha=.3); a.legend(fontsize=6)
        for idx in range(len(present), rows * cols):
            axs[idx // cols][idx % cols].axis("off")
        fig.suptitle(sup, fontsize=13); fig.supxlabel("time [s]"); fig.supylabel(unit)
        fig.tight_layout(rect=[0, 0, 1, .97])
        p = os.path.join(args.out, fname); fig.savefig(p, dpi=90); plt.close(fig)
        return p

    out["torque_ts"] = grid(tau, 0, "|tau| [N*m]", f"Joint torque time-series  (peak=red--, rated=orange:) — {title}",
                            f"{args.tag}_torque_ts.png", rated_idx=1)
    if have_w:
        out["speed_ts"] = grid(rpm, 2, "speed [rpm]", f"Joint speed time-series  (limit=red--) — {title}",
                               f"{args.tag}_speed_ts.png")

    print(f"[motorviz] {title}: wrote {len(out)} PNGs -> {args.out}")
    worst_t = sorted(zip(lbl, sat_t), key=lambda kv: -kv[1])[:3]
    print("  토크 포화 top:", ", ".join(f"{n} {s:.0f}%" for n, s in worst_t))
    if have_w:
        worst_s = sorted(zip(lbl, sat_s), key=lambda kv: -kv[1])[:3]
        print("  속도 포화 top:", ", ".join(f"{n} {s:.0f}%" for n, s in worst_s))
    for k, v in out.items():
        print(f"  {k}: {os.path.basename(v)}")


if __name__ == "__main__":
    main()
