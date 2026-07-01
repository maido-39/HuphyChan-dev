"""Analyse how the measured loads evolve over training.

Reads analysis/out/prog/prog_<iter>.npz (one per 6000-iter checkpoint, produced
by progression.sh) and plots the key analysed quantities vs training iteration,
then writes/refreshes the progression note. Re-run as new checkpoints are added.

Usage:
  uv run python analysis/progression_analyze.py --out <docs/mujoco/assets> \
      --note <docs/mujoco/2026-07-01_training_progression.md>
"""

from __future__ import annotations

import argparse
import glob
import os
import re

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RAD2RPM = 60.0 / (2.0 * np.pi)
SPEC = {  # (peak N*m, rated N*m, speed-limit rpm)
    "hip_pitch": (120.0, 40.0, 143.0), "hip_roll": (120.0, 40.0, 143.0),
    "hip_yaw": (60.0, 20.0, 191.0), "knee": (120.0, 40.0, 143.0),
    "ankle_pitch": (60.0, 20.0, 191.0), "ankle_roll": (14.0, 5.0, 315.0),
}
JT = ["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll"]


def metrics(d):
    """Scalar load metrics for one checkpoint's rollout."""
    m = {}
    for jt in JT:
        pk, rt, vl = SPEC[jt]
        agg = {}
        for s in ("L", "R"):
            jn = f"{s}_{jt}_joint"
            if "tau_" + jn not in d.files:
                continue
            t = np.abs(d["tau_" + jn]); o = np.abs(d["omega_" + jn]) * RAD2RPM
            # torque -> % of peak; speed -> % of limit; keep max/p95/RMS, worst of L/R
            for nm, val, lim in [
                ("tq_pk", t.max(), pk), ("tq_p99", np.percentile(t, 99), pk),
                ("tq_p95", np.percentile(t, 95), pk), ("tq_rms", np.sqrt(np.mean(t ** 2)), pk),
                ("sp_pk", o.max(), vl), ("sp_p99", np.percentile(o, 99), vl),
                ("sp_p95", np.percentile(o, 95), vl), ("sp_rms", np.sqrt(np.mean(o ** 2)), vl)]:
                agg[nm] = max(agg.get(nm, 0.0), 100 * val / lim)
        for nm, v in agg.items():
            m[f"{jt}_{nm}"] = v
    # GRF + foot force
    gmag = [d[k] for k in ("GRF_L_foot_link_mag", "GRF_R_foot_link_mag") if k in d.files]
    if gmag:
        allg = np.concatenate(gmag)
        m["GRF_peak"] = float(np.max([g.max() for g in gmag]))
        m["GRF_p99"] = float(np.percentile(allg, 99))
        m["GRF_p95"] = float(np.percentile(allg, 95))
    fF = []
    for b in ("L_foot_link", "R_foot_link"):
        if "Fx_" + b in d.files:
            fF.append(np.sqrt(d["Fx_" + b] ** 2 + d["Fy_" + b] ** 2 + d["Fz_" + b] ** 2).max())
    if fF:
        m["footF_peak"] = float(max(fF))
    # total mechanical power (sum |tau*omega| over actuated joints)
    P = None
    for jt in JT:
        for s in ("L", "R"):
            jn = f"{s}_{jt}_joint"
            if "Pmech_" + jn in d.files:
                p = np.abs(d["Pmech_" + jn])
                P = p if P is None else P + p
    if P is not None:
        m["power_peak"] = float(P.max()); m["power_rms"] = float(np.sqrt(np.mean(P ** 2)))
    m["base_mean"] = float(d["base_height"].mean()) if "base_height" in d.files else np.nan
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prog-dir", default="analysis/out/prog")
    ap.add_argument("--out", required=True)
    ap.add_argument("--note", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    files = sorted(glob.glob(os.path.join(args.prog_dir, "prog_*.npz")),
                   key=lambda f: int(re.search(r"prog_(\d+)", f).group(1)))
    rows = []
    for f in files:
        it = int(re.search(r"prog_(\d+)", f).group(1))
        d = np.load(f, allow_pickle=True)
        r = {"iter": it, **metrics(d)}
        rows.append(r)
    if not rows:
        print("[prog] no prog_*.npz yet"); return
    its = [r["iter"] for r in rows]

    def col(k):
        return [r.get(k, np.nan) for r in rows]

    # ---- trend plot (parametrised by percentile: p95 or p99) ----
    JOINTS = [("ankle_pitch", "#c0392b"), ("knee", "#2980b9"),
              ("ankle_roll", "#e67e22"), ("hip_pitch", "#27ae60")]

    def trend_plot(pct, fname):
        fig, ax = plt.subplots(3, 3, figsize=(17, 11))
        a = ax.ravel()
        panels = [("tq_pk", "torque max %peak"), (f"tq_{pct}", f"torque {pct} %peak"),
                  ("tq_rms", "torque RMS %peak"), ("sp_pk", "speed max %limit"),
                  (f"sp_{pct}", f"speed {pct} %limit"), ("sp_rms", "speed RMS %limit")]
        for i, (mk, ttl) in enumerate(panels):
            for jt, c in JOINTS:
                a[i].plot(its, col(f"{jt}_{mk}"), "o-", color=c, label=jt, ms=3)
            a[i].axhline(100, color="k", ls="--", lw=0.8)
            a[i].set_title(ttl); a[i].set_ylabel("%")
            if i == 0:
                a[i].legend(fontsize=6)
        a[6].plot(its, col("GRF_peak"), "o-", color="#c0392b", label="peak", ms=3)
        a[6].plot(its, col(f"GRF_{pct}"), "s-", color="#e67e22", label=pct, ms=3)
        a[6].axhspan(1500, 2700, color="#e03030", alpha=0.1)
        a[6].set_title("foot GRF |F| [N]"); a[6].legend(fontsize=6)
        a[7].plot(its, col("power_peak"), "o-", color="#8e44ad", label="peak", ms=3)
        a[7].plot(its, col("power_rms"), "s-", color="#9b59b6", label="RMS", ms=3)
        a[7].set_title("total mech. power |Στω| [W]"); a[7].legend(fontsize=6)
        a[8].plot(its, col("base_mean"), "o-", color="#34495e", ms=3)
        a[8].set_title("base height mean [m]")
        for x in a:
            x.set_xlabel("training iteration"); x.grid(alpha=.3)
        fig.suptitle(f"Load evolution over training (flat, wide-DR) — torque/speed max·{pct}·RMS",
                     fontsize=13)
        fig.tight_layout(rect=[0, 0, 1, 0.97])
        fig.savefig(os.path.join(args.out, fname), dpi=100); plt.close(fig)

    trend_plot("p95", "progression_trends.png")
    trend_plot("p99", "progression_trends_p99.png")

    # ---- markdown table (torque/speed max·p95·RMS for the two bottleneck joints) ----
    keys = ["ankle_pitch_tq_pk", "ankle_pitch_tq_p95", "ankle_pitch_tq_rms",
            "ankle_pitch_sp_pk", "ankle_pitch_sp_p95", "ankle_pitch_sp_rms",
            "knee_sp_pk", "knee_sp_p95", "knee_sp_rms",
            "GRF_peak", "GRF_p95", "power_peak", "power_rms", "base_mean"]
    hdr = "| iter | " + " | ".join(k.replace("_", " ") for k in keys) + " |"
    sep = "|" + "---|" * (len(keys) + 1)
    lines = [hdr, sep]
    for r in rows:
        vals = " | ".join(f"{r.get(k, float('nan')):.0f}" if not k.startswith("base")
                          else f"{r.get(k, float('nan')):.3f}" for k in keys)
        lines.append(f"| {r['iter']} | {vals} |")
    table = "\n".join(lines)

    # deltas first->last for the auto-summary
    def delta(k):
        v0, v1 = rows[0].get(k), rows[-1].get(k)
        if v0 is None or v1 is None:
            return "?"
        fmt = "{:.3f}→{:.3f}" if k.startswith("base") else "{:.0f}→{:.0f}"
        return fmt.format(v0, v1)

    note = f"""# 학습 진행에 따른 부하 변화 (progression) — flat

> 3000 iter마다 체크포인트를 flat wide-DR로 검증해, 앞서 분석한 값들이 학습에 따라 어떻게 변하는지 추적.
> 도구: `analysis/progression.sh`(측정) + `analysis/progression_analyze.py`(추세/노트). 재실행 시 새 체크포인트 자동 추가.
> 커버 iter: {its}  ·  각 {int(np.load(files[0])['time'].shape[0])} step wide-DR (vx[-2,3]·vy±1·yaw±0.7).

![progression trends (p95)](assets/progression_trends.png)
![progression trends (p99)](assets/progression_trends_p99.png)

> 위=p95판, 아래=**p99판**(상위 1%, max에 더 근접·스파이크에 민감하나 단일 max보다 robust).

## 지표 추세 (iter별)
{table}

- `tq_*` = 토크 %peak, `sp_*` = 속도 %limit, 각 max/p95/rms. GRF [N], power [W], base [m]. (전부 flat wide-DR)
- ★ 관절별 **토크·속도 max/p95/RMS 6패널**은 위 플롯 참조 (표는 병목 2관절만).

## 자동 요약 (첫→끝 iter {its[0]}→{its[-1]}, max/p95/rms)
- ankle_pitch 토크 %peak: {delta('ankle_pitch_tq_pk')} / {delta('ankle_pitch_tq_p95')} / {delta('ankle_pitch_tq_rms')}
- ankle_pitch 속도 %limit: {delta('ankle_pitch_sp_pk')} / {delta('ankle_pitch_sp_p95')} / {delta('ankle_pitch_sp_rms')}
- knee 속도 %limit: {delta('knee_sp_pk')} / {delta('knee_sp_p95')} / {delta('knee_sp_rms')}
- GRF [N] peak/p95: {delta('GRF_peak')} / {delta('GRF_p95')}
- power [W] peak/RMS: {delta('power_peak')} / {delta('power_rms')} · base: {delta('base_mean')}
"""
    # Preserve the manual "## 해석" section (and below) across regenerations so the
    # watcher's periodic refresh never wipes hand-written interpretation.
    default_manual = (
        "## 해석 (수동 — 데이터 보고 채움)\n"
        "- [학습에 따른 부하 감소/증가/수렴, ankle_pitch·knee 포화, GRF 충격, 효율(power) 추세 서술]\n\n"
        "## 상태\n"
        "- `progression_watch.sh`가 새 6000-배수 체크포인트를 자동 측정하고 이 노트를 갱신(해석 섹션 보존).\n")
    manual = default_manual
    if os.path.exists(args.note):
        old = open(args.note).read()
        i = old.find("## 해석")
        if i >= 0:
            manual = old[i:]
    open(args.note, "w").write(note + "\n" + manual)
    print(f"[prog] {len(rows)} checkpoints -> progression_trends[_p99].png + {args.note}")
    print(table)


if __name__ == "__main__":
    main()
