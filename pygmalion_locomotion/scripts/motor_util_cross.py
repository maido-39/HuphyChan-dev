# -*- coding: utf-8 -*-
"""Cross-experiment motor torque utilization (user 2026-06-25: "how much of the max-torque region did we use?").

For every logs/measure/*.npz and every motor (L+R combined), compute peak/RMS/p95 |tau| and express vs the
RobStride RATED (continuous/thermal) and PEAK (short-term) ratings (docs/28). The key sizing metrics:
  * RMS % of RATED  -> thermal/continuous binding (>100% = overheats at that duty)
  * peak % of PEAK  -> short-term saturation (==100% => pinned at the effort_limit clip = wants MORE)
  * sat%            -> fraction of time within 1% of the peak clip (how often the motor is maxed)
ENGLISH plot labels. Pure numpy/matplotlib.  ->  docs/48 + docs/assets/motor_util_cross.png + CSV.
"""
import os, glob
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEAS = os.path.join(ROOT, "logs", "measure")
ASSET = os.path.join(ROOT, "..", "docs", "assets")
DOCS = os.path.join(ROOT, "..", "docs")

# joint substring -> (RATED, PEAK) N·m  (RobStride, docs/28; knee = direct RS04 g=1.0 current config)
RATING = {"hip_pitch": (40, 120), "hip_roll": (40, 120), "hip_yaw": (20, 60),
          "knee": (40, 120), "ankle_pitch": (20, 60), "ankle_roll": (5, 14)}
ORDER = ["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll"]
KEY = ["gaitfix_v7", "g1van_full", "g1vanilla", "flat_trained_v1", "stage4_clip", "stage4_unclip", "stage5"]


def motor_of(joint):
    for m in ORDER:
        if m in joint:
            return m
    return None


def main():
    files = sorted(glob.glob(os.path.join(MEAS, "*.npz")))
    rows = {}   # exp -> motor -> (peak, rms, p95, sat, rated, peakr)
    for f in files:
        exp = os.path.basename(f)[:-4]
        d = np.load(f, allow_pickle=True)
        taus = {}
        for k in d.files:
            if k.startswith("tau_"):
                m = motor_of(k)
                if m:
                    taus.setdefault(m, []).append(np.abs(np.asarray(d[k], dtype=float)))
        rows[exp] = {}
        for m, arrs in taus.items():
            a = np.concatenate(arrs)
            rated, peak = RATING[m]
            pk = a.max(); rms = np.sqrt(np.mean(a ** 2)); p95 = np.percentile(a, 95)
            sat = 100.0 * np.mean(a >= 0.99 * peak)
            rows[exp][m] = (pk, rms, p95, sat, 100 * rms / rated, 100 * pk / peak)

    # ---- CSV (all experiments, all motors) ----
    csv = ["experiment,motor,rated,peak,tau_peak,tau_rms,tau_p95,sat_pct,rms_pct_rated,peak_pct_peak"]
    for exp in rows:
        for m in ORDER:
            if m in rows[exp]:
                pk, rms, p95, sat, rr, pp = rows[exp][m]
                rated, peak = RATING[m]
                csv.append(f"{exp},{m},{rated},{peak},{pk:.2f},{rms:.2f},{p95:.2f},{sat:.1f},{rr:.0f},{pp:.0f}")
    open(os.path.join(MEAS, "motor_util_cross.csv"), "w").write("\n".join(csv) + "\n")

    # ---- markdown ----
    md = ["# 48 · 전-실험 모터 토크 이용률 — 최대토크영역 사용량 + ankle_roll 모터선정\n",
          "> measure npz의 관절토크(L+R)를 RobStride **rated(연속/열)·peak(순간)**([[28_reward_actuator_fidelity]])와 대조. "
          "`scripts/motor_util_cross.py`. CSV: `logs/measure/motor_util_cross.csv`. ★ NOMINAL(DR off).\n",
          "**핵심 지표**: `RMS%rated`=열/연속 binding(>100%=과열) · `peak%peak`=순간포화(=100%면 effort_limit clip에 붙음=더 원함) · `sat%`=peak에 붙어있는 시간비.\n"]

    # Table A: ankle_roll across ALL experiments
    md.append("\n## A. ankle_roll (RS00: rated 5 / peak 14 N·m) — 전 실험\n")
    md.append("| 실험 | peak | sat% | RMS | **RMS%rated** | peak%peak |")
    md.append("|---|--:|--:|--:|--:|--:|")
    arr = [(exp, rows[exp]["ankle_roll"]) for exp in rows if "ankle_roll" in rows[exp]]
    arr.sort(key=lambda x: -x[1][4])  # by RMS%rated desc
    for exp, (pk, rms, p95, sat, rr, pp) in arr:
        flag = " ⚠" if rr > 130 else ""
        md.append(f"| {exp} | {pk:.1f} | {sat:.0f} | {rms:.1f} | **{rr:.0f}%**{flag} | {pp:.0f}% |")

    # Table B: all motors RMS%rated for key experiments
    md.append("\n## B. 전 모터 RMS%rated (대표 실험) — ankle_roll만 과부하\n")
    keyexps = [e for e in rows if any(k in e for k in KEY)]
    keyexps.sort()
    md.append("| 실험 | " + " | ".join(ORDER) + " |")
    md.append("|---|" + "--:|" * len(ORDER))
    for exp in keyexps:
        cells = []
        for m in ORDER:
            if m in rows[exp]:
                rr = rows[exp][m][4]
                cells.append(f"**{rr:.0f}**" if rr > 100 else f"{rr:.0f}")
            else:
                cells.append("-")
        md.append(f"| {exp} | " + " | ".join(cells) + " |")
    md.append("\n(굵게 = RMS가 연속정격 초과 = 그 듀티서 과열. ankle_roll만 만성 초과; 나머지는 여유.)\n")

    open(os.path.join(DOCS, "48_motor_util_sizing.md"), "w").write("\n".join(md) + "\n")

    # ---- bar plot: RMS%rated per motor, key experiments ----
    fig, ax = plt.subplots(figsize=(12, 5))
    x = np.arange(len(ORDER)); w = 0.8 / max(len(keyexps), 1)
    for i, exp in enumerate(keyexps):
        vals = [rows[exp].get(m, (0, 0, 0, 0, 0, 0))[4] for m in ORDER]
        ax.bar(x + i * w, vals, w, label=exp)
    ax.axhline(100, color="r", ls="--", lw=1.2, label="RATED (continuous) = 100%")
    ax.set_xticks(x + 0.4 - w / 2); ax.set_xticklabels(ORDER, rotation=15)
    ax.set_ylabel("RMS torque [% of RATED]"); ax.set_title("Motor thermal utilization (RMS/rated) — ankle_roll chronically >100%")
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout(); fig.savefig(os.path.join(ASSET, "motor_util_cross.png"), dpi=130); plt.close(fig)
    print("[motor_util] docs/48_motor_util_sizing.md + assets/motor_util_cross.png + CSV")
    print(f"[motor_util] ankle_roll worst RMS%rated: {arr[0][0]} = {arr[0][1][4]:.0f}%  (peak always {arr[0][1][0]:.1f}=clip)")


if __name__ == "__main__":
    main()
