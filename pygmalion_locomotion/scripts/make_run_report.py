# -*- coding: utf-8 -*-
"""Generate a reproducible training-run report + back up configs.

RULE (see memory feedback-training-report-rule): every training run gets a report at
docs/experiments/<run>.md with reproducibility, config backup, metrics, plots, parent-comparison,
analysis, and dynamic links. This script does the mechanical parts; the analysis/links sections are
left as TODO for a human/agent to complete.

Usage:
  python scripts/make_run_report.py --run logs/rsl_rl/pygmalion_flat/<ts>_<name> \
     --log logs/<name>.log [--parent_run <dir> --parent_log <log>] \
     [--measure ../docs/assets/<tag>_motor_util.png] [--cmd "<train cmd>"] [--note "<intent>"]

Backs up spec/robot/env/agent cfg into <run>/repro/, parses the console log for the reward curve +
final metrics + reward-term breakdown, plots the reward curve (with parent overlay if given), diffs
the backed-up cfg vs the parent's, and writes docs/experiments/<name>.md.
"""

from __future__ import annotations

import argparse
import difflib
import glob
import os
import re
import shutil

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

WS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROOT = os.path.abspath(os.path.join(WS, ".."))
BACKUP_FILES = [
    "pygmalion_locomotion/assets/robot_specs/robstride_biped.yaml",
    "pygmalion_locomotion/assets/biped_lower_body_mjcf/robot.xml",
    "pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/velocity_env_cfg.py",
    "pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/flat_env_cfg.py",
    "pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/curriculums.py",
    "pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/agents/rsl_rl_ppo_cfg.py",
]
OBS_NOTE = ("base_lin_vel(3)+base_ang_vel(3)+projected_gravity(3)+velocity_commands(3)+joint_pos(14)"
            "+joint_vel(14)+last_action(12)+height_scan(187) = 239 dims; enable_corruption=obs noise")
ACTION_NOTE = "12 actuated joint position targets (hip pitch/roll/yaw, knee, ankle pitch/roll x2); passive toe excluded"


def parse_log(logp):
    """Return (iters, rewards, final_metrics dict, reward_terms dict)."""
    iters, rewards = [], []
    metrics, terms = {}, {}
    if not logp or not os.path.exists(logp):
        return iters, rewards, metrics, terms
    txt = open(logp, errors="ignore").read()
    for m in re.finditer(r"Learning iteration\s+(\d+)/\d+.*?Mean reward:\s*([-\d.]+)", txt, re.S):
        iters.append(int(m.group(1))); rewards.append(float(m.group(2)))
    for key in ["error_vel_xy", "error_vel_yaw"]:
        mm = re.findall(rf"{key}:\s*([-\d.]+)", txt)
        if mm:
            metrics[key] = float(mm[-1])
    mm = re.findall(r"command_vel_x:\s*([-\d.]+)", txt)
    if mm:
        metrics["curriculum_vel_x"] = float(mm[-1])
    for m in re.finditer(r"Episode_Reward/(\S+):\s*([-\d.]+)", txt):
        terms[m.group(1)] = float(m.group(2))  # last wins
    return iters, rewards, metrics, terms


def backup(run):
    repro = os.path.join(run, "repro")
    os.makedirs(repro, exist_ok=True)
    manifest = []
    for rel in BACKUP_FILES:
        src = os.path.join(ROOT, rel)
        if os.path.exists(src):
            dst = os.path.join(repro, os.path.basename(src))
            shutil.copy2(src, dst)
            manifest.append(f"{os.path.basename(src)}  <-  {rel}")
    return repro, manifest


