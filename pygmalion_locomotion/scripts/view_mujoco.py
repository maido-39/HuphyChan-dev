# -*- coding: utf-8 -*-
"""MuJoCo viewer launcher that starts at the 'stand' keyframe (so the robot is VISIBLE).

`python -m mujoco.viewer --mjcf=scene.xml` starts at qpos0 (base z=0) → the legs penetrate the
floor and the robot gets launched off-screen. This launcher loads the 'stand' keyframe first.

    python scripts/view_mujoco.py            # stand, then free-fall (no balance policy -> collapses)
    python scripts/view_mujoco.py --hold     # hold the standing pose for inspection (no collapse)

Needs a display (run on the machine's desktop). Controls: Space=pause, mouse=orbit/zoom.
"""

from __future__ import annotations

import argparse
import os

import mujoco
import mujoco.viewer

_THIS = os.path.dirname(os.path.abspath(__file__))
WS = os.path.abspath(os.path.join(_THIS, ".."))
DEFAULT_SCENE = os.path.join(WS, "assets", "biped_lower_body_mjcf", "scene.xml")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default=DEFAULT_SCENE)
    ap.add_argument("--keyframe", default="stand")
    ap.add_argument("--hold", action="store_true", help="freeze at the standing pose for inspection")
    args = ap.parse_args()

    m = mujoco.MjModel.from_xml_path(args.scene)
    d = mujoco.MjData(m)
    kid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_KEY, args.keyframe)
    if kid >= 0:
        mujoco.mj_resetDataKeyframe(m, d, kid)
        qpos_stand = d.qpos.copy()
    else:
        qpos_stand = None
    mujoco.mj_forward(m, d)

    with mujoco.viewer.launch_passive(m, d) as viewer:
        while viewer.is_running():
            if args.hold and qpos_stand is not None:
                # keep it standing for static inspection (no collapse)
                d.qpos[:] = qpos_stand
                d.qvel[:] = 0.0
                mujoco.mj_forward(m, d)
            else:
                mujoco.mj_step(m, d)
            viewer.sync()


if __name__ == "__main__":
    main()
