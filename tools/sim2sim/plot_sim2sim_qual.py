#!/usr/bin/env python3
"""Qualitative MuJoCo-vs-IsaacSim (sim2sim) comparison plots for the RP policy.

Builds 4 PNGs into docs/img/ from data already on disk (no sim re-run):
  a. sim2sim_grf_waveform.png  -- GRF waveform overlay (soft spread vs rigid spike)
  b. sim2sim_solver_iters.png  -- peak & loading-rate vs solver iteration count
  c. sim2sim_agreement.png     -- cross-engine agreement bars (ratio-to-MuJoCo)
  d. sim2sim_tracking.png      -- forward-velocity & base-height stability

Palette: Okabe-Ito (published colour-vision-deficiency-safe categorical set).
All labels English. Run with system python3 (needs numpy + matplotlib only).
"""
import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

WORK   = "/home/syaro/pyg_fea/work"
SWEEP  = f"{WORK}/contact_sweep"
IMG    = "/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img"
os.makedirs(IMG, exist_ok=True)

# --- Okabe-Ito roles ---------------------------------------------------------
C_MJ   = "#0072B2"   # MuJoCo (blue)
C_IMP  = "#D55E00"   # Isaac imported 32/1 (vermillion)
C_FIX  = "#009E73"   # Isaac fixed 4/8 (bluish green)
C_GREY = "#8a8f98"   # de-emphasised / neutral
INK    = "#1a1a1a"
MUTED  = "#5b6169"

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "font.family": "DejaVu Sans", "font.size": 11,
    "axes.edgecolor": "#c9ccd1", "axes.linewidth": 0.8,
    "axes.grid": True, "grid.color": "#e8eaed", "grid.linewidth": 0.8,
    "axes.axisbelow": True, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.labelcolor": INK, "text.color": INK,
    "legend.frameon": False, "axes.titleweight": "bold",
})

def load_json(tag):
    return json.load(open(f"{SWEEP}/isaac_grf_pygmalion_v3_printed_{tag}.json"))

def load_trace(tag=None, path=None):
    p = path or f"{SWEEP}/isaac_grf_pygmalion_v3_printed_{tag}_traces.npz"
    return np.load(p, allow_pickle=True)

# MuJoCo reference numbers (bundleD1_RP, 24 env, no DR)
MJ = load_json("base")["mujoco"]

# =============================================================================
# (a) GRF waveform overlay
# =============================================================================
def find_strikes(f, thr=0.15, minpeak=0.6):
    s = []
    for i in range(1, len(f)):
        if f[i-1] < thr <= f[i]:
            seg = f[i:i+14]
            if len(seg) and seg.max() > minpeak:
                s.append(i)
    return s

def rep_strike(f, t0=8.0, t1=36.0, dt=0.005):
    """Pick a representative strike (median peak) in a steady window."""
    strikes = [i for i in find_strikes(f) if t0 <= i*dt <= t1]
    peaks = [f[i:i+14].max() for i in strikes]
    med = np.median(peaks)
    j = int(np.argmin([abs(p-med) for p in peaks]))
    return strikes[j]

