# Copyright (c) 2022-2025, The Isaac Lab Project Developers (https://github.com/isaac-sim/IsaacLab/blob/main/CONTRIBUTORS.md).
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Script to train RL agent with RSL-RL."""

"""Launch Isaac Sim Simulator first."""

import argparse
import sys

from isaaclab.app import AppLauncher

# local imports
import cli_args  # isort: skip


# add argparse arguments
parser = argparse.ArgumentParser(description="Train an RL agent with RSL-RL.")
parser.add_argument("--video", action="store_true", default=False, help="(legacy) record videos during training.")
parser.add_argument("--no_video", action="store_true", default=False, help="DISABLE the default in-training video recording.")
parser.add_argument("--video_length", type=int, default=400, help="Length of the recorded video (in steps). 400 ~= 8s.")
parser.add_argument("--video_interval", type=int, default=1500, help="Interval between video recordings (in steps, ~60 iters).")
parser.add_argument("--init_checkpoint", type=str, default=None,
                    help="TRANSFER: initialize policy weights from this checkpoint (fresh optimizer, iter 0). "
                         "e.g. flat->rough. Requires matching obs/action dims.")
parser.add_argument("--num_envs", type=int, default=None, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, default=None, help="Name of the task.")
parser.add_argument("--seed", type=int, default=None, help="Seed used for the environment")
parser.add_argument("--max_iterations", type=int, default=None, help="RL Policy training iterations.")
parser.add_argument(
    "--distributed", action="store_true", default=False, help="Run training with multiple GPUs or nodes."
)
# append RSL-RL cli arguments
cli_args.add_rsl_rl_args(parser)
# append AppLauncher cli args
AppLauncher.add_app_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()

# ★ in-training video recording is ON BY DEFAULT (so progress can be checked mid-run without
#   waiting for training to finish). Disable with --no_video. Saved to <log_dir>/videos/train/.
args_cli.video = not args_cli.no_video
# always enable cameras to record video
if args_cli.video:
    args_cli.enable_cameras = True

# clear out sys.argv for Hydra
sys.argv = [sys.argv[0]] + hydra_args

# launch omniverse app
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

"""Check for minimum supported RSL-RL version."""

import importlib.metadata as metadata
import platform

from packaging import version

# for distributed training, check minimum supported rsl-rl version
RSL_RL_VERSION = "2.3.1"
installed_version = metadata.version("rsl-rl-lib")
if args_cli.distributed and version.parse(installed_version) < version.parse(RSL_RL_VERSION):
    if platform.system() == "Windows":
        cmd = [r".\isaaclab.bat", "-p", "-m", "pip", "install", f"rsl-rl-lib=={RSL_RL_VERSION}"]
    else:
        cmd = ["./isaaclab.sh", "-p", "-m", "pip", "install", f"rsl-rl-lib=={RSL_RL_VERSION}"]
    print(
        f"Please install the correct version of RSL-RL.\nExisting version is: '{installed_version}'"
        f" and required version is: '{RSL_RL_VERSION}'.\nTo install the correct version, run:"
        f"\n\n\t{' '.join(cmd)}\n"
    )
    exit(1)

"""Rest everything follows."""

import gymnasium as gym
import os
import torch
from datetime import datetime

from rsl_rl.runners import OnPolicyRunner

from isaaclab.envs import (
    DirectMARLEnv,
    DirectMARLEnvCfg,
    DirectRLEnvCfg,
    ManagerBasedRLEnvCfg,
    multi_agent_to_single_agent,
)
from isaaclab.utils.dict import print_dict
from isaaclab.utils.io import dump_pickle, dump_yaml

from isaaclab_rl.rsl_rl import RslRlOnPolicyRunnerCfg, RslRlVecEnvWrapper

import isaaclab_tasks  # noqa: F401
from isaaclab_tasks.utils import get_checkpoint_path
from isaaclab_tasks.utils.hydra import hydra_task_config

# PLACEHOLDER: Extension template (do not remove this comment)
import pygmalion_locomotion  # noqa: F401  (registers Pygmalion-Velocity-* gym tasks)

torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True
torch.backends.cudnn.deterministic = False
torch.backends.cudnn.benchmark = False


@hydra_task_config(args_cli.task, "rsl_rl_cfg_entry_point")
def main(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg, agent_cfg: RslRlOnPolicyRunnerCfg):
    """Train with RSL-RL agent."""
    # override configurations with non-hydra CLI arguments
    agent_cfg = cli_args.update_rsl_rl_cfg(agent_cfg, args_cli)
    env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs
    agent_cfg.max_iterations = (
        args_cli.max_iterations if args_cli.max_iterations is not None else agent_cfg.max_iterations
    )

    # set the environment seed
    # note: certain randomizations occur in the environment initialization so we set the seed here
    env_cfg.seed = agent_cfg.seed
    env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device

    # multi-gpu training configuration
    if args_cli.distributed:
        env_cfg.sim.device = f"cuda:{app_launcher.local_rank}"
        agent_cfg.device = f"cuda:{app_launcher.local_rank}"

        # set seed to have diversity in different threads
        seed = agent_cfg.seed + app_launcher.local_rank
        env_cfg.seed = seed
        agent_cfg.seed = seed

    # specify directory for logging experiments
    log_root_path = os.path.join("logs", "rsl_rl", agent_cfg.experiment_name)
    log_root_path = os.path.abspath(log_root_path)
    print(f"[INFO] Logging experiment in directory: {log_root_path}")
    # specify directory for logging runs: {time-stamp}_{run_name}
    log_dir = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # The Ray Tune workflow extracts experiment name using the logging line below, hence, do not change it (see PR #2346, comment-2819298849)
    print(f"Exact experiment name requested from command line: {log_dir}")
    if agent_cfg.run_name:
        log_dir += f"_{agent_cfg.run_name}"
    log_dir = os.path.join(log_root_path, log_dir)

    # in-training video: ELEVATED OVERVIEW of several envs (so domain-randomization is visible:
    # each robot gets its own random cmd_vel / mass / friction / push) + draw the command arrows.
    if args_cli.video:
        try:
            # ★ FEWER robots IN THE VIDEO without touching training: the velocity envs are independent
            #   (base-relative obs) so env_spacing is PURE PLACEMENT -> training-neutral. On FLAT we
            #   spread the envs far apart and frame the corner, so only a HANDFUL land in the camera
            #   frustum (genuinely fewer robots, not just a zoom). ROUGH's spacing is terrain-bound, so
            #   there we follow a single env's robot instead.
            if "Flat" in args_cli.task:
                # ★ RULE (user, persisted + VERIFIED by frame extraction): FEW robots in frame. env_spacing
                #   is pure placement for the independent velocity envs -> TRAINING-NEUTRAL. Tuning history:
                #   8m = ~15-20 robots (too many); 30m+world = 0 robots (env 0 walks off the framed patch).
                #   FIX: origin_type="env" ANCHORS the camera on env 0 (its robot is always centered, no
                #   empty patch) + 15m spacing keeps neighbours sparse so only ~a few land in frame.
                env_cfg.scene.env_spacing = 15.0
                env_cfg.viewer.origin_type = "env"
                env_cfg.viewer.env_index = 0
                env_cfg.viewer.eye = (5.0, -5.0, 4.0)
                env_cfg.viewer.lookat = (0.0, 0.0, 0.4)
            else:                                    # rough: terrain-tied spacing -> follow env 0
                env_cfg.viewer.origin_type = "env"
                env_cfg.viewer.env_index = 0
                env_cfg.viewer.eye = (3.0, -3.0, 2.2)
                env_cfg.viewer.lookat = (0.0, 0.0, 0.5)
            # per-robot commanded(green)+actual(blue) velocity arrows -> the cmd_vel DR is on-screen
            env_cfg.commands.base_velocity.debug_vis = True
        except Exception as exc:  # pragma: no cover - viewer cfg is best-effort
            print(f"[WARN] could not set video viewer: {exc}")
        # ★ RULE (user-requested, repeated): always run the step-captioned ACCUMULATE video in PARALLEL
        #   (concat of every in-training clip, each stamped with its training step) so the whole
        #   progression is one scrubbable video. Auto-started here so it is NEVER forgotten; killed on exit.
        try:
            import atexit
            import subprocess
            _acc_sh = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accumulate_train_videos.sh")
            _acc_proc = subprocess.Popen(["bash", _acc_sh, log_dir],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            atexit.register(_acc_proc.terminate)
            print(f"[train] accumulate-video watcher pid {_acc_proc.pid} -> {log_dir}/accumulated_progress.mp4")
        except Exception as exc:  # pragma: no cover
            print(f"[WARN] could not start accumulate-video watcher: {exc}")

    # create isaac environment
    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array" if args_cli.video else None)

    # convert to single-agent instance if required by the RL algorithm
    if isinstance(env.unwrapped, DirectMARLEnv):
        env = multi_agent_to_single_agent(env)

    # save resume path before creating a new log_dir
    if agent_cfg.resume or agent_cfg.algorithm.class_name == "Distillation":
        resume_path = get_checkpoint_path(log_root_path, agent_cfg.load_run, agent_cfg.load_checkpoint)

    # wrap for video recording
    if args_cli.video:
        video_kwargs = {
            "video_folder": os.path.join(log_dir, "videos", "train"),
            "step_trigger": lambda step: step % args_cli.video_interval == 0,
            "video_length": args_cli.video_length,
            "disable_logger": True,
        }
        print("[INFO] Recording videos during training.")
        print_dict(video_kwargs, nesting=4)
        env = gym.wrappers.RecordVideo(env, **video_kwargs)

    # wrap around environment for rsl-rl
    env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)

    # create runner from rsl-rl
    runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=log_dir, device=agent_cfg.device)
    # write git state to logs
    runner.add_git_repo_to_log(__file__)
    # load the checkpoint
    if agent_cfg.resume or agent_cfg.algorithm.class_name == "Distillation":
        print(f"[INFO]: Loading model checkpoint from: {resume_path}")
        # load previously trained model
        runner.load(resume_path)
    elif args_cli.init_checkpoint:
        # ★ TRANSFER (e.g. flat -> rough): load POLICY weights only (fresh optimizer + iter 0),
        #   so the run fine-tunes from the transferred policy. Needs matching obs/action dims.
        print(f"[transfer] init policy weights from: {args_cli.init_checkpoint}")
        runner.load(args_cli.init_checkpoint, load_optimizer=False)
        runner.current_learning_iteration = 0

    # dump the configuration into log-directory
    dump_yaml(os.path.join(log_dir, "params", "env.yaml"), env_cfg)
    dump_yaml(os.path.join(log_dir, "params", "agent.yaml"), agent_cfg)
    dump_pickle(os.path.join(log_dir, "params", "env.pkl"), env_cfg)
    dump_pickle(os.path.join(log_dir, "params", "agent.pkl"), agent_cfg)

    # run training
    runner.learn(num_learning_iterations=agent_cfg.max_iterations, init_at_random_ep_len=True)

    # close the simulator
    env.close()


if __name__ == "__main__":
    # run the main function
    main()
    # close sim app
    simulation_app.close()
