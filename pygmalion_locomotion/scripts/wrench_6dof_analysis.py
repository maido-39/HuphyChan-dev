# -*- coding: utf-8 -*-
"""6-DoF joint-load analysis across ALL measure experiments (user 2026-06-22).

For every logs/measure/*.npz: per JOINT (= child link's incoming joint wrench), the 6 components
Fx/Fy/Fz (N) + Tx/Ty/Tz (N.m) over time -> (1) time-series plots per experiment, (2) Peak/RMS/p95
table (CSV + markdown). No Isaac -- pure numpy/matplotlib. Plot labels are ENGLISH only.

    python3 scripts/wrench_6dof_analysis.py
"""
import os, glob
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEAS = os.path.join(ROOT, "logs", "measure")
ASSET = os.path.join(ROOT, "..", "docs", "assets", "wrench")
DOCS = os.path.join(ROOT, "..", "docs")
os.makedirs(ASSET, exist_ok=True)

COMP = ["Fx", "Fy", "Fz", "Tx", "Ty", "Tz"]                       # T = moment (N.m)
LINK2JOINT = {"hip_pitch_link": "hip_pitch", "hip_roll_link": "hip_roll", "thigh_link": "hip_yaw",
              "shin_link": "knee", "ankle_pitch_link": "ankle_pitch", "foot_link": "ankle_roll",
              "toe_link": "toe"}
ORDER = ["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll", "toe"]
# recent/relevant experiments first (rest still go in the CSV)
RECENT = ["gaitfix_v3", "gaitfix_v4", "gaitfix_v5", "gaitfix_v6", "gaitfix_v7",
          "g1vanilla", "g1van_flat", "g1van_full", "g1_rigidtoe2"]


def joint_label(link):
    for side in ("L_", "R_"):
        if link.startswith(side):
            base = link[2:]
            if base in LINK2JOINT:
                return f"{side[0]}_{LINK2JOINT[base]}"
    return link


def stats(a):
    aa = np.abs(a)
    return float(aa.max()), float(np.sqrt(np.mean(a ** 2))), float(np.percentile(aa, 95))


