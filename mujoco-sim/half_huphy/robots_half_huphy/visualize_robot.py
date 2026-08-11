"""Visualize the Half Huphy balance spawn pose with physics frozen.

Shows the exact ``INIT_STATE`` used by ``Mjlab-Balance-HalfHuphy``:
all joints at 0 rad, free-base height ``STAND_BASE_HEIGHT``.

Usage:

  cd mujoco-sim/mjlab
  ./.venv/bin/python -m mjlab.asset_zoo.robots.half_huphy.visualize_robot
"""

from __future__ import annotations

import time

import mujoco
import mujoco.viewer
import numpy as np

from mjlab.asset_zoo.robots.half_huphy.half_huphy_constants import (
  INIT_STATE,
  STAND_BASE_HEIGHT,
  get_half_huphy_robot_cfg,
)
from mjlab.entity.entity import Entity
from mjlab.utils import spec_config as spec_cfg
from mjlab.utils.string import resolve_expr

VISUAL_GROUP = 2
COLLISION_GROUP = 3
AXES_GROUP = 5
SPAWN_KEY_NAME = "balance_spawn"


def _add_spawn_keyframe(robot: Entity) -> None:
  """Write the balance INIT_STATE as a named MuJoCo keyframe."""
  state = INIT_STATE
  qpos_components: list = []
  if not robot.is_fixed_base:
    qpos_components.extend([state.pos, state.rot])

  joint_pos = resolve_expr(state.joint_pos, robot.joint_names, 0.0)
  qpos_components.append(joint_pos)

  key = robot.spec.add_key(
    name=SPAWN_KEY_NAME,
    qpos=np.hstack(qpos_components).tolist(),
  )
  if robot.is_actuated:
    name_to_pos = {n: joint_pos[i] for i, n in enumerate(robot.joint_names)}
    key.ctrl = np.array(
      [name_to_pos.get(act.target, 0.0) for act in robot.spec.actuators]
    )


def _add_scene(spec: mujoco.MjSpec) -> None:
  """Add a bright floor and lighting for inspection."""
  spec_cfg.TextureCfg(
    name="skybox",
    type="skybox",
    builtin="gradient",
    rgb1=(0.55, 0.65, 0.85),
    rgb2=(0.9, 0.92, 0.95),
    width=512,
    height=512,
  ).edit_spec(spec)

  spec_cfg.TextureCfg(
    name="groundplane",
    type="2d",
    builtin="checker",
    mark="edge",
    rgb1=(0.55, 0.72, 0.90),
    rgb2=(0.75, 0.85, 0.95),
    markrgb=(0.15, 0.35, 0.60),
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

  spec.visual.headlight.ambient[:] = (0.5, 0.5, 0.5)
  spec.visual.headlight.diffuse[:] = (0.6, 0.6, 0.6)
  spec_cfg.LightCfg(name="sun", pos=(0.0, 0.0, 3.0), type="directional").edit_spec(spec)


def _mark_base_link(spec: mujoco.MjSpec) -> None:
  """Highlight ``base_link`` with a red sphere and local XYZ axes."""
  base = spec.body("base_link")

  # Recolor the existing base collision box so the whole base region stands out.
  for geom in base.geoms:
    if geom.name == "base_collision":
      geom.rgba = (1.0, 0.35, 0.05, 0.55)

  # Origin marker of the free-base body used by fall terminations.
  base.add_geom(
    name="base_link_origin_marker",
    type=mujoco.mjtGeom.mjGEOM_SPHERE,
    size=(0.035, 0.0, 0.0),
    rgba=(1.0, 0.05, 0.05, 0.95),
    group=AXES_GROUP,
    contype=0,
    conaffinity=0,
    density=0,
  )

  axis_len = 0.12
  for name, end, rgba in (
    ("base_link_x_axis", (axis_len, 0.0, 0.0), (1.0, 0.0, 0.0, 1.0)),
    ("base_link_y_axis", (0.0, axis_len, 0.0), (0.0, 1.0, 0.0, 1.0)),
    ("base_link_z_axis", (0.0, 0.0, axis_len), (0.0, 0.35, 1.0, 1.0)),
  ):
    base.add_geom(
      name=name,
      type=mujoco.mjtGeom.mjGEOM_CYLINDER,
      group=AXES_GROUP,
      fromto=(0.0, 0.0, 0.0, *end),
      size=(0.008, 0.0, 0.0),
      rgba=rgba,
      contype=0,
      conaffinity=0,
      density=0,
    )


def main() -> None:
  robot = Entity(get_half_huphy_robot_cfg())
  _add_spawn_keyframe(robot)
  _add_scene(robot.spec)
  _mark_base_link(robot.spec)
  model = robot.spec.compile()
  data = mujoco.MjData(model)

  key_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, SPAWN_KEY_NAME)
  mujoco.mj_resetDataKeyframe(model, data, key_id)
  mujoco.mj_forward(model, data)

  base_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "base_link")
  foot_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "foot_collision")
  base_pos = data.xpos[base_id]
  foot_z = float(data.geom_xpos[foot_id, 2])
  foot_bottom = foot_z - float(model.geom_size[foot_id, 2])
  print("Half Huphy balance spawn pose (physics frozen)")
  print(f"  base_z           = {STAND_BASE_HEIGHT:.3f} m")
  print(
    f"  base_link pos    = ({base_pos[0]:.3f}, {base_pos[1]:.3f}, {base_pos[2]:.3f}) m"
  )
  print("  joint targets    = all 0 rad")
  print(f"  foot geom center = {foot_z:.4f} m")
  print(f"  foot bottom      = {foot_bottom:.4f} m")
  print("Markers:")
  print("  RED SPHERE  = base_link origin (height / tilt terminate reference)")
  print("  ORANGE BOX  = base_link collision geom")
  print("  RGB AXES    = base_link local x/y/z")
  print("Close the viewer window to exit.")

  with mujoco.viewer.launch_passive(model, data) as viewer:
    viewer.opt.geomgroup[VISUAL_GROUP] = 1
    viewer.opt.geomgroup[COLLISION_GROUP] = 1
    viewer.opt.geomgroup[AXES_GROUP] = 1
    # Hold the pose: do not call mj_step.
    while viewer.is_running():
      viewer.sync()
      time.sleep(0.02)


if __name__ == "__main__":
  main()
