# -*- coding: utf-8 -*-
"""Gait-cycle-resampled 6-DoF joint loads (user 2026-06-22). Within the steady FORWARD-walking part
of the measure sweep, detect L-foot heel-strikes -> segment strides -> resample each to phase 0-100%
-> per-phase MEAN curve + shaded p5-p95 band, per joint. 6 colored lines (Fx/Fy/Fz left axis, Mx/My/Mz
right axis). ENGLISH labels only. NOTE: nominal rollout (DR off in the PLAY env), NOT DR-worst.

    python3 scripts/wrench_gaitcycle.py
"""
import os, glob
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEAS = os.path.join(ROOT, "logs", "measure")
ASSET = os.path.join(ROOT, "..", "docs", "assets", "wrench")
os.makedirs(ASSET, exist_ok=True)

L2J = {"hip_pitch_link": "hip_pitch", "hip_roll_link": "hip_roll", "thigh_link": "hip_yaw",
       "shin_link": "knee", "ankle_pitch_link": "ankle_pitch", "foot_link": "ankle_roll", "toe_link": "toe"}
ORDER = list(L2J.values())
RECENT = ["gaitfix_v3", "gaitfix_v4", "gaitfix_v5", "gaitfix_v6", "gaitfix_v7",
          "g1vanilla", "g1van_flat", "g1van_full", "g1_rigidtoe2"]
NP = 100  # phase points


def jlabel(link):
    for s in ("L_", "R_"):
        if link.startswith(s) and link[2:] in L2J:
            return f"{s[0]}_{L2J[link[2:]]}"
    return link


def heel_strikes(grf, thr=150.0, debounce=10):
    """rising crossings of thr (contact onset)."""
    above = grf > thr
    hs = np.where((~above[:-1]) & (above[1:]))[0] + 1
    out = []
    for i in hs:
        if not out or i - out[-1] >= debounce:
            out.append(int(i))
    return out


def main():
    for f in sorted(glob.glob(os.path.join(MEAS, "*.npz"))):
        exp = os.path.basename(f)[:-4]
        if exp not in RECENT:
            continue
        d = np.load(f, allow_pickle=True)
        if "GRF_L_foot_link_z" not in d.files:
            print(f"[gc] {exp}: no GRF, skip"); continue
        vx = d["cmd_vx"] if "cmd_vx" in d.files else np.ones(len(d["GRF_L_foot_link_z"]))
        vy = d["cmd_vy"] if "cmd_vy" in d.files else np.zeros_like(vx)
        wz = d["cmd_wz"] if "cmd_wz" in d.files else np.zeros_like(vx)
        fwd = (vx > 0.3) & (np.abs(vy) < 0.15) & (np.abs(wz) < 0.2)   # steady forward mask
        cycles, bside = [], "L"   # auto-pick the foot with more clean contacts (asymmetric gaits favor one leg)
        for side in ("L", "R"):
            hs = heel_strikes(np.where(fwd, np.abs(d[f"GRF_{side}_foot_link_z"]).astype(float), 0.0))
            cyc = [(hs[i], hs[i + 1]) for i in range(len(hs) - 1) if 6 < hs[i + 1] - hs[i] < 120]
            if len(cyc) > len(cycles):
                cycles, bside = cyc, side
        if len(cycles) < 3:
            print(f"[gc] {exp}: <3 clean cycles (asymmetric/irregular gait), skip plot"); continue

        links = sorted({k.split("_", 1)[1] for k in d.files if k.split("_", 1)[0] in ("Fx", "Fy", "Fz", "Tx", "Ty", "Tz")})
        joints = [(jlabel(lk), lk) for lk in links if lk != "base_link" and any(o in jlabel(lk) for o in ORDER)]
        joints.sort(key=lambda j: (j[0][0], next((i for i, o in enumerate(ORDER) if o in j[0]), 9)))
        ph = np.linspace(0, 100, NP)

        n = len(joints); cols = 4; rows = (n + cols - 1) // cols
        fig, axes = plt.subplots(rows, cols, figsize=(4.3 * cols, 2.8 * rows), squeeze=False)
        for ax in axes.flat:
            ax.axis("off")
        FC = {"Fx": "#1f77b4", "Fy": "#2ca02c", "Fz": "#d62728"}
        MC = {"Tx": "#9467bd", "Ty": "#8c564b", "Tz": "#e377c2"}
        for idx, (jl, lk) in enumerate(joints):
            ax = axes[idx // cols][idx % cols]; ax.axis("on"); ax2 = ax.twinx()
            for comp, cc, axx in [(FC, "F", ax), (MC, "M", ax2)]:
                for c, col in comp.items():
                    key = f"{c}_{lk}"
                    if key not in d.files:
                        continue
                    sig = np.asarray(d[key]).astype(float)
                    stk = np.stack([np.interp(np.linspace(0, 1, NP), np.linspace(0, 1, b - a), sig[a:b]) for a, b in cycles])
                    mu = stk.mean(0); lo = np.percentile(stk, 5, 0); hi = np.percentile(stk, 95, 0)
                    lab = c if c[0] == "F" else c.replace("T", "M")
                    axx.plot(ph, mu, col, lw=1.3, label=lab)
                    axx.fill_between(ph, lo, hi, color=col, alpha=0.13)
            ax.set_title(f"{jl}  (n={len(cycles)} cyc)", fontsize=9)
            ax.set_ylabel("force [N]", fontsize=7); ax2.set_ylabel("moment [N.m]", fontsize=7)
            ax.set_xlabel("gait cycle [%]", fontsize=7); ax.tick_params(labelsize=6); ax2.tick_params(labelsize=6)
            ax.axhline(0, color="#bbb", lw=0.5)
            if idx == 0:
                ax.legend(loc="upper left", fontsize=6, ncol=3); ax2.legend(loc="upper right", fontsize=6, ncol=3)
        fig.suptitle(f"{exp} — per-joint 6-DoF over gait cycle ({bside}-foot stride, n={len(cycles)} cyc, mean + p5-p95 band; forward; NOMINAL not DR-worst)", fontsize=10.5)
        fig.tight_layout(rect=[0, 0, 1, 0.97])
        out = os.path.join(ASSET, f"{exp}_gaitcycle.png")
        fig.savefig(out, dpi=85); plt.close(fig)
        print(f"[gc] {exp}: {len(cycles)} cycles -> {out}")


if __name__ == "__main__":
    main()
