"""Makes ``python3 -m tools.pygviewer ...`` work from the repo root.

``tools/`` has no ``__init__.py``, so ``tools`` is a PEP 420 namespace package and this file
is what ``-m tools.pygviewer`` executes.  It puts this directory on ``sys.path`` so the inner
``pygviewer`` package is importable, then hands over to the same entry point ``run.py`` uses.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pygviewer.__main__ import main  # noqa: E402

raise SystemExit(main(sys.argv[1:]))
