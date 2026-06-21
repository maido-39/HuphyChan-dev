# -*- coding: utf-8 -*-
"""TensorBoard analysis of a training run — loss / convergence / stability / reward-term health.

Beyond the reward curve, the rsl_rl TensorBoard exposes signals that say WHETHER training is healthy
and HOW to tune the next run:
  * Policy/mean_noise_std   -> exploration->exploitation; should DROP as the policy converges
  * Loss/value_function     -> critic fit (should fall + stabilize)
  * Loss/surrogate, entropy -> PPO step; Loss/learning_rate -> rsl_rl's adaptive LR (KL-driven)
  * Episode_Termination/base_contact vs time_out -> FALL RATE vs survival (gait stability!)
  * Metrics/.../error_vel_* + Curriculum/command_vel_x -> tracking vs the command curriculum
  * Episode_Reward/<term>   -> which terms dominate / fight

Produces <tag>_tensorboard.png (6-panel) + <tag>_tensorboard.md (key finals + auto-eval).
Usage: python scripts/analyze_tensorboard.py --run <run_dir> --tag <name> --title "..." --out ../docs/assets
"""

from __future__ import annotations

import argparse
import glob
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from tensorboard.backend.event_processing import event_accumulator  # noqa: E402


def load(run):
    evs = sorted(glob.glob(os.path.join(run, "events.out.tfevents.*")), key=os.path.getmtime)
    ea = event_accumulator.EventAccumulator(evs[-1], size_guidance={"scalars": 0}); ea.Reload()
    out = {}
    for t in ea.Tags()["scalars"]:
        s = ea.Scalars(t)
        out[t] = (np.array([x.step for x in s]), np.array([x.value for x in s]))
    return out


