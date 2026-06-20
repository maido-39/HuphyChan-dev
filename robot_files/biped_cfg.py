# -*- coding: utf-8 -*-
"""
Isaac Lab ArticulationCfg for the RobStride-driven lower-body biped.

Pipeline:
    robot.xml (MJCF)  --MjcfConverter-->  biped_lower_body.usd  --> this cfg

Actuator limits are derived from the real motors (output-shaft values):
    RS04 : peak 120 N*m, no-load 200 rpm (20.9 rad/s)            -> hip pitch, hip roll
    RS04 + AT3 belt 1:3 : peak 360 N*m, no-load 66.7 rpm (6.98)  -> knee
    RS03 : peak 60  N*m, no-load 220 rpm (23.0 rad/s)            -> hip yaw, ankle pitch (link-driven)
    RS00 : peak 14  N*m, no-load 315 rpm (33.0 rad/s)            -> ankle roll
    toe  : passive (no motor) -> handled as a passive spring/damper joint in the MJCF

NOTE: stiffness/damping below are RL starting points - tune for your task.
"""

import math

import isaaclab.sim as sim_utils
from isaaclab.actuators import ImplicitActuatorCfg  # swap to DCMotorCfg for torque-speed droop
from isaaclab.assets import ArticulationCfg

# ----------------------------------------------------------------------------
# 1) (one-time) Convert robot.xml -> USD with the Isaac Lab MJCF converter.
#    Run this once, then point UsdFileCfg at the produced .usd.
# ----------------------------------------------------------------------------
# from isaaclab.sim.converters import MjcfConverter, MjcfConverterCfg
# cfg = MjcfConverterCfg(
#     asset_path="robot.xml",
#     usd_dir="./usd",
#     usd_file_name="biped_lower_body.usd",
#     fix_base=False,              # floating-base locomotion
#     import_inertia_tensor=True,  # use the <inertial> tags from the MJCF
#     self_collision=False,        # match the MJCF contype/conaffinity scheme
#     make_instanceable=True,
# )
# usd_path = MjcfConverter(cfg).usd_path

RPM2RAD = 2.0 * math.pi / 60.0

BIPED_CFG = ArticulationCfg(
    spawn=sim_utils.UsdFileCfg(
        usd_path="./usd/biped_lower_body.usd",  # <-- output of MjcfConverter
        activate_contact_sensors=True,
        rigid_props=sim_utils.RigidBodyPropertiesCfg(
            disable_gravity=False,
            retain_accelerations=False,
            linear_damping=0.0,
            angular_damping=0.0,
            max_linear_velocity=1000.0,
            max_angular_velocity=1000.0,
            max_depenetration_velocity=1.0,
        ),
        articulation_props=sim_utils.ArticulationRootPropertiesCfg(
            enabled_self_collisions=False,
            solver_position_iteration_count=8,
            solver_velocity_iteration_count=0,
        ),
    ),
    init_state=ArticulationCfg.InitialStateCfg(
        pos=(0.0, 0.0, 0.87),  # spawn height (lowest foot point ~ ground)
        joint_pos={
            ".*_hip_pitch_joint": 0.0,
            ".*_hip_roll_joint": 0.0,
            ".*_hip_yaw_joint": 0.0,
            ".*_knee_joint": 0.0,
            ".*_ankle_pitch_joint": 0.0,
            ".*_ankle_roll_joint": 0.0,
            ".*_toe_joint": 0.0,
        },
        joint_vel={".*": 0.0},
    ),
    soft_joint_pos_limit_factor=0.9,
    actuators={
        # --- RS04 : hip pitch + hip roll ---
        "hip_rs04": ImplicitActuatorCfg(
            joint_names_expr=[".*_hip_pitch_joint", ".*_hip_roll_joint"],
            effort_limit=120.0,
            velocity_limit=200.0 * RPM2RAD,   # 20.9 rad/s
            stiffness=200.0,
            damping=5.0,
            armature=0.0097,
        ),
        # --- RS03 : hip yaw ---
        "hip_yaw_rs03": ImplicitActuatorCfg(
            joint_names_expr=[".*_hip_yaw_joint"],
            effort_limit=60.0,
            velocity_limit=220.0 * RPM2RAD,   # 23.0 rad/s
            stiffness=150.0,
            damping=5.0,
            armature=0.0049,
        ),
        # --- RS04 + AT3 belt 1:3 : knee (peak 120*3 = 360 N*m, speed /3) ---
        "knee_rs04_belt": ImplicitActuatorCfg(
            joint_names_expr=[".*_knee_joint"],
            effort_limit=360.0,
            velocity_limit=(200.0 / 3.0) * RPM2RAD,  # 6.98 rad/s
            stiffness=200.0,
            damping=5.0,
            armature=0.0875,  # reflected rotor inertia incl. belt (J_rotor * (9*3)^2)
        ),
        # --- RS03 : ankle pitch (link-driven; assumes ~1:1 effective ratio) ---
        "ankle_pitch_rs03": ImplicitActuatorCfg(
            joint_names_expr=[".*_ankle_pitch_joint"],
            effort_limit=60.0,
            velocity_limit=220.0 * RPM2RAD,
            stiffness=80.0,
            damping=3.0,
            armature=0.0049,
        ),
        # --- RS00 : ankle roll ---
        "ankle_roll_rs00": ImplicitActuatorCfg(
            joint_names_expr=[".*_ankle_roll_joint"],
            effort_limit=14.0,
            velocity_limit=315.0 * RPM2RAD,   # 33.0 rad/s
            stiffness=40.0,
            damping=2.0,
            armature=0.0015,
        ),
        # --- passive toe (no motor): tiny stiffness/damping only ---
        "toe_passive": ImplicitActuatorCfg(
            joint_names_expr=[".*_toe_joint"],
            effort_limit=0.0,
            velocity_limit=33.0,
            stiffness=20.0,
            damping=0.5,
            armature=0.0005,
        ),
    },
)
