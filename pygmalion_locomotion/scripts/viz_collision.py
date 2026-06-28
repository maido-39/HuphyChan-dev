# -*- coding: utf-8 -*-
"""Visualize the robot's COLLISION geometry (MJCF geom group 3) — capsules + the toe collision mesh.
Renders collision-only views (full body + foot close-up + foot bottom) so we can verify the contact setup
(5 foot_link sole capsules + thigh/shin/torso/head capsules + the newly-added toe collision). Headless MuJoCo.
    python scripts/viz_collision.py
"""
import os
os.environ.setdefault("MUJOCO_GL", "egl")   # headless GL
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mujoco

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML = os.path.join(ROOT, "assets", "biped_lower_body_mjcf", "robot.xml")
OUT = "/tmp"


def main():
    m = mujoco.MjModel.from_xml_path(XML)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    r = mujoco.Renderer(m, 480, 640)   # (h, w) within the default 640x480 offscreen framebuffer
    opt = mujoco.MjvOption()
    for g in range(len(opt.geomgroup)):
        opt.geomgroup[g] = 0
    opt.geomgroup[3] = 1                       # ★ COLLISION group only
    cam = mujoco.MjvCamera()
    mujoco.mjv_defaultFreeCamera(m, cam)

    fid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "L_foot_link")
    foot = d.xpos[fid].copy()
    # count collision geoms
    ncol = sum(1 for i in range(m.ngeom) if m.geom_group[i] == 3)
    print(f"[viz] collision geoms (group 3): {ncol}")
    names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, i) for i in range(m.ngeom) if m.geom_group[i] == 3]
    print(f"[viz] names: {names}")

    views = [
        ("body",  dict(azimuth=90, elevation=-6, distance=2.3, lookat=[0, -0.05, 0.05])),
        ("foot_side", dict(azimuth=90, elevation=-12, distance=0.42, lookat=list(foot))),
        ("foot_persp", dict(azimuth=135, elevation=-35, distance=0.42, lookat=list(foot))),
    ]
    for nm, c in views:
        cam.azimuth = c["azimuth"]; cam.elevation = c["elevation"]; cam.distance = c["distance"]
        cam.lookat[:] = c["lookat"]
        r.update_scene(d, cam, opt)
        img = r.render()
        p = os.path.join(OUT, f"collision_{nm}.png")
        plt.imsave(p, img)
        print(f"[viz] {nm} -> {p}")


if __name__ == "__main__":
    main()
