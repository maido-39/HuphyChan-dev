# -*- coding: utf-8 -*-
"""Motor-utilization analysis: clipped vs unclipped joint torque vs Spec rated/peak.

Re-runnable hardware-sizing view for the biped. For each actuated joint it reports the measured
peak |tau| (clipped = with the effort_limit clamp; unclipped = the policy's TRUE torque demand,
measured with measure.py --effort_scale >1) and expresses it as:
  * % of Spec RATED  (continuous-duty rating; >100% => exceeds continuous rating, watch duty cycle)
  * % of Spec PEAK   (absolute motor peak; unclipped >100% => motor undersized for true demand)

Usage (re-run any time conditions/rewards change):
  python scripts/analyze_motor_util.py --clipped logs/measure/<clip>.npz \
      [--unclipped logs/measure/<unclip>.npz] --tag v3_corrected --out ../docs/assets

Outputs <tag>_motor_util.png (main: peak |tau| vs rated/peak; supplementary: % of rated + % of peak)
and <tag>_motor_util.md / .json. Pure numpy + matplotlib.
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Spec motor rating (PEAK, RATED) [N*m] by joint substring -- mirrors analyze.py / robstride_biped.yaml
MOTOR_RATING = {
    "hip_pitch": (120.0, 40.0), "hip_roll": (120.0, 40.0), "hip_yaw": (60.0, 20.0),
    "knee": (360.0, 120.0), "ankle_pitch": (60.0, 20.0), "ankle_roll": (14.0, 5.0),
}
ORDER = ["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll"]


def rating_for(joint):
    for k, v in MOTOR_RATING.items():
        if k in joint:
            return v
    return (None, None)


def zone_color(pct_peak):
    # green < rated(=33% peak), yellow < 80% peak, orange < 100%, red >= 100% (matches the HUD)
    if pct_peak < 100.0 / 3.0:
        return "#40c040"
    if pct_peak < 80.0:
        return "#d0c000"
    if pct_peak < 100.0:
        return "#f09010"
    return "#e03030"


def peak_by_joint(npz):
    d = np.load(npz)
    out = {}
    for c in d.keys():
        if c.startswith("tau_") and "toe" not in c:
            out[c[len("tau_"):]] = float(np.max(np.abs(d[c])))
    return out


def order_joints(joints):
    def key(j):
        side = 0 if j.startswith("L") else 1
        for i, k in enumerate(ORDER):
            if k in j:
                return (i, side)
        return (99, side)
    return sorted(joints, key=key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clipped", required=True, help="npz of the clipped (effort_scale=1) run")
    ap.add_argument("--unclipped", default=None, help="npz of the unclipped (effort_scale>1) run")
    ap.add_argument("--tag", default="motor_util")
    ap.add_argument("--out", default="../docs/assets")
    ap.add_argument("--title", default=None, help="figure title suffix (e.g. 'v3 corrected, flat, 51.79kg')")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    title = args.title or args.tag

    clip = peak_by_joint(args.clipped)
    unclip = peak_by_joint(args.unclipped) if args.unclipped else {}
    joints = order_joints([j for j in clip if rating_for(j)[0]])
    labels = [j.replace("_joint", "").replace("_link", "") for j in joints]
    x = np.arange(len(joints))

    rows = []
    for j in joints:
        pk, rt = rating_for(j)
        c = clip.get(j, float("nan"))
        u = unclip.get(j, None)
        rows.append({
            "joint": j, "peak_clipped": c, "peak_unclipped": u, "spec_peak": pk, "spec_rated": rt,
            "pct_rated_clipped": 100 * c / rt, "pct_peak_clipped": 100 * c / pk,
            "pct_rated_unclipped": (100 * u / rt) if u is not None else None,
            "pct_peak_unclipped": (100 * u / pk) if u is not None else None,
        })

    have_u = bool(unclip)
    fig, ax = plt.subplots(1, 3, figsize=(18, 5.2))

    # --- panel 0: measured peak |tau| vs Spec rated/peak (absolute N*m) ---
    w = 0.38
    ax[0].bar(x - (w/2 if have_u else 0), [r["peak_clipped"] for r in rows], w, label="measured clipped", color="#3b78c0")
    if have_u:
        ax[0].bar(x + w/2, [r["peak_unclipped"] for r in rows], w, label="measured unclipped (true demand)", color="#9b59b6")
    ax[0].plot(x, [r["spec_rated"] for r in rows], "s--", color="#2a8a2a", label="Spec rated", ms=5)
    ax[0].plot(x, [r["spec_peak"] for r in rows], "D--", color="#c0392b", label="Spec peak", ms=5)
    ax[0].set_yscale("log"); ax[0].set_ylabel("torque |tau| [N*m] (log)")
    ax[0].set_xticks(x); ax[0].set_xticklabels(labels, rotation=90, fontsize=7)
    ax[0].set_title(f"Peak joint torque vs Spec\n{title}"); ax[0].legend(fontsize=7); ax[0].grid(alpha=.3, axis="y")

    # --- panel 1 (SUPPLEMENTARY): % of Spec RATED (continuous duty) ---
    ax[1].bar(x - (w/2 if have_u else 0), [r["pct_rated_clipped"] for r in rows], w, label="clipped", color="#3b78c0")
    if have_u:
        ax[1].bar(x + w/2, [r["pct_rated_unclipped"] for r in rows], w, label="unclipped", color="#9b59b6")
    ax[1].axhline(100, ls="--", c="#2a8a2a", label="100% = rated")
    ax[1].set_ylabel("% of Spec RATED"); ax[1].set_xticks(x); ax[1].set_xticklabels(labels, rotation=90, fontsize=7)
    ax[1].set_title("% of Spec RATED (continuous duty)\n>100% => over continuous rating"); ax[1].legend(fontsize=7); ax[1].grid(alpha=.3, axis="y")

    # --- panel 2 (SUPPLEMENTARY): % of Spec PEAK (absolute, color-zoned) ---
    src = "pct_peak_unclipped" if have_u else "pct_peak_clipped"
    vals = [r[src] if r[src] is not None else r["pct_peak_clipped"] for r in rows]
    ax[2].bar(x, vals, 0.6, color=[zone_color(v) for v in vals])
    ax[2].axhline(100, ls="--", c="#c0392b", label="100% = peak")
    ax[2].axhline(80, ls=":", c="#f09010", label="80% peak"); ax[2].axhline(100/3, ls=":", c="#2a8a2a", label="rated level")
    ax[2].set_ylabel(f"% of Spec PEAK ({'unclipped' if have_u else 'clipped'})")
    ax[2].set_xticks(x); ax[2].set_xticklabels(labels, rotation=90, fontsize=7)
    ax[2].set_title("% of Spec PEAK (color=safety zone)\ngreen<rated yellow<80% orange<100% red>peak"); ax[2].legend(fontsize=7); ax[2].grid(alpha=.3, axis="y")

    fig.tight_layout()
    fpng = os.path.join(args.out, f"{args.tag}_motor_util.png")
    fig.savefig(fpng, dpi=100); plt.close(fig)

    # --- markdown + json ---
    md = [f"# Motor utilization — {title}", "",
          "| joint | clip |τ| | unclip |τ| | rated | peak | %rated(clip) | %rated(unclip) | %peak(clip) | %peak(unclip) |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        u = r["peak_unclipped"]; ur = r["pct_rated_unclipped"]; up = r["pct_peak_unclipped"]
        md.append(f"| {r['joint']} | {r['peak_clipped']:.1f} | {u:.1f} | {r['spec_rated']:.0f} | {r['spec_peak']:.0f} | "
                  f"{r['pct_rated_clipped']:.0f}% | {ur:.0f}% | {r['pct_peak_clipped']:.0f}% | {up:.0f}% |"
                  if u is not None else
                  f"| {r['joint']} | {r['peak_clipped']:.1f} | - | {r['spec_rated']:.0f} | {r['spec_peak']:.0f} | "
                  f"{r['pct_rated_clipped']:.0f}% | - | {r['pct_peak_clipped']:.0f}% | - |")
    fmd = os.path.join(args.out, f"{args.tag}_motor_util.md")
    open(fmd, "w").write("\n".join(md) + "\n")
    fjson = os.path.join(args.out, f"{args.tag}_motor_util.json")
    json.dump({"title": title, "rows": rows}, open(fjson, "w"), indent=2)
    print(f"[motor_util] wrote {fpng}\n[motor_util] wrote {fmd}\n[motor_util] wrote {fjson}")
    print("\n".join(md))


if __name__ == "__main__":
    main()
