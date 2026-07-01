"""Per-joint commanded-vs-actual joint angle (q) tracking.

For a trained policy on a steady command, records each joint's COMMANDED position
(the position-servo target = actuator ctrl) and ACTUAL position (qpos), then plots
them overlaid + the tracking error (actual - commanded). CPU-isolated.

Usage:
  CUDA_VISIBLE_DEVICES="" uv run python analysis/track_q.py \
      --run-dir logs/rsl_rl/pygmalion_velocity/<run> --vx 0.5 --out <docs/mujoco/assets>
"""

from __future__ import annotations

import argparse
import time as _time
from dataclasses import asdict
from pathlib import Path

import mujoco
import numpy as np
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import mjlab.tasks  # noqa: F401
from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg

ORDER = ["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll"]


def latest_ckpt(run_dir: Path, min_age=10.0):
    now = _time.time(); c = []
    for f in run_dir.glob("model_*.pt"):
        try:
            it = int(f.stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        if now - f.stat().st_mtime >= min_age:
            c.append((it, f))
    return sorted(c)[-1][1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task", default="Mjlab-Velocity-Flat-Pygmalion")
    p.add_argument("--run-dir", required=True, type=Path)
    p.add_argument("--checkpoint", type=Path, default=None)
    p.add_argument("--vx", type=float, default=0.5)
    p.add_argument("--steps", type=int, default=400)
    p.add_argument("--warmup", type=int, default=120)
    p.add_argument("--out", required=True)
    p.add_argument("--tag", default="track_q")
    args = p.parse_args()
    ckpt = args.checkpoint or latest_ckpt(args.run_dir)

    cfg = load_env_cfg(args.task, play=True)
    cfg.scene.num_envs = 1
    tw = cfg.commands["twist"]; assert isinstance(tw, UniformVelocityCommandCfg)
    tw.ranges.lin_vel_x = (args.vx, args.vx); tw.ranges.lin_vel_y = (0.0, 0.0)
    tw.ranges.ang_vel_z = (0.0, 0.0); tw.rel_standing_envs = 0.0
    if hasattr(tw, "heading_command"):
        tw.heading_command = False; tw.ranges.heading = None
    ag = load_rl_cfg(args.task)
    env = RslRlVecEnvWrapper(ManagerBasedRlEnv(cfg=cfg, device="cpu"),
                             clip_actions=ag.clip_actions)
    rn = (load_runner_cls(args.task) or MjlabOnPolicyRunner)(env, asdict(ag), device="cpu")
    rn.load(str(ckpt), load_cfg={"actor": True}, strict=True, map_location="cpu")
    policy = rn.get_inference_policy(device="cpu")
    sim = env.unwrapped.sim; m = sim.mj_model

    # joint -> (qpos addr, ctrl/actuator index)
    joints = []
    for a in range(m.nu):
        jid = int(m.actuator_trnid[a][0])
        nm = (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, jid) or "").split("/")[-1]
        joints.append({"name": nm, "qadr": int(m.jnt_qposadr[jid]), "act": a})
    joints.sort(key=lambda j: (next((i for i, o in enumerate(ORDER) if o in j["name"]), 9),
                               0 if j["name"].startswith("L") else 1))
    print(f"[track_q] {ckpt.name}  joints={[j['name'] for j in joints]}")

    def set_cmd():
        env.unwrapped.command_manager.get_command("twist")[:] = torch.tensor(
            [[args.vx, 0.0, 0.0]])

    env.reset()
    for _ in range(args.warmup):
        set_cmd(); obs = env.get_observations()
        with torch.no_grad():
            act = policy(obs)
        env.step(act)

    T = args.steps
    q_cmd = np.zeros((T, len(joints))); q_act = np.zeros((T, len(joints)))
    tvec = np.zeros(T); dt = float(env.unwrapped.step_dt)
    for t in range(T):
        set_cmd(); obs = env.get_observations()
        with torch.no_grad():
            act = policy(obs)
        env.step(act)
        ctrl = np.asarray(sim.data.ctrl[0].clone().cpu())
        qpos = np.asarray(sim.data.qpos[0].clone().cpu())
        for k, j in enumerate(joints):
            q_cmd[t, k] = ctrl[j["act"]]; q_act[t, k] = qpos[j["qadr"]]
        tvec[t] = t * dt
    env.close()

    names = [j["name"].replace("_joint", "") for j in joints]
    err = q_act - q_cmd
    np.savez_compressed(f"{args.out}/{args.tag}.npz", t=tvec, q_cmd=q_cmd, q_act=q_act,
                        names=np.array(names))

    # ---- Fig 1: commanded vs actual overlay (+ error shaded) ----
    n = len(joints); cols = 3; rows = int(np.ceil(n / cols))
    fig, ax = plt.subplots(rows, cols, figsize=(4.6 * cols, 2.7 * rows), squeeze=False)
    for k in range(n):
        a = ax[k // cols][k % cols]
        a.plot(tvec, np.degrees(q_cmd[:, k]), color="#e67e22", lw=1.4, ls="--", label="cmd")
        a.plot(tvec, np.degrees(q_act[:, k]), color="#2980b9", lw=1.0, label="actual")
        a.fill_between(tvec, np.degrees(q_cmd[:, k]), np.degrees(q_act[:, k]),
                       color="#c0392b", alpha=0.18)
        rms = np.degrees(np.sqrt(np.mean(err[:, k] ** 2)))
        mx = np.degrees(np.abs(err[:, k]).max())
        a.set_title(f"{names[k]}  (err RMS {rms:.1f}° max {mx:.1f}°)", fontsize=8)
        a.grid(alpha=.3); a.tick_params(labelsize=6)
        if k == 0:
            a.legend(fontsize=7)
    for k in range(n, rows * cols):
        ax[k // cols][k % cols].axis("off")
    fig.suptitle(f"Commanded vs actual joint angle q — vx={args.vx} — {ckpt.name}", fontsize=12)
    fig.supxlabel("time [s]"); fig.supylabel("joint angle [deg]")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(f"{args.out}/{args.tag}_overlay.png", dpi=110); plt.close(fig)

    # ---- Fig 2: tracking error (actual - commanded) ----
    fig, ax = plt.subplots(rows, cols, figsize=(4.6 * cols, 2.7 * rows), squeeze=False)
    for k in range(n):
        a = ax[k // cols][k % cols]
        a.plot(tvec, np.degrees(err[:, k]), color="#c0392b", lw=1.0)
        a.axhline(0, color="k", lw=0.6)
        rms = np.degrees(np.sqrt(np.mean(err[:, k] ** 2)))
        a.set_title(f"{names[k]}  RMS {rms:.1f}°", fontsize=8)
        a.grid(alpha=.3); a.tick_params(labelsize=6)
    for k in range(n, rows * cols):
        ax[k // cols][k % cols].axis("off")
    fig.suptitle(f"Joint angle tracking error (actual - cmd) — vx={args.vx} — {ckpt.name}",
                 fontsize=12)
    fig.supxlabel("time [s]"); fig.supylabel("error [deg]")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(f"{args.out}/{args.tag}_error.png", dpi=110); plt.close(fig)

    print("[track_q] per-joint tracking error RMS / max [deg]:")
    for k in range(n):
        print(f"  {names[k]:14s} RMS {np.degrees(np.sqrt(np.mean(err[:,k]**2))):5.2f}  "
              f"max {np.degrees(np.abs(err[:,k]).max()):5.2f}")


if __name__ == "__main__":
    main()