def main():
    files = sorted(glob.glob(os.path.join(MEAS, "*.npz")))
    csv_rows = ["experiment,joint,component,peak,rms,p95"]
    md = ["# 46 · 전 실험 관절 6-DoF 하중 (Fx/Fy/Fz·Mx/My/Mz) — Peak/RMS/p95\n",
          "> measure npz의 관절별 incoming-joint-wrench(body frame). 링크→관절: thigh=hip_yaw·shin=knee·foot=ankle_roll. "
          "F=N, M(=T)=N·m. 전체 per-component CSV: `logs/measure/wrench_6dof_stats.csv`. 시계열 plot: `docs/assets/wrench/<exp>_6dof.png`.\n"]

    def exp_key(f):
        e = os.path.basename(f)[:-4]
        return (RECENT.index(e) if e in RECENT else 100 + files.index(f), e)
    files = sorted(files, key=exp_key)

    for f in files:
        exp = os.path.basename(f)[:-4]
        d = np.load(f, allow_pickle=True)
        t = d["time"] if "time" in d.files else np.arange(len(d[d.files[0]]))
        # joints present (exclude base_link = root, wrench ~0)
        links = sorted({k.split("_", 1)[1] for k in d.files if k.split("_", 1)[0] in COMP})
        joints = [(joint_label(lk), lk) for lk in links if lk != "base_link"]
        joints = [j for j in joints if any(o in j[0] for o in ORDER)]
        joints.sort(key=lambda j: (j[0][0], next((i for i, o in enumerate(ORDER) if o in j[0]), 99)))

        # --- table rows for this experiment ---
        md.append(f"\n## {exp}\n")
        md.append("| 관절(joint) | Fx pk | Fy pk | Fz pk | Mx pk | My pk | Mz pk | \\|F\\| pk/rms/p95 | \\|M\\| pk/rms/p95 |")
        md.append("|---|--:|--:|--:|--:|--:|--:|--:|--:|")
        for jl, lk in joints:
            comp_pk = {}
            F = []; M = []
            for c in COMP:
                key = f"{c}_{lk}"
                a = np.asarray(d[key]) if key in d.files else np.zeros_like(t, dtype=float)
                pk, rms, p95 = stats(a)
                comp_pk[c] = pk
                csv_rows.append(f"{exp},{jl},{c},{pk:.2f},{rms:.2f},{p95:.2f}")
                (F if c[0] == "F" else M).append(a)
            Fmag = np.sqrt(np.sum(np.square(F), axis=0)); Mmag = np.sqrt(np.sum(np.square(M), axis=0))
            fpk, frms, fp95 = stats(Fmag); mpk, mrms, mp95 = stats(Mmag)
            csv_rows.append(f"{exp},{jl},|F|,{fpk:.2f},{frms:.2f},{fp95:.2f}")
            csv_rows.append(f"{exp},{jl},|M|,{mpk:.2f},{mrms:.2f},{mp95:.2f}")
            md.append(f"| {jl} | {comp_pk['Fx']:.0f} | {comp_pk['Fy']:.0f} | {comp_pk['Fz']:.0f} | "
                      f"{comp_pk['Tx']:.1f} | {comp_pk['Ty']:.1f} | {comp_pk['Tz']:.1f} | "
                      f"{fpk:.0f}/{frms:.0f}/{fp95:.0f} | {mpk:.1f}/{mrms:.1f}/{mp95:.1f} |")

        # --- time-series plot (only for the recent/relevant set, to keep it usable) ---
        if exp in RECENT:
            n = len(joints); cols = 4; rows = (n + cols - 1) // cols
            fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 2.6 * rows), squeeze=False)
            for ax in axes.flat:
                ax.axis("off")
            for i, (jl, lk) in enumerate(joints):
                ax = axes[i // cols][i % cols]; ax.axis("on")
                ax2 = ax.twinx()
                for c, col in zip(["Fx", "Fy", "Fz"], ["#1f77b4", "#2ca02c", "#d62728"]):
                    k = f"{c}_{lk}"
                    if k in d.files:
                        ax.plot(t, d[k], col, lw=0.6, label=c)
                for c, col in zip(["Tx", "Ty", "Tz"], ["#9467bd", "#8c564b", "#e377c2"]):
                    k = f"{c}_{lk}"
                    if k in d.files:
                        ax2.plot(t, d[k], col, lw=0.6, ls="--", label=c.replace("T", "M"))
                ax.set_title(jl, fontsize=9)
                ax.set_ylabel("force [N]", fontsize=7); ax2.set_ylabel("moment [N.m]", fontsize=7)
                ax.tick_params(labelsize=6); ax2.tick_params(labelsize=6); ax.set_xlabel("time [s]", fontsize=7)
                if i == 0:
                    ax.legend(loc="upper left", fontsize=5, ncol=3); ax2.legend(loc="upper right", fontsize=5, ncol=3)
            fig.suptitle(f"{exp} — per-joint 6-DoF reaction wrench (solid=force, dashed=moment)", fontsize=11)
            fig.tight_layout(rect=[0, 0, 1, 0.97])
            fig.savefig(os.path.join(ASSET, f"{exp}_6dof.png"), dpi=85)
            plt.close(fig)
            md.append(f"\n![{exp}](assets/wrench/{exp}_6dof.png)")

    with open(os.path.join(MEAS, "wrench_6dof_stats.csv"), "w") as fp:
        fp.write("\n".join(csv_rows) + "\n")
    with open(os.path.join(DOCS, "46_wrench_6dof_loads.md"), "w") as fp:
        fp.write("\n".join(md) + "\n")
    print(f"[wrench] experiments={len(files)}  csv_rows={len(csv_rows)-1}")
    print(f"[wrench] CSV  -> logs/measure/wrench_6dof_stats.csv")
    print(f"[wrench] DOC  -> docs/46_wrench_6dof_loads.md")
    print(f"[wrench] PLOTS-> docs/assets/wrench/<exp>_6dof.png ({len([e for e in RECENT])} recent)")


if __name__ == "__main__":
    main()
