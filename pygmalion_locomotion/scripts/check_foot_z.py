# -*- coding: utf-8 -*-
"""Build the env (validates the new feet_swing_height term) + print the STANDING foot_link world-z, so we set
feet_swing_height h_target = standing_z + clearance correctly (the foot_link origin sits above ground due to the
sole-capsule offset). Settle a few steps with zero action, then report mean foot_link z.
    python scripts/check_foot_z.py --task Pygmalion-Velocity-Flat-G1ImpactStable-v0 --headless
"""
from __future__ import annotations
import argparse
from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--task", type=str, default="Pygmalion-Velocity-Flat-G1ImpactStable-v0")
AppLauncher.add_app_launcher_args(parser)
args_cli, _ = parser.parse_known_args()
app = AppLauncher(args_cli).app

import torch  # noqa: E402
import gymnasium as gym  # noqa: E402
from isaaclab.managers import SceneEntityCfg  # noqa: E402
from isaaclab_tasks.utils.parse_cfg import parse_env_cfg  # noqa: E402
import pygmalion_locomotion  # noqa: E402,F401


def main():
    cfg = parse_env_cfg(args_cli.task, device=args_cli.device, num_envs=16)
    env = gym.make(args_cli.task, cfg=cfg); base = env.unwrapped
    base.reset()
    # settle a few steps with zero action (let feet rest on ground)
    a = torch.zeros((base.num_envs, base.action_manager.total_action_dim), device=base.device)
    for _ in range(40):
        base.step(a)
    robot = base.scene["robot"]
    fcfg = SceneEntityCfg("robot", body_names=".*_foot_link"); fcfg.resolve(base.scene)
    fz = robot.data.body_pos_w[:, fcfg.body_ids, 2]      # [E, nfoot]
    bz = robot.data.root_pos_w[:, 2]
    print(f"\n[footz] foot_link bodies: {[robot.body_names[i] for i in fcfg.body_ids]}")
    print(f"[footz] STANDING foot_link z: mean {fz.mean().item():.4f}  min {fz.min().item():.4f}  max {fz.max().item():.4f}")
    print(f"[footz] base(root) z mean: {bz.mean().item():.4f}")
    print(f"[footz] -> set feet_swing_height h_target = standing_z + ~0.06 clearance ≈ {fz.mean().item()+0.06:.3f}")
    app.close()


if __name__ == "__main__":
    main()
