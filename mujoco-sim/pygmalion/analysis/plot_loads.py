"""Plot Pygmalion motor/structural loads in the IsaacLab note format (mjlab data).

Mirrors the style of pygmalion_locomotion/scripts/analyze_motor_timeseries.py and
analyze_motor_speed.py, but with the **mjlab ROBSTRIDE motor spec** (the mjlab
Pygmalion knee is a plain RS04 -- no 3:1 reduction -- unlike the IsaacLab build).

Per terrain tag it writes (same filenames/style as the IsaacLab §7 plots):
  <tag>_torque.png      RMS/p95/max |tau| bars vs peak/rated spec lines + saturation%
  <tag>_speed.png       RMS/p95/max |omega|(rpm) bars vs speed limit + saturation%
  <tag>_torque_ts.png   per joint-type L/R torque time-series + spec lines
  <tag>_speed_ts.png    per joint-type L/R speed time-series + limit line

Comparing terrains (flat vs rough, color-coded) it writes:
  cmp_torque_speed_scatter.png   torque-RPM operating points, flat+rough overlaid per motor box
  cmp_saturation.png             torque/speed saturation% grouped bars, flat vs rough
  cmp_link_force.png             per-body reaction |F|/|M|, flat vs rough

Usage:
  uv run python analysis/plot_loads.py --flat analysis/out/flat.npz \
      --rough analysis/out/rough.npz --out <docs/mujoco/assets>
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RAD2RPM = 60.0 / (2.0 * np.pi)

# mjlab ROBSTRIDE spec -- (peak N*m, continuous/rated N*m, joint-side speed limit rpm).
# peak & speed from pygmalion_constants.py (effort_limit / velocity_limit);
# rated = ROBSTRIDE nominal continuous torque (RS04 40, RS03 20, RS00 5).
SPEC = {
    "hip_pitch": (120.0, 40.0, 143.0), "hip_roll": (120.0, 40.0, 143.0),
    "hip_yaw": (60.0, 20.0, 191.0), "knee": (120.0, 40.0, 143.0),
    "ankle_pitch": (60.0, 20.0, 191.0), "ankle_roll": (14.0, 5.0, 315.0),
}
TYPES = ["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll", "toe"]
COLOR = {"flat": "#2980b9", "rough": "#e67e22"}


def spec_for(j):
    for k, v in SPEC.items():
        if k in j:
            return v
    return None


def jtype(j):
    for t in TYPES:
        if t in j:
            return t
    return j


def zone(pct):
    return "#40c040" if pct < 33.3 else "#d0c000" if pct < 80 else "#f09010" if pct < 100 else "#e03030"


def act_joints(d):
    js = [k[4:] for k in d.files if k.startswith("tau_")]
    js = [j for j in js if spec_for(j) is not None]
    return sorted(js, key=lambda n: (TYPES.index(jtype(n)), 0 if n.startswith("L_") else 1))


def bars(d, tag, title, out):
    """Replicate analyze_motor_timeseries.bars for torque & speed (single terrain)."""
    act = act_joints(d)
    x = np.arange(len(act))
    lbl = [j.replace("_joint", "") for j in act]

    def _one(getter, peak_i, rated_i, unit, ttl, sat_ttl, fname):
        fig, ax = plt.subplots(1, 2, figsize=(16, 6))
        rms = [float(np.sqrt(np.mean(getter(j) ** 2))) for j in act]
        p95 = [float(np.percentile(getter(j), 95)) for j in act]
        mx = [float(getter(j).max()) for j in act]
        ax[0].bar(x - 0.27, rms, 0.26, label="RMS", color="#9bbbd6")
        ax[0].bar(x, p95, 0.26, label="p95", color="#5a9bd4")
        ax[0].bar(x + 0.27, mx, 0.26, label="max", color="#2980b9")
        for i, j in enumerate(act):
            sp = spec_for(j)
            ax[0].plot([i - .45, i + .45], [sp[peak_i]] * 2, color="#c0392b", lw=1.6, ls="--")
            if rated_i is not None:
                ax[0].plot([i - .45, i + .45], [sp[rated_i]] * 2, color="#e67e22", lw=1.4)
        ax[0].plot([], [], color="#c0392b", lw=1.6, ls="--", label="peak (spec)")
        if rated_i is not None:
            ax[0].plot([], [], color="#e67e22", lw=1.4, label="rated (est., unverified)")
        ax[0].set_xticks(x); ax[0].set_xticklabels(lbl, rotation=60, ha="right", fontsize=7)
        ax[0].set_ylabel(unit); ax[0].set_title(ttl); ax[0].legend(fontsize=8)
        ax[0].grid(alpha=.3, axis="y")
        cont_i = rated_i if rated_i is not None else peak_i
        sat_mx = [100 * mx[i] / spec_for(act[i])[peak_i] for i in range(len(act))]
        sat_p95 = [100 * p95[i] / spec_for(act[i])[peak_i] for i in range(len(act))]
        sat_rms = [100 * rms[i] / spec_for(act[i])[cont_i] for i in range(len(act))]
        rms_lbl = "RMS %rated (est.)" if rated_i is not None else "RMS %limit"
        ax[1].bar(x - 0.27, sat_mx, 0.26, color=[zone(s) for s in sat_mx], label="max %peak (transient)")
        ax[1].bar(x, sat_p95, 0.26, color=[zone(s) for s in sat_p95], label="p95 %peak")
        ax[1].bar(x + 0.27, sat_rms, 0.26, color=[zone(s) for s in sat_rms], label=rms_lbl)
        ax[1].axhline(100, color="#c0392b", ls="--", lw=1); ax[1].axhline(80, color="#f09010", ls=":", lw=1)
        for i in range(len(act)):
            ax[1].text(i - .27, sat_mx[i] + 1, f"{sat_mx[i]:.0f}", ha="center", fontsize=4.5)
            ax[1].text(i + .27, sat_rms[i] + 1, f"{sat_rms[i]:.0f}", ha="center", fontsize=4.5)
        ax[1].set_xticks(x); ax[1].set_xticklabels(lbl, rotation=60, ha="right", fontsize=7)
        ax[1].set_ylabel("% of limit"); ax[1].set_title(sat_ttl); ax[1].legend(fontsize=8)
        ax[1].grid(alpha=.3, axis="y")
        fig.suptitle(f"{ttl.split('(')[0].strip()} — {title}", fontsize=13)
        fig.tight_layout(rect=[0, 0, 1, .96])
        fig.savefig(os.path.join(out, fname), dpi=95); plt.close(fig)

    _one(lambda j: np.abs(d["tau_" + j]), 0, 1, "torque [N*m]",
         "Joint torque  RMS/p95/max vs spec (rated/peak)",
         "Torque sat:  max %peak + p95 %peak + RMS %rated (continuous/thermal)",
         f"{tag}_torque.png")
    _one(lambda j: np.abs(d["omega_" + j]) * RAD2RPM, 2, None, "speed [rpm]",
         "Joint speed  RMS/p95/max vs spec (limit)",
         "Speed sat:  max %limit (binding) + p95/RMS %limit", f"{tag}_speed.png")


def ts_grid(d, tag, title, out):
    """Replicate analyze_motor_timeseries.grid for torque & speed time-series."""
    files = set(d.files)
    joints = act_joints(d)
    present = [ty for ty in TYPES if any(jtype(j) == ty for j in joints)]
    t = d["time"]

    def _one(getter, spec_i, rated_i, unit, sup, fname):
        cols = 3; rows = (len(present) + cols - 1) // cols
        fig, axs = plt.subplots(rows, cols, figsize=(4.3 * cols, 2.9 * rows), squeeze=False)
        for idx, ty in enumerate(present):
            a = axs[idx // cols][idx % cols]
            for side, c in [("L", "#2980b9"), ("R", "#e67e22")]:
                j = f"{side}_{ty}_joint"
                if "tau_" + j in files:
                    a.plot(t, getter(j), color=c, lw=.6, label=side)
            sp = spec_for(f"L_{ty}_joint")
            if sp is not None:
                a.axhline(sp[spec_i], color="#c0392b", ls="--", lw=1)
                if rated_i is not None:
                    a.axhline(sp[rated_i], color="#e67e22", ls=":", lw=1)
            a.set_title(ty, fontsize=9); a.grid(alpha=.3); a.legend(fontsize=6)
        for idx in range(len(present), rows * cols):
            axs[idx // cols][idx % cols].axis("off")
        fig.suptitle(sup, fontsize=13); fig.supxlabel("time [s]"); fig.supylabel(unit)
        fig.tight_layout(rect=[0, 0, 1, .97])
        fig.savefig(os.path.join(out, fname), dpi=90); plt.close(fig)

    _one(lambda j: np.abs(d["tau_" + j]), 0, 1, "|tau| [N*m]",
         f"Joint torque time-series (peak=red--, rated=orange:) — {title}", f"{tag}_torque_ts.png")
    _one(lambda j: np.abs(d["omega_" + j]) * RAD2RPM, 2, None, "speed [rpm]",
         f"Joint speed time-series (limit=red--) — {title}", f"{tag}_speed_ts.png")


def cmp_scatter(runs, out):
    """Torque-RPM operating points per motor family, terrains overlaid (colored)."""
    fams = ["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll"]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for ax, fam in zip(axes.flat, fams):
        pk, _, vlim = SPEC[fam]
        for label, d in runs.items():
            js = [j for j in act_joints(d) if fam in j]
            pts_w = np.concatenate([np.abs(d["omega_" + j]) * RAD2RPM for j in js]) if js else np.array([])
            pts_t = np.concatenate([np.abs(d["tau_" + j]) for j in js]) if js else np.array([])
            ax.scatter(pts_w, pts_t, s=3, alpha=0.25, c=COLOR.get(label, None), label=label)
        ax.add_patch(plt.Rectangle((0, 0), vlim, pk, fill=False, ls="--", ec="#c0392b", lw=1.5))
        ax.set_xlim(0, vlim * 1.15); ax.set_ylim(0, pk * 1.15)
        ax.set_title(f"{fam}  (box={vlim:.0f}rpm x {pk:.0f}N*m)", fontsize=9)
        ax.set_xlabel("|speed| [rpm]", fontsize=8); ax.set_ylabel("|tau| [N*m]", fontsize=8)
        ax.legend(fontsize=7, markerscale=3); ax.grid(alpha=.3)
    fig.suptitle("Torque-speed operating points vs envelope — flat vs rough", fontsize=12)
    fig.tight_layout(); fig.savefig(os.path.join(out, "cmp_torque_speed_scatter.png"), dpi=95)
    plt.close(fig)


def cmp_qtorque_scatter(runs, out):
    """Per-joint (joint angle, torque) operating points, terrains overlaid.

    Shows WHERE in the range of motion the high torques occur -- key for
    structural/actuator sizing (peak torque vs joint angle)."""
    any_d = next(iter(runs.values()))
    act = act_joints(any_d)
    cols = 4
    rows = (len(act) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3 * rows), squeeze=False)
    axf = axes.ravel()
    for i, j in enumerate(act):
        ax = axf[i]
        pk = spec_for(j)[0]
        rt = spec_for(j)[1]
        for label, d in runs.items():
            q = np.degrees(d["qpos_" + j])
            ax.scatter(q, d["tau_" + j], s=3, alpha=0.25, c=COLOR.get(label), label=label)
        ax.axhline(pk, color="#c0392b", ls="--", lw=0.9)
        ax.axhline(-pk, color="#c0392b", ls="--", lw=0.9)
        ax.axhline(rt, color="#e67e22", ls=":", lw=0.9)
        ax.axhline(-rt, color="#e67e22", ls=":", lw=0.9)
        ax.set_title(j.replace("_joint", ""), fontsize=9)
        ax.set_xlabel("joint angle [deg]", fontsize=7)
        ax.set_ylabel("torque [N*m]", fontsize=7)
        ax.legend(fontsize=6, markerscale=3); ax.grid(alpha=.3)
    for k in range(len(act), len(axf)):
        axf[k].axis("off")
    fig.suptitle("Joint angle (q) vs torque operating points  (peak=red--, rated=orange:)"
                 " — flat vs rough", fontsize=12)
    fig.tight_layout(); fig.savefig(os.path.join(out, "cmp_q_torque_scatter.png"), dpi=95)
    plt.close(fig)


def cmp_saturation(runs, out):
    """Per-joint max-torque %peak and max-speed %limit, flat vs rough grouped."""
    any_d = next(iter(runs.values()))
    act = act_joints(any_d)
    lbl = [j.replace("_joint", "") for j in act]
    x = np.arange(len(act))
    fig, (axt, axs) = plt.subplots(2, 1, figsize=(max(9, len(act)), 9))
    n = len(runs)
    w = 0.8 / n
    for k, (label, d) in enumerate(runs.items()):
        st = [100 * np.abs(d["tau_" + j]).max() / spec_for(j)[0] for j in act]
        ss = [100 * (np.abs(d["omega_" + j]).max() * RAD2RPM) / spec_for(j)[2] for j in act]
        off = (k - (n - 1) / 2) * w
        axt.bar(x + off, st, w, color=COLOR.get(label), label=label)
        axs.bar(x + off, ss, w, color=COLOR.get(label), label=label)
    for ax, ttl, yl in [(axt, "max torque % of motor peak", "% peak torque"),
                        (axs, "max speed % of speed limit", "% speed limit")]:
        ax.axhline(100, color="#c0392b", ls="--", lw=1); ax.axhline(80, color="#f09010", ls=":", lw=1)
        ax.set_xticks(x); ax.set_xticklabels(lbl, rotation=55, ha="right", fontsize=8)
        ax.set_ylabel(yl); ax.set_title(ttl); ax.legend(); ax.grid(alpha=.3, axis="y")
    fig.suptitle("Saturation: flat vs rough (max over all commanded directions)", fontsize=13)
    fig.tight_layout(); fig.savefig(os.path.join(out, "cmp_saturation.png"), dpi=100)
    plt.close(fig)


def cmp_link_force(runs, out):
    """Per-body reaction |F| (peak) and |M| (peak), flat vs rough grouped."""
    any_d = next(iter(runs.values()))
    bodies = sorted({k[3:] for k in any_d.files if k.startswith("Fx_")},
                    key=lambda b: (0 if b.startswith("L_") else 1 if b.startswith("R_") else 2, b))
    bodies = [b for b in bodies if b not in ("terrain",)]
    x = np.arange(len(bodies))
    fig, (axf, axm) = plt.subplots(2, 1, figsize=(max(9, len(bodies)), 9))
    n = len(runs); w = 0.8 / n
    for k, (label, d) in enumerate(runs.items()):
        Fpk, Mpk = [], []
        for b in bodies:
            F = np.sqrt(d["Fx_" + b] ** 2 + d["Fy_" + b] ** 2 + d["Fz_" + b] ** 2)
            M = np.sqrt(d["Tx_" + b] ** 2 + d["Ty_" + b] ** 2 + d["Tz_" + b] ** 2)
            Fpk.append(float(F.max())); Mpk.append(float(M.max()))
        off = (k - (n - 1) / 2) * w
        axf.bar(x + off, Fpk, w, color=COLOR.get(label), label=label)
        axm.bar(x + off, Mpk, w, color=COLOR.get(label), label=label)
    for ax, ttl, yl in [(axf, "peak reaction force |F|", "|F| [N]"),
                        (axm, "peak reaction moment |M| (about robot COM)", "|M| [N*m]")]:
        ax.set_xticks(x); ax.set_xticklabels(bodies, rotation=55, ha="right", fontsize=7)
        ax.set_ylabel(yl); ax.set_title(ttl); ax.legend(); ax.grid(alpha=.3, axis="y")
    fig.suptitle("Per-body joint reaction wrench (cfrc_int): flat vs rough", fontsize=13)
    fig.tight_layout(); fig.savefig(os.path.join(out, "cmp_link_force.png"), dpi=100)
    plt.close(fig)


def cmp_grf(runs, out):
    """Ground reaction force analysis: per-foot GRF |F| distribution + peak/p95/RMS,
    with the HW failure band (1.5-2.7 kN) and bodyweight multiples marked."""
    BW = 51.8 * 9.81  # ~508 N
    fig, (axh, axb) = plt.subplots(2, 1, figsize=(11, 8))
    # (1) GRF magnitude distribution (both feet pooled), flat vs rough
    for label, d in runs.items():
        if "GRF_L_foot_link_mag" not in d.files:
            continue
        mags = np.concatenate([d["GRF_L_foot_link_mag"], d["GRF_R_foot_link_mag"]])
        axh.hist(mags, bins=80, alpha=0.5, color=COLOR.get(label), label=label, density=True)
    axh.axvspan(1500, 2700, color="#e03030", alpha=0.12, label="HW failure band 1.5-2.7kN")
    for k in (1, 2, 3, 4, 5):
        axh.axvline(k * BW, color="#888", ls=":", lw=0.8)
        axh.text(k * BW, axh.get_ylim()[1] * 0.92, f"{k}xBW", fontsize=6,
                 ha="center", color="#555")
    axh.set_xlabel("foot GRF |F| [N]"); axh.set_ylabel("density")
    axh.set_title("Foot ground-reaction-force distribution (both feet) — flat vs rough")
    axh.legend(fontsize=8); axh.grid(alpha=.3)
    # (2) per-foot peak/p95/RMS bars, flat vs rough
    feet = ["L_foot_link", "R_foot_link"]
    labels = [f"{f.split('_')[0]}" for f in feet]
    x = np.arange(len(feet)); n = len(runs); w = 0.8 / (n * 3)
    for k, (label, d) in enumerate(runs.items()):
        for s, (stat, fn) in enumerate([("peak", lambda a: a.max()),
                                        ("p95", lambda a: np.percentile(a, 95)),
                                        ("RMS", lambda a: np.sqrt(np.mean(a ** 2)))]):
            vals = [fn(d[f"GRF_{f}_mag"]) for f in feet]
            off = (k * 3 + s - (n * 3 - 1) / 2) * w
            axb.bar(x + off, vals, w, color=COLOR.get(label),
                    alpha=[1.0, 0.7, 0.4][s],
                    label=f"{label} {stat}" if x[0] == 0 else None)
    axb.axhspan(1500, 2700, color="#e03030", alpha=0.10)
    axb.axhline(BW, color="#888", ls=":", lw=0.8)
    axb.set_xticks(x); axb.set_xticklabels(labels)
    axb.set_ylabel("foot GRF |F| [N]"); axb.set_title("Per-foot GRF peak/p95/RMS (band=HW failure)")
    axb.legend(fontsize=7, ncol=2); axb.grid(alpha=.3, axis="y")
    fig.tight_layout(); fig.savefig(os.path.join(out, "cmp_grf.png"), dpi=100)
    plt.close(fig)


def wrench_csv(runs, out):
    """Full 6-DoF reaction wrench per body (Fx,Fy,Fz,Mx,My,Mz; peak & RMS) for
    each terrain -> CSV for structural design."""
    any_d = next(iter(runs.values()))
    bodies = sorted({k[3:] for k in any_d.files if k.startswith("Fx_")},
                    key=lambda b: (0 if b.startswith("L_") else 1 if b.startswith("R_") else 2, b))
    comps = [("Fx", "Fx"), ("Fy", "Fy"), ("Fz", "Fz"),
             ("Mx", "Tx"), ("My", "Ty"), ("Mz", "Tz")]
    head = ["terrain", "body"]
    for nm, _ in comps:
        head += [f"{nm}_peak", f"{nm}_rms"]
    lines = [",".join(head)]
    for label, d in runs.items():
        for b in bodies:
            row = [label, b]
            for _, key in comps:
                v = d[f"{key}_{b}"]
                row += [f"{np.abs(v).max():.1f}", f"{np.sqrt(np.mean(v ** 2)):.1f}"]
            lines.append(",".join(row))
    with open(os.path.join(out, "wrench_6dof.csv"), "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--flat", type=str, default=None)
    ap.add_argument("--rough", type=str, default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    runs = {}
    for label, path in [("flat", args.flat), ("rough", args.rough)]:
        if path and os.path.exists(path):
            d = np.load(path, allow_pickle=True)
            runs[label] = d
            bars(d, label, f"{label} (multi-direction sweep)", args.out)
            ts_grid(d, label, f"{label}", args.out)
            print(f"[plot] {label}: per-terrain torque/speed/ts written")

    if runs:
        cmp_scatter(runs, args.out)
        cmp_qtorque_scatter(runs, args.out)
        cmp_saturation(runs, args.out)
        cmp_link_force(runs, args.out)
        cmp_grf(runs, args.out)
        wrench_csv(runs, args.out)
        print(f"[plot] comparison (tspeed/qtorque/saturation/link_force/grf/wrench_csv) -> {args.out}")


if __name__ == "__main__":
    main()
