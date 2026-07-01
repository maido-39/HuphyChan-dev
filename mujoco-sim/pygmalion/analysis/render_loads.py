"""Render a load-coloured video of a measured Pygmalion rollout.

Replays the full qpos trajectory saved by measure_loads.py (no dynamics) and
draws a **coloured sphere indicator at each joint's world anchor**, sized a bit
larger than the joint, coloured by that joint's instantaneous torque saturation:

    |tau| < rated (nominal)      -> grey
    |tau| >= rated               -> YELLOW
    |tau| >= 0.70 * peak         -> ORANGE
    |tau| >= peak                -> RED

A separate sphere per joint disambiguates ankle roll vs pitch and hip
yaw/roll/pitch vs knee (link colouring could not). The ankle_pitch sphere is
lifted toward the shin (above the malleolus, below the calf) so it does not
overlap the ankle_roll sphere.

The robot is rendered on the **actual terrain it walked on** (the compiled model
`<tag>_model.mjb` saved by measure_loads.py, incl. the rough heightfield), so
feet sit on the ground instead of being buried in a flat plane.

Usage:
    MUJOCO_GL=egl uv run python analysis/render_loads.py \
        --npz analysis/out/rough.npz --tag rough --out <docs/mujoco/assets>
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import mujoco

RAD2RPM = 60.0 / (2.0 * np.pi)
SPEC = {  # (peak N*m, rated/continuous N*m)
    "hip_pitch": (120.0, 40.0), "hip_roll": (120.0, 40.0), "hip_yaw": (60.0, 20.0),
    "knee": (120.0, 40.0), "ankle_pitch": (60.0, 20.0), "ankle_roll": (14.0, 5.0),
}
# joint type -> sphere z-offset [m] from its anchor (separate overlapping joints)
JOINT_OFFSET = {"ankle_pitch": 0.08}  # lift above ankle, below calf
LEVEL_COLOUR = {
    0: (0.55, 0.59, 0.64, 1.0), 1: (0.97, 0.86, 0.0, 1.0),
    2: (1.0, 0.50, 0.0, 1.0), 3: (0.95, 0.05, 0.05, 1.0),
}
JTYPES = ["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll"]


def severity(tau_abs, peak, rated):
    if tau_abs >= peak:
        return 3
    if tau_abs >= 0.70 * peak:
        return 2
    if tau_abs >= rated:
        return 1
    return 0


def _jid(m, name):
    j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "robot/" + name)
    if j < 0:
        j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, name)
    return j


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--npz", required=True)
    ap.add_argument("--tag", default="flat")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model-task", default="Mjlab-Velocity-Flat-Pygmalion")
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=540)
    ap.add_argument("--downsample", type=int, default=2)
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--radius", type=float, default=0.06)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    d = np.load(args.npz, allow_pickle=True)
    qpos_full = d["qpos_full"]
    T = len(qpos_full)
    cmd = np.stack([d["cmd_vx"], d["cmd_vy"], d["cmd_wz"]], axis=1)
    dt = float(d["time"][1] - d["time"][0]) if len(d["time"]) > 1 else 0.02

    # Prefer the saved compiled model (real terrain); fall back to building env.
    mjb = os.path.join(os.path.dirname(args.npz), f"{args.tag}_model.mjb")
    if os.path.exists(mjb):
        m = mujoco.MjModel.from_binary_path(mjb)
        print(f"[render] model: {mjb} (real terrain)")
    else:
        import mjlab.tasks  # noqa: F401
        from mjlab.envs import ManagerBasedRlEnv
        from mjlab.tasks.registry import load_env_cfg
        cfg = load_env_cfg(args.model_task, play=True)
        cfg.scene.num_envs = 1
        m = ManagerBasedRlEnv(cfg=cfg, device="cpu").unwrapped.sim.mj_model
        print(f"[render] model: built from {args.model_task} (no saved .mjb)")
    md = mujoco.MjData(m)
    assert m.nq == qpos_full.shape[1], (m.nq, qpos_full.shape)

    # Neutralise ONLY the terrain colour: mjlab tints rough sub-terrains
    # red/orange/yellow by height, which clashes with the load-indicator colours.
    # Recolour to a flat earthy tone (height still reads via 3D shape + shading).
    # The robot is left untouched -- including its base-link CoM marker.
    for g in range(m.ngeom):
        gn = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        if gn.startswith("terrain"):
            m.geom_matid[g] = -1
            m.geom_rgba[g] = (0.62, 0.56, 0.47, 1.0)

    # Per-joint indicators: (jid, tau_key, peak, rated, z_offset)
    inds = []
    for side in ("L", "R"):
        for jt in JTYPES:
            jn = f"{side}_{jt}_joint"
            jid = _jid(m, jn)
            key = "tau_" + jn
            if jid >= 0 and key in d.files:
                pk, rt = SPEC[jt]
                inds.append((jid, key, pk, rt, JOINT_OFFSET.get(jt, 0.0)))
    print(f"[render] joint indicators: {len(inds)}")

    renderer = mujoco.Renderer(m, height=args.height, width=args.width)
    opt = mujoco.MjvOption()
    opt.geomgroup[3] = 0  # hide robot collision capsules (keep terrain)
    cam = mujoco.MjvCamera()
    cam.distance = 2.9   # wide enough to show terrain roughness around the robot
    cam.azimuth = 130.0
    cam.elevation = -18.0
    eye = np.eye(3).flatten()

    try:
        from PIL import Image, ImageDraw
        have_pil = True
    except Exception:
        have_pil = False

    def overlay(img, t):
        if not have_pil:
            return img
        im = Image.fromarray(img)
        dr = ImageDraw.Draw(im)
        vx, vy, wz = cmd[t]
        dr.text((8, 6), f"{args.tag}  t={t * dt:.1f}s  cmd vx={vx:+.1f} vy={vy:+.1f} "
                f"yaw={wz:+.1f}", fill=(255, 255, 255))
        leg = [("<nominal", (140, 150, 163)), (">nominal", (245, 224, 0)),
               (">70% peak", (255, 128, 0)), (">100% peak", (237, 18, 18))]
        for i, (txt, c) in enumerate(leg):
            y = 26 + i * 16
            dr.rectangle([8, y, 22, y + 12], fill=c)
            dr.text((26, y), txt, fill=(255, 255, 255))
        dr.text((8, 26 + 4 * 16 + 4), "spheres = joints (ankle_pitch lifted up shin)",
                fill=(210, 210, 210))
        return np.asarray(im)

    def add_sphere(scn, pos, rgba):
        if scn.ngeom >= scn.maxgeom:
            return
        g = scn.geoms[scn.ngeom]
        mujoco.mjv_initGeom(
            g, int(mujoco.mjtGeom.mjGEOM_SPHERE),
            np.array([args.radius, 0, 0], float), np.asarray(pos, float), eye,
            np.asarray(rgba, np.float32))
        scn.ngeom += 1

    frames = []
    for t in range(0, T, args.downsample):
        md.qpos[:] = qpos_full[t]
        md.qvel[:] = 0.0
        mujoco.mj_forward(m, md)
        cam.lookat[:] = md.qpos[0:3]
        renderer.update_scene(md, cam, opt)
        for jid, key, pk, rt, zoff in inds:
            lvl = severity(abs(float(d[key][t])), pk, rt)
            pos = md.xanchor[jid].copy()
            pos[2] += zoff
            add_sphere(renderer.scene, pos, LEVEL_COLOUR[lvl])
        frames.append(overlay(renderer.render(), t))

    renderer.close()
    out_mp4 = os.path.join(args.out, f"{args.tag}_loadviz.mp4")
    import imageio
    try:
        imageio.mimwrite(out_mp4, frames, fps=args.fps, macro_block_size=None,
                         codec="libx264", quality=7)
        print(f"[render] {len(frames)} frames -> {out_mp4}")
    except Exception as e:
        out_gif = os.path.join(args.out, f"{args.tag}_loadviz.gif")
        imageio.mimwrite(out_gif, frames, fps=args.fps)
        print(f"[render] mp4 failed ({e}); wrote {out_gif}")


if __name__ == "__main__":
    main()