def plot_a():
    mj = np.load(f"{WORK}/impact_multi_nodr/bundleD1_RP_raw.npz")
    Fmj = mj["F"][:, 0, 0].astype(float)          # env0, foot0, already in BW
    dt = 0.005
    tr_imp = load_trace("base")                    # Isaac 32/1
    tr_fix = load_trace("b7_pos4vel8")             # Isaac 4/8
    Fimp = tr_imp["F_BW"][:, 0].astype(float)
    Ffix = tr_fix["F_BW"][:, 0].astype(float)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.2, 7.4))

    # --- top: consecutive strikes, each engine's window aligned to a touchdown
    #     so the strike CADENCE can be compared directly (independent rollouts). ---
    SPAN = 1.55
    for F, c, lab, lw, z in [(Fmj,  C_MJ,  "MuJoCo  (reference)", 2.2, 4),
                             (Fimp, C_IMP, "IsaacSim  32/1  (URDF-imported)", 1.9, 3),
                             (Ffix, C_FIX, "IsaacSim  4/8  (solver fixed)", 1.9, 2)]:
        i0 = rep_strike(F, t0=5.5, t1=8.5) if F is Fmj else rep_strike(F, t0=12.0, t1=30.0)
        lo = i0 - int(0.06/dt); hi = lo + int(SPAN/dt)
        t = (np.arange(lo, hi) - i0) * dt
        ax1.plot(t, F[lo:hi], color=c, lw=lw, label=lab, zorder=z, solid_capstyle="round")
    ax1.axhline(1.0, color=C_GREY, lw=1.0, ls=":", zorder=1)
    ax1.text(1.47, 1.05, "1 BW", color=MUTED, fontsize=9, ha="right")
    ax1.set_xlim(-0.06, 1.49); ax1.set_ylim(0, 4.3)
    ax1.set_xlabel("time from a touchdown (s)"); ax1.set_ylabel("foot vertical GRF (BW)")
    ax1.set_title("Same policy, same 1.6 m/s command — same cadence, but a taller strike",
                  fontsize=12, loc="left")
    ax1.legend(loc="upper right", fontsize=9.5)
    ax1.annotate("strikes stay in step:\ncadence agrees within 9%", xy=(0.83, 0.2),
                 xytext=(0.55, 3.5), color=MUTED, fontsize=9.5, fontweight="bold")

    # --- bottom: single strike aligned at touchdown ---
    for F, c, lab, dts, z in [(Fmj, C_MJ, "MuJoCo", 0.005, 4),
                              (Fimp, C_IMP, "IsaacSim 32/1", 0.005, 3),
                              (Ffix, C_FIX, "IsaacSim 4/8", 0.005, 2)]:
        i = rep_strike(F)
        lo, hi = i-3, i+13
        seg = F[lo:hi]
        tms = (np.arange(lo, hi) - i) * dts * 1000.0
        ax2.plot(tms, seg, color=c, lw=2.2, marker="o", ms=4.5, label=lab,
                 zorder=z, solid_capstyle="round")
    ax2.axvline(0, color=C_GREY, lw=1.0, ls="--")
    ax2.text(0.7, 3.9, "touchdown", color=MUTED, fontsize=9, rotation=90, va="top")
    # annotate the ~20 ms MuJoCo spread
    ax2.annotate("", xy=(0, 1.25), xytext=(20, 1.25),
                 arrowprops=dict(arrowstyle="<->", color=C_MJ, lw=1.6))
    ax2.text(10, 1.42, "MuJoCo spreads the strike\nover ~20 ms (solref = 0.02 s, 4 substeps)",
             color=C_MJ, fontsize=9.5, ha="center", fontweight="bold")
    ax2.annotate("PhysX resolves it in\none 5 ms substep → ~2× peak",
                 xy=(0, 2.7), xytext=(6, 3.55), color=C_IMP, fontsize=9.5, fontweight="bold",
                 arrowprops=dict(arrowstyle="->", color=C_IMP, lw=1.4))
    ax2.set_xlim(-16, 62); ax2.set_ylim(0, 4.3)
    ax2.set_xlabel("time from touchdown (ms)"); ax2.set_ylabel("foot vertical GRF (BW)")
    ax2.set_title("One foot-strike, aligned at touchdown", fontsize=12, loc="left")
    ax2.legend(loc="upper right", fontsize=9.5)

    fig.tight_layout(pad=1.2)
    fig.savefig(f"{IMG}/sim2sim_grf_waveform.png", dpi=140, bbox_inches="tight")
    plt.close(fig); print("wrote sim2sim_grf_waveform.png")

