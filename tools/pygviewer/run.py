#!/usr/bin/env python3
"""Entry point that works without a ``tools/__init__.py``.

    mujoco-sim/mjlab/.venv/bin/python3 tools/pygviewer/run.py --variant LegOnly-AB
    mujoco-sim/mjlab/.venv/bin/python3 tools/pygviewer/run.py bake model --all

``python3 -m tools.pygviewer ...`` from the repo root works too (namespace package).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pygviewer.__main__ import main  # noqa: E402

if __name__ == "__main__":
  raise SystemExit(main(sys.argv[1:]))
