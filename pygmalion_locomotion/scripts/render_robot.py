# -*- coding: utf-8 -*-
"""Offscreen-render the MuJoCo robot to PNGs for the docs (CPU/EGL — no Isaac Sim / no display).

    MUJOCO_GL=egl python scripts/render_robot.py --out ../docs/assets

Renders the 'stand' keyframe from several camera angles. Useful any time (independent of the
GPU PhysX driver situation) to visually document the robot / a swapped robot file.
"""

from __future__ import annotations

import argparse
import os

os.environ.setdefault("MUJOCO_GL", "egl")  # GPU-less offscreen via EGL

import mujoco
import numpy as np
from PIL import Image

_THIS = os.path.dirname(os.path.abspath(__file__))
WS = os.path.abspath(os.path.join(_THIS, ".."))
DEFAULT_SCENE = os.path.join(WS, "assets", "biped_lower_body_mjcf", "scene.xml")

# (name, azimuth, elevation, distance) free-camera views around lookat=(0,0,0.55)
VIEWS = [
    ("perspective", 125, -18, 2.6),
    ("side_sagittal", 90, -8, 2.4),
    ("front_coronal", 180, -8, 2.4),
    ("back", 0, -8, 2.4),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default=DEFAULT_SCENE)
    ap.add_argument("--out", default=os.path.join(WS, "..", "docs", "assets"))
    ap.add_argument("--prefix", default="robot")
    ap.add_argument("--width", type=int, default=1100)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--keyframe", default="stand")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    m = mujoco.MjModel.from_xml_path(args.scene)
    # enlarge the offscreen framebuffer to the requested resolution (default is 640x480)
    m.vis.global_.offwidth = max(args.width, int(m.vis.global_.offwidth))
    m.vis.global_.offheight = max(args.height, int(m.vis.global_.offheight))
    d = mujoco.MjData(m)
    # set the named keyframe if present
    kid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_KEY, args.keyframe)
    if kid >= 0:
        mujoco.mj_resetDataKeyframe(m, d, kid)
    mujoco.mj_forward(m, d)

    renderer = mujoco.Renderer(m, args.height, args.width)
    cam = mujoco.MjvCamera()
    cam.lookat[:] = [0.0, 0.0, 0.55]

    saved = []
    for name, az, el, dist in VIEWS:
        cam.azimuth, cam.elevation, cam.distance = az, el, dist
        renderer.update_scene(d, cam)
        img = renderer.render()
        path = os.path.join(args.out, f"{args.prefix}_{name}.png")
        Image.fromarray(img).save(path)
        saved.append(path)
        print(f"[render] {path}  ({img.shape[1]}x{img.shape[0]})")

    # quick model summary alongside the images
    print(f"[render] model: nbody={m.nbody} njnt={m.njnt} nq={m.nq} nv={m.nv} actuators={m.nu}")
    print(f"[render] saved {len(saved)} images to {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
