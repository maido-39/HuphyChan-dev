# -*- coding: utf-8 -*-
"""Convert the robot source file (MJCF .xml/.mjcf OR URDF) to USD, driven by the robot spec.

    python scripts/convert_asset.py            # rebuild USD if source/params changed (lazy cache)
    python scripts/convert_asset.py --force    # always rebuild (needed after editing a referenced mesh)
    python scripts/convert_asset.py --spec assets/robot_specs/other_robot.yaml

The spec (assets/robot_specs/*.yaml) is authoritative: it picks the source file, converter
options and output USD path. To swap robots, edit/point at a different spec and re-run.
"""

from __future__ import annotations

import argparse
import os
import sys

from isaaclab.app import AppLauncher

_THIS = os.path.dirname(os.path.abspath(__file__))
WS = os.path.abspath(os.path.join(_THIS, ".."))
sys.path.insert(0, os.path.join(WS, "source"))  # allow importing the package without install

parser = argparse.ArgumentParser(description="Spec-driven MJCF/URDF -> USD for the biped.")
parser.add_argument("--spec", default=None, help="robot spec YAML (default: robstride_biped.yaml)")
parser.add_argument("--force", action="store_true", help="force re-conversion (e.g. after editing a mesh)")
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.headless = True

app_launcher = AppLauncher(args)
simulation_app = app_launcher.app

import contextlib  # noqa: E402

from pygmalion_locomotion.robots.spec import RobotSpec, convert_to_usd  # noqa: E402


def main():
    spec = RobotSpec.from_yaml(args.spec)
    print(f"[convert] spec   : {spec.path}")
    print(f"[convert] source : {spec.source_file}")
    print(f"[convert] -> usd : {spec.usd_path}  (force={args.force})")
    usd_path = convert_to_usd(spec, force=args.force)
    print(f"[convert] DONE. usd_path = {usd_path}")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        main()
    simulation_app.close()
