# -*- coding: utf-8 -*-
"""Keyboard teleop of the trained biped policy, with live HUD + torque/force logging.

Drive the robot with the keyboard; watch per-joint torque, foot GRF and the base reaction
force live in the HUD; press R to start/stop recording a CSV/NPZ for offline analysis.

    python scripts/play_keyboard.py --task Pygmalion-Velocity-Flat-Play-v0 \
        --checkpoint logs/rsl_rl/pygmalion_flat/<run>/model_xxx.pt --mass_scale 1.0

Keys:
    Arrows / Numpad 8245 : vx, vy      Z / X : yaw      L : zero command
    R : toggle logging (saves on stop)  P : push disturbance
    [ / ] : robot mass scale -/+ 5%     ESC : quit
Use the rough Play task to walk over stairs / rough / slopes.
"""

from __future__ import annotations

import argparse
import os
import sys

from isaaclab.app import AppLauncher

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS)  # allow `import cli_args`
import cli_args  # noqa: E402  isort: skip

parser = argparse.ArgumentParser(description="Keyboard teleop + force logging for the biped.")
parser.add_argument("--task", type=str, default="Pygmalion-Velocity-Flat-Play-v0")
parser.add_argument("--num_envs", type=int, default=1)
# NOTE: --checkpoint is provided by cli_args.add_rsl_rl_args (do not re-add: argparse conflict)
parser.add_argument("--mass_scale", type=float, default=1.0, help="uniform robot mass scale")
parser.add_argument("--base_mass", type=float, default=None, help="absolute base_link mass [kg] (overrides scale on base)")
parser.add_argument("--log_dir", type=str, default=None, help="dir for recorded CSV/NPZ")
parser.add_argument("--seed", type=int, default=None)
cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
sys.argv = [sys.argv[0]] + hydra_args

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

# ---- post-app imports ----
import gymnasium as gym  # noqa: E402
import torch  # noqa: E402

from rsl_rl.runners import OnPolicyRunner  # noqa: E402

from isaaclab.devices import Se2Keyboard, Se2KeyboardCfg  # noqa: E402
from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper  # noqa: E402
from isaaclab_tasks.utils import get_checkpoint_path  # noqa: E402
from isaaclab_tasks.utils.parse_cfg import parse_env_cfg  # noqa: E402

import pygmalion_locomotion  # noqa: E402,F401  (registers tasks)
from pygmalion_locomotion import LOGS_DIR  # noqa: E402
from pygmalion_locomotion.sensors import WrenchLogger, apply_mass_scale, set_base_mass, get_mass_summary  # noqa: E402
from pygmalion_locomotion.ui import Hud  # noqa: E402
from pygmalion_locomotion.tasks.locomotion.agents.rsl_rl_ppo_cfg import (  # noqa: E402
    BipedFlatPPORunnerCfg,
    BipedRoughPPORunnerCfg,
)

# torque scale for the HUD bars (symmetric N*m per joint family)
EFFORT_BY_REGEX = [
    ("knee", 360.0),
    ("hip_pitch", 120.0), ("hip_roll", 120.0), ("hip_yaw", 60.0),
    ("ankle_pitch", 60.0), ("ankle_roll", 14.0), ("toe", 5.0),
]


def effort_limit_for(name: str) -> float:
    for key, lim in EFFORT_BY_REGEX:
        if key in name:
            return lim
    return 120.0


