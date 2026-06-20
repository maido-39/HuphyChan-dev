# -*- coding: utf-8 -*-
"""Robot spec loader — turns one YAML file into everything the workspace needs.

This is the SINGLE SOURCE OF TRUTH so the user can swap the robot / change physical
properties (mass / inertia / COM) / change joint structure by editing one YAML and running
one convert command, then retrain. Nothing else hardcodes joint/body names.

Public API:
    spec = RobotSpec.from_yaml(path)            # parse + validate (pure python, no Isaac Sim)
    roles(spec) -> dict(base, foot, undesired, action_joints, target_base_height, init_*)
    build_articulation_cfg(spec, usd_path, prim_path) -> ArticulationCfg   (needs Isaac Sim)
    convert_to_usd(spec, force=False) -> usd_path                          (needs Isaac Sim)
    apply_physics_overrides(robot, spec)                                   (needs torch + sim)

Design notes (verified against Isaac Lab 2.2 source):
  * ImplicitActuatorCfg DEPRECATES effort_limit/velocity_limit — for implicit actuators
    velocity_limit is IGNORED. We therefore emit effort_limit_sim / velocity_limit_sim only.
  * Every joint in the USD must belong to some actuator group or Isaac Lab errors at startup;
    the toe is covered by a passive_spring group (validated here).
  * default_mass / default_inertia are captured once at articulation init -> a stable baseline;
    apply_physics_overrides rebuilds from them every call so it is idempotent.
"""

from __future__ import annotations

import math
import os
import re
import warnings
from dataclasses import dataclass, field
from typing import Any

import yaml

RPM2RAD = 2.0 * math.pi / 60.0

# workspace root, computed locally so importing this module does NOT trigger the package
# __init__ (which imports isaaclab) — keeps from_yaml/_validate usable without Isaac Sim.
_THIS = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.abspath(os.path.join(_THIS, "..", "..", ".."))
DEFAULT_SPEC_PATH = os.path.join(WORKSPACE_DIR, "assets", "robot_specs", "robstride_biped.yaml")


@dataclass
class RobotSpec:
    raw: dict
    path: str

    # ----- convenience accessors -----
    @property
    def name(self) -> str:
        return self.raw.get("name", "robot")

    @property
    def source_file(self) -> str:
        return self._abs(self.raw["source"]["file"])

    @property
    def usd_dir(self) -> str:
        return self._abs(self.raw["source"]["usd_dir"])

    @property
    def usd_file_name(self) -> str:
        return self.raw["source"]["usd_file_name"]

    @property
    def usd_path(self) -> str:
        name = self.usd_file_name
        if not name.endswith((".usd", ".usda")):
            name += ".usd"
        return os.path.join(self.usd_dir, name)

    @property
    def actuators(self) -> dict[str, dict]:
        return self.raw["actuators"]

    def _abs(self, p: str) -> str:
        return p if os.path.isabs(p) else os.path.join(WORKSPACE_DIR, p)

    # ----- joint groupings -----
    def motor_joints(self) -> list[str]:
        out: list[str] = []
        for g in self.actuators.values():
            if g.get("type", "motor") == "motor":
                out += list(g["joints"])
        return out

    def passive_joints(self) -> list[str]:
        out: list[str] = []
        for g in self.actuators.values():
            if g.get("type") == "passive_spring":
                out += list(g["joints"])
        return out

    def action_joints(self) -> list[str]:
        aj = self.raw.get("action_joints")
        return list(aj) if aj else self.motor_joints()

    # ----- load + validate -----
    @classmethod
    def from_yaml(cls, path: str | None = None) -> "RobotSpec":
        path = path or DEFAULT_SPEC_PATH
        with open(path) as f:
            raw = yaml.safe_load(f)
        spec = cls(raw=raw, path=path)
        spec._validate()
        return spec

    def _validate(self):
        r = self.raw
        for key in ("source", "init", "roles", "actuators"):
            if key not in r:
                raise ValueError(f"[RobotSpec] missing top-level key '{key}' in {self.path}")
        # actuator group sanity
        all_group_joints: list[str] = []
        for gname, g in self.actuators.items():
            for k in ("joints", "effort_limit", "stiffness", "damping"):
                if k not in g:
                    raise ValueError(f"[RobotSpec] actuator '{gname}' missing '{k}'")
            gtype = g.get("type", "motor")
            if gtype not in ("motor", "passive_spring"):
                raise ValueError(f"[RobotSpec] actuator '{gname}' bad type '{gtype}'")
            if gtype == "passive_spring" and not (g["effort_limit"] > 0):
                raise ValueError(
                    f"[RobotSpec] passive_spring '{gname}' needs effort_limit>0 "
                    f"(0 silently clips the spring torque to zero -> limp joint)"
                )
            all_group_joints += list(g["joints"])
        # action joints: subset of motor, disjoint from passive
        motor, passive = set(self.motor_joints()), set(self.passive_joints())
        for aj in self.action_joints():
            if aj in passive:
                raise ValueError(f"[RobotSpec] action joint '{aj}' is a passive_spring joint")
            if self.raw.get("action_joints") and aj not in motor:
                raise ValueError(f"[RobotSpec] action joint '{aj}' not in any motor group")
        # every init joint must be claimed by some actuator group (else Isaac Lab errors)
        group_set = set(all_group_joints)
        for j in self.raw["init"].get("joint_pos", {}):
            if j not in group_set:
                warnings.warn(
                    f"[RobotSpec] init joint '{j}' is not listed in any actuator group; "
                    f"Isaac Lab requires every joint to be actuated — add it to a group."
                )


