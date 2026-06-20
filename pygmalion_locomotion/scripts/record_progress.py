# -*- coding: utf-8 -*-
"""Build a CLEAN single-robot training-progress video from saved checkpoints.

Plays every `model_*.pt` checkpoint in a run (one robot, forward walk command), records a
~5 s clip of each, stamps the iteration in the bottom-right, and concatenates them all into one
accumulated video showing the policy evolve (clumsy -> walking).

    python scripts/record_progress.py --run logs/rsl_rl/pygmalion_flat/<run-dir>
    python scripts/record_progress.py --run <run> --task Pygmalion-Velocity-Flat-Play-v0 --seconds 5 --vx 0.8

Why from checkpoints (not --video during training): training uses many envs (a grid) which makes
an ugly video; replaying each checkpoint with num_envs=1 gives a clear single robot. One Isaac Sim
session handles all checkpoints. Outputs: <run>/progress/clip_iterNNNN.mp4 + <run>/progress_accumulated.mp4.
Uses the viewport render (rgb_array) — NOT TiledCamera (which hangs on Blackwell).
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys

from isaaclab.app import AppLauncher

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS)
import cli_args  # noqa: E402  isort: skip

parser = argparse.ArgumentParser()
parser.add_argument("--run", required=True, help="rsl_rl run dir containing model_*.pt")
parser.add_argument("--task", default="Pygmalion-Velocity-Flat-Play-v0")
parser.add_argument("--seconds", type=float, default=5.0, help="clip length per checkpoint")
parser.add_argument("--vx", type=float, default=0.8, help="forward command during the clip")
parser.add_argument("--width", type=int, default=1280)
parser.add_argument("--height", type=int, default=720)
parser.add_argument("--stride", type=int, default=1, help="use every Nth checkpoint (always keeps the last)")
parser.add_argument("--num_envs", type=int, default=25, help="robots shown per clip (a sample population, grid view)")
cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.headless = True
args.enable_cameras = True   # needed for rgb_array render

app_launcher = AppLauncher(args)
simulation_app = app_launcher.app

import numpy as np  # noqa: E402
import torch  # noqa: E402
import gymnasium as gym  # noqa: E402

from rsl_rl.runners import OnPolicyRunner  # noqa: E402
from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper  # noqa: E402
from isaaclab_tasks.utils.parse_cfg import parse_env_cfg  # noqa: E402

import pygmalion_locomotion  # noqa: E402,F401
from pygmalion_locomotion.tasks.locomotion.agents.rsl_rl_ppo_cfg import (  # noqa: E402
    BipedFlatPPORunnerCfg, BipedRoughPPORunnerCfg,
)


def ckpt_iter(p):
    m = re.search(r"model_(\d+)", os.path.basename(p))
    return int(m.group(1)) if m else 0


def write_clip(frames, path, iter_n, fps):
    """Pipe RGB frames to ffmpeg, stamp 'iter N' bottom-right, encode mp4."""
    h, w, _ = frames[0].shape
    label = f"iter {iter_n}"
    vf = (f"drawtext=text='{label}':x=w-tw-14:y=h-th-14:fontsize=30:fontcolor=white:"
          f"box=1:boxcolor=black@0.55:boxborderw=10")
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
           "-r", str(fps), "-i", "-", "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for fr in frames:
        p.stdin.write(np.ascontiguousarray(fr[:, :, :3], dtype=np.uint8).tobytes())
    p.stdin.close()
    return p.wait() == 0


def main():
    run_dir = os.path.abspath(args.run)
    ckpts = sorted(glob.glob(os.path.join(run_dir, "model_*.pt")), key=ckpt_iter)
    if not ckpts:
        print(f"[record_progress] no model_*.pt in {run_dir}"); simulation_app.close(); return
    if args.stride > 1:
        sel = ckpts[:: args.stride]
        if ckpts[-1] not in sel:
            sel.append(ckpts[-1])  # always include the final policy
        ckpts = sel
    print(f"[record_progress] {len(ckpts)} checkpoints: {[ckpt_iter(c) for c in ckpts]}")

    env_cfg = parse_env_cfg(args.task, device=args.device, num_envs=args.num_envs)
    env_cfg.commands.base_velocity.resampling_time_range = (1.0e9, 1.0e9)
    env_cfg.commands.base_velocity.heading_command = False
    # show a SAMPLE POPULATION of robots in a grid (not just one) — overview camera
    env_cfg.scene.env_spacing = 2.0
    import math as _m
    span = _m.ceil(_m.sqrt(max(1, args.num_envs))) * env_cfg.scene.env_spacing
    env_cfg.viewer.origin_type = "world"
    env_cfg.viewer.eye = (span * 0.9, span * 0.9, span * 0.7)
    env_cfg.viewer.lookat = (0.0, 0.0, 0.4)
    env_cfg.sim.render_interval = env_cfg.decimation

    agent_cfg = BipedRoughPPORunnerCfg() if "Rough" in args.task else BipedFlatPPORunnerCfg()
    env = gym.make(args.task, cfg=env_cfg, render_mode="rgb_array")
    env = RslRlVecEnvWrapper(env)
    base = env.unwrapped
    runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
    cmd_term = base.command_manager.get_term("base_velocity")

    dt = base.step_dt
    fps = round(1.0 / dt)
    n_steps = int(args.seconds / dt)
    out_dir = os.path.join(run_dir, "progress")
    os.makedirs(out_dir, exist_ok=True)

    clips = []
    for c in ckpts:
        it = ckpt_iter(c)
        runner.load(c)
        policy = runner.get_inference_policy(device=base.device)
        obs, _ = env.get_observations()
        cmd_term.vel_command_b[:, 0] = args.vx
        cmd_term.vel_command_b[:, 1] = 0.0
        cmd_term.vel_command_b[:, 2] = 0.0
        frames = []
        for _ in range(n_steps):
            with torch.inference_mode():
                obs, _, _, _ = env.step(policy(obs))
            cmd_term.vel_command_b[:, 0] = args.vx  # keep command after any reset
            fr = base.render()  # ManagerBasedRLEnv.render() (the rsl_rl wrapper has no render)
            if fr is not None:
                frames.append(np.asarray(fr))
        if not frames:
            print(f"[record_progress] iter {it}: render returned no frames — skipping"); continue
        clip = os.path.join(out_dir, f"clip_iter{it:05d}.mp4")
        ok = write_clip(frames, clip, it, fps)
        print(f"[record_progress] iter {it}: {len(frames)} frames -> {clip} ({'ok' if ok else 'FAIL'})")
        if ok:
            clips.append(clip)

    env.close()

    # concat all clips
    if clips:
        listf = os.path.join(out_dir, "concat.txt")
        with open(listf, "w") as f:
            for c in clips:
                f.write(f"file '{c}'\n")
        acc = os.path.join(run_dir, "progress_accumulated.mp4")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listf,
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", acc],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[record_progress] DONE -> {acc}  ({len(clips)} clips)")


if __name__ == "__main__":
    main()
    simulation_app.close()
