"""Pygmalion constants."""

from pathlib import Path

import mujoco

from mjlab import MJLAB_SRC_PATH
from mjlab.actuator import BuiltinPositionActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.actuator import (
  ElectricActuator,
)
from mjlab.utils.spec_config import CollisionCfg

##
# MJCF and assets.
##

PYG_XML: Path = (
  MJLAB_SRC_PATH / "asset_zoo" / "robots" / "pygmalion" / "xmls" / "pygmalion.xml"
)
assert PYG_XML.exists()


def get_spec() -> mujoco.MjSpec:
  return mujoco.MjSpec.from_file(str(PYG_XML))


##
# Actuator config.
##

# Motor specs

# Path: kbot/ksim-kbot/ksim_kbot/kscale-assets/kbot/robot.mjcf
# <default class="motor_00">
#   <joint armature="0.0005" frictionloss="0.1" actuatorfrcrange="-20.0 20.0" />
#   <motor ctrlrange="-20.0 20.0" />
# </default>
# <default class="motor_02">
#   <joint armature="0.0015" frictionloss="0.1" actuatorfrcrange="-30.0 30.0" />
#   <motor ctrlrange="-30.0 30.0" />
# </default>
# <default class="motor_03">
#   <joint armature="0.005" frictionloss="0.001" actuatorfrcrange="-100.0 100.0" />
#   <motor ctrlrange="-100.0 100.0" />
# </default>
# <default class="motor_04">
#   <joint armature="0.007" frictionloss="0.0015" actuatorfrcrange="-200.0 200.0" />
#   <motor ctrlrange="-200.0 200.0" />
# </default>

# Path: kbot/ksim-kbot/ksim_kbot/kscale-assets/kbot-v2/robot.mjcf
# <default class="motor_00">
#   <joint armature="0.0005" frictionloss="0.1" actuatorfrcrange="-14.0 14.0" />
#   <motor ctrlrange="-14.0 14.0" />
# </default>
# <default class="motor_02">
#   <joint armature="0.002" frictionloss="0.1" actuatorfrcrange="-17.0 17.0" />
#   <motor ctrlrange="-17.0 17.0" />
# </default>
# <default class="motor_03">
#   <joint armature="0.005" frictionloss="0.3" actuatorfrcrange="-60.0 60.0" />
#   <motor ctrlrange="-60.0 60.0" />
# </default>
# <default class="motor_04">
#   <joint armature="0.007" frictionloss="0.1" actuatorfrcrange="-120.0 120.0" />
#   <motor ctrlrange="-120.0 120.0" />
# </default>

ARMATURE_00 = 0.0005
ARMATURE_03 = 0.0050
ARMATURE_04 = 0.0070
ARMATURE_04_KNEES = 0.0070

# velocity_limit, effort_limit
# https://www.scribd.com/document/932254876/ROBSTRIDE-00-Motor-Instruction-Manual
# https://www.scribd.com/document/932254882/ROBSTRIDE-04-Motor-Instruction-Manual

ACTUATOR_00 = ElectricActuator(
  reflected_inertia=ARMATURE_00,
  velocity_limit=33.0,
  effort_limit=14.0,
)
ACTUATOR_03 = ElectricActuator(
  reflected_inertia=ARMATURE_03,
  velocity_limit=20.0,
  effort_limit=60.0,
)
ACTUATOR_04 = ElectricActuator(
  reflected_inertia=ARMATURE_04,
  velocity_limit=15.0,
  effort_limit=120.0,
)
ACTUATOR_04_KNEES = ElectricActuator(
  reflected_inertia=ARMATURE_04_KNEES,
  velocity_limit=15.0,
  effort_limit=120.0,
)

NATURAL_FREQ = 10 * 2.0 * 3.1415926535  # 10Hz
DAMPING_RATIO = 2.0

STIFFNESS_00 = ARMATURE_00 * NATURAL_FREQ**2
STIFFNESS_03 = ARMATURE_03 * NATURAL_FREQ**2
STIFFNESS_04 = ARMATURE_04 * NATURAL_FREQ**2
STIFFNESS_04_KNEES = ARMATURE_04_KNEES * NATURAL_FREQ**2

DAMPING_00 = 2.0 * DAMPING_RATIO * ARMATURE_00 * NATURAL_FREQ
DAMPING_03 = 2.0 * DAMPING_RATIO * ARMATURE_03 * NATURAL_FREQ
DAMPING_04 = 2.0 * DAMPING_RATIO * ARMATURE_04 * NATURAL_FREQ
DAMPING_04_KNEES = 2.0 * DAMPING_RATIO * ARMATURE_04_KNEES * NATURAL_FREQ

# BuiltinPositionActuatorCfg Class의 attribute로
# frictionloss와 viscous_damping을 설정할 수 있음
# 우선은 비워놓고 진행 (2026-06-22)

