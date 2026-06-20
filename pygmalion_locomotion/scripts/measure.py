# -*- coding: utf-8 -*-
"""Automated measurement campaign: drive the trained policy through a scripted command
schedule (and optional pushes), on a chosen terrain + robot mass, logging joint torque,
link reaction wrench (x/y/z) and foot GRF for hardware-design analysis.

    python scripts/measure.py --task Pygmalion-Velocity-Rough-Play-v0 \
        --checkpoint logs/rsl_rl/pygmalion_rough/<run>/model.pt \
        --mass_scale 1.0 --duration 30 --headless --tag rough_m1.0

Schedule (default): stand -> walk fwd -> faster -> lateral -> yaw -> push, looped to --duration.
Output: logs/measure/<tag>.csv / .npz / _meta.json  (analyze with scripts/analyze.py).
"""

from __future__ import annotations

import argparse
import os
import sys

from isaaclab.app import AppLauncher

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS)
import cli_args  # noqa: E402  isort: skip

parser = argparse.ArgumentParser(description="Measurement campaign for the biped.")
parser.add_argument("--task", type=str, default="Pygmalion-Velocity-Flat-Play-v0")
parser.add_argument("--num_envs", type=int, default=1)
# NOTE: --checkpoint is provided by cli_args.add_rsl_rl_args (do not re-add: argparse conflict)
parser.add_argument("--mass_scale", type=float, default=1.0)
parser.add_argument("--base_mass", type=float, default=None)
parser.add_argument("--effort_scale", type=float, default=1.0,
                    help=">1 raises the motor torque limits so torque is NOT clipped — reveals the "
                         "policy's TRUE (unclipped) torque demand for motor sizing (research recommendation)")
parser.add_argument("--duration", type=float, default=30.0, help="measurement seconds")
parser.add_argument("--push", action="store_true", help="inject periodic lateral pushes")
parser.add_argument("--tag", type=str, default="measure")
parser.add_argument("--seed", type=int, default=None)
cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
sys.argv = [sys.argv[0]] + hydra_args

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import torch  # noqa: E402
import gymnasium as gym  # noqa: E402

from rsl_rl.runners import OnPolicyRunner  # noqa: E402

from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper  # noqa: E402
from isaaclab_tasks.utils import get_checkpoint_path  # noqa: E402
from isaaclab_tasks.utils.parse_cfg import parse_env_cfg  # noqa: E402

import pygmalion_locomotion  # noqa: E402,F401
from pygmalion_locomotion import LOGS_DIR  # noqa: E402
from pygmalion_locomotion.sensors import WrenchLogger, apply_mass_scale, set_base_mass, get_mass_summary  # noqa: E402
from pygmalion_locomotion.tasks.locomotion.agents.rsl_rl_ppo_cfg import (  # noqa: E402
    BipedFlatPPORunnerCfg,
    BipedRoughPPORunnerCfg,
)

# (duration_s, vx, vy, wz) command segments — OMNIDIRECTIONAL sweep for hardware loads
SCHEDULE = [
    (2.0, 0.0, 0.0, 0.0),    # stand
    (4.0, 0.6, 0.0, 0.0),    # forward
    (3.0, 1.0, 0.0, 0.0),    # forward fast
    (3.0, -0.6, 0.0, 0.0),   # ★ backward
    (3.0, 0.0, 0.5, 0.0),    # strafe left
    (3.0, 0.0, -0.5, 0.0),   # ★ strafe right
    (3.0, 0.0, 0.0, 1.0),    # turn in place
    (4.0, 0.8, 0.0, 0.5),    # forward + turn
]


def main():
    env_cfg = parse_env_cfg(args_cli.task, device=args_cli.device, num_envs=args_cli.num_envs)
    env_cfg.commands.base_velocity.resampling_time_range = (1.0e9, 1.0e9)
    env_cfg.commands.base_velocity.heading_command = False
    agent_cfg = BipedRoughPPORunnerCfg() if "Rough" in args_cli.task else BipedFlatPPORunnerCfg()

    env = gym.make(args_cli.task, cfg=env_cfg)
    env = RslRlVecEnvWrapper(env)
    base = env.unwrapped

    ckpt = args_cli.checkpoint
    if ckpt is None:
        log_root = os.path.abspath(os.path.join("logs", "rsl_rl", agent_cfg.experiment_name))
        ckpt = get_checkpoint_path(log_root, agent_cfg.load_run, agent_cfg.load_checkpoint)
    print(f"[measure] checkpoint: {ckpt}")
    runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
    runner.load(ckpt)
    policy = runner.get_inference_policy(device=base.device)

    robot = base.scene["robot"]
    contact_sensor = base.scene.sensors.get("contact_forces", None)
    cmd_term = base.command_manager.get_term("base_velocity")
    root_body_idx = 0

    if args_cli.base_mass is not None:
        summ = set_base_mass(robot, args_cli.base_mass)
    elif args_cli.mass_scale != 1.0:
        summ = apply_mass_scale(robot, args_cli.mass_scale)
    else:
        summ = get_mass_summary(robot)
    print(f"[measure] total mass = {summ['TOTAL']:.2f} kg")

    if args_cli.effort_scale != 1.0:
        # raise torque limits so PhysX does not clip -> log the policy's true (unclipped) demand
        new_lim = robot.data.joint_effort_limits * args_cli.effort_scale
        robot.write_joint_effort_limit_to_sim(new_lim)
        print(f"[measure] UNCLIPPED mode: effort limits x{args_cli.effort_scale} "
              f"(true torque demand, not motor-rated)")

    logger = WrenchLogger(robot, contact_sensor=contact_sensor, foot_body_regex=".*_foot_link",
                          env_idx=0, out_dir=os.path.join(LOGS_DIR, "measure"))

    obs, _ = env.get_observations()
    dt = base.step_dt
    sim_t = 0.0
    n_steps = int(args_cli.duration / dt)
    sched_total = sum(s[0] for s in SCHEDULE)

    for k in range(n_steps):
        # pick current command from looped schedule
        ph = sim_t % sched_total
        acc, vx, vy, wz = 0.0, 0.0, 0.0, 0.0
        for seg in SCHEDULE:
            acc += seg[0]
            if ph < acc:
                _, vx, vy, wz = seg
                break
        with torch.inference_mode():
            cmd = torch.tensor([vx, vy, wz], device=base.device)
            cmd_term.vel_command_b[:, 0] = vx
            cmd_term.vel_command_b[:, 1] = vy
            cmd_term.vel_command_b[:, 2] = wz
            if args_cli.push and (k % int(5.0 / dt) == 0) and k > 0:
                f = torch.zeros(base.num_envs, 1, 3, device=base.device)
                f[:, 0, 1] = 250.0
                robot.set_external_force_and_torque(f, torch.zeros_like(f), body_ids=[root_body_idx])
            actions = policy(obs)
            obs, _, _, _ = env.step(actions)
            sim_t += dt
        logger.record(sim_t, command=(vx, vy, wz))

    paths = logger.save(tag=args_cli.tag)
    print(f"[measure] done. {paths}")
    env.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