# ----------------------------------------------------------------------- roles
def roles(spec: RobotSpec) -> dict[str, Any]:
    rl = spec.raw["roles"]
    return {
        "base": rl["base"],
        "foot": rl["foot"],
        "undesired": list(rl.get("undesired_contact", [])),
        "target_base_height": float(rl.get("target_base_height", 0.85)),
        "action_joints": spec.action_joints(),
        "init_height": float(spec.raw["init"].get("height", 0.9)),
        "init_joint_pos": dict(spec.raw["init"].get("joint_pos", {})),
    }


# --------------------------------------------------- ArticulationCfg (needs sim)
def build_articulation_cfg(spec: RobotSpec, usd_path: str | None = None,
                           prim_path: str = "{ENV_REGEX_NS}/Robot"):
    """Build an ArticulationCfg from the spec. Imports Isaac Lab lazily."""
    import isaaclab.sim as sim_utils
    from isaaclab.actuators import ImplicitActuatorCfg
    from isaaclab.assets import ArticulationCfg

    usd_path = usd_path or spec.usd_path
    rl = roles(spec)

    actuators = {}
    for gname, g in spec.actuators.items():
        kwargs = dict(
            joint_names_expr=list(g["joints"]),
            # *_sim variants: plain effort_limit/velocity_limit are deprecated & velocity_limit
            # is ignored for implicit actuators (Isaac Lab 2.2 actuator_cfg.py).
            effort_limit_sim=float(g["effort_limit"]),
            stiffness=float(g["stiffness"]),
            damping=float(g["damping"]),
        )
        if "velocity_limit_rpm" in g and g["velocity_limit_rpm"] is not None:
            kwargs["velocity_limit_sim"] = float(g["velocity_limit_rpm"]) * RPM2RAD
        if "armature" in g and g["armature"] is not None:
            kwargs["armature"] = float(g["armature"])
        actuators[gname] = ImplicitActuatorCfg(**kwargs)

    cv = spec.raw.get("convert", {})
    return ArticulationCfg(
        prim_path=prim_path,
        spawn=sim_utils.UsdFileCfg(
            usd_path=usd_path,
            activate_contact_sensors=True,
            rigid_props=sim_utils.RigidBodyPropertiesCfg(
                disable_gravity=False, retain_accelerations=False,
                linear_damping=0.0, angular_damping=0.0,
                max_linear_velocity=1000.0, max_angular_velocity=1000.0,
                max_depenetration_velocity=1.0,
            ),
            articulation_props=sim_utils.ArticulationRootPropertiesCfg(
                enabled_self_collisions=bool(cv.get("self_collision", False)),
                solver_position_iteration_count=8, solver_velocity_iteration_count=0,
            ),
        ),
        init_state=ArticulationCfg.InitialStateCfg(
            pos=(0.0, 0.0, rl["init_height"]),
            joint_pos=rl["init_joint_pos"],
            joint_vel={".*": 0.0},
        ),
        soft_joint_pos_limit_factor=0.9,
        actuators=actuators,
    )


def _strip_spurious_worldbody_root(usd_path: str):
    """Deactivate the empty ``worldBody`` Xform the MJCF importer leaves behind with an
    ArticulationRootAPI applied. Without this, Isaac Lab finds TWO articulation roots
    (worldBody + the real base body) and errors with "Failed to find a single articulation".
    Deactivating (vs deleting) is reversible and composes over any sublayer. isaaclab untouched.
    """
    from pxr import Usd, UsdPhysics

    stage = Usd.Stage.Open(usd_path)
    changed = False
    for prim in stage.Traverse():
        if prim.GetName() == "worldBody" and prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            prim.SetActive(False)
            changed = True
            print(f"[convert] deactivated spurious articulation root: {prim.GetPath()}")
    if changed:
        stage.GetRootLayer().Save()


