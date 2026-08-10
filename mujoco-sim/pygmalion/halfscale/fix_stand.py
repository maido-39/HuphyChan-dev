"""FixStand joint-space controller for the half-scale Pygmalion leg.

The controller is intentionally independent of the viewer and simulation loop
so it can later be used as an FSM state:

  controller.enter(model, data)
  controller.run(model, data, control_dt)
  mujoco.mj_step(model, data)
  controller.exit(data)

Running this file directly opens a MuJoCo viewer for a standalone test.
"""

from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass
from pathlib import Path

import mujoco
import mujoco.viewer
import numpy as np


PACKAGE_DIR = (
    Path(__file__).parent / "0.5Scale_HuphyChan_SIM_URDF_nohistory_description"
)
XACRO_PATH = PACKAGE_DIR / "urdf/0.5Scale_HuphyChan_SIM_URDF_nohistory.xacro"
GENERATED_URDF_PATH = Path("/tmp/halfscale_leg_fix_stand.urdf")
FALL_TEST_URDF_PATH = Path("/tmp/halfscale_leg_fix_stand_fall_test.urdf")


@dataclass(frozen=True)
class JointPdConfig:
    """PD and target configuration for one joint."""

    role: str
    target_position: float
    kp: float
    kd: float
    torque_limit: float
    armature: float


# Provisional gains inherited from the current full-size Pygmalion motor model:
#   RS00: ankle roll                     (Kp=1.97,  Kd=0.126, 14 Nm)
#   RS03: hip yaw and ankle pitch        (Kp=19.74, Kd=1.257, 60 Nm)
#   RS04: hip pitch, hip roll, and knee  (Kp=27.63, Kd=1.759, 120 Nm)
#
# The URDF only contains generic Revolute names and does not identify motors.
# Roles below are inferred from the link chain and joint axes. Verify this map
# and replace the gains with half-scale hardware values before real deployment.
FIX_STAND_JOINTS: dict[str, JointPdConfig] = {
    "Revolute 9": JointPdConfig(
        role="hip_roll",
        target_position=0.0,
        kp=27.6349,
        kd=1.7593,
        torque_limit=120.0,
        armature=0.007,
    ),
    "Revolute 11": JointPdConfig(
        role="hip_pitch",
        target_position=0.0,
        kp=27.6349,
        kd=1.7593,
        torque_limit=120.0,
        armature=0.007,
    ),
    "Revolute 12": JointPdConfig(
        role="hip_yaw",
        target_position=0.0,
        kp=19.7392,
        kd=1.2566,
        torque_limit=60.0,
        armature=0.005,
    ),
    "Revolute 13": JointPdConfig(
        role="knee",
        target_position=0.0,
        kp=27.6349,
        kd=1.7593,
        torque_limit=120.0,
        armature=0.007,
    ),
    "Revolute 14": JointPdConfig(
        role="ankle_pitch",
        target_position=0.0,
        kp=19.7392,
        kd=1.2566,
        torque_limit=60.0,
        armature=0.005,
    ),
    "Revolute 15": JointPdConfig(
        role="ankle_roll",
        target_position=0.0,
        kp=1.9739,
        kd=0.1257,
        torque_limit=14.0,
        armature=0.0005,
    ),
}


@dataclass(frozen=True)
class _JointBinding:
    """Resolved MuJoCo addresses for one configured joint."""

    name: str
    qpos_address: int
    dof_address: int
    config: JointPdConfig


