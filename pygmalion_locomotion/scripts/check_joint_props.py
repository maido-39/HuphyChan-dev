# -*- coding: utf-8 -*-
"""One-off: build the env and print the ACTUAL PhysX-applied joint properties (effort/damping/
armature/stiffness) for the knee, to confirm whether the YAML ImplicitActuatorCfg overrides the
MJCF/USD defaults in training. (user 2026-06-22: knee MJCF actuatorfrcrange 360 vs YAML effort 120.)
    python scripts/check_joint_props.py --headless
"""
from __future__ import annotations
import argparse, os, sys
from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--task", type=str, default="Pygmalion-Velocity-Flat-Play-v0")
AppLauncher.add_app_launcher_args(parser)
args_cli, _ = parser.parse_known_args()
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym  # noqa: E402
from isaaclab_tasks.utils.parse_cfg import parse_env_cfg  # noqa: E402
import pygmalion_locomotion  # noqa: E402,F401


def get(view, *names):
    for n in names:
        fn = getattr(view, n, None)
        if fn is not None:
            try:
                return fn()
            except Exception:
                pass
    return None


def main():
    env_cfg = parse_env_cfg(args_cli.task, device=args_cli.device, num_envs=4)
    env = gym.make(args_cli.task, cfg=env_cfg)
    base = env.unwrapped
    base.reset()
    robot = base.scene["robot"]
    names = list(robot.joint_names)
    print("[check] joint_names =", names)
    ki = [i for i, n in enumerate(names) if "knee" in n.lower()]

    pv = robot.root_physx_view
    ef = get(pv, "get_dof_max_forces")
    dm = get(pv, "get_dof_dampings")
    ar = get(pv, "get_dof_armatures")
    st = get(pv, "get_dof_stiffnesses")
    fr = get(pv, "get_dof_friction_coefficients")
    print("\n[check] ===== PhysX-applied joint props (env 0) =====")
    for i in ki:
        e = ef[0, i].item() if ef is not None else float("nan")
        d = dm[0, i].item() if dm is not None else float("nan")
        a = ar[0, i].item() if ar is not None else float("nan")
        s = st[0, i].item() if st is not None else float("nan")
        f = fr[0, i].item() if fr is not None else float("nan")
        print(f"  {names[i]}: effort_limit={e:.2f}  damping={d:.4f}  armature={a:.5f}  stiffness={s:.2f}  friction={f:.4f}")
    print("\n[check] YAML 기대값: effort=120  damping=11  armature=0.0097  stiffness=200")
    print("[check] MJCF 값(override 안 되면 이게 나옴): actuatorfrcrange=360  damping=1.5  armature=0.0875")
    # actuator cfg values
    print("\n[check] ===== ImplicitActuator cfg (knee) =====")
    for an, a in robot.actuators.items():
        if "knee" in an.lower():
            for attr in ("effort_limit_sim", "effort_limit", "damping", "armature", "stiffness", "velocity_limit_sim"):
                v = getattr(a, attr, None)
                if v is not None:
                    try:
                        v = float(v.flatten()[0]) if hasattr(v, "flatten") else float(v)
                    except Exception:
                        pass
                    print(f"  actuator[{an}].{attr} = {v}")
    simulation_app.close()


if __name__ == "__main__":
    main()
