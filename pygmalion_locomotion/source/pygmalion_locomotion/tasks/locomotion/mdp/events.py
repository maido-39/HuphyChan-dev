# -*- coding: utf-8 -*-
"""Custom MDP events for the biped task."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import torch

    from isaaclab.envs import ManagerBasedEnv

# cache parsed specs by path so the startup event doesn't re-read/validate every call
_SPEC_CACHE: dict = {}


def apply_robot_physics(env: "ManagerBasedEnv", env_ids: "torch.Tensor", spec_path: str | None = None,
                        asset_name: str = "robot"):
    """Startup event: apply the spec's deterministic mass/inertia/COM overrides to the robot.

    Lets the user change physical properties frequently by editing the YAML (no MJCF edit /
    no USD reconvert). Idempotent (rebuilds from default_mass each call).
    """
    from ....robots.spec import RobotSpec, apply_physics_overrides

    spec = _SPEC_CACHE.get(spec_path)
    if spec is None:
        spec = RobotSpec.from_yaml(spec_path)
        _SPEC_CACHE[spec_path] = spec
    robot = env.scene[asset_name]
    apply_physics_overrides(robot, spec)