def main():
    # env cfg (single robot, play variant -> no noise/push)
    env_cfg = parse_env_cfg(args_cli.task, device=args_cli.device, num_envs=args_cli.num_envs)
    # teleop: stop command resampling + heading control so keyboard fully owns (vx,vy,wz)
    env_cfg.commands.base_velocity.resampling_time_range = (1.0e9, 1.0e9)
    env_cfg.commands.base_velocity.heading_command = False
    # NOTE: command debug_vis (velocity arrows) crashes in GUI on this Isaac Lab build
    # (_resolve_xy_velocity_to_arrow device mismatch cuda vs cpu) -> keep it OFF for teleop.
    env_cfg.commands.base_velocity.debug_vis = False

    agent_cfg = BipedRoughPPORunnerCfg() if "Rough" in args_cli.task else BipedFlatPPORunnerCfg()

    env = gym.make(args_cli.task, cfg=env_cfg)
    env = RslRlVecEnvWrapper(env)
    base = env.unwrapped

    # resolve checkpoint
    ckpt = args_cli.checkpoint
    if ckpt is None:
        log_root = os.path.abspath(os.path.join("logs", "rsl_rl", agent_cfg.experiment_name))
        ckpt = get_checkpoint_path(log_root, agent_cfg.load_run, agent_cfg.load_checkpoint)
    print(f"[play_keyboard] loading checkpoint: {ckpt}")
    runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
    runner.load(ckpt)
    policy = runner.get_inference_policy(device=base.device)

    # scene handles
    robot = base.scene["robot"]
    contact_sensor = base.scene.sensors.get("contact_forces", None)
    cmd_term = base.command_manager.get_term("base_velocity")
    root_body_idx = 0  # base_link is the articulation root

    # adjustable mass (applied once, post-reset)
    if args_cli.base_mass is not None:
        summ = set_base_mass(robot, args_cli.base_mass)
    elif args_cli.mass_scale != 1.0:
        summ = apply_mass_scale(robot, args_cli.mass_scale)
    else:
        summ = get_mass_summary(robot)
    print(f"[play_keyboard] total mass = {summ['TOTAL']:.2f} kg")

    # devices / UI / logging
    kbd = Se2Keyboard(Se2KeyboardCfg(v_x_sensitivity=0.8, v_y_sensitivity=0.4, omega_z_sensitivity=1.0,
                                     sim_device=base.device))
    # ★ remap teleop to WASD (Se2Keyboard defaults to the numpad). W/S=fwd/back, A/D=strafe, Q/E=turn.
    import numpy as _np
    kbd._INPUT_KEY_MAPPING = {
        "W": _np.array([0.8, 0.0, 0.0]),   "S": _np.array([-0.8, 0.0, 0.0]),
        "A": _np.array([0.0, 0.4, 0.0]),   "D": _np.array([0.0, -0.4, 0.0]),
        "Q": _np.array([0.0, 0.0, 1.0]),   "E": _np.array([0.0, 0.0, -1.0]),
    }
    print("[play_keyboard] teleop keys: W/S=fwd/back, A/D=strafe, Q/E=turn | R=record, P=push, [ ]=mass")
    log_dir = args_cli.log_dir or os.path.join(LOGS_DIR, "teleop")
    logger = WrenchLogger(robot, contact_sensor=contact_sensor, foot_body_regex=".*_foot_link",
                          env_idx=0, out_dir=log_dir)
    hud = Hud(robot.joint_names, logger.foot_body_names,
              effort_limits={n: effort_limit_for(n) for n in robot.joint_names})

    state = {"recording": False, "mass_scale": args_cli.mass_scale, "push": 0}

    def toggle_record():
        state["recording"] = not state["recording"]
        if not state["recording"]:
            logger.save(tag=f"teleop_{base.common_step_counter}")
        print(f"[play_keyboard] recording = {state['recording']}")

    def push():
        state["push"] = 8  # apply a lateral shove for a few steps

    def mass_down():
        state["mass_scale"] = max(0.5, state["mass_scale"] - 0.05)
        apply_mass_scale(robot, state["mass_scale"])

    def mass_up():
        state["mass_scale"] = min(2.0, state["mass_scale"] + 0.05)
        apply_mass_scale(robot, state["mass_scale"])

    kbd.add_callback("R", toggle_record)
    kbd.add_callback("P", push)
    kbd.add_callback("LEFT_BRACKET", mass_down)
    kbd.add_callback("RIGHT_BRACKET", mass_up)
    print(kbd)

    obs, _ = env.get_observations()
    sim_t = 0.0
    dt = base.step_dt
    # ---- teleop feel: HOLD-TO-ACCELERATE toward the policy's command range, DAMPED release ----
    try:
        rng = cmd_term.cfg.ranges
        cmax = [max(abs(rng.lin_vel_x[0]), abs(rng.lin_vel_x[1])),
                max(abs(rng.lin_vel_y[0]), abs(rng.lin_vel_y[1])),
                max(abs(rng.ang_vel_z[0]), abs(rng.ang_vel_z[1]))]
    except Exception:  # noqa: BLE001
        cmax = [1.5, 0.6, 1.57]
    T_TO_MAX = 1.8                              # s of holding a key to reach max speed
    DAMP_TAU = 0.35                            # s release decay time-constant (damping)
    acc = [c / T_TO_MAX for c in cmax]
    damp_factor = float(_np.exp(-dt / DAMP_TAU))
    cur = [0.0, 0.0, 0.0]
    print(f"[play_keyboard] hold-to-accelerate: max(vx,vy,wz)={[round(c,2) for c in cmax]} | "
          f"reach max ~{T_TO_MAX}s, release damps ~{DAMP_TAU}s")
    while simulation_app.is_running():
        with torch.inference_mode():
            # keyboard -> accel/damp integrator -> command buffer (all envs)
            raw = kbd.advance()  # [vx, vy, wz] held-target (sign = direction, 0 = released)
            for i in range(3):
                ri = float(raw[i])
                if abs(ri) > 1e-6:                      # key held -> accelerate toward +/-max
                    cur[i] += (1.0 if ri > 0 else -1.0) * acc[i] * dt
                    cur[i] = max(-cmax[i], min(cmax[i], cur[i]))
                else:                                   # released -> damp toward 0
                    cur[i] *= damp_factor
                    if abs(cur[i]) < 0.02 * cmax[i] + 1e-4:
                        cur[i] = 0.0
            cmd_np = _np.asarray(cur, dtype=_np.float32)
            cmd_term.vel_command_b[:, 0] = cur[0]
            cmd_term.vel_command_b[:, 1] = cur[1]
            cmd_term.vel_command_b[:, 2] = cur[2]

            # optional disturbance push (lateral force on base for a few steps)
            if state["push"] > 0:
                f = torch.zeros(base.num_envs, 1, 3, device=base.device)
                f[:, 0, 1] = 250.0  # N, +y shove
                robot.set_external_force_and_torque(f, torch.zeros_like(f), body_ids=[root_body_idx])
                state["push"] -= 1
            elif state["push"] == 0:
                z = torch.zeros(base.num_envs, 1, 3, device=base.device)
                robot.set_external_force_and_torque(z, z, body_ids=[root_body_idx])
                state["push"] = -1

            actions = policy(obs)
            obs, _, _, _ = env.step(actions)
            sim_t += dt

        # live HUD + logging (env 0)
        summary = logger.latest_summary()
        base_reac = float(robot.data.body_incoming_joint_wrench_b[0, root_body_idx, :3].norm().cpu())
        foot_pos = robot.data.body_pos_w[0, logger.foot_body_idx, :].detach().cpu().numpy()
        if contact_sensor is not None and logger.cs_foot_idx:
            foot_vec = contact_sensor.data.net_forces_w[0, logger.cs_foot_idx, :].detach().cpu().numpy()
        else:
            foot_vec = None
        hud.update(command=cmd_np, summary=summary, base_reaction=base_reac,
                   mass_total=get_mass_summary(robot)["TOTAL"], foot_positions=foot_pos, foot_force_vecs=foot_vec)
        if state["recording"]:
            logger.record(sim_t, command=cmd_np)

    if state["recording"]:
        logger.save(tag="teleop_final")
    env.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
