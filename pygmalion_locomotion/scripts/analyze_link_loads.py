# -*- coding: utf-8 -*-
"""Connection / link STRUCTURAL load analysis from the 6-axis link reaction wrench.

For each link the measurement logs the joint reaction wrench (Fx,Fy,Fz,Tx,Ty,Tz) at the joint that
attaches it to its parent — i.e. the load that CONNECTION (joint housing / bracket / bolt pattern /
bearing / link cross-section) must carry. This script reduces it to the structural design loads:
  * |F|  = sqrt(Fx^2+Fy^2+Fz^2)  resultant force  [N]  -> bolt/bearing/cross-section sizing
  * |M|  = sqrt(Tx^2+Ty^2+Tz^2)  resultant moment [N*m]-> bending/torsion strength
  * per-axis peaks (Fx,Fy,Fz / Tx,Ty,Tz) for CAD-frame interpretation (axial vs shear vs bend vs torsion)
Reports peak (worst-case design) + RMS (fatigue/duty) per link, a bar chart, and a markdown table.

Usage:
  python scripts/analyze_link_loads.py --npz logs/measure/<tag>.npz --tag <name> --title "..." --out ../docs/assets
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

# structural links worth sizing (skip base for the bar chart clarity; keep in table)
ORDER = ["hip_pitch", "hip_roll", "hip_yaw", "thigh", "shin", "knee", "ankle_pitch", "ankle_roll", "foot", "toe"]


def order_key(b):
    s = 0 if b.startswith("L") else (1 if b.startswith("R") else 2)
    for i, k in enumerate(ORDER):
        if k in b:
            return (i, s)
    return (99, s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", required=True)
    ap.add_argument("--tag", default="link_loads")
    ap.add_argument("--title", default=None)
    ap.add_argument("--out", default="../docs/assets")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    title = args.title or args.tag
    d = np.load(args.npz)
    bodies = sorted({re.sub(r"^F[xyz]_", "", c) for c in d.keys() if re.match(r"^Fx_", c)}, key=order_key)

    rows = []
    for b in bodies:
        Fx, Fy, Fz = d.get(f"Fx_{b}"), d.get(f"Fy_{b}"), d.get(f"Fz_{b}")
        Tx, Ty, Tz = d.get(f"Tx_{b}"), d.get(f"Ty_{b}"), d.get(f"Tz_{b}")
        if Fx is None or Tx is None:
            continue
        Fmag = np.sqrt(Fx**2 + Fy**2 + Fz**2)
        Mmag = np.sqrt(Tx**2 + Ty**2 + Tz**2)
        rows.append({
            "link": b,
            "F_peak": float(Fmag.max()), "F_rms": float(np.sqrt(np.mean(Fmag**2))),
            "M_peak": float(Mmag.max()), "M_rms": float(np.sqrt(np.mean(Mmag**2))),
            "Fx": float(np.abs(Fx).max()), "Fy": float(np.abs(Fy).max()), "Fz": float(np.abs(Fz).max()),
            "Tx": float(np.abs(Tx).max()), "Ty": float(np.abs(Ty).max()), "Tz": float(np.abs(Tz).max()),
        })

    # --- bar chart: peak |F| and |M| per link (skip base_link for scale) ---
    plot_rows = [r for r in rows if "base" not in r["link"]]
    labels = [r["link"].replace("_link", "") for r in plot_rows]
    x = np.arange(len(plot_rows))
    fig, ax = plt.subplots(1, 2, figsize=(16, 5))
    ax[0].bar(x, [r["F_peak"] for r in plot_rows], color="#3b78c0")
    ax[0].bar(x, [r["F_rms"] for r in plot_rows], color="#9bc0e8", label="RMS")
    ax[0].set_title(f"Connection peak resultant FORCE |F| [N]\n{title}"); ax[0].set_ylabel("N")
    ax[0].set_xticks(x); ax[0].set_xticklabels(labels, rotation=90, fontsize=7); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3, axis="y")
    ax[1].bar(x, [r["M_peak"] for r in plot_rows], color="#c0392b")
    ax[1].bar(x, [r["M_rms"] for r in plot_rows], color="#e8a59b", label="RMS")
    ax[1].set_title(f"Connection peak resultant MOMENT |M| [N*m]\n{title}"); ax[1].set_ylabel("N*m")
    ax[1].set_xticks(x); ax[1].set_xticklabels(labels, rotation=90, fontsize=7); ax[1].legend(fontsize=8); ax[1].grid(alpha=.3, axis="y")
    fig.tight_layout(); png = os.path.join(args.out, f"{args.tag}_link_loads.png")
    fig.savefig(png, dpi=100); plt.close(fig)

    md = [f"# Connection / link structural loads — {title}", "",
          "| link (connection) | peak \\|F\\| [N] | RMS \\|F\\| | peak \\|M\\| [N·m] | RMS \\|M\\| | Fx | Fy | Fz | Tx | Ty | Tz |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append("| {link} | {F_peak:.0f} | {F_rms:.0f} | {M_peak:.1f} | {M_rms:.1f} | {Fx:.0f} | {Fy:.0f} | "
                  "{Fz:.0f} | {Tx:.1f} | {Ty:.1f} | {Tz:.1f} |".format(**r))
    open(os.path.join(args.out, f"{args.tag}_link_loads.md"), "w").write("\n".join(md) + "\n")
    json.dump({"title": title, "rows": rows}, open(os.path.join(args.out, f"{args.tag}_link_loads.json"), "w"), indent=2)
    print(f"[link_loads] wrote {png} + .md + .json")
    print("\n".join(md))


if __name__ == "__main__":
    main()
