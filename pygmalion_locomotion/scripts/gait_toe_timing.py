# -*- coding: utf-8 -*-
"""Toe-timing check: WHEN in the gait cycle does the passive toe actually bend? (user question)

The human-reference reward tracks only the 3 sagittal ACTUATED joints (hip_pitch/knee/ankle_pitch); the toe is
PASSIVE (spring) so it is NOT tracked -- it is meant to bend emergently when the foot rolls onto the forefoot at
push-off (windlass). This verifies that: detect cycles from foot GRF (phase 0 = contact onset), resample the toe
qpos AND the foot GRF over the cycle, and report the phase at which the toe is MOST deflected. For a correct
windlass that phase should be LATE STANCE / push-off (~45-62% of the cycle, just before the foot leaves the ground).
    python scripts/gait_toe_timing.py <tag> [<tag2> ...]
"""
from __future__ import annotations
import os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import gait_humanlikeness as GH  # reuse detect_cycles / resample_cycles / BW

NPH = 100


def analyze_toe(tag):
    f = os.path.join(ROOT, "logs", "measure", f"{tag}.npz")
    if not os.path.exists(f):
        print(f"[{tag}] npz 없음"); return None
    d = np.load(f, allow_pickle=True)
    grfL, grfR = np.abs(d["GRF_L_foot_link_z"]), np.abs(d["GRF_R_foot_link_z"])
    out = {"tag": tag, "ph": np.linspace(0, 1, NPH), "legs": {}}
    for leg, grf in (("L", grfL), ("R", grfR)):
        starts = GH.detect_cycles(grf, fz_thresh=0.1 * GH.BW)
        if len(starts) < 3:
            continue
        toe = d[f"qpos_{leg}_toe_joint"]
        toe_c = GH.resample_cycles(toe, starts)            # [ncyc, NPH]
        grf_c = GH.resample_cycles(grf, starts)
        if toe_c.shape[0] == 0:
            continue
        toe_m = toe_c.mean(0)
        grf_m = grf_c.mean(0)
        defl = toe_m - toe_m[0]                             # deflection from cycle start
        # toe bends to NEGATIVE (range [0,-0.87]); most-deflected = min
        peak_i = int(np.argmin(toe_m))
        peak_phase = peak_i  # already 0-100 since NPH=100
        peak_defl = float(toe_m.min() - toe_m.max())        # signed range (negative)
        # stance fraction: where GRF > 10% BW
        stance = grf_m > 0.1 * GH.BW
        stance_end = int(np.where(stance)[0].max()) if stance.any() else 0
        out["legs"][leg] = dict(toe=toe_m, grf=grf_m, peak_phase=peak_phase, peak_defl=peak_defl,
                                stance_end=stance_end, rng=float(toe_m.max() - toe_m.min()))
    return out


def report_and_plot(analyses):
    analyses = [a for a in analyses if a and a["legs"]]
    if not analyses:
        print("결과 없음"); return
    for a in analyses:
        print(f"\n=== {a['tag']} ===")
        for leg, r in a["legs"].items():
            verdict = ("✅ push-off대" if 42 <= r["peak_phase"] <= 65 else
                       "⚠ 시기 어긋남" if r["rng"] > 0.05 else "✗ 거의 안 굽음")
            print(f"  {leg} toe: 최대굽힘 위상 {r['peak_phase']}% | 굽힘량 {r['rng']:.3f} rad "
                  f"| stance끝 ~{r['stance_end']}% | {verdict}")
    n = len(analyses)
    fig, ax = plt.subplots(n, 1, figsize=(10, 3.0 * n), dpi=130, squeeze=False)
    for i, a in enumerate(analyses):
        axx = ax[i][0]
        for leg, r in a["legs"].items():
            c = "tab:blue" if leg == "L" else "tab:red"
            axx.plot(a["ph"] * 100, r["toe"], color=c, lw=1.8, label=f"{leg} toe angle [rad]")
            axx.axvline(r["peak_phase"], color=c, ls=":", lw=1.0)
            # GRF on twin axis (normalized) to show stance/swing
        ax2 = axx.twinx()
        for leg, r in a["legs"].items():
            c = "tab:cyan" if leg == "L" else "tab:orange"
            ax2.plot(a["ph"] * 100, r["grf"] / GH.BW, color=c, ls="--", lw=0.9, alpha=0.6, label=f"{leg} GRF [xBW]")
        axx.axvspan(45, 62, color="green", alpha=0.08)  # human push-off window
        axx.set_title(f"{a['tag']} — toe angle (solid) + GRF (dashed); green = human push-off ~45-62%", fontsize=10)
        axx.set_xlabel("gait cycle [%]"); axx.set_ylabel("toe angle [rad]")
        ax2.set_ylabel("GRF [xBW]")
        axx.grid(alpha=0.3); axx.legend(fontsize=7, loc="upper left")
    fig.tight_layout()
    out = "/tmp/gait_toe_timing.png"
    fig.savefig(out)
    print(f"\n[toe_timing] saved {out}")


if __name__ == "__main__":
    tags = sys.argv[1:] or ["g1is_v2_flat"]
    report_and_plot([analyze_toe(t) for t in tags])
