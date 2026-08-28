#!/usr/bin/env python3
"""Side-by-side sim2sim comparison video: MuJoCo (left) vs IsaacSim (right),
same bundleD1_RP policy, same 1.6 m/s command, rendered frame-locked and real-time.

Both panels are drawn with MuJoCo's own offscreen renderer:
  LEFT  = MuJoCo's own physics rollout (qpos_full from measure_loads).
  RIGHT = IsaacSim's logged joint trajectory (qpos from isaac_grf_rollout.py, PYG_LOG_QPOS=1),
          replayed through the same compiled model -> "IsaacSim physics, MuJoCo pixels".
This avoids building any Isaac camera/replicator pipeline (Isaac has none wired in this repo)
and keeps the two panels visually identical so only the MOTION differs.

A caption bar steps through the five story beats; each panel shows a live vertical-GRF readout.

Run (CPU/EGL, no GPU lock needed):
  cd mujoco-sim/mjlab
  MUJOCO_GL=egl CUDA_VISIBLE_DEVICES="" .venv/bin/python3 \
      ../../tools/sim2sim/render_sim2sim_compare.py \
      --mj analysis/out/sim2sim_rp_mj.npz \
      --isaac /home/syaro/pyg_fea/work/sim2sim/isaac_rp_qpos_i4x8.npz \
      --out ../../docs/video/sim2sim_rp_compare.mp4
"""
from __future__ import annotations
import argparse, os
import numpy as np
import mujoco
from PIL import Image, ImageDraw, ImageFont

BEATS = [
    "1  Same policy (bundleD1 RP), same 1.6 m/s forward command, two physics engines.",
    "2  Gait matches: duty, cadence, stride and impulse agree within about 10 percent.",
    "3  Impact differs: peak foot force and loading rate differ ~2x  -  a solver setting, not the gait.",
    "4  The knob: URDF import wrote 32/1 solver iterations. 4/8 (shown here) brings peak to 1.1x MuJoCo.",
    "5  Verdict: impulse, duty and timing transfer unconditionally; peak and rate need the solver iters "
    "stated. Design loads come from MuJoCo - Isaac is the cross-check.",
]


def font(sz, bold=True):
    p = ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
         else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    try:
        return ImageFont.truetype(p, sz)
    except Exception:
        return ImageFont.load_default()


class Panel:
    """Renders one robot from a qpos_full array through a shared compiled model."""
    def __init__(self, model_path, qpos_full, w, h):
        self.m = mujoco.MjModel.from_binary_path(model_path)
        # calm the terrain: flat matte colour, drop checker material
        for g in range(self.m.ngeom):
            gn = mujoco.mj_id2name(self.m, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
            if gn.startswith("terrain") or "ground" in gn.lower() or "floor" in gn.lower():
                self.m.geom_matid[g] = -1
                self.m.geom_rgba[g] = (0.60, 0.55, 0.47, 1.0)
        self.q = np.asarray(qpos_full, float)
        self.md = mujoco.MjData(self.m)
        self.ren = mujoco.Renderer(self.m, height=h, width=w)
        self.opt = mujoco.MjvOption(); self.opt.geomgroup[3] = 0
        for gg in range(6):                          # hide sensor/marker sites
            self.opt.sitegroup[gg] = 0
        self.cam = mujoco.MjvCamera()
        self.cam.distance = 2.55; self.cam.azimuth = 128.0; self.cam.elevation = -10.0
        self.cam_zoff = 0.18                          # look slightly above the base

    def frame(self, t):
        md, m = self.md, self.m
        md.qpos[:] = self.q[t]; md.qvel[:] = 0.0
        mujoco.mj_forward(m, md)
        self.cam.lookat[:] = md.qpos[0:3]
        self.cam.lookat[2] += self.cam_zoff
        self.ren.update_scene(md, self.cam, self.opt)
        return self.ren.render()


def build_isaac_qpos_full(m, isaac):
    """Map Isaac's [T,12] leg joints (pol_names order) + base pose into the model's qpos."""
    pol_names = [str(x) for x in isaac["pol_names"]]
    legs = np.asarray(isaac["qpos"], float)          # [T,12], pol order
    bpos = np.asarray(isaac["base_pos"], float)      # [T,3]
    bquat = np.asarray(isaac["base_quat"], float)    # [T,4] wxyz
    T = len(legs)
    # model joint name -> qpos address (strip any "robot/" prefix for matching)
    name2adr = {}
    for j in range(m.njnt):
        nm = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j) or ""
        name2adr[nm] = m.jnt_qposadr[j]
        name2adr[nm.split("/")[-1]] = m.jnt_qposadr[j]
    col_adr = []
    for pn in pol_names:
        adr = name2adr.get(pn, name2adr.get(pn.split("/")[-1]))
        if adr is None:
            raise KeyError(f"joint {pn} not in render model")
        col_adr.append(int(adr))
    Q = np.zeros((T, m.nq))
    Q[:, 0:3] = bpos
    Q[:, 3:7] = bquat
    for c, adr in enumerate(col_adr):
        Q[:, adr] = legs[:, c]
    return Q


def total_mass_bw(m):
    return float(m.body_mass.sum()) * 9.81


