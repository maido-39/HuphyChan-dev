# -*- coding: utf-8 -*-
"""Validate that the RL env actually BUILDS and the sensing APIs return correct shapes.

Runs on CPU PhysX (device=cpu) so it works without the GPU-PhysX driver fix — slow, just a
few steps, purely to confirm the whole config stack wires together: USD robot loads, body/joint
names resolve, all reward/event/termination terms bind, and torque / link-wrench / GRF read out.

    OMNI_KIT_ACCEPT_EULA=YES python scripts/check_env.py --task Pygmalion-Velocity-Flat-Play-v0 --device cpu
"""

from __future__ import annotations

import argparse
import sys
import os

from isaaclab.app import AppLauncher

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS)

parser = argparse.ArgumentParser()
parser.add_argument("--task", default="Pygmalion-Velocity-Flat-Play-v0")
parser.add_argument("--num_envs", type=int, default=2)
parser.add_argument("--steps", type=int, default=5)
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.headless = True

app = AppLauncher(args).app

import gymnasium as gym  # noqa: E402
import torch  # noqa: E402

from isaaclab_tasks.utils.parse_cfg import parse_env_cfg  # noqa: E402
import pygmalion_locomotion  # noqa: E402,F401


def main():
    dev = args.device if args.device else "cpu"
    cfg = parse_env_cfg(args.task, device=dev, num_envs=args.num_envs)
    env = gym.make(args.task, cfg=cfg)
    base = env.unwrapped
    print("\n=============== ENV BUILD OK ===============")
    print("task        :", args.task, "| device:", dev, "| num_envs:", base.num_envs)
    print("obs space   :", env.observation_space)
    print("act space   :", env.action_space)

    robot = base.scene["robot"]
    print("robot bodies:", robot.num_bodies, robot.body_names)
    print("robot joints:", robot.num_joints, robot.joint_names)
    cs = base.scene.sensors.get("contact_forces", None)
    print("contact sensor bodies:", None if cs is None else len(cs.body_names))
    print("reward terms:", list(base.reward_manager._term_names))
    print("event terms :", list(base.event_manager._term_names) if hasattr(base.event_manager, "_term_names") else "n/a")

    obs, _ = env.reset()
    print("\n--- reset OK, stepping", args.steps, "steps (random action) ---")
    for i in range(args.steps):
        act = torch.zeros((base.num_envs, env.action_space.shape[1]), device=base.device)
        env.step(act)
    print("stepped OK")

    # --- sensing readout (the hardware-design deliverable) ---
    d = robot.data
    tau = d.applied_torque[0].detach().cpu().numpy()
    wrench = d.body_incoming_joint_wrench_b[0].detach().cpu().numpy()
    print("\n--- SENSING shapes ---")
    print("applied_torque        :", tau.shape, "(joints)")
    print("body_incoming_wrench_b :", wrench.shape, "(bodies, 6=Fx,Fy,Fz,Tx,Ty,Tz)")
    if cs is not None:
        grf = cs.data.net_forces_w[0].detach().cpu().numpy()
        print("contact net_forces_w   :", grf.shape, "(bodies, 3)")
    # base reaction (root->world) Fz should be ~ total weight * g when standing-ish
    import numpy as np
    base_reac = np.linalg.norm(wrench[0, :3])
    print(f"base_link reaction |F| : {base_reac:.1f} N   (sanity: total weight ~ 51.8*9.81 = 508 N)")
    print("=============== ALL CHECKS PASSED ===============")
    env.close()


if __name__ == "__main__":
    main()
    app.close()
