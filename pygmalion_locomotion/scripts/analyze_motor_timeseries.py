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
    "hip_pitch": (120.0, 40.0, 200.0), "hip_roll": (120.0, 40.0, 200.0), "hip_yaw": (60.0, 20.0, 200.0),
    "knee": (360.0, 120.0, 66.7), "ankle_pitch": (60.0, 20.0, 200.0), "ankle_roll": (14.0, 5.0, 315.0),
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

    def bars(getter, peak_idx, unit, ttl, sat_ttl, fname, rated_idx=None):
        # peak_idx = HARD limit index (torque peak / speed limit). rated_idx = CONTINUOUS (thermal) rating
        # (torque rated; None for speed). ★ SIZING PAIR (De2011 etc): RMS torque vs RATED (thermal — motor
        # heating ~ I^2R ~ tau^2, so RMS = the thermally-equivalent constant torque, NOT the arithmetic
        # mean which UNDER-states heat) + MAX vs peak (transient). Speed has no thermal rating -> max vs
        # limit (back-EMF/mechanical hard cap) is the binding check; RMS shown only as a "typical" stat.
        fig, ax = plt.subplots(1, 2, figsize=(16, 6))
        cont_idx = rated_idx if rated_idx is not None else peak_idx
        rms = [float(np.sqrt(np.mean(getter(j) ** 2))) for j in act]
        p95 = [float(np.percentile(getter(j), 95)) for j in act]   # sustained near-peak, robust to single spikes
        mx = [float(getter(j).max()) for j in act]
        ax[0].bar(x - 0.27, rms, 0.26, label="RMS", color="#9bbbd6")
        ax[0].bar(x, p95, 0.26, label="p95", color="#5a9bd4")
        ax[0].bar(x + 0.27, mx, 0.26, label="max", color="#2980b9")
        for i, j in enumerate(act):
            sp = spec_for(j)
            ax[0].plot([i - 0.45, i + 0.45], [sp[peak_idx], sp[peak_idx]], color="#c0392b", lw=1.6, ls="--")
            if rated_idx is not None:
                ax[0].plot([i - 0.45, i + 0.45], [sp[rated_idx], sp[rated_idx]], color="#e67e22", lw=1.4)
        ax[0].plot([], [], color="#c0392b", lw=1.6, ls="--", label="peak/limit")
        if rated_idx is not None:
            ax[0].plot([], [], color="#e67e22", lw=1.4, label="rated (continuous)")
        ax[0].set_xticks(x); ax[0].set_xticklabels(lbl, rotation=60, ha="right", fontsize=7)
        ax[0].set_ylabel(unit); ax[0].set_title(ttl); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3, axis="y")
        # saturation: MAX vs peak/limit (transient) + RMS vs rated/limit (continuous/thermal)
        sat_mx = [100 * mx[i] / spec_for(act[i])[peak_idx] for i in range(len(act))]
        sat_p95 = [100 * p95[i] / spec_for(act[i])[peak_idx] for i in range(len(act))]
        sat_rms = [100 * rms[i] / spec_for(act[i])[cont_idx] for i in range(len(act))]
        rms_lbl = "RMS %rated (cont/thermal)" if rated_idx is not None else "RMS %limit"
        ax[1].bar(x - 0.27, sat_mx, 0.26, color=[zone(s) for s in sat_mx], label="max %peak (transient)")
        ax[1].bar(x, sat_p95, 0.26, color=[zone(s) for s in sat_p95], label="p95 %peak")
        ax[1].bar(x + 0.27, sat_rms, 0.26, color=[zone(s) for s in sat_rms], label=rms_lbl)
        ax[1].axhline(100, color="#c0392b", ls="--", lw=1); ax[1].axhline(80, color="#f09010", ls=":", lw=1)
        for i in range(len(act)):
            ax[1].text(i - 0.27, sat_mx[i] + 1, f"{sat_mx[i]:.0f}", ha="center", fontsize=4.5)
            ax[1].text(i + 0.27, sat_rms[i] + 1, f"{sat_rms[i]:.0f}", ha="center", fontsize=4.5)
        ax[1].set_xticks(x); ax[1].set_xticklabels(lbl, rotation=60, ha="right", fontsize=7)
        ax[1].set_ylabel("% of limit"); ax[1].set_title(sat_ttl)
        ax[1].legend(fontsize=8); ax[1].grid(alpha=.3, axis="y")
        fig.suptitle(f"{ttl.split('(')[0].strip()} — {title}", fontsize=13); fig.tight_layout(rect=[0, 0, 1, .96])
        p = os.path.join(args.out, fname); fig.savefig(p, dpi=95); plt.close(fig)
        return p, sat_mx, sat_p95, sat_rms

    satS_mx = satS_p95 = satS_rms = None
    out["torque"], satT_mx, satT_p95, satT_rms = bars(tau, 0, "torque [N*m]", "Joint torque  RMS/p95/max vs spec (rated/peak)",
                                "Torque sat:  max %peak + p95 %peak + RMS %rated (continuous/thermal)",
                                f"{args.tag}_torque.png", rated_idx=1)
    if have_w:
        out["speed"], satS_mx, satS_p95, satS_rms = bars(rpm, 2, "speed [rpm]", "Joint speed  RMS/p95/max vs spec (limit)",
                                   "Speed sat:  max %limit (binding) + p95/RMS %limit", f"{args.tag}_speed.png")

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
    top = lambda pairs: ", ".join(f"{n} {s:.0f}%" for n, s in sorted(pairs, key=lambda kv: -kv[1])[:3])
    print("  토크 max%peak(과도) top:", top(zip(lbl, satT_mx)))
    print("  토크 p95%peak(지속근접) top:", top(zip(lbl, satT_p95)))
    print("  토크 RMS%rated(연속/열) top:", top(zip(lbl, satT_rms)))
    if have_w:
        print("  속도 max%limit(binding) top:", top(zip(lbl, satS_mx)))
    for k, v in out.items():
        print(f"  {k}: {os.path.basename(v)}")


if __name__ == "__main__":
    main()