class FixStandController:
    """Interpolate to a fixed pose, then hold it with per-joint PD control."""

    def __init__(
        self,
        joint_configs: dict[str, JointPdConfig] | None = None,
        transition_duration: float = 3.0,
        gravity_compensation: bool = True,
    ) -> None:
        if transition_duration <= 0.0:
            raise ValueError("transition_duration must be positive")

        self.joint_configs = joint_configs or FIX_STAND_JOINTS
        self.transition_duration = transition_duration
        self.gravity_compensation = gravity_compensation
        self._bindings: tuple[_JointBinding, ...] = ()
        self._start_positions = np.empty(0)
        self._elapsed = 0.0
        self._active = False

    @property
    def transition_complete(self) -> bool:
        """Whether the controller reached the final FixStand target."""
        return self._elapsed >= self.transition_duration

    def enter(self, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        """Capture the current pose and initialize the FixStand transition."""
        bindings: list[_JointBinding] = []

        for name, config in self.joint_configs.items():
            joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if joint_id < 0:
                raise ValueError(f"FixStand joint not found in model: {name}")
            if model.jnt_type[joint_id] != mujoco.mjtJoint.mjJNT_HINGE:
                raise ValueError(f"FixStand only supports hinge joints: {name}")

            dof_address = int(model.jnt_dofadr[joint_id])
            # The physical motor contributes this reflected inertia. The source
            # URDF does not carry it, so apply it when binding the controller.
            model.dof_armature[dof_address] = config.armature

            bindings.append(
                _JointBinding(
                    name=name,
                    qpos_address=int(model.jnt_qposadr[joint_id]),
                    dof_address=dof_address,
                    config=config,
                )
            )

        # Refresh the mass matrix and bias forces after changing armatures.
        mujoco.mj_forward(model, data)

        self._bindings = tuple(bindings)
        self._start_positions = np.array(
            [data.qpos[b.qpos_address] for b in self._bindings],
            dtype=np.float64,
        )
        self._elapsed = 0.0
        self._active = True

    def run(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
        control_dt: float,
    ) -> None:
        """Write one control cycle of torques into ``data.qfrc_applied``."""
        if not self._active:
            raise RuntimeError("FixStandController.enter() must be called first")
        if control_dt <= 0.0:
            raise ValueError("control_dt must be positive")

        phase = min(self._elapsed / self.transition_duration, 1.0)
        blend = phase * phase * (3.0 - 2.0 * phase)

        # The FSM owns qfrc_applied while FixStand is active.
        data.qfrc_applied[:] = 0.0

        for index, binding in enumerate(self._bindings):
            cfg = binding.config
            q_desired = (1.0 - blend) * self._start_positions[
                index
            ] + blend * cfg.target_position
            torque = (
                cfg.kp * (q_desired - data.qpos[binding.qpos_address])
                - cfg.kd * data.qvel[binding.dof_address]
            )

            if self.gravity_compensation:
                torque += data.qfrc_bias[binding.dof_address]

            data.qfrc_applied[binding.dof_address] = np.clip(
                torque,
                -cfg.torque_limit,
                cfg.torque_limit,
            )

        self._elapsed += control_dt

    def exit(self, data: mujoco.MjData) -> None:
        """Stop FixStand output and clear externally applied torques."""
        data.qfrc_applied[:] = 0.0
        self._active = False


def build_standalone_urdf(floating_with_floor: bool = False) -> Path:
    """Expand the simple xacro into a URDF that MuJoCo can load without ROS."""
    source = XACRO_PATH.read_text()
    source = re.sub(r"<xacro:include[^/]*/>\n?", "", source)
    source = source.replace(
        ' xmlns:xacro="http://www.ros.org/wiki/xacro"',
        "",
    )
    source = source.replace(
        "package://0.5Scale_HuphyChan_SIM_URDF_nohistory_description/meshes/",
        f"{PACKAGE_DIR / 'meshes'}/",
    )
    source = re.sub(r'\s*<material name="[^"]+"/>', "", source)

    if not floating_with_floor:
        GENERATED_URDF_PATH.write_text(source)
        return GENERATED_URDF_PATH

    # The original URDF has a fixed root and no world geometry. Add a floating
    # root plus a fixed floor for an interactive drop/FixStand demonstration.
    world = """
<link name="world"/>
<link name="ground">
  <visual>
    <origin xyz="0 0 -0.05" rpy="0 0 0"/>
    <geometry><box size="6 6 0.1"/></geometry>
  </visual>
  <collision name="ground_collision">
    <origin xyz="0 0 -0.05" rpy="0 0 0"/>
    <geometry><box size="6 6 0.1"/></geometry>
  </collision>
</link>
<joint name="world_to_ground" type="fixed">
  <parent link="world"/>
  <child link="ground"/>
</joint>
<joint name="root" type="floating">
  <origin xyz="0 0 0.55" rpy="0 0 0"/>
  <parent link="world"/>
  <child link="base_link"/>
</joint>
"""
    source = source.replace("</robot>", f"{world}\n</robot>")
    FALL_TEST_URDF_PATH.write_text(source)
    return FALL_TEST_URDF_PATH


def configure_fall_test_collisions(model: mujoco.MjModel) -> None:
    """Enable ground and non-adjacent-link self-collisions."""
    ground_geom_id = mujoco.mj_name2id(
        model,
        mujoco.mjtObj.mjOBJ_GEOM,
        "ground_collision",
    )
    if ground_geom_id < 0:
        raise ValueError("Fall-test ground geom was not compiled")

    shin_body_id = mujoco.mj_name2id(
        model,
        mujoco.mjtObj.mjOBJ_BODY,
        "shin_link_1",
    )
    foot_body_id = mujoco.mj_name2id(
        model,
        mujoco.mjtObj.mjOBJ_BODY,
        "foot_link_1",
    )
    if shin_body_id < 0 or foot_body_id < 0:
        raise ValueError("Fall-test shin or foot body was not compiled")

    # MuJoCo already filters direct parent-child collisions. Enable the other
    # robot pairs, except shin<>foot: their raw STL convex hulls overlap by
    # 27 mm even in the valid zero pose. Separate collision bits suppress only
    # that known export artifact while preserving their contacts with all other
    # links and with the floor.
    model.geom_contype[:] = 1
    model.geom_conaffinity[:] = 0b0111

    shin_geoms = model.geom_bodyid == shin_body_id
    model.geom_contype[shin_geoms] = 0b0010
    model.geom_conaffinity[shin_geoms] = 0b0001

    foot_geoms = model.geom_bodyid == foot_body_id
    model.geom_contype[foot_geoms] = 0b0100
    model.geom_conaffinity[foot_geoms] = 0b0001

    model.geom_contype[ground_geom_id] = 0b1000
    model.geom_conaffinity[ground_geom_id] = 0b0111
    model.geom_rgba[ground_geom_id] = (0.72, 0.86, 0.96, 1.0)

    # Bright neutral lighting makes the silver robot readable against the floor.
    model.vis.headlight.ambient[:] = (0.55, 0.55, 0.55)
    model.vis.headlight.diffuse[:] = (0.8, 0.8, 0.8)
    model.vis.headlight.specular[:] = (0.2, 0.2, 0.2)


def add_blue_viewer_grid(scene: mujoco.MjvScene) -> None:
    """Add a visual-only blue 25 cm grid over the six-metre floor."""
    scene.ngeom = 0
    half_extent = 3.0
    coordinates = np.arange(-half_extent, half_extent + 0.001, 0.25)
    identity = np.eye(3).ravel()

    for coordinate in coordinates:
        is_major = abs(coordinate - round(coordinate)) < 1e-6
        width = 0.006 if is_major else 0.0025
        color = np.array(
            (0.05, 0.25, 0.55, 0.9) if is_major else (0.18, 0.48, 0.78, 0.55),
            dtype=np.float32,
        )

        for position, size in (
            ((coordinate, 0.0, 0.002), (width, half_extent, 0.001)),
            ((0.0, coordinate, 0.002), (half_extent, width, 0.001)),
        ):
            if scene.ngeom >= len(scene.geoms):
                raise RuntimeError("MuJoCo user scene has no room for floor grid")
            geom = scene.geoms[scene.ngeom]
            mujoco.mjv_initGeom(
                geom,
                type=mujoco.mjtGeom.mjGEOM_BOX,
                size=np.asarray(size, dtype=np.float64),
                pos=np.asarray(position, dtype=np.float64),
                mat=identity,
                rgba=color,
            )
            geom.category = mujoco.mjtCatBit.mjCAT_DECOR
            scene.ngeom += 1


def set_fall_test_initial_pose(model: mujoco.MjModel, data: mujoco.MjData) -> None:
    """Reset the floating root above the floor with an intentional tilt."""
    mujoco.mj_resetData(model, data)
    root_joint_id = mujoco.mj_name2id(
        model,
        mujoco.mjtObj.mjOBJ_JOINT,
        "root",
    )
    if root_joint_id < 0:
        raise ValueError("Fall-test floating root joint was not compiled")

    qpos_address = int(model.jnt_qposadr[root_joint_id])
    tilt = np.deg2rad(35.0)
    data.qpos[qpos_address : qpos_address + 3] = (0.0, 0.0, 0.55)
    # MuJoCo free-joint quaternion order is w, x, y, z.
    data.qpos[qpos_address + 3 : qpos_address + 7] = (
        np.cos(tilt / 2.0),
        0.0,
        np.sin(tilt / 2.0),
        0.0,
    )
    mujoco.mj_forward(model, data)


def print_joint_config() -> None:
    """Print the active per-joint FixStand parameters."""
    print("FixStand joint configuration:")
    for name, cfg in FIX_STAND_JOINTS.items():
        print(
            f"  {name:11s} {cfg.role:12s} "
            f"q={cfg.target_position:+.3f} "
            f"Kp={cfg.kp:7.4f} Kd={cfg.kd:6.4f} "
            f"limit={cfg.torque_limit:5.1f} Nm "
            f"armature={cfg.armature:.4f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the half-scale leg FixStand controller in MuJoCo."
    )
    parser.add_argument(
        "--transition-time",
        type=float,
        default=3.0,
        help="Seconds to interpolate from the current pose to FixStand.",
    )
    parser.add_argument(
        "--no-gravity-compensation",
        action="store_true",
        help="Use pure PD without MuJoCo gravity compensation.",
    )
    parser.add_argument(
        "--fall-test",
        action="store_true",
        help="Drop a floating leg on a floor; press F to engage FixStand.",
    )
    args = parser.parse_args()

    model = mujoco.MjModel.from_xml_path(
        str(build_standalone_urdf(floating_with_floor=args.fall_test))
    )
    model.opt.timestep = 0.002

    if args.fall_test:
        configure_fall_test_collisions(model)
    else:
        # The raw URDF starts with five false mesh self-contacts.
        model.geom_contype[:] = 0
        model.geom_conaffinity[:] = 0

    data = mujoco.MjData(model)
    if args.fall_test:
        set_fall_test_initial_pose(model, data)
    else:
        mujoco.mj_forward(model, data)

    controller = FixStandController(
        transition_duration=args.transition_time,
        gravity_compensation=not args.no_gravity_compensation,
    )
    controller_active = not args.fall_test
    if controller_active:
        controller.enter(model, data)

    print_joint_config()
    requests = {"fix_stand": False, "reset": False}

    def on_key(keycode: int) -> None:
        if keycode == ord("F"):
            requests["fix_stand"] = True
        elif keycode == ord("R"):
            requests["reset"] = True

    if args.fall_test:
        print("\nFall test controls:")
        print("  F: engage/restart FixStand from the current fallen pose")
        print("  R: reset and drop the leg again")

    try:
        with mujoco.viewer.launch_passive(
            model,
            data,
            key_callback=on_key,
        ) as viewer:
            if args.fall_test:
                add_blue_viewer_grid(viewer.user_scn)

            while viewer.is_running():
                step_started = time.monotonic()

                if requests["reset"] and args.fall_test:
                    controller.exit(data)
                    controller_active = False
                    set_fall_test_initial_pose(model, data)
                    requests["reset"] = False

                if requests["fix_stand"]:
                    controller.enter(model, data)
                    controller_active = True
                    requests["fix_stand"] = False

                if controller_active:
                    controller.run(model, data, model.opt.timestep)

                mujoco.mj_step(model, data)
                viewer.sync()

                remaining = model.opt.timestep - (time.monotonic() - step_started)
                if remaining > 0.0:
                    time.sleep(remaining)
    finally:
        if controller_active:
            controller.exit(data)


if __name__ == "__main__":
    main()