# ----------------------------------------------------- USD conversion (needs sim)
def convert_to_usd(spec: RobotSpec, force: bool = False) -> str:
    """Convert source MJCF/URDF -> USD (auto-selected by extension). Lazy cache: rebuilds
    when the source bytes or convert/* params change; pass force=True after editing a mesh."""
    ext = os.path.splitext(spec.source_file)[1].lower()
    cv = spec.raw.get("convert", {})
    common = dict(
        asset_path=spec.source_file,
        usd_dir=spec.usd_dir,
        usd_file_name=spec.usd_file_name,
        force_usd_conversion=bool(force),
        make_instanceable=bool(cv.get("make_instanceable", True)),
    )
    os.makedirs(spec.usd_dir, exist_ok=True)
    if ext in (".xml", ".mjcf"):
        # MjcfConverter (unlike UrdfConverter) does NOT auto-enable its importer extension,
        # so the "MJCFCreateImportConfig" kit command is unregistered -> enable it ourselves.
        from isaacsim.core.utils.extensions import enable_extension
        import omni.kit.app

        if not omni.kit.app.get_app().get_extension_manager().is_extension_enabled(
            "isaacsim.asset.importer.mjcf"
        ):
            enable_extension("isaacsim.asset.importer.mjcf")

        from isaaclab.sim.converters import MjcfConverter, MjcfConverterCfg
        cfg = MjcfConverterCfg(
            fix_base=bool(cv.get("fix_base", False)),
            import_inertia_tensor=bool(cv.get("import_inertia_tensor", True)),
            self_collision=bool(cv.get("self_collision", False)),
            **common,
        )
        usd_path = MjcfConverter(cfg).usd_path
        _strip_spurious_worldbody_root(usd_path)
        return usd_path
    elif ext == ".urdf":
        from isaaclab.sim.converters import UrdfConverter, UrdfConverterCfg
        cfg = UrdfConverterCfg(
            fix_base=bool(cv.get("fix_base", False)),
            self_collision=bool(cv.get("self_collision", False)),
            merge_fixed_joints=bool(cv.get("merge_fixed_joints", True)),
            # joint drive comes from our ArticulationCfg actuators, not the URDF
            joint_drive=None,
            **common,
        )
        return UrdfConverter(cfg).usd_path
    raise ValueError(f"[RobotSpec] unsupported source extension '{ext}' (use .xml/.mjcf/.urdf)")


# --------------------------------------------- runtime physics overrides (needs torch)
def apply_physics_overrides(robot, spec: RobotSpec):
    """Apply deterministic mass / inertia / COM overrides from spec.physics at runtime.

    Idempotent: rebuilt from robot.data.default_mass/default_inertia each call (a stable
    baseline captured at articulation init), so calling repeatedly is safe.
    """
    import torch

    phys = spec.raw.get("physics", {}) or {}
    scale_all = float(phys.get("mass_scale_all", 1.0))
    overrides = phys.get("overrides", []) or []

    # No spec-level physics change requested -> DON'T touch masses. This lets the env's
    # mass/COM domain-randomization events do their job during training. (Measurement scripts
    # set a deliberate mass via mass_utils / a spec with overrides.)
    if scale_all == 1.0 and not overrides:
        return float(robot.root_physx_view.get_masses()[0].sum())

    view = robot.root_physx_view
    n_env = robot.num_instances if hasattr(robot, "num_instances") else robot.data.default_mass.shape[0]
    env_ids = torch.arange(n_env)
    names = list(robot.body_names)

    masses = (robot.data.default_mass.detach().cpu().clone() * scale_all)
    inertias = (robot.data.default_inertia.detach().cpu().clone() * scale_all)
    coms = view.get_coms().clone()

    def ids_for(regex):
        return [i for i, n in enumerate(names) if re.match(regex, n)]

    touched_com = False
    for ov in overrides:
        ids = ids_for(ov["body"])
        if not ids:
            warnings.warn(f"[physics override] body regex '{ov['body']}' matched no body")
            continue
        idt = torch.tensor(ids, dtype=torch.long)
        if "mass" in ov:
            new_m = float(ov["mass"])
            base = robot.data.default_mass.detach().cpu()[env_ids[:, None], idt]
            ratio = new_m / torch.clamp(base, min=1e-6)
            masses[env_ids[:, None], idt] = new_m
            inertias[env_ids[:, None], idt] = (
                robot.data.default_inertia.detach().cpu()[env_ids[:, None], idt] * ratio[..., None]
            )
        elif "mass_scale" in ov:
            s = float(ov["mass_scale"])
            masses[env_ids[:, None], idt] = robot.data.default_mass.detach().cpu()[env_ids[:, None], idt] * s
            inertias[env_ids[:, None], idt] = robot.data.default_inertia.detach().cpu()[env_ids[:, None], idt] * s
        if "inertia_scale" in ov:
            inertias[env_ids[:, None], idt] = inertias[env_ids[:, None], idt] * float(ov["inertia_scale"])
        if "com" in ov:
            dx = torch.tensor(ov["com"], dtype=coms.dtype)
            coms[env_ids[:, None], idt, 0:3] = coms[env_ids[:, None], idt, 0:3] + dx
            touched_com = True

    view.set_masses(masses, env_ids)
    view.set_inertias(inertias, env_ids)
    if touched_com:
        view.set_coms(coms, env_ids)
    total = float(masses[0].sum())
    print(f"[physics override] mass_scale_all={scale_all}  overrides={len(overrides)}  total_mass={total:.2f} kg")
    return total
