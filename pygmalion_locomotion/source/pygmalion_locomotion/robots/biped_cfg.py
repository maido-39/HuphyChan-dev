# -*- coding: utf-8 -*-
"""ArticulationCfg for the RobStride lower-body biped — now spec-driven.

Everything (actuators, motor vs passive-spring, init pose, USD path) comes from the YAML
spec (``assets/robot_specs/robstride_biped.yaml``) via ``robots/spec.py``. To change the
robot / its physics / its joint structure, edit that YAML — NOT this file.

Backwards-compatible exports: ``BIPED_CFG`` and ``get_biped_cfg`` are unchanged in signature.
"""

from __future__ import annotations

from .spec import (  # noqa: F401
    DEFAULT_SPEC_PATH,
    RobotSpec,
    apply_physics_overrides,
    build_articulation_cfg,
    convert_to_usd,
    roles,
)

# Loaded once; the env (velocity_env_cfg) reads body/joint roles from here so nothing drifts.
SPEC = RobotSpec.from_yaml(DEFAULT_SPEC_PATH)
ROLES = roles(SPEC)


def get_biped_cfg(usd_path: str | None = None, prim_path: str = "{ENV_REGEX_NS}/Robot",
                  init_height: float | None = None, spec: RobotSpec | None = None):
    """Build the biped ArticulationCfg from the spec.

    Args:
        usd_path: override the converted-USD path (defaults to the spec's usd_path).
        prim_path: USD prim path for the articulation root.
        init_height: optional override of the spawn base height.
        spec: optional pre-loaded RobotSpec (defaults to the module-level SPEC).
    """
    spec = spec or SPEC
    cfg = build_articulation_cfg(spec, usd_path=usd_path, prim_path=prim_path)
    if init_height is not None:
        cfg.init_state.pos = (0.0, 0.0, float(init_height))
    return cfg


# Default instance used by the env configs.
BIPED_CFG = get_biped_cfg()
