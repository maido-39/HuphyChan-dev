"""Visualize the Pygmalion robot and switch between keyframe poses.

Spawns the robot in an interactive MuJoCo viewer on a ground plane, with both
the visual meshes (geom group 2) and the collision primitives (geom group 3)
made visible so the collision geometry can be checked against the visual mesh.
No physics is stepped: the pose is held static.

Press 1 for HOME_KEYFRAME, 2 for KNEES_BENT_KEYFRAME.

Usage:

  uv run python -m mjlab.asset_zoo.robots.pygmalion.visualize_robot
"""

from __future__ import annotations

import time

import mujoco
import mujoco.viewer
import numpy as np

from mjlab.asset_zoo.robots.pygmalion.pygmalion_constants import (
  KNEES_BENT_KEYFRAME,
  get_pygmalion_robot_cfg,
)
from mjlab.entity.entity import Entity, EntityCfg
from mjlab.utils import spec_config as spec_cfg
from mjlab.utils.string import resolve_expr

# Geom groups: 2 = visual mesh, 3 = collision primitives, 5 = world axes.
VISUAL_GROUP = 2
COLLISION_GROUP = 3
AXES_GROUP = 5

HOME_KEY_NAME = "init_state"
KNEES_BENT_KEY_NAME = "knees_bent"


def _add_keyframe(
  robot: Entity,
  name: str,
  state: EntityCfg.InitialStateCfg,
) -> None:
  """Add a MuJoCo keyframe from an InitialStateCfg (mirrors Entity logic)."""
  qpos_components: list = []
  if not robot.is_fixed_base:
    qpos_components.extend([state.pos, state.rot])

  joint_pos = resolve_expr(state.joint_pos, robot.joint_names, 0.0)
  qpos_components.append(joint_pos)

  key = robot.spec.add_key(name=name, qpos=np.hstack(qpos_components).tolist())
  if robot.is_actuated:
    name_to_pos = {n: joint_pos[i] for i, n in enumerate(robot.joint_names)}
    key.ctrl = np.array(
      [name_to_pos.get(act.target, 0.0) for act in robot.spec.actuators]
    )


def _apply_keyframe(model: mujoco.MjModel, data: mujoco.MjData, name: str) -> None:
  key_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, name)
  mujoco.mj_resetDataKeyframe(model, data, key_id)
  mujoco.mj_forward(model, data)


def _add_scene(spec: mujoco.MjSpec) -> None:
  """Add a ground plane, skybox, and bright lighting to the spec."""
  # Bright gradient skybox so the background is not black.
  spec_cfg.TextureCfg(
    name="skybox",
    type="skybox",
    builtin="gradient",
    rgb1=(0.55, 0.65, 0.85),
    rgb2=(0.9, 0.92, 0.95),
    width=512,
    height=512,
  ).edit_spec(spec)

  # Checkered ground plane.
  spec_cfg.TextureCfg(
    name="groundplane",
    type="2d",
    builtin="checker",
    mark="edge",
    rgb1=(0.4, 0.45, 0.5),
    rgb2=(0.5, 0.55, 0.6),
    markrgb=(0.8, 0.8, 0.8),
    width=300,
    height=300,
  ).edit_spec(spec)
  spec.worldbody.add_geom(
    name="floor",
    type=mujoco.mjtGeom.mjGEOM_PLANE,
    size=(0, 0, 0.05),
  )
  spec_cfg.MaterialCfg(
    name="groundplane",
    texuniform=True,
    texrepeat=(4.0, 4.0),
    reflectance=0.1,
    texture="groundplane",
    geom_names_expr=("floor",),
  ).edit_spec(spec)

  # Brighten the headlight and add a directional sun light.
  spec.visual.headlight.ambient[:] = (0.5, 0.5, 0.5)
  spec.visual.headlight.diffuse[:] = (0.5, 0.5, 0.5)
  spec_cfg.LightCfg(name="sun", pos=(0.0, 0.0, 3.0), type="directional").edit_spec(spec)

  # World coordinate axes as group-5 cylinder geoms (red=x, green=y, blue=z)
  # so they can be toggled on/off in the viewer with the group-5 key.
  axis_len = 0.5
  axes = (
    ("x_axis", (axis_len, 0.0, 0.0), (1.0, 0.0, 0.0, 1.0)),
    ("y_axis", (0.0, axis_len, 0.0), (0.0, 1.0, 0.0, 1.0)),
    ("z_axis", (0.0, 0.0, axis_len), (0.0, 0.0, 1.0, 1.0)),
  )
  for name, end, rgba in axes:
    spec.worldbody.add_geom(
      name=name,
      type=mujoco.mjtGeom.mjGEOM_CYLINDER,
      group=AXES_GROUP,
      fromto=(0.0, 0.0, 0.0, *end),
      size=(0.012, 0.0, 0.0),
      rgba=rgba,
      contype=0,
      conaffinity=0,
    )


def main() -> None:
  robot = Entity(get_pygmalion_robot_cfg())
  _add_keyframe(robot, KNEES_BENT_KEY_NAME, KNEES_BENT_KEYFRAME)
  _add_scene(robot.spec)
  model = robot.spec.compile()
  data = mujoco.MjData(model)

  _apply_keyframe(model, data, HOME_KEY_NAME)

  def on_key(key: int) -> None:
    if key == ord("1"):
      _apply_keyframe(model, data, HOME_KEY_NAME)
    elif key == ord("2"):
      _apply_keyframe(model, data, KNEES_BENT_KEY_NAME)

  with mujoco.viewer.launch_passive(model, data, key_callback=on_key) as viewer:
    # Show the visual meshes, collision primitives, and world axes. Each is a
    # separate geom group, so they can be toggled independently in the viewer.
    viewer.opt.geomgroup[VISUAL_GROUP] = 1
    viewer.opt.geomgroup[COLLISION_GROUP] = 1
    viewer.opt.geomgroup[AXES_GROUP] = 1
    viewer.sync()
    # Hold the pose (no physics stepping) so it stays static.
    while viewer.is_running():
      viewer.sync()
      time.sleep(0.02)


if __name__ == "__main__":
  main()
