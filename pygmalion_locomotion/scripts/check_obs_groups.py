# -*- coding: utf-8 -*-
"""Validate the asymmetric actor-critic obs wiring WITHOUT training (no train.py hook).
Builds the env (num_envs=4) and prints the observation-manager group dims + terms, so we can confirm:
  * a `critic` group exists and is LARGER than `policy` (asymmetry activated, not silently critic==actor),
  * the encoder-less passive toe is NOT in the actor `policy` group (leak fixed),
  * base_lin_vel is in `critic` only.
    python scripts/check_obs_groups.py --task Pygmalion-Velocity-Flat-G1ImpactStableAsymObs-v0 --headless
"""
from __future__ import annotations
import argparse
from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--task", type=str, default="Pygmalion-Velocity-Flat-G1ImpactStableAsymObs-v0")
AppLauncher.add_app_launcher_args(parser)
args_cli, _ = parser.parse_known_args()
app = AppLauncher(args_cli).app

import gymnasium as gym  # noqa: E402
from isaaclab_tasks.utils.parse_cfg import parse_env_cfg  # noqa: E402
import pygmalion_locomotion  # noqa: E402,F401


def main():
    cfg = parse_env_cfg(args_cli.task, device=args_cli.device, num_envs=4)
    env = gym.make(args_cli.task, cfg=cfg)
    base = env.unwrapped
    base.reset()
    om = base.observation_manager
    print("\n[obs] ===== observation groups =====")
    print("[obs] group_obs_dim:", dict(om.group_obs_dim))
    for g in om.active_terms:
        print(f"[obs] group '{g}' terms: {om.active_terms[g]}")
    pol = om.group_obs_dim.get("policy"); cri = om.group_obs_dim.get("critic")
    print(f"\n[obs] policy(actor) dim = {pol}   critic dim = {cri}")
    print(f"[obs] ASYMMETRY ACTIVE: {cri is not None and (sum(cri) if isinstance(cri,tuple) else cri) > (sum(pol) if isinstance(pol,tuple) else pol)}")
    print(f"[obs] toe in actor? {'toe' in str(om.active_terms.get('policy'))}  (want False)")
    app.close()


if __name__ == "__main__":
    main()