PYG_ACTUATOR_00 = BuiltinPositionActuatorCfg(
  target_names_expr=(".*_ankle_roll_joint",),
  stiffness=STIFFNESS_00,
  damping=DAMPING_00,
  effort_limit=ACTUATOR_00.effort_limit,
  armature=ACTUATOR_00.reflected_inertia,
)

PYG_ACTUATOR_03 = BuiltinPositionActuatorCfg(
  target_names_expr=(
    ".*_hip_yaw_joint",
    ".*_ankle_pitch_joint",
  ),
  stiffness=STIFFNESS_03,
  damping=DAMPING_03,
  effort_limit=ACTUATOR_03.effort_limit,
  armature=ACTUATOR_03.reflected_inertia,
)

PYG_ACTUATOR_04 = BuiltinPositionActuatorCfg(
  target_names_expr=(
    ".*_hip_pitch_joint",
    ".*_hip_roll_joint",
  ),
  stiffness=STIFFNESS_04,
  damping=DAMPING_04,
  effort_limit=ACTUATOR_04.effort_limit,
  armature=ACTUATOR_04.reflected_inertia,
)

PYG_ACTUATOR_04_KNEES = BuiltinPositionActuatorCfg(
  target_names_expr=(".*_knee_joint",),
  stiffness=STIFFNESS_04_KNEES,
  damping=DAMPING_04_KNEES,
  effort_limit=ACTUATOR_04_KNEES.effort_limit,
  armature=ACTUATOR_04_KNEES.reflected_inertia,
)

##
# Keyframe config.
##

HOME_KEYFRAME = EntityCfg.InitialStateCfg(
  pos=(0, 0, 0.87),
  joint_pos={".*": 0.0},
  joint_vel={".*": 0.0},
)

KNEES_BENT_KEYFRAME = EntityCfg.InitialStateCfg(
  pos=(0, 0, 0.83),
  joint_pos={
    ".*_hip_pitch_joint": -0.32,
    ".*_knee_joint": -0.67,
    ".*_ankle_pitch_joint": 0.36,
  },
  joint_vel={".*": 0.0},
)

##
# Collision config.
##

# This enables all collisions, including self collisions.
# Self-collisions are given condim=1
# while foot collisions are given condim=3.
FULL_COLLISION = CollisionCfg(
  geom_names_expr=(".*_collision",),
  condim={r"^(L|R)_foot[1-7]_collision$": 3, ".*_collision": 1},
  priority={r"^(L|R)_foot[1-7]_collision$": 1},
  friction={r"^(L|R)_foot[1-7]_collision$": (0.6,)},
)

FULL_COLLISION_WITHOUT_SELF = CollisionCfg(
  geom_names_expr=(".*_collision",),
  contype=0,
  conaffinity=1,
  condim={r"^(L|R)_foot[1-7]_collision$": 3, ".*_collision": 1},
  priority={r"^(L|R)_foot[1-7]_collision$": 1},
  friction={r"^(L|R)_foot[1-7]_collision$": (0.6,)},
)

# This disables all collisions except the feet.
# Feet get condim=3, all other geoms are disabled.
FEET_ONLY_COLLISION = CollisionCfg(
  geom_names_expr=(r"^(L|R)_foot[1-7]_collision$",),
  contype=0,
  conaffinity=1,
  condim=3,
  priority=1,
  friction=(0.6,),
)

##
# Final config.
##

PYG_ARTICULATION = EntityArticulationInfoCfg(
  actuators=(
    PYG_ACTUATOR_00,
    PYG_ACTUATOR_03,
    PYG_ACTUATOR_04,
    PYG_ACTUATOR_04_KNEES,
  ),
  soft_joint_pos_limit_factor=0.9,
)


def get_pygmalion_robot_cfg() -> EntityCfg:
  """Get a fresh Pygmalion robot configuration instance.

  Returns a new EntityCfg instance each time to avoid mutation issues when
  the config is shared across multiple places.
  """
  return EntityCfg(
    init_state=KNEES_BENT_KEYFRAME,
    collisions=(FULL_COLLISION,),
    spec_fn=get_spec,
    articulation=PYG_ARTICULATION,
  )


PYG_ACTION_SCALE: dict[str, float] = {}
for a in PYG_ARTICULATION.actuators:
  assert isinstance(a, BuiltinPositionActuatorCfg)
  e = a.effort_limit
  s = a.stiffness
  names = a.target_names_expr
  assert e is not None
  for n in names:
    PYG_ACTION_SCALE[n] = 0.25 * e / s


if __name__ == "__main__":
  import mujoco.viewer as viewer

  from mjlab.entity.entity import Entity

  robot = Entity(get_pygmalion_robot_cfg())

  viewer.launch(robot.spec.compile())
