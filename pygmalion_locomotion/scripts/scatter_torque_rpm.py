# -*- coding: utf-8 -*-
"""Ankle actuator torque-vs-RPM operating-point scatter (user 2026-06-25), colored by experiment, ROUGH included.

Purpose: we want to ADD a gear reduction to the ankle actuator (torque x N, speed / N). That lowers the no-load
speed, so we must check whether the policy ever DEMANDS high joint speed (which a reduced no-load speed would
clip). Each measure rollout contributes (|omega| [rpm], |tau| [N.m]) operating points; we overlay the
torque-speed envelopes of RS00 (current) and DM-J4310-2EC (+external reductions). Specs verified via workflow
actuator-tn-specs (official manuals + distributors, HIGH confidence).

T-N envelope model = trapezoid: hold PEAK torque from 0 up to the rated/corner speed, then linear to 0 at the
no-load speed (more faithful to a QDD than pure linear-from-stall). ENGLISH labels.

    python3 scripts/scatter_torque_rpm.py
"""
import os, glob
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEAS = os.path.join(ROOT, "logs", "measure")
ASSET = os.path.join(ROOT, "..", "docs", "assets")
R2RPM = 60.0 / (2.0 * np.pi)

EXPS = [("stage4_clip", "rough"), ("stage4_unclip", "rough"),
        ("g1vanilla", "flat"), ("g1van_full", "flat"), ("pushoff3", "flat"),
        ("sweep_g1p0", "flat"), ("gaitfix_v7", "flat"), ("gaitfix_v4", "flat")]

# verified OUTPUT/joint-side T-N (workflow actuator-tn-specs). corner = rated speed (peak held to here, then ->0 at no-load).
RS00 = dict(name="RS00 (current)", peak=14, rated=5, corner=260, noload=315, color="#000000", lw=2.6, ls="-")
DM = dict(name="DM-J4310-2EC alone", peak=7, rated=3, corner=120, noload=200, color="#d62728", lw=1.8, ls="-")
DM_RED = [dict(name="DM-4310 +2:1", peak=14, rated=6, corner=60, noload=100, color="#ff7f0e", lw=2.0, ls="--"),
          dict(name="DM-4310 +3:1", peak=21, rated=9, corner=40, noload=66.7, color="#9467bd", lw=2.0, ls="--"),
          dict(name="DM-4310 +4:1", peak=28, rated=12, corner=30, noload=50, color="#8c564b", lw=2.0, ls="--")]
RS03 = dict(name="RS03 (current)", peak=60, rated=20, corner=180, noload=200, color="#000000", lw=2.6, ls="-")


def load_points(tag, joint):
    f = os.path.join(MEAS, tag + ".npz")
    if not os.path.exists(f):
        return None, None
    d = np.load(f, allow_pickle=True)
    ok = [k for k in d.files if k.startswith("omega_") and joint in k]
    tk = [k for k in d.files if k.startswith("tau_") and joint in k]
    if not ok or not tk:
        return None, None
    w = np.concatenate([np.abs(d[k]) for k in ok]) * R2RPM
    t = np.concatenate([np.abs(d[k]) for k in tk])
    n = min(len(w), len(t))
    return w[:n], t[:n]


def envline(ax, e):
    ax.plot([0, e["corner"], e["noload"]], [e["peak"], e["peak"], 0], color=e["color"], lw=e["lw"], ls=e["ls"],
            label=f"{e['name']}: peak {e['peak']:.0f} N·m (to {e['corner']:.0f} rpm), no-load {e['noload']:.0f} rpm")
    if e.get("rated"):
        ax.axhline(e["rated"], color=e["color"], lw=0.9, ls=":", alpha=0.45)