def cfg_diff(run, parent_run, fname="velocity_env_cfg.py"):
    a = os.path.join(parent_run, "repro", fname); b = os.path.join(run, "repro", fname)
    if not (os.path.exists(a) and os.path.exists(b)):
        return None
    da, db = open(a).readlines(), open(b).readlines()
    d = [ln.rstrip() for ln in difflib.unified_diff(da, db, fromfile="parent/" + fname, tofile="this/" + fname, n=1)
         if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))]
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--log", default=None)
    ap.add_argument("--parent_run", default=None)
    ap.add_argument("--parent_log", default=None)
    ap.add_argument("--measure", default=None, help="path to a motor_util png to embed")
    ap.add_argument("--cmd", default=None)
    ap.add_argument("--note", default=None, help="intent / what changed vs parent")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs/experiments"))
    ap.add_argument("--assets", default=os.path.join(ROOT, "docs/assets"))
    args = ap.parse_args()

    run = os.path.abspath(args.run)
    name = os.path.basename(run.rstrip("/"))
    os.makedirs(args.out, exist_ok=True); os.makedirs(args.assets, exist_ok=True)

    repro, manifest = backup(run)
    if args.cmd:
        open(os.path.join(repro, "cmd.txt"), "w").write(args.cmd + "\n")
    elif os.path.exists(os.path.join(repro, "cmd.txt")):
        args.cmd = open(os.path.join(repro, "cmd.txt")).read().strip()

    iters, rewards, metrics, terms = parse_log(args.log)
    pit, prew, _, _ = parse_log(args.parent_log) if args.parent_log else ([], [], {}, {})

    # reward curve plot (+ parent overlay)
    rew_png = None
    if rewards:
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.plot(iters, rewards, label=name, color="#2980b9")
        if prew:
            ax.plot(pit, prew, label="parent: " + os.path.basename(args.parent_run or "parent"), color="#aaa", ls="--")
        ax.set_xlabel("iteration"); ax.set_ylabel("Mean reward"); ax.set_title(f"Reward curve — {name}")
        ax.legend(fontsize=8); ax.grid(alpha=.3)
        rew_png = os.path.join(args.assets, f"{name}_reward.png")
        fig.tight_layout(); fig.savefig(rew_png, dpi=100); plt.close(fig)

    videos = sorted(glob.glob(os.path.join(run, "videos/train/*.mp4")))
    diff = cfg_diff(run, args.parent_run) if args.parent_run else None

    md = [f"# 학습 리포트 — {name}", "",
          f"- **task/run**: `{name}`  ·  **명령**: `{args.cmd or '(미기록)'}`",
          f"- **의도/변경점**: {args.note or '**[작성 필요]**'}", "",
          "## 1. 재현성 (Reproducibility)",
          f"- **OBS**: {OBS_NOTE}",
          f"- **Output(action)**: {ACTION_NOTE}",
          f"- **사용 파일(백업: `{os.path.relpath(repro, ROOT)}/`)**:"]
    md += [f"  - {m}" for m in manifest]
    ckpts = sorted(glob.glob(os.path.join(run, "model_*.pt")), key=os.path.getmtime)
    md += [f"- **체크포인트**: `{os.path.relpath(ckpts[-1], ROOT)}`" if ckpts else "- 체크포인트: (없음)", ""]

    md += ["## 2. 지표 (Metrics)"]
    if rewards:
        md.append(f"- **최종 Mean reward**: {rewards[-1]:.2f} (iter {iters[-1]}), max {max(rewards):.2f}")
    for k, v in metrics.items():
        md.append(f"- **{k}**: {v:.4f}")
    if rew_png:
        md += ["", f"![reward curve](assets/{os.path.basename(rew_png)})"]
    if terms:
        md += ["", "**보상 항목별 기여(최종)**:"]
        md += [f"  - {k}: {v:+.4f}" for k, v in sorted(terms.items(), key=lambda x: x[1])]
    md.append("")

    md += ["## 3. 영상 / 이미지"]
    if videos:
        md.append(f"- 학습 영상 {len(videos)}개: `{os.path.relpath(os.path.dirname(videos[0]), ROOT)}/` (예: {os.path.basename(videos[0])} … {os.path.basename(videos[-1])})")
        acc = os.path.join(run, "accumulated_progress.mp4")
        if os.path.exists(acc):
            md.append(f"- 누적 영상: `{os.path.relpath(acc, ROOT)}`")
    else:
        md.append("- (영상 없음)")
    if args.measure:
        md += [f"- 측정/모터util: ![motor util]({os.path.relpath(args.measure, os.path.join(ROOT,'docs'))})"]
    md.append("")

    if args.parent_run:
        md += ["## 4. 부모 학습 대비 비교",
               f"- **부모**: `{os.path.basename(args.parent_run)}`",
               "- **변경된 설정(velocity_env_cfg diff)**:"]
        if diff:
            md += ["```diff"] + diff[:40] + (["... (생략)"] if len(diff) > 40 else []) + ["```"]
        else:
            md.append("  - (부모 repro 백업 없음 → 수동 기재 **[작성 필요]**)")
        if rew_png:
            md.append(f"- reward 곡선 비교: 위 그래프(부모 점선). **정량 비교 [작성 필요]**: 무엇이 좋아졌나/나빠졌나.")
        md.append("")

    md += ["## 5. 분석 (정성/정량)  **[작성 필요]**",
           "- 정량: gait(추종·CoT)·관절 토크/파워·toe 사용도·진동(>5Hz)·낙상 — 측정 npz/analyze_motor_util 인용.",
           "- 정성: 보행 자연스러움·실패모드·의도한 변경의 효과.", "",
           "## 6. 관련 학습 / 연구 링크  **[작성 필요]**",
           "- 관련 run: [[experiments/<run>]] — *어떤 관계, 무엇을 바꿨고 왜*.",
           "- 활용 연구: [[Paperreview/<slug>]] / docs/16·17·18 — *어떤 결정에 썼는지*.", ""]

    outp = os.path.join(args.out, f"{name}.md")
    open(outp, "w").write("\n".join(md) + "\n")
    print(f"[report] wrote {outp}")
    print(f"[report] backed up {len(manifest)} cfg files -> {repro}")
    if rew_png:
        print(f"[report] reward curve -> {rew_png}")
    print("[report] TODO: fill sections 4(정량비교)/5(분석)/6(링크) by hand.")


if __name__ == "__main__":
    main()