# =============================================================================
# (b) peak & loading-rate vs solver iterations
# =============================================================================
def plot_b():
    J = {t: load_json(t)["isaac"] for t in
         ["base","b1_pos8vel1","b2_pos32vel4","b3_pos4vel4","b4_pos16vel4",
          "b5_pos2vel4","b6_pos1vel4","b7_pos4vel8","b8_pos4vel16","b9_pos8vel8","b_iters84"]}
    def pk(t): return J[t]["peak_BW_med"]
    def rt(t): return J[t]["rate_BWs_med"]

    fig, (axP, axR) = plt.subplots(1, 2, figsize=(11.6, 5.0))

    # --- Peak vs VELOCITY iterations (position held) ---
    vel_pos32 = [(1, pk("base")), (4, pk("b2_pos32vel4"))]                # pos32
    vel_pos4  = [(4, pk("b3_pos4vel4")), (8, pk("b7_pos4vel8")), (16, pk("b8_pos4vel16"))]
    xv, yv = zip(*vel_pos32); axP.plot(xv, yv, "-o", color=C_MJ, lw=2.2, ms=8,
                                       label="position iters = 32", zorder=4)
    xv2, yv2 = zip(*vel_pos4); axP.plot(xv2, yv2, "--s", color=C_GREY, lw=1.8, ms=7,
                                        label="position iters = 4", zorder=3)
    # MuJoCo band
    axP.axhspan(MJ["peak_BW_p90"]-0.0, MJ["peak_BW_p90"], alpha=0)  # noop keep order
    axP.axhline(MJ["peak_BW_med"], color=C_GREY, lw=1.4, ls=":")
    axP.axhspan(MJ["peak_BW_med"], MJ["peak_BW_p90"], color=C_MJ, alpha=0.10, zorder=1)
    axP.text(16, MJ["peak_BW_med"]-0.06, "MuJoCo reference", color=MUTED, fontsize=9, ha="right")
    # mark imported / fixed
    axP.scatter([1], [pk("base")], s=160, marker="*", color=C_IMP, zorder=6, edgecolor="white", linewidth=0.8)
    axP.annotate("32/1 imported\n1.97× MuJoCo", (1, pk("base")), xytext=(1.4, 2.30),
                 color=C_IMP, fontsize=9.5, fontweight="bold")
    axP.scatter([8], [pk("b7_pos4vel8")], s=160, marker="*", color=C_FIX, zorder=6, edgecolor="white", linewidth=0.8)
    axP.annotate("4/8 fixed\n1.10×", (8, pk("b7_pos4vel8")), xytext=(9.0, 1.62),
                 color=C_FIX, fontsize=9.5, fontweight="bold")
    axP.set_xscale("log", base=2); axP.set_xticks([1,2,4,8,16])
    axP.set_xticklabels(["1","2","4","8","16"])
    axP.set_xlim(0.8, 20); axP.set_ylim(1.0, 2.7)
    axP.set_xlabel("velocity solver iterations"); axP.set_ylabel("peak GRF (BW, median strike)")
    axP.set_title("Peak force ← VELOCITY iterations", fontsize=12, loc="left")
    axP.legend(loc="upper right", fontsize=9.5)

    # --- Loading rate vs POSITION iterations (velocity held = 4) ---
    pos_v4 = [(1, rt("b6_pos1vel4")), (2, rt("b5_pos2vel4")), (4, rt("b3_pos4vel4")),
              (16, rt("b4_pos16vel4")), (32, rt("b2_pos32vel4"))]
    xp, yp = zip(*pos_v4); axR.plot(xp, yp, "-o", color=C_MJ, lw=2.2, ms=8,
                                    label="velocity iters = 4", zorder=4)
    axR.axhline(MJ["rate_BWs_med"], color=C_GREY, lw=1.4, ls=":")
    axR.axhspan(MJ["rate_BWs_p25"], MJ["rate_BWs_p90"], color=C_MJ, alpha=0.10, zorder=1)
    axR.text(32, MJ["rate_BWs_med"]-6, "MuJoCo reference", color=MUTED, fontsize=9, ha="right")
    # imported 32/1 (vel=1, off the vel=4 line) and fixed 4/8 (vel=8)
    axR.scatter([32], [rt("base")], s=170, marker="*", color=C_IMP, zorder=6, edgecolor="white", linewidth=0.8)
    axR.annotate("32/1 imported\n2.92× MuJoCo", (32, rt("base")), xytext=(6.0, 178),
                 color=C_IMP, fontsize=9.5, fontweight="bold",
                 arrowprops=dict(arrowstyle="->", color=C_IMP, lw=1.2))
    axR.scatter([4], [rt("b7_pos4vel8")], s=170, marker="*", color=C_FIX, zorder=6, edgecolor="white", linewidth=0.8)
    axR.annotate("4/8 fixed\n1.14×", (4, rt("b7_pos4vel8")), xytext=(1.3, 60),
                 color=C_FIX, fontsize=9.5, fontweight="bold",
                 arrowprops=dict(arrowstyle="->", color=C_FIX, lw=1.2))
    axR.set_xscale("log", base=2); axR.set_xticks([1,2,4,8,16,32])
    axR.set_xticklabels(["1","2","4","8","16","32"])
    axR.set_xlim(0.8, 40); axR.set_ylim(40, 200)
    axR.set_xlabel("position solver iterations"); axR.set_ylabel("loading rate (BW/s, median strike)")
    axR.set_title("Loading rate ← POSITION iterations", fontsize=12, loc="left")
    axR.legend(loc="upper left", fontsize=9.5)

    fig.suptitle("The knob: the URDF importer silently wrote 32/1 — the worst setting in the sweep",
                 fontsize=12.5, fontweight="bold", x=0.02, ha="left", y=1.00)
    fig.tight_layout(pad=1.1, rect=(0, 0, 1, 0.97))
    fig.savefig(f"{IMG}/sim2sim_solver_iters.png", dpi=140, bbox_inches="tight")
    plt.close(fig); print("wrote sim2sim_solver_iters.png")