def scatter_panel(joint, jname, envelopes):
    cmap = plt.get_cmap("tab10")
    fig, ax = plt.subplots(figsize=(12, 7.5))
    for i, (tag, terr) in enumerate(EXPS):
        w, t = load_points(tag, joint)
        if w is None:
            continue
        mk = "X" if terr == "rough" else "o"
        ax.scatter(w, t, s=16 if terr == "rough" else 5, c=[cmap(i)], marker=mk,
                   alpha=0.5 if terr == "rough" else 0.22, edgecolors="none",
                   zorder=3 if terr == "rough" else 2, label=f"{tag} ({terr})")
    for e in envelopes:
        envline(ax, e)
    ax.set_xlabel("joint speed |omega| [rpm]", fontsize=12)
    ax.set_ylabel("joint torque |tau| [N·m]", fontsize=12)
    ax.set_title(f"{jname}: torque-vs-speed operating points (rough = X)\n"
                 "envelope x-intercept = no-load speed ceiling; points to its RIGHT are infeasible after that reduction",
                 fontsize=11)
    ax.grid(alpha=0.25); ax.set_xlim(0, 345); ax.set_ylim(0, 30)
    ax.legend(fontsize=8, loc="upper right", ncol=2)
    out = os.path.join(ASSET, f"scatter_tn_{joint}.png")
    fig.tight_layout(); fig.savefig(out, dpi=130); plt.close(fig)
    print(f"[scatter] {joint} -> {out}")


def tn_curves(ar_demand):
    fig, ax = plt.subplots(figsize=(10.5, 7.5))
    for e in [RS00, DM] + DM_RED:
        envline(ax, e)
    p95, mx = ar_demand
    ax.axvline(p95, color="#2ca02c", lw=1.5, ls="-.", label=f"ankle_roll demand p95 = {p95:.0f} rpm")
    ax.axvline(mx, color="#17becf", lw=1.3, ls="-.", label=f"ankle_roll demand MAX = {mx:.0f} rpm")
    ax.set_xlabel("output (joint-side) speed [rpm]", fontsize=12)
    ax.set_ylabel("output torque [N·m]", fontsize=12)
    ax.set_title("Actuator T-N envelopes: RS00 vs DM-J4310-2EC (+ external gear reductions)\n"
                 "trapezoid model (peak held to rated speed -> 0 at no-load); dotted = continuous/rated torque", fontsize=11)
    ax.grid(alpha=0.3); ax.set_xlim(0, 345); ax.set_ylim(0, 30)
    ax.legend(fontsize=9, loc="upper right")
    out = os.path.join(ASSET, "tn_curves_rs00_dm4310.png")
    fig.tight_layout(); fig.savefig(out, dpi=130); plt.close(fig)
    print(f"[tn] -> {out}")


def clip_report():
    pts = {"rough": [], "all": []}
    for tag, terr in EXPS:
        w, _ = load_points(tag, "ankle_roll")
        if w is None:
            continue
        pts["all"].append(w)
        if terr == "rough":
            pts["rough"].append(w)
    out = {}
    for grp, lst in pts.items():
        if not lst:
            continue
        a = np.concatenate(lst)
        out[grp] = dict(p95=float(np.percentile(a, 95)), mx=float(a.max()),
                        c2=100 * float(np.mean(a > 100)), c3=100 * float(np.mean(a > 66.7)),
                        c4=100 * float(np.mean(a > 50)))
    return out


def main():
    scatter_panel("ankle_roll", "Ankle ROLL (RS00 today)", [RS00, DM] + DM_RED)
    scatter_panel("ankle_pitch", "Ankle PITCH (RS03 today)", [RS03])
    rep = clip_report()
    tn_curves((rep["all"]["p95"], rep["all"]["mx"]))
    print("\n[clip] ankle_roll % of operating points BEYOND each reduction's no-load ceiling:")
    for grp, r in rep.items():
        print(f"  {grp:<6} p95={r['p95']:.0f} max={r['mx']:.0f} rpm | "
              f">100(2:1)={r['c2']:.1f}%  >67(3:1)={r['c3']:.1f}%  >50(4:1)={r['c4']:.1f}%")


if __name__ == "__main__":
    main()