def ema(y, a=0.1):
    if len(y) == 0:
        return y
    out = np.empty_like(y, dtype=float); out[0] = y[0]
    for i in range(1, len(y)):
        out[i] = a * y[i] + (1 - a) * out[i - 1]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--tag", default="run")
    ap.add_argument("--title", default=None)
    ap.add_argument("--out", default="../docs/assets")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    title = args.title or args.tag
    d = load(args.run)

    def g(t):
        return d.get(t, (np.array([]), np.array([])))

    fig, ax = plt.subplots(2, 3, figsize=(17, 9))
    # (0,0) reward + episode length (twin)
    x, y = g("Train/mean_reward"); ax[0, 0].plot(x, y, color="#bbb", lw=.8); ax[0, 0].plot(x, ema(y), color="#2980b9", label="reward")
    ax[0, 0].set_title("Mean reward (EMA)"); ax[0, 0].set_xlabel("iter"); ax[0, 0].grid(alpha=.3)
    a2 = ax[0, 0].twinx(); xe, ye = g("Train/mean_episode_length"); a2.plot(xe, ye, color="#27ae60", lw=1, label="ep_len")
    a2.set_ylabel("ep_len", color="#27ae60")
    # (0,1) convergence: noise_std + LR
    x, y = g("Policy/mean_noise_std"); ax[0, 1].plot(x, y, color="#8e44ad", label="noise_std")
    ax[0, 1].set_title("Convergence: action noise_std (low=converged) + LR"); ax[0, 1].set_xlabel("iter"); ax[0, 1].grid(alpha=.3); ax[0, 1].legend(loc="upper left", fontsize=8)
    a2 = ax[0, 1].twinx(); xl, yl = g("Loss/learning_rate"); a2.plot(xl, yl, color="#e67e22", lw=.8); a2.set_ylabel("LR", color="#e67e22")
    # (0,2) losses
    for t, c in [("Loss/value_function", "#c0392b"), ("Loss/surrogate", "#2980b9"), ("Loss/entropy", "#7f8c8d")]:
        x, y = g(t)
        if len(x):
            ax[0, 2].plot(x, ema(y), color=c, label=t.split("/")[-1])
    ax[0, 2].set_title("PPO losses (EMA)"); ax[0, 2].set_xlabel("iter"); ax[0, 2].set_yscale("symlog"); ax[0, 2].legend(fontsize=8); ax[0, 2].grid(alpha=.3)
    # (1,0) tracking error + curriculum
    for t, c in [("Metrics/base_velocity/error_vel_xy", "#c0392b"), ("Metrics/base_velocity/error_vel_yaw", "#e67e22")]:
        x, y = g(t)
        if len(x):
            ax[1, 0].plot(x, ema(y), color=c, label=t.split("/")[-1])
    ax[1, 0].set_title("Tracking error (low=good) + curriculum"); ax[1, 0].set_xlabel("iter"); ax[1, 0].legend(loc="upper right", fontsize=8); ax[1, 0].grid(alpha=.3)
    a2 = ax[1, 0].twinx(); xc, yc = g("Curriculum/command_vel_x"); a2.plot(xc, yc, color="#16a085", lw=1, ls="--"); a2.set_ylabel("cmd vx ceil", color="#16a085")
    # (1,1) termination: falls vs timeout
    xf, yf = g("Episode_Termination/base_contact"); xt, yt = g("Episode_Termination/time_out")
    if len(xf):
        ax[1, 1].plot(xf, ema(yf), color="#c0392b", label="base_contact (fall)")
    if len(xt):
        ax[1, 1].plot(xt, ema(yt), color="#27ae60", label="time_out (survive)")
    ax[1, 1].set_title("Termination: falls vs survival"); ax[1, 1].set_xlabel("iter"); ax[1, 1].legend(fontsize=8); ax[1, 1].grid(alpha=.3)
    # (1,2) reward-term final contributions (top by |.|)
    terms = {k.split("/")[-1]: v[1][-1] for k, v in d.items() if k.startswith("Episode_Reward/") and len(v[1])}
    top = sorted(terms.items(), key=lambda kv: abs(kv[1]), reverse=True)[:12]
    names = [k for k, _ in top]; vals = [v for _, v in top]
    ax[1, 2].barh(range(len(top)), vals, color=["#27ae60" if v > 0 else "#c0392b" for v in vals])
    ax[1, 2].set_yticks(range(len(top))); ax[1, 2].set_yticklabels(names, fontsize=7); ax[1, 2].invert_yaxis()
    ax[1, 2].set_title("Reward term contributions (final)"); ax[1, 2].grid(alpha=.3, axis="x")
    fig.suptitle(f"Training TensorBoard — {title}", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    png = os.path.join(args.out, f"{args.tag}_tensorboard.png"); fig.savefig(png, dpi=95); plt.close(fig)

    # --- auto-eval ---
    def last(t, default=float("nan")):
        v = g(t)[1]
        return float(v[-1]) if len(v) else default

    def first(t, default=float("nan")):
        v = g(t)[1]
        return float(v[0]) if len(v) else default

    ns0, ns1 = first("Policy/mean_noise_std"), last("Policy/mean_noise_std")
    fall = last("Episode_Termination/base_contact"); surv = last("Episode_Termination/time_out")
    md = [f"# Training TensorBoard 분석 — {title}", "", f"![tb](assets/{os.path.basename(png)})", "",
          "## 자동 평가 (정량)",
          f"- **수렴(noise_std)**: {ns0:.2f} → **{ns1:.2f}** ({'수렴 ✅' if ns1 < ns0 * 0.85 and ns1 < 0.6 else ('미수렴·탐색↑ ⚠️ (std 증가)' if ns1 > ns0 * 1.05 else '정체 ~')})",
          f"- **mean_reward**: {first('Train/mean_reward'):.1f} → **{last('Train/mean_reward'):.1f}**, ep_len 최종 **{last('Train/mean_episode_length'):.0f}**",
          f"- **추종 error_vel_xy**: 최종 **{last('Metrics/base_velocity/error_vel_xy'):.3f}** (낮을수록 good), yaw {last('Metrics/base_velocity/error_vel_yaw'):.3f}",
          f"- **안정성 낙상률 {100 * fall / (fall + surv + 1e-9):.0f}%** (base_contact {fall:.2f} / time_out {surv:.2f}) "
          f"({'안정 ✅' if 100 * fall / (fall + surv + 1e-9) < 5 else ('주의 ⚠️' if 100 * fall / (fall + surv + 1e-9) < 15 else '낙상多 ❌')})",
          f"- **value loss 최종** {last('Loss/value_function'):.3f}, entropy {last('Loss/entropy'):.3f}, LR {last('Loss/learning_rate'):.1e}",
          f"- **커리큘럼 vx 상한 최종** {last('Curriculum/command_vel_x'):.2f}",
          "", "## 해석 (정성) — **[작성 필요: 위 수치로 학습이 잘 됐나/다음 튜닝]**", ""]
    open(os.path.join(args.out, f"{args.tag}_tensorboard.md"), "w").write("\n".join(md) + "\n")
    print(f"[tb] wrote {png} + .md")
    print("\n".join(md[:12]))


if __name__ == "__main__":
    main()
