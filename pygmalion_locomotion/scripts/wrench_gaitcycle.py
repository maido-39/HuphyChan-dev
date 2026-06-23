# -*- coding: utf-8 -*-
"""Gait-cycle-resampled 6-DoF joint loads (user 2026-06-22, rev2). Layout: rows = joint type (proximal->distal),
cols = [L | R] adjacent with SHARED y per row (direct L/R comparison). Forces = COOL/solid (left axis),
Moments = WARM/dashed (right axis) -> clear force/moment separation. DPI 140 (no garbled text). Phased variant
adds stance(green)/swing(blue) shading + toe-off & opposite-contact lines. NOMINAL (DR off), not DR-worst.

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

# joint type -> child link base (thigh=hip_yaw, shin=knee, foot=ankle_roll)
J2L = {"hip_pitch": "hip_pitch_link", "hip_roll": "hip_roll_link", "hip_yaw": "thigh_link",
       "knee": "shin_link", "ankle_pitch": "ankle_pitch_link", "ankle_roll": "foot_link", "toe": "toe_link"}
ORDER = list(J2L.keys())
FCOL = {"Fx": "#1f77b4", "Fy": "#17becf", "Fz": "#08306b"}   # COOL family = forces  (blue/cyan/navy)
MCOL = {"Tx": "#d62728", "Ty": "#ff7f0e", "Tz": "#7b3294"}   # WARM family = moments (red/orange/purple)
RECENT = ["gaitfix_v3", "gaitfix_v4", "gaitfix_v5", "gaitfix_v6", "gaitfix_v7",
          "g1vanilla", "g1van_flat", "g1van_full", "g1_rigidtoe2"]
NP = 100


def heel_strikes(grf, thr=150.0, debounce=10):
    above = grf > thr
    hs = np.where((~above[:-1]) & (above[1:]))[0] + 1
    out = []
    for i in hs:
        if not out or i - out[-1] >= debounce:
            out.append(int(i))
    return out


def resample(sig, cycles):
    return np.stack([np.interp(np.linspace(0, 1, NP), np.linspace(0, 1, b - a), np.asarray(sig)[a:b].astype(float))
                     for a, b in cycles])


def draw(exp, d, cycles, ph, out, phased, info):
    jtypes = [jt for jt in ORDER if any(f"Fz_{s}_{J2L[jt]}" in d.files for s in "LR")]
    rows = len(jtypes)
    fig, axes = plt.subplots(rows, 2, figsize=(10, 2.05 * rows), squeeze=False)
    for r, jt in enumerate(jtypes):
        cell = {}
        for side in "LR":
            lk = f"{side}_{J2L[jt]}"; comps = {}
            for c in list(FCOL) + list(MCOL):
                k = f"{c}_{lk}"
                if k in d.files:
                    stk = resample(d[k], cycles)
                    comps[c] = (stk.mean(0), np.percentile(stk, 5, 0), np.percentile(stk, 95, 0))
            cell[side] = comps
        fmax = max([np.abs(np.r_[v[1], v[2]]).max() for s in cell for c, v in cell[s].items() if c[0] == "F"] + [1.0])
        mmax = max([np.abs(np.r_[v[1], v[2]]).max() for s in cell for c, v in cell[s].items() if c[0] == "T"] + [1.0])
        for cidx, side in enumerate("LR"):
            ax = axes[r][cidx]; ax2 = ax.twinx()
            if phased:
                ax.axvspan(0, info["toeoff"], color="#2ca02c", alpha=0.06, zorder=0)
                ax.axvspan(info["toeoff"], 100, color="#1f77b4", alpha=0.06, zorder=0)
                ax.axvline(info["toeoff"], color="#555", lw=0.9, ls=":", zorder=1)
                ax.axvline(info["opp_ic"], color="#999", lw=0.7, ls=":", zorder=1)
            for c, (mu, lo, hi) in cell[side].items():
                axx = ax if c[0] == "F" else ax2
                col = FCOL.get(c) or MCOL.get(c)
                axx.plot(ph, mu, col, lw=1.5, ls=("-" if c[0] == "F" else "--"),
                         label=(c if c[0] == "F" else c.replace("T", "M")))
                axx.fill_between(ph, lo, hi, color=col, alpha=0.10)
            ax.set_ylim(-fmax * 1.12, fmax * 1.12); ax2.set_ylim(-mmax * 1.12, mmax * 1.12)
            ax.axhline(0, color="#ccc", lw=0.4)
            ax.set_title(f"{side}_{jt}", fontsize=11)
            ax.tick_params(labelsize=7.5); ax2.tick_params(labelsize=7.5)
            if r == rows - 1:
                ax.set_xlabel("gait cycle [%]", fontsize=9)
            ax.set_ylabel("force [N]", fontsize=8.5, color="#08306b")
            ax2.set_ylabel("moment [N.m]", fontsize=8.5, color="#d62728")
            if r == 0 and cidx == 0:
                ax.legend(loc="upper left", fontsize=7.5, ncol=3, title="forces (cool, solid)", title_fontsize=7)
            if r == 0 and cidx == 1:
                ax2.legend(loc="upper right", fontsize=7.5, ncol=3, title="moments (warm, dashed)", title_fontsize=7)
    ttl = f"{exp} — 6-DoF over gait cycle ({info['bside']}-stride, n={info['n']}; rows=joint L|R, shared y; mean + p5-p95 band)"
    if phased:
        ttl = (f"{exp} — 6-DoF gait cycle WITH PHASES ({info['bside']}-stride n={info['n']}): "
               f"green=stance, blue=swing, dotted=toe-off {info['toeoff']:.0f}% & opp-contact {info['opp_ic']:.0f}%, "
               f"DS {info['ds']:.0f}%")
    fig.suptitle(ttl + "  (NOMINAL not DR-worst)", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.99])
    fig.savefig(out, dpi=140); plt.close(fig)


def main():
    for f in sorted(glob.glob(os.path.join(MEAS, "*.npz"))):
        exp = os.path.basename(f)[:-4]
        if exp not in RECENT:
            continue
        d = np.load(f, allow_pickle=True)
        if "GRF_L_foot_link_z" not in d.files:
            continue
        vx = d.get("cmd_vx", None) if hasattr(d, "get") else None
        vx = d["cmd_vx"] if "cmd_vx" in d.files else np.ones(len(d["GRF_L_foot_link_z"]))
        vy = d["cmd_vy"] if "cmd_vy" in d.files else np.zeros_like(vx)
        wz = d["cmd_wz"] if "cmd_wz" in d.files else np.zeros_like(vx)
        fwd = (vx > 0.3) & (np.abs(vy) < 0.15) & (np.abs(wz) < 0.2)
        cycles, bside = [], "L"
        for side in ("L", "R"):
            hs = heel_strikes(np.where(fwd, np.abs(d[f"GRF_{side}_foot_link_z"]).astype(float), 0.0))
            cyc = [(hs[i], hs[i + 1]) for i in range(len(hs) - 1) if 6 < hs[i + 1] - hs[i] < 120]
            if len(cyc) > len(cycles):
                cycles, bside = cyc, side
        if len(cycles) < 3:
            print(f"[gc] {exp}: <3 cycles, skip"); continue
        ph = np.linspace(0, 100, NP)
        refg = resample(np.abs(d[f"GRF_{bside}_foot_link_z"]), cycles).mean(0)
        opp = "R" if bside == "L" else "L"
        oppg = resample(np.abs(d[f"GRF_{opp}_foot_link_z"]), cycles).mean(0)
        ron = refg > 0.15 * max(refg.max(), 1.0); oon = oppg > 0.15 * max(oppg.max(), 1.0)
        info = {"bside": bside, "n": len(cycles),
                "toeoff": float(ph[np.where(ron)[0][-1]]) if ron.any() else 60.0,
                "opp_ic": float(ph[np.where(oon)[0][0]]) if oon.any() else 50.0,
                "ds": float((ron & oon).mean() * 100)}
        draw(exp, d, cycles, ph, os.path.join(ASSET, f"{exp}_gaitcycle.png"), False, info)
        draw(exp, d, cycles, ph, os.path.join(ASSET, f"{exp}_gaitcycle_phased.png"), True, info)
        print(f"[gc] {exp}: {len(cycles)} cyc ({bside}), toe-off {info['toeoff']:.0f}% DS {info['ds']:.0f}% -> 2 plots")


if __name__ == "__main__":
    main()
