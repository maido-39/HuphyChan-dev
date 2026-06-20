# -*- coding: utf-8 -*-
"""Build a training-progress video from the per-interval clips Isaac Lab saves during
training (`--video`). Each clip gets a step caption in the bottom-right corner, and ALL clips
so far are concatenated into one accumulated video that shows the policy improving over training.

    # during/after training (run anytime — idempotent, regenerates from whatever clips exist):
    python scripts/progress_video.py --run logs/rsl_rl/pygmalion_flat/<run-dir>
    # or point straight at a videos dir:
    python scripts/progress_video.py --videos logs/rsl_rl/pygmalion_flat/<run>/videos/train

Outputs (in the run dir):
    progress/clip_<step>_captioned.mp4   (each clip + caption, cached)
    progress_accumulated.mp4             (all clips concatenated, in step order)

Needs ffmpeg (system). Uses iteration = step // num_steps_per_env for a readable caption.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys


def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def find_videos_dir(run_dir):
    cands = [os.path.join(run_dir, "videos", "train"), os.path.join(run_dir, "videos")]
    for c in cands:
        if os.path.isdir(c) and glob.glob(os.path.join(c, "*.mp4")):
            return c
    # search recursively
    hits = glob.glob(os.path.join(run_dir, "**", "rl-video-step-*.mp4"), recursive=True)
    return os.path.dirname(hits[0]) if hits else None


def step_of(path):
    m = re.search(r"step-(\d+)", os.path.basename(path))
    return int(m.group(1)) if m else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=None, help="training run dir (contains videos/train/)")
    ap.add_argument("--videos", default=None, help="videos dir directly")
    ap.add_argument("--out", default=None, help="output dir (default: run dir or videos parent)")
    ap.add_argument("--steps_per_env", type=int, default=24, help="num_steps_per_env, for step->iter caption")
    ap.add_argument("--fontsize", type=int, default=28)
    args = ap.parse_args()

    if not args.videos:
        if not args.run:
            print("provide --run or --videos"); sys.exit(1)
        args.videos = find_videos_dir(args.run)
        if not args.videos:
            print(f"[progress_video] no clips found under {args.run}"); sys.exit(1)
    out_dir = args.out or (args.run or os.path.dirname(args.videos))
    cap_dir = os.path.join(out_dir, "progress")
    os.makedirs(cap_dir, exist_ok=True)

    clips = sorted(glob.glob(os.path.join(args.videos, "rl-video-step-*.mp4")), key=step_of)
    if not clips:
        clips = sorted(glob.glob(os.path.join(args.videos, "*.mp4")), key=step_of)
    if not clips:
        print(f"[progress_video] no .mp4 in {args.videos}"); sys.exit(1)
    print(f"[progress_video] {len(clips)} clips in {args.videos}")

    # 1) caption each clip (cached) with "iter N (step S)" bottom-right
    captioned = []
    for c in clips:
        s = step_of(c)
        it = s // max(1, args.steps_per_env)
        outc = os.path.join(cap_dir, f"clip_{s:08d}_captioned.mp4")
        if not os.path.exists(outc) or os.path.getmtime(outc) < os.path.getmtime(c):
            label = f"iter {it}  (step {s})"
            vf = (f"drawtext=text='{label}':x=w-tw-12:y=h-th-12:fontsize={args.fontsize}:"
                  f"fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=8")
            r = run(["ffmpeg", "-y", "-i", c, "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                     "-an", outc])
            if r.returncode != 0 or not os.path.exists(outc):
                print(f"[progress_video] caption FAILED for {c}:\n{r.stdout[-600:]}"); sys.exit(1)
        captioned.append(outc)

    # 2) concat (re-encode for safe concat across clips)
    listf = os.path.join(cap_dir, "concat_list.txt")
    with open(listf, "w") as f:
        for c in captioned:
            f.write(f"file '{os.path.abspath(c)}'\n")
    acc = os.path.join(out_dir, "progress_accumulated.mp4")
    r = run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listf,
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", acc])
    if r.returncode != 0 or not os.path.exists(acc):
        print(f"[progress_video] concat FAILED:\n{r.stdout[-800:]}"); sys.exit(1)
    print(f"[progress_video] OK -> {acc}  ({len(captioned)} clips)")


if __name__ == "__main__":
    main()
