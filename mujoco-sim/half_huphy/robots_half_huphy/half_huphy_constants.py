"""Half Huphy robot asset and articulation configuration."""

from pathlib import Path

import mujoco

from mjlab import MJLAB_SRC_PATH
from mjlab.actuator.xml_actuator import XmlActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg

HALF_HUPHY_XML: Path = (
  MJLAB_SRC_PATH / "asset_zoo" / "robots" / "half_huphy" / "xmls" / "half_huphy.xml"
)
assert HALF_HUPHY_XML.exists()

JOINT_NAMES = (
  "hip_pitch_joint",
  "hip_roll_joint",
  "hip_yaw_joint",
  "knee_pitch_joint",
  "ankle_pitch_joint",
  "ankle_roll_joint",
)


def get_spec() -> mujoco.MjSpec:
  """Load a fresh Half Huphy MJCF specification."""
  return mujoco.MjSpec.from_file(str(HALF_HUPHY_XML))


# Ankle-motor variant: lower peak torque + slightly lighter rotor / friction.
ANKLE_JOINT_NAMES = ("ankle_pitch_joint", "ankle_roll_joint")
ANKLE_ACTUATOR_NAMES = ("ankle_pitch_actuator", "ankle_roll_actuator")
ANKLE14_TORQUE_NM = 14.0
ANKLE14_ARMATURE = 0.002
ANKLE14_FRICTIONLOSS = 0.116


def get_spec_ankle14() -> mujoco.MjSpec:
  """Half Huphy with ankle motors at ±14 Nm, armature 0.002, frictionloss 0.116."""
  spec = get_spec()
  for name in ANKLE_JOINT_NAMES:
    joint = spec.joint(name)
    joint.armature = ANKLE14_ARMATURE
    joint.frictionloss = ANKLE14_FRICTIONLOSS
  for name in ANKLE_ACTUATOR_NAMES:
    act = spec.actuator(name)
    act.forcerange = [-ANKLE14_TORQUE_NM, ANKLE14_TORQUE_NM]
  return spec


# Keep XML link/joint origins unchanged. Only the free-base spawn height is
# lowered so the foot contacts the ground at the zero standing pose.
# Measured foot bottom ≈ +0.022 m when base_z=0.45 and all joints are 0.
STAND_BASE_HEIGHT = 0.428

INIT_STATE = EntityCfg.InitialStateCfg(
  pos=(0.0, 0.0, STAND_BASE_HEIGHT),
  joint_pos={name: 0.0 for name in JOINT_NAMES},
  joint_vel={".*": 0.0},
)

HALF_HUPHY_ARTICULATION = EntityArticulationInfoCfg(
  actuators=(
    XmlActuatorCfg(
      target_names_expr=JOINT_NAMES,
    ),
  ),
  soft_joint_pos_limit_factor=0.9,
)

# Position-action scale used by balance/jump tasks.
HALF_HUPHY_ACTION_SCALE = 0.25


def get_half_huphy_robot_cfg() -> EntityCfg:
  """Return a fresh floating-base Half Huphy entity configuration."""
  return EntityCfg(
    init_state=INIT_STATE,
    spec_fn=get_spec,
    articulation=HALF_HUPHY_ARTICULATION,
  )


def get_half_huphy_ankle14_robot_cfg() -> EntityCfg:
  """Same robot with ankle torque/inertia/friction retuned for JumpKnee training."""
  return EntityCfg(
    init_state=INIT_STATE,
    spec_fn=get_spec_ankle14,
    articulation=HALF_HUPHY_ARTICULATION,
  )
