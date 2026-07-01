"""Side-by-side load dashboard video (reusable routine).

LEFT  = load-coloured robot (sphere indicator per joint, on the real terrain).
RIGHT = per joint-type torque & RPM HISTOGRAMS (whole rollout) with peak/rated/
        speed-limit lines + a live marker (L blue, R orange) at the current value.

Re-runnable: point it at any <tag>.npz (+ <tag>_model.mjb) produced by
measure_loads.py. Keep this routine in the loop as new data/checkpoints arrive.

Usage:
  MUJOCO_GL=egl uv run python analysis/make_dashboard_video.py \
      --npz analysis/out/flat.npz --tag flat --out <docs/mujoco/assets>
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import mujoco
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RAD2RPM = 60.0 / (2.0 * np.pi)
SPEC = {  # (peak N*m, rated N*m, speed-limit rpm)
    "hip_pitch": (120.0, 40.0, 143.0), "hip_roll": (120.0, 40.0, 143.0),
    "hip_yaw": (60.0, 20.0, 191.0), "knee": (120.0, 40.0, 143.0),
    "ankle_pitch": (60.0, 20.0, 191.0), "ankle_roll": (14.0, 5.0, 315.0),
}
JTYPES = ["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll"]
JOINT_OFFSET = {"ankle_pitch": 0.08}
LEVEL_COLOUR = {
    0: (0.55, 0.59, 0.64, 1.0), 1: (0.97, 0.86, 0.0, 1.0),
    2: (1.0, 0.50, 0.0, 1.0), 3: (0.95, 0.05, 0.05, 1.0),
}


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
    ap.add_argument("--rh", type=int, default=540)
    ap.add_argument("--rw", type=int, default=620)
    ap.add_argument("--downsample", type=int, default=0, help="0=auto(~1200 frames)")
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--radius", type=float, default=0.06)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    d = np.load(args.npz, allow_pickle=True)
    q = d["qpos_full"]
    T = len(q)
    cmd = np.stack([d["cmd_vx"], d["cmd_vy"], d["cmd_wz"]], axis=1)
    dt = float(d["time"][1] - d["time"][0]) if len(d["time"]) > 1 else 0.02
    ds = args.downsample or max(1, T // 1200)

    # Per joint-type |torque| and |rpm| arrays for L and R (whole rollout).
    series = {}
    for jt in JTYPES:
        for side in ("L", "R"):
            jn = f"{side}_{jt}_joint"
            if "tau_" + jn in d.files:
                series[(jt, side, "tau")] = np.abs(d["tau_" + jn])
                series[(jt, side, "rpm")] = np.abs(d["omega_" + jn]) * RAD2RPM

    # ---- robot model (real terrain) ----
    mjb = os.path.join(os.path.dirname(args.npz), f"{args.tag}_model.mjb")
    m = mujoco.MjModel.from_binary_path(mjb)
    for g in range(m.ngeom):
        gn = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        if gn.startswith("terrain"):
            m.geom_matid[g] = -1
            m.geom_rgba[g] = (0.62, 0.56, 0.47, 1.0)
    md = mujoco.MjData(m)
    inds = []
    for side in ("L", "R"):
        for jt in JTYPES:
            jn = f"{side}_{jt}_joint"
            jid = _jid(m, jn)
            if jid >= 0 and "tau_" + jn in d.files:
                pk, rt, _ = SPEC[jt]
                inds.append((jid, "tau_" + jn, pk, rt, JOINT_OFFSET.get(jt, 0.0)))
    renderer = mujoco.Renderer(m, height=args.rh, width=args.rw)
    opt = mujoco.MjvOption()
    opt.geomgroup[3] = 0
    cam = mujoco.MjvCamera()
    cam.distance = 2.9
    cam.azimuth = 130.0
    cam.elevation = -18.0
    eye = np.eye(3).flatten()

    # ---- dashboard figure (persistent; only markers move) ----
    px = 1.0 / 100
    fig, axes = plt.subplots(6, 2, figsize=(640 * px, args.rh * px), dpi=100)
    markers = {}
    for i, jt in enumerate(JTYPES):
        pk, rt, vlim = SPEC[jt]
        for c, kind in enumerate(("tau", "rpm")):
            ax = axes[i][c]
            allv = np.concatenate([series[(jt, s, kind)] for s in ("L", "R")
                                   if (jt, s, kind) in series]) if any(
                (jt, s, kind) in series for s in ("L", "R")) else np.zeros(1)
            ax.hist(allv, bins=30, color="#b9c2cc")
            if kind == "tau":
                ax.axvline(pk, color="#c0392b", lw=1.2)
                ax.axvline(rt, color="#e67e22", lw=1.0, ls=":")
                ax.set_xlim(0, pk * 1.1)
            else:
                ax.axvline(vlim, color="#c0392b", lw=1.2)
                ax.set_xlim(0, max(vlim * 1.1, float(allv.max()) * 1.05 + 1))
            mL = ax.axvline(0, color="#2980b9", lw=1.6)
            mR = ax.axvline(0, color="#e67e22", lw=1.6)
            markers[(jt, kind)] = (mL, mR)
            ax.set_yticks([])
            ax.tick_params(labelsize=5)
            if i == 0:
                ax.set_title("torque [N*m]" if c == 0 else "speed [rpm]", fontsize=8)
            ax.set_ylabel(jt, fontsize=6) if c == 0 else None
    fig.suptitle(f"{args.tag}: per-joint load histograms (peak=red, rated=:, L=blue R=orange)",
                 fontsize=8)
    fig.tight_layout(rect=[0, 0, 1, 0.97])

    def dash_rgb(t):
        for jt in JTYPES:
            for kind in ("tau", "rpm"):
                mL, mR = markers[(jt, kind)]
                vL = series.get((jt, "L", kind))
                vR = series.get((jt, "R", kind))
                if vL is not None:
                    mL.set_xdata([vL[t], vL[t]])
                if vR is not None:
                    mR.set_xdata([vR[t], vR[t]])
        fig.canvas.draw()
        w, h = fig.canvas.get_width_height()
        buf = np.frombuffer(fig.canvas.buffer_rgba(), dtype=np.uint8).reshape(h, w, 4)
        return buf[:, :, :3].copy()

    try:
        from PIL import Image, ImageDraw
        have_pil = True
    except Exception:
        have_pil = False

    def robot_rgb(t):
        md.qpos[:] = q[t]
        md.qvel[:] = 0.0
        mujoco.mj_forward(m, md)
        cam.lookat[:] = md.qpos[0:3]
        renderer.update_scene(md, cam, opt)
        scn = renderer.scene
        for jid, key, pk, rt, zoff in inds:
            lvl = severity(abs(float(d[key][t])), pk, rt)
            pos = md.xanchor[jid].copy()
            pos[2] += zoff
            if scn.ngeom < scn.maxgeom:
                mujoco.mjv_initGeom(
                    scn.geoms[scn.ngeom], int(mujoco.mjtGeom.mjGEOM_SPHERE),
                    np.array([args.radius, 0, 0], float), pos, eye,
                    np.asarray(LEVEL_COLOUR[lvl], np.float32))
                scn.ngeom += 1
        img = renderer.render()
        if have_pil:
            im = Image.fromarray(img)
            dr = ImageDraw.Draw(im)
            vx, vy, wz = cmd[t]
            dr.text((6, 6), f"{args.tag} t={t * dt:.1f}s cmd vx={vx:+.1f} "
                    f"vy={vy:+.1f} yaw={wz:+.1f}", fill=(255, 255, 255))
            img = np.asarray(im)
        return img

    frames = []
    for t in range(0, T, ds):
        rob = robot_rgb(t)
        dsh = dash_rgb(t)
        h = min(rob.shape[0], dsh.shape[0])
        comp = np.concatenate([rob[:h], dsh[:h]], axis=1)
        frames.append(comp)
    plt.close(fig)
    renderer.close()

    out_mp4 = os.path.join(args.out, f"{args.tag}_dashboard.mp4")
    import imageio
    imageio.mimwrite(out_mp4, frames, fps=args.fps, macro_block_size=None,
                     codec="libx264", quality=7)
    print(f"[dashboard] {len(frames)} frames (ds={ds}) -> {out_mp4}")


if __name__ == "__main__":
    main()
