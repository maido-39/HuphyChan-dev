# -*- coding: utf-8 -*-
"""Human-likeness check: compare a run's measured joint trajectories to the human normative gait reference.

This is the user's "참고용으로 쓰던지" (use the human gait as a reference to check whether it walked properly):
works on ANY measured run (logs/measure/<tag>.npz) regardless of the training reward — quantifies how human-like
the gait is and exposes the tiptoe/shuffle failure (small joint range vs human).

Method: detect gait cycles from foot vertical GRF (contact onset = phase 0), resample each cycle's joint angles to
0-100%, average over cycles (mean +- std band), and overlay vs the retargeted human reference (gait_reference.py).
Per sagittal joint reports: RMS error [rad], RANGE RATIO (robot range / human range; <1 = shuffle), and shape
CORRELATION. Overall human-likeness = mean correlation gated by range ratio.
    python scripts/gait_humanlikeness.py <tag> [<tag2> ...]      # e.g. g1is_dm4340_flat
"""
from __future__ import annotations
import os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "source", "pygmalion_locomotion", "tasks", "locomotion"))
import gait_reference as GR  # numpy-only module; safe to import standalone

BW = 51.8 * 9.81  # body weight [N]
SAGITTAL = ["hip_pitch", "knee", "ankle_pitch"]  # the joints the human reference defines
NPH = 100


def detect_cycles(grf_z, fz_thresh):
    """Return cycle-start indices = rising edges of foot contact (GRF crosses above thresh)."""
    c = grf_z > fz_thresh
    starts = np.where((~c[:-1]) & (c[1:]))[0] + 1
    # drop too-short cycles (debounce): keep starts separated by >= 10 samples
    keep = [starts[0]] if len(starts) else []
    for s in starts[1:]:
        if s - keep[-1] >= 10:
            keep.append(s)
    return np.array(keep)


def resample_cycles(sig, starts, n=NPH):
    """Resample each [starts[i], starts[i+1]) segment of sig to n phase points -> [n_cycles, n]."""
    out = []
    for a, b in zip(starts[:-1], starts[1:]):
        seg = sig[a:b]
        if len(seg) < 5:
            continue
        xp = np.linspace(0, 1, len(seg))
        out.append(np.interp(np.linspace(0, 1, n), xp, seg))
    return np.array(out) if out else np.zeros((0, n))


def _extra_metrics(d):
    """Energy/toe/force/symmetry metrics the user cares about (CoT, toe-use, peak GRF, L/R asymmetry)."""
    import numpy as np
    m = {}
    # toe USE: passive-toe deflection range [rad] (windlass loads the toe -> it bends; ~0 = unused)
    for leg in ("L", "R"):
        key = f"qpos_{leg}_toe_joint"
        if key in d.files:
            toe = d[key]
            m[f"toe_range_{leg}"] = float(toe.max() - toe.min())
    # ENERGY: cost of transport = mean sum_j|tau*omega| / (m*g*v)  (dimensionless; lower = more efficient)
    power = None
    for k in d.files:
        if k.startswith("tau_"):
            jn = k[4:]
            if f"omega_{jn}" in d.files:
                p = np.abs(d[k] * d[f"omega_{jn}"])
                power = p if power is None else power + p
    m["mech_power_W"] = float(np.mean(power)) if power is not None else 0.0
    vmean = float(np.mean(np.abs(d["cmd_vx"]))) if "cmd_vx" in d.files else 0.0
    m["cot"] = m["mech_power_W"] / (BW * max(vmean, 0.1))
    # FORCE: peak vertical GRF vs the HW break limit (1.5-2.7 kN)
    gl = np.abs(d["GRF_L_foot_link_z"]); gr = np.abs(d["GRF_R_foot_link_z"])
    m["peak_grf_N"] = float(max(gl.max(), gr.max()))
    m["peak_grf_BW"] = m["peak_grf_N"] / BW
    # SYMMETRY: GRF impulse L/R asymmetry (0 = symmetric, ->1 = limping)
    iL, iR = float(gl.sum()), float(gr.sum())
    m["grf_asym"] = abs(iL - iR) / (iL + iR + 1e-6)
    return m


