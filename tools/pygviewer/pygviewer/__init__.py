"""pygviewer - Pygmalion Sim<->Real comparison web viewer.

A single process that owns one MuJoCo model (baked out of the mjlab training env so it
carries the actuators, the floor and the keyframes the raw XML has no idea about), runs it
at the training rates on the CPU, and exposes it two ways:

  * a viser 3D scene + control panel  (default :8094)
  * a FastAPI REST/WebSocket surface  (default :8095, OpenAPI at /docs)

Phases: P0 (bake + sim loop + scene + /status) and P1 (manual joint control, base fixing,
ground toggle, plots) are implemented.  P2 (policy), P3 (telemetry bridge) and P4
(comparison) are skeletons - see ``policy.py``, ``modes.py``, ``record.py`` and
``docs/121_pygviewer_design.md``.

Nothing in this package edits a model XML, a reward file or any mjlab source.  ``bake.py``
is the ONLY module that imports mjlab/torch; everything else is plain mujoco + numpy so the
viewer stays inside a ~300 MB resident footprint while the GPU trainer runs.
"""

__version__ = "0.1.0"

VARIANTS = (
  "FullDoF-AB",
  "FullDoF-RP",
  "SemiFullDoF-AB",
  "SemiFullDoF-RP",
  "LegOnly-AB",
  "LegOnly-RP",
)

CACHE_DIR = "/home/syaro/pyg_fea/pygviewer/cache"
REPO = "/home/syaro/MikuchanRemote/Human-Pygmalion"
