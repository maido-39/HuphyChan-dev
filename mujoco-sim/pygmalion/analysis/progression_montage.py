"""Montage video of the policy across training checkpoints (load-coloured).

Renders several 3000-iter checkpoints side-by-side in a grid, each robot replaying
the SAME (seed-fixed) command sequence, so you see how the gait + joint loads
evolve with training. Per-joint sphere indicators use the same colour scheme as
render_loads.py (grey<rated · yellow≥nominal · orange≥70%peak · red≥peak).

Reads analysis/out/prog/prog_<iter>.npz (+ prog_<iter>_model.mjb) from
progression.sh. Re-runnable as new checkpoints appear.

Usage:
  MUJOCO_GL=egl uv run python analysis/progression_montage.py --out <docs/mujoco/assets>
"""

from __future__ import annotations

import argparse
import glob
import os
import re

import numpy as np
import mujoco

SPEC = {
    "hip_pitch": (120.0, 40.0), "hip_roll": (120.0, 40.0), "hip_yaw": (60.0, 20.0),
    "knee": (120.0, 40.0), "ankle_pitch": (60.0, 20.0), "ankle_roll": (14.0, 5.0),
}
JTYPES = ["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll"]
JOINT_OFFSET = {"ankle_pitch": 0.08}
LEVEL = {0: (0.55, 0.59, 0.64, 1.0), 1: (0.97, 0.86, 0.0, 1.0),
         2: (1.0, 0.50, 0.0, 1.0), 3: (0.95, 0.05, 0.05, 1.0)}


def sev(t, pk, rt):
    return 3 if t >= pk else 2 if t >= 0.7 * pk else 1 if t >= rt else 0


def spec_for(n):
    for k, v in SPEC.items():
        if k in n:
            return v
    return None


def _jid(m, n):
    j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "robot/" + n)
    return j if j >= 0 else mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, n)


class Panel:
    """One checkpoint's renderer + data."""

    def __init__(self, it, npz, mjb, w, h, radius):
        self.it = it
        self.d = np.load(npz, allow_pickle=True)
        self.q = self.d["qpos_full"]
        self.m = mujoco.MjModel.from_binary_path(mjb)
        for g in range(self.m.ngeom):
            gn = mujoco.mj_id2name(self.m, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
            if gn.startswith("terrain"):
                self.m.geom_matid[g] = -1
                self.m.geom_rgba[g] = (0.62, 0.56, 0.47, 1.0)
        self.md = mujoco.MjData(self.m)
        self.inds = []
        for side in ("L", "R"):
            for jt in JTYPES:
                jn = f"{side}_{jt}_joint"
                jid = _jid(self.m, jn)
                if jid >= 0 and "tau_" + jn in self.d.files:
                    pk, rt = SPEC[jt]
                    self.inds.append((jid, "tau_" + jn, pk, rt, JOINT_OFFSET.get(jt, 0.0)))
        self.r = mujoco.Renderer(self.m, height=h, width=w)
        self.opt = mujoco.MjvOption(); self.opt.geomgroup[3] = 0
        self.cam = mujoco.MjvCamera()
        self.cam.distance = 2.6; self.cam.azimuth = 130.0; self.cam.elevation = -14.0
        self.radius = radius
        self._eye = np.eye(3).flatten()

    def frame(self, t):
        t = min(t, len(self.q) - 1)
        self.md.qpos[:] = self.q[t]; self.md.qvel[:] = 0.0
        mujoco.mj_forward(self.m, self.md)
        self.cam.lookat[:] = self.md.qpos[0:3]
        self.r.update_scene(self.md, self.cam, self.opt)
        scn = self.r.scene
        for jid, key, pk, rt, z in self.inds:
            lvl = sev(abs(float(self.d[key][t])), pk, rt)
            pos = self.md.xanchor[jid].copy(); pos[2] += z
            if scn.ngeom < scn.maxgeom:
                mujoco.mjv_initGeom(scn.geoms[scn.ngeom], int(mujoco.mjtGeom.mjGEOM_SPHERE),
                                    np.array([self.radius, 0, 0], float), pos, self._eye,
                                    np.asarray(LEVEL[lvl], np.float32))
                scn.ngeom += 1
        return self.r.render()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prog-dir", default="analysis/out/prog")
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=6, help="how many checkpoints to tile")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--tile-w", type=int, default=440)
    ap.add_argument("--tile-h", type=int, default=380)
    ap.add_argument("--downsample", type=int, default=0)
    ap.add_argument("--fps", type=int, default=25)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    files = sorted(glob.glob(os.path.join(args.prog_dir, "prog_*.npz")),
                   key=lambda f: int(re.search(r"prog_(\d+)", f).group(1)))
    files = [f for f in files if os.path.exists(f.replace(".npz", "_model.mjb"))]
    if not files:
        print("[montage] no prog npz+mjb"); return
    # evenly spaced selection
    idx = np.linspace(0, len(files) - 1, min(args.n, len(files))).round().astype(int)
    sel = [files[i] for i in sorted(set(idx))]
    panels = []
    for f in sel:
        it = int(re.search(r"prog_(\d+)", f).group(1))
        panels.append(Panel(it, f, f.replace(".npz", "_model.mjb"),
                            args.tile_w, args.tile_h, 0.055))
    T = min(len(p.q) for p in panels)
    ds = args.downsample or max(1, T // 600)
    cmd = np.stack([panels[0].d["cmd_vx"], panels[0].d["cmd_vy"], panels[0].d["cmd_wz"]], 1)
    dt = float(panels[0].d["time"][1] - panels[0].d["time"][0])
    print(f"[montage] {len(panels)} checkpoints {[p.it for p in panels]}, T={T} ds={ds}")

    try:
        from PIL import Image, ImageDraw
        pil = True
    except Exception:
        pil = False
    cols = args.cols
    rows = int(np.ceil(len(panels) / cols))

    frames = []
    for t in range(0, T, ds):
        tiles = []
        for p in panels:
            img = p.frame(t)
            if pil:
                im = Image.fromarray(img); dr = ImageDraw.Draw(im)
                dr.rectangle([0, 0, 96, 16], fill=(0, 0, 0))
                dr.text((3, 3), f"iter {p.it}", fill=(255, 255, 0))
                img = np.asarray(im)
            tiles.append(img)
        # pad to full grid
        while len(tiles) < rows * cols:
            tiles.append(np.zeros_like(tiles[0]))
        grid = np.concatenate([np.concatenate(tiles[r * cols:(r + 1) * cols], axis=1)
                               for r in range(rows)], axis=0)
        if pil:
            im = Image.fromarray(grid); dr = ImageDraw.Draw(im)
            vx, vy, wz = cmd[min(t, len(cmd) - 1)]
            dr.rectangle([0, 0, 360, 15], fill=(0, 0, 0))
            dr.text((3, 2), f"t={t * dt:.1f}s  cmd vx={vx:+.1f} vy={vy:+.1f} yaw={wz:+.1f}"
                    "  (grey<rated·yel≥nom·org≥70%pk·red≥pk)", fill=(255, 255, 255))
            grid = np.asarray(im)
        frames.append(grid)
    for p in panels:
        p.r.close()

    out = os.path.join(args.out, "progression_montage.mp4")
    import imageio
    imageio.mimwrite(out, frames, fps=args.fps, macro_block_size=None,
                     codec="libx264", quality=7)
    print(f"[montage] {len(frames)} frames -> {out}")


if __name__ == "__main__":
    main()