def analyze(tag):
    f = os.path.join(ROOT, "logs", "measure", f"{tag}.npz")
    if not os.path.exists(f):
        print(f"[{tag}] npz 없음: {f}"); return None
    d = np.load(f, allow_pickle=True)
    # pick the busier foot for cycle detection
    grfL, grfR = np.abs(d["GRF_L_foot_link_z"]), np.abs(d["GRF_R_foot_link_z"])
    grf = grfL if grfL.std() >= grfR.std() else grfR
    side = "L" if grfL.std() >= grfR.std() else "R"
    starts = detect_cycles(grf, fz_thresh=0.1 * BW)
    if len(starts) < 3:
        print(f"[{tag}] 주기 부족({len(starts)})"); return None
    ph = np.linspace(0, 1, NPH)
    results = {}
    for leg in ("L", "R"):
        for j in SAGITTAL:
            q = d[f"qpos_{leg}_{j}_joint"]
            cyc = resample_cycles(q, starts)
            if cyc.shape[0] == 0:
                continue
            mean, std = cyc.mean(0), cyc.std(0)
            # human reference for this joint+leg (R = phase+0.5)
            php = ph + (0.5 if leg == "R" else 0.0)
            hl, _, _hk = None, None, None
            ref = np.array([GR.leg_targets_rad(p) for p in php])[:, GR._LEG.index(j)]
            rms = float(np.sqrt(np.mean((mean - ref) ** 2)))
            rng_robot = float(mean.max() - mean.min())
            rng_ref = float(ref.max() - ref.min())
            ratio = rng_robot / rng_ref if rng_ref > 1e-6 else 0.0
            corr = float(np.corrcoef(mean, ref)[0, 1]) if mean.std() > 1e-6 else 0.0
            results[f"{leg}_{j}"] = dict(mean=mean, std=std, ref=ref, rms=rms, ratio=ratio, corr=corr)
    return dict(tag=tag, side=side, ncyc=len(starts) - 1, ph=ph, results=results, extra=_extra_metrics(d))


def report_and_plot(analyses):
    analyses = [a for a in analyses if a]
    if not analyses:
        print("분석 결과 없음"); return
    # text report
    for a in analyses:
        print(f"\n=== {a['tag']} (cycle-detect foot {a['side']}, {a['ncyc']} cycles) ===")
        corrs, ratios = [], []
        for k in [f"{leg}_{j}" for leg in ("L", "R") for j in SAGITTAL]:
            r = a["results"].get(k)
            if not r:
                continue
            print(f"  {k:16s} RMS {r['rms']:.3f} rad | range_ratio {r['ratio']:.2f} (robot/human) | corr {r['corr']:+.2f}")
            corrs.append(r["corr"]); ratios.append(r["ratio"])
        score = float(np.mean(corrs) * np.clip(np.mean(ratios), 0, 1)) if corrs else 0.0
        print(f"  -> human-likeness score = {score:.2f} (mean corr x min(1,mean range_ratio); 1.0=human, ~0=shuffle/tiptoe)")
        e = a.get("extra", {})
        if e:
            tr = f"L{e.get('toe_range_L', 0):.3f} R{e.get('toe_range_R', 0):.3f}"
            print(f"     energy/toe: CoT {e['cot']:.2f} ({e['mech_power_W']:.0f}W) | toe-use(range rad) {tr} | "
                  f"peak GRF {e['peak_grf_N']:.0f}N ({e['peak_grf_BW']:.1f}xBW) | GRF L/R asym {e['grf_asym']:.2f}")
        a["score"] = score
    # plot: rows = sagittal joint, cols = L|R; robot mean+-band vs human ref
    fig, ax = plt.subplots(len(SAGITTAL), 2, figsize=(12, 3.0 * len(SAGITTAL)), dpi=130, squeeze=False)
    colors = plt.cm.tab10(np.linspace(0, 1, max(len(analyses), 3)))
    for ri, j in enumerate(SAGITTAL):
        for ci, leg in enumerate(("L", "R")):
            axx = ax[ri][ci]
            for ai, a in enumerate(analyses):
                r = a["results"].get(f"{leg}_{j}")
                if not r:
                    continue
                x = a["ph"] * 100
                axx.plot(x, r["mean"], color=colors[ai], lw=1.6, label=f"{a['tag']} (rr {r['ratio']:.2f})")
                axx.fill_between(x, r["mean"] - r["std"], r["mean"] + r["std"], color=colors[ai], alpha=0.15)
                if ai == 0:
                    axx.plot(x, r["ref"], "k--", lw=1.8, label="human ref")
            axx.axvline(60, color="gray", ls=":", lw=0.8)
            axx.set_title(f"{leg}_{j}", fontsize=10)
            axx.set_xlabel("gait cycle [%]"); axx.set_ylabel("angle [rad]")
            axx.grid(alpha=0.3); axx.legend(fontsize=7)
    fig.suptitle("Gait human-likeness: robot joint trajectories vs human reference (heel-strike aligned)", fontsize=12)
    fig.tight_layout()
    out = "/tmp/gait_humanlikeness.png"
    fig.savefig(out)
    print(f"\n[humanlikeness] saved {out}")


if __name__ == "__main__":
    tags = sys.argv[1:] or ["g1is_dm4340_flat"]
    report_and_plot([analyze(t) for t in tags])