def mj_grf_bw(mj, bw_n):
    keys = [k for k in mj.files if k.startswith("GRF_") and k.endswith("_z")]
    if not keys:
        return None
    z = np.zeros(len(mj[keys[0]]))
    for k in keys:
        z = z + np.asarray(mj[k], float)
    return z / bw_n     # [T] vertical GRF in BW, control-step rate


def isaac_grf_bw(isaac, T, decim=4):
    Fz = np.asarray(isaac["Fz_BW"], float)           # [T_phys,2] BW
    tot = Fz.sum(axis=1)                             # [T_phys]
    out = np.zeros(T)
    for k in range(T):
        seg = tot[k * decim:(k + 1) * decim]
        out[k] = seg.max() if len(seg) else 0.0     # peak within the control step
    return out


def wrap(dr, text, fnt, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if dr.textlength(t, font=fnt) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mj", required=True, help="MuJoCo measure_loads npz (qpos_full+GRF)")
    ap.add_argument("--isaac", required=True, help="Isaac qpos npz (PYG_LOG_QPOS dump)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--width", type=int, default=560)
    ap.add_argument("--height", type=int, default=560)
    ap.add_argument("--downsample", type=int, default=2)
    ap.add_argument("--skip", type=int, default=150, help="control steps to skip (ramp/settle)")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fps = max(1, round(50 / args.downsample))        # REAL-TIME rule

    mj = np.load(args.mj, allow_pickle=True)
    isaac = np.load(args.isaac, allow_pickle=True)
    model_path = args.mj.replace(".npz", "_model.mjb")

    mj_q = np.asarray(mj["qpos_full"], float)
    A = Panel(model_path, mj_q, args.width, args.height)
    B = Panel(model_path, build_isaac_qpos_full(A.m, isaac), args.width, args.height)

    bw_n = total_mass_bw(A.m)
    grf_a = mj_grf_bw(mj, bw_n)                       # [T] or None
    grf_b = isaac_grf_bw(isaac, len(B.q))             # [T]

    T = min(len(A.q), len(B.q))
    idx = list(range(args.skip, T, args.downsample))
    nbeat = len(idx)
    print(f"[sbs] frames={nbeat} fps={fps} realtime_s={nbeat/fps:.1f} T={T}")

    W, H = args.width, args.height
    CAP = 96                                          # caption bar height
    Flab = font(24); Feng = font(22); Fgrf = font(26); Fcap = font(23); Fnum = font(19, False)
    frames = []
    for i, t in enumerate(idx):
        img = np.concatenate([A.frame(t), B.frame(t)], axis=1)      # (H, 2W, 3)
        canvas = np.full((H + CAP, 2 * W, 3), 22, np.uint8)
        canvas[:H, :, :] = img
        im = Image.fromarray(canvas); dr = ImageDraw.Draw(im)
        # divider
        dr.line([W, 0, W, H], fill=(30, 30, 30), width=2)
        # panel labels (shadow + colour)
        for (x, lab, col, anchor) in [
                (14, "MuJoCo", (70, 150, 235), "la"),
                (2 * W - 14, "IsaacSim  (PhysX, 4/8)", (235, 140, 60), "ra")]:
            dr.text((x + 2, 12), lab, fill=(0, 0, 0), font=Flab, anchor=anchor)
            dr.text((x, 10), lab, fill=col, font=Flab, anchor=anchor)
        # live GRF readout
        ga = f"foot GRF  {grf_a[t]:.2f} BW" if grf_a is not None else ""
        gb = f"foot GRF  {grf_b[t]:.2f} BW"
        dr.text((14, H - 30), ga, fill=(210, 225, 245), font=Fnum)
        dr.text((2 * W - 14, H - 30), gb, fill=(245, 220, 195), font=Fnum, anchor="ra")
        # command tag centered top
        cmd = "command: 1.6 m/s forward"
        dr.text((W - dr.textlength(cmd, font=Feng) / 2, 12), cmd, fill=(150, 220, 160), font=Feng)
        # caption bar (stepped through 5 beats)
        beat = min(len(BEATS) - 1, int(i / max(1, nbeat) * len(BEATS)))
        dr.rectangle([0, H, 2 * W, H + CAP], fill=(16, 16, 18))
        dr.line([0, H, 2 * W, H], fill=(90, 90, 95), width=1)
        lines = wrap(dr, BEATS[beat], Fcap, 2 * W - 40)
        y = H + (CAP - len(lines) * 27) // 2
        for ln in lines:
            dr.text((20, y), ln, fill=(235, 235, 240), font=Fcap); y += 27
        # progress ticks for the 5 beats
        for b in range(len(BEATS)):
            x0 = 20 + b * (2 * W - 40) / len(BEATS)
            col = (90, 200, 120) if b == beat else (70, 70, 75)
            dr.rectangle([x0, H + CAP - 6, x0 + (2 * W - 40) / len(BEATS) - 6, H + CAP - 3], fill=col)
        frames.append(np.asarray(im))

    import imageio
    imageio.mimwrite(args.out, frames, fps=fps, macro_block_size=None,
                     codec="libx264", quality=8)
    print(f"[sbs] {len(frames)} frames ({len(frames)/fps:.1f}s) -> {args.out}")


if __name__ == "__main__":
    main()
