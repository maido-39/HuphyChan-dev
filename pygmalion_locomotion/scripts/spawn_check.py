# -*- coding: utf-8 -*-
"""Phase-1 sanity check: spawn the converted biped USD, drop it in the 'stand' pose, step
physics, and report body/joint names, masses and base height — verifying the MJCF->USD
conversion and the ArticulationCfg before building the full RL env.

    python scripts/spawn_check.py --headless         # diagnostics only
    python scripts/spawn_check.py                     # GUI (watch it settle)
    python scripts/spawn_check.py --screenshot ../docs/assets/02_spawn_stand.png
"""

from __future__ import annotations

import argparse
import os

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--steps", type=int, default=200)
parser.add_argument("--screenshot", type=str, default=None, help="save a viewport PNG here")
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import torch  # noqa: E402

import isaaclab.sim as sim_utils  # noqa: E402
from isaaclab.assets import Articulation  # noqa: E402
from isaaclab.sim import SimulationContext  # noqa: E402

import pygmalion_locomotion  # noqa: E402,F401
from pygmalion_locomotion.robots.biped_cfg import get_biped_cfg  # noqa: E402


def main():
    sim = SimulationContext(sim_utils.SimulationCfg(dt=0.005, device=args_cli.device))
    sim.set_camera_view(eye=[2.2, 2.2, 1.4], target=[0.0, 0.0, 0.6])

    # ground + light
    sim_utils.GroundPlaneCfg().func("/World/ground", sim_utils.GroundPlaneCfg())
    sim_utils.DomeLightCfg(intensity=2000.0, color=(0.9, 0.9, 0.9)).func("/World/Light", sim_utils.DomeLightCfg())

    # robot
    robot = Articulation(get_biped_cfg(prim_path="/World/Robot"))
    sim.reset()

    print("\n================= BIPED SPAWN DIAGNOSTICS =================")
    print(f"num_bodies : {robot.num_bodies}")
    print(f"num_joints : {robot.num_joints}")
    print(f"body_names : {robot.body_names}")
    print(f"joint_names: {robot.joint_names}")
    masses = robot.root_physx_view.get_masses()[0].cpu().numpy()
    print(f"per-body mass [kg]: {[round(float(m),3) for m in masses]}")
    print(f"TOTAL mass [kg]: {float(masses.sum()):.3f}  (robot_files says ~51.8)")
    print("==========================================================\n")

    dt = sim.get_physics_dt()
    default_targets = robot.data.default_joint_pos.clone()
    nan_seen = False
    for i in range(args_cli.steps):
        robot.set_joint_position_target(default_targets)
        robot.write_data_to_sim()
        sim.step()
        robot.update(dt)
        if torch.isnan(robot.data.root_pos_w).any():
            print(f"[FAIL] NaN in root pose at step {i}")
            nan_seen = True
            break
        if i % 40 == 0:
            h = float(robot.data.root_pos_w[0, 2])
            print(f"step {i:4d}  base_height={h:.3f} m")

    if not nan_seen:
        h = float(robot.data.root_pos_w[0, 2])
        print(f"\n[OK] no NaN/explosion. final base height = {h:.3f} m")

    # optional screenshot (best-effort; rendering may differ on Blackwell)
    if args_cli.screenshot:
        try:
            from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport
            os.makedirs(os.path.dirname(os.path.abspath(args_cli.screenshot)), exist_ok=True)
            for _ in range(30):  # let frames render
                sim.render()
            capture_viewport_to_file(get_active_viewport(), args_cli.screenshot)
            for _ in range(30):
                sim.render()
            print(f"[screenshot] saved -> {args_cli.screenshot}")
        except Exception as e:  # noqa: BLE001
            print(f"[screenshot] skipped ({e})")


if __name__ == "__main__":
    main()
    simulation_app.close()
