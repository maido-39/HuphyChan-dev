# -*- coding: utf-8 -*-
"""Pygmalion locomotion — external Isaac Lab workspace for the RobStride lower-body biped.

This package is intentionally separate from the Isaac Lab source tree: it only *imports*
isaaclab / isaaclab_tasks and never modifies them. Importing this package registers the
custom Gym environments (see ``pygmalion_locomotion.tasks``).
"""

import os

# ---------------------------------------------------------------------------
# Filesystem anchors (resolved relative to this file, so the workspace is movable)
# ---------------------------------------------------------------------------
# .../pygmalion_locomotion/source/pygmalion_locomotion/__init__.py
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
# repo workspace root: .../pygmalion_locomotion
WORKSPACE_DIR = os.path.abspath(os.path.join(_PKG_DIR, "..", ".."))
ASSETS_DIR = os.path.join(WORKSPACE_DIR, "assets")
USD_DIR = os.path.join(WORKSPACE_DIR, "usd")
LOGS_DIR = os.path.join(WORKSPACE_DIR, "logs")

# Default converted-USD path (output of scripts/convert_asset.py)
BIPED_USD_PATH = os.path.join(USD_DIR, "biped_lower_body.usd")
# Source MJCF (extracted from robot_files, kept read-only-ish under assets/)
BIPED_MJCF_PATH = os.path.join(ASSETS_DIR, "biped_lower_body_mjcf", "robot.xml")

# Register Gym environments on import (guarded so a bare import without isaaclab
# installed — e.g. for path inspection — does not hard-fail).
try:  # pragma: no cover - import side effect
    from . import tasks  # noqa: F401
except Exception as _e:  # noqa: BLE001
    import warnings

    warnings.warn(f"[pygmalion_locomotion] task registration deferred: {_e}")