# =============================================================================
# (c) cross-engine agreement bars
# =============================================================================
def plot_c():
    imp = load_json("base")["isaac"]
    fix = load_json("abd15_i4x8")["isaac"]      # corrected-arm 4/8
    def ratio(iso, key): return iso[key] / MJ[key]
    rows = [
        ("Loading rate",      ratio(imp,"rate_BWs_med"),        ratio(fix,"rate_BWs_med"),        "solver-dependent"),
        ("Peak GRF",          ratio(imp,"peak_BW_med"),         ratio(fix,"peak_BW_med"),         "solver-dependent"),
        ("60 ms impulse",     ratio(imp,"impulse60ms_BWs_med"), ratio(fix,"impulse60ms_BWs_med"), "unconditional"),
        ("Cadence (strikes)", ratio(imp,"strikes_per_s_per_env"),ratio(fix,"strikes_per_s_per_env"),"unconditional"),
        ("Duty factor",       ratio(imp,"duty"),                ratio(fix,"duty"),                "unconditional"),
    ]
    labels = [r[0] for r in rows]
    imp_r  = [r[1] for r in rows]
    fix_r  = [r[2] for r in rows]
    y = np.arange(len(rows)); h = 0.36

    fig, ax = plt.subplots(figsize=(9.6, 5.4))
    ax.axvspan(0.90, 1.10, color=C_MJ, alpha=0.08, zorder=0)
    ax.axvline(1.0, color=C_GREY, lw=1.6, ls="-", zorder=1)
    ax.text(1.0, len(rows)-0.35, "MuJoCo = 1.0", color=MUTED, fontsize=9.5, ha="center")
    ax.text(1.0, -0.85, "±10% agreement band", color=MUTED, fontsize=8.5, ha="center")

    b1 = ax.barh(y+h/2, imp_r, height=h, color=C_IMP, label="IsaacSim 32/1 (imported)", zorder=3)
    b2 = ax.barh(y-h/2, fix_r, height=h, color=C_FIX, label="IsaacSim 4/8 (fixed)", zorder=3)
    for bars in (b1, b2):
        for b in bars:
            w = b.get_width()
            ax.text(w+0.03, b.get_y()+b.get_height()/2, f"{w:.2f}×",
                    va="center", fontsize=9, color=INK)
    ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=11)
    # bracket the two families
    ax.axhline(1.5, color="#d5d8dc", lw=1.0)
    ax.text(3.05, 3.5, "cross-engine valid\nunconditionally", color=MUTED, fontsize=9.5, va="center", ha="right", fontweight="bold")
    ax.text(3.05, 0.5, "valid only with\nsolver iters stated", color=MUTED, fontsize=9.5, va="center", ha="right", fontweight="bold")
    ax.set_xlim(0, 3.2); ax.set_ylim(-1.0, len(rows)-0.1)
    ax.set_xlabel("ratio to MuJoCo  (1.0 = perfect cross-engine agreement)")
    ax.set_title("What transfers across engines — and what needs the solver setting stated",
                 fontsize=12.5, loc="left")
    ax.legend(loc="lower right", fontsize=10)
    ax.grid(axis="y", visible=False)
    fig.tight_layout(pad=1.1)
    fig.savefig(f"{IMG}/sim2sim_agreement.png", dpi=140, bbox_inches="tight")
    plt.close(fig); print("wrote sim2sim_agreement.png")

# =============================================================================
# (d) tracking / stability
# =============================================================================
def plot_d(mj_trace_path="/home/syaro/pyg_fea/work/sim2sim/mujoco_rp_trace.npz",
           isaac_trace_path=f"{SWEEP}/isaac_grf_pygmalion_v3_printed_sim2sim_rp_i4x8_traces.npz"):
    tr = np.load(isaac_trace_path, allow_pickle=True)
    ti = tr["t_ctrl"]; vxi = tr["vx_b"]; bzi = tr["base_z"]
    mj = np.load(mj_trace_path, allow_pickle=True) if os.path.exists(mj_trace_path) else None
    tmax = float(ti.max())

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.6, 6.6), sharex=True)

    # command profile: 2 s linear ramp to 1.6
    tc = np.linspace(0, tmax, 400)
    cmd = np.clip(tc/2.0, 0, 1)*1.6
    ax1.plot(tc, cmd, color=C_GREY, lw=1.8, ls="--", label="command (1.6 m/s, 2 s ramp)", zorder=2)
    if mj is not None:
        ax1.plot(mj["t_ctrl"], mj["vx_b"], color=C_MJ, lw=1.5, label="MuJoCo", zorder=3)
    ax1.plot(ti, vxi, color=C_FIX, lw=1.5, label="IsaacSim 4/8", zorder=4)
    ax1.set_ylim(-0.2, 2.35); ax1.set_ylabel("forward velocity  $v_x$ (m/s)")
    ax1.set_title("The gait is stable and tracks command in both engines (no falls)",
                  fontsize=12.5, loc="left")
    ax1.legend(loc="lower right", fontsize=9, ncol=3)
    ax1.text(4.6, 0.30, "mean $v_x$: MuJoCo 1.73,  Isaac 1.72 m/s  (both oscillate within a stride)",
             color=MUTED, fontsize=9)

    if mj is not None:
        ax2.plot(mj["t_ctrl"], mj["base_z"], color=C_MJ, lw=1.5, label="MuJoCo", zorder=3)
    ax2.plot(ti, bzi, color=C_FIX, lw=1.5, label="IsaacSim 4/8", zorder=4)
    ax2.set_ylim(0.82, 0.93); ax2.set_xlim(0, tmax)
    ax2.set_xlabel("time (s)"); ax2.set_ylabel("base height (m)")
    ax2.set_title("Base height holds ~0.87 m in both engines", fontsize=11.5, loc="left")
    ax2.legend(loc="lower right", fontsize=9.5, ncol=2)

    fig.tight_layout(pad=1.1)
    fig.savefig(f"{IMG}/sim2sim_tracking.png", dpi=140, bbox_inches="tight")
    plt.close(fig); print("wrote sim2sim_tracking.png")

if __name__ == "__main__":
    import sys
    mjp = sys.argv[1] if len(sys.argv) > 1 else None
    plot_a(); plot_b(); plot_c(); plot_d(mj_trace_path=mjp)
    print("done ->", IMG)
