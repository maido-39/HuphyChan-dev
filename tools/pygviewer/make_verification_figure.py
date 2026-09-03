#!/usr/bin/env python3
"""P0/P1 evidence figure for docs and the briefing.  No OpenGL on this host, so the robot
panel is a body-frame stick figure drawn with matplotlib (same approach as
tools/robot_model/loop_ankle_verify.py's mesh projection, minus the meshes).

    CUDA_VISIBLE_DEVICES="" mujoco-sim/mjlab/.venv/bin/python3 \
        tools/pygviewer/make_verification_figure.py

Writes docs/img/pygviewer_p1_verification.png.  English labels only.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mujoco
import numpy as np

from pygviewer import CACHE_DIR, REPO
from pygviewer.contract import load_contract
from pygviewer.sim_core import SimCore

OUT = f"{REPO}/docs/img/pygviewer_p1_verification.png"
PROBES = [(0.0, 0.0), (-0.35, 0.0), (0.17, 0.0), (0.0, 0.17), (0.0, -0.17), (-0.2, 0.1)]


def skeleton(ax, core, title):
  m, d = core.m, core.d
  for b in range(1, m.nbody):
    p = m.body_parentid[b]
    if p < 1:
      continue
    a, c = d.xpos[p], d.xpos[b]
    ax.plot([a[0], c[0]], [a[2], c[2]], "-", color="#4c78a8", lw=1.6, zorder=2)
  ax.plot(d.xpos[1:, 0], d.xpos[1:, 2], ".", color="#e45756", ms=3, zorder=3)
  ax.axhline(0.0, color="#888", lw=1.0, ls="--")
  ax.set_aspect("equal")
  ax.set_xlabel("x [m]  (side view, +x = forward)")
  ax.set_ylabel("z [m]")
  ax.set_title(title, fontsize=9)
  ax.grid(alpha=0.25)


def main():
  c = load_contract(CACHE_DIR, "LegOnly-AB")
  core = SimCore(c, realtime=False)

  fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.4))

  # --- 1. base fixed, bent keyframe ------------------------------------------------
  core.reset("knees_bent")
  core.set_base(mode="fixed", pos=[0.0, 0.0, 0.95])
  core.step_n(400)
  p0 = core.d.qpos[core.free_adr : core.free_adr + 3].copy()
  core.step_n(400)
  drift = float(np.linalg.norm(core.d.qpos[core.free_adr : core.free_adr + 3] - p0))
  skeleton(
    axes[0],
    core,
    f"base FIXED (weld to mocap anchor)\n"
    f"drift over 2 s = {drift:.2e} m   loop closure = {core.closure_mm():.4f} mm",
  )

  # --- 2. ankle foot-space command tracking ----------------------------------------
  got_fit, got_raw = [], []
  for tp, tr in PROBES:
    core.reset("home")
    core.set_base(mode="fixed", pos=[0.0, 0.0, 1.0])
    core.set_ankle("L", tp, tr)
    core.step_n(1200)
    a = core.snapshot()["ankle_derived"]["L"]
    got_fit.append((a["pitch"], a["roll"]))
  # the same grid WITHOUT the fitted sign map = what the plan's recipe would have given
  sm = core.ankle_inverse.sign_map
  core.ankle_inverse.sign_map = {"L": {}, "R": {}}
  for tp, tr in PROBES:
    core.reset("home")
    core.set_base(mode="fixed", pos=[0.0, 0.0, 1.0])
    core.set_ankle("L", tp, tr)
    core.step_n(1200)
    a = core.snapshot()["ankle_derived"]["L"]
    got_raw.append((a["pitch"], a["roll"]))
  core.ankle_inverse.sign_map = sm

  ax = axes[1]
  tgt = np.asarray(PROBES)
  gf, gr = np.asarray(got_fit), np.asarray(got_raw)
  ax.plot(tgt[:, 0], tgt[:, 1], "ks", ms=9, mfc="none", label="commanded")
  ax.plot(gr[:, 0], gr[:, 1], "x", color="#e45756", ms=8, label="v3 grid as-is")
  ax.plot(gf[:, 0], gf[:, 1], "o", color="#54a24b", ms=5, label="v3 grid + fitted sign map")
  for a, b in zip(tgt, gf):
    ax.plot([a[0], b[0]], [a[1], b[1]], "-", color="#54a24b", lw=0.7)
  ax.set_xlabel("ankle pitch [rad]")
  ax.set_ylabel("ankle roll [rad]")
  ax.set_title(
    "AB foot-space command -> cranks -> achieved ankle (left leg)\n"
    f"worst error {np.abs(gf - tgt).max():.3f} rad fitted vs "
    f"{np.abs(gr - tgt).max():.3f} rad as-is",
    fontsize=9,
  )
  ax.legend(fontsize=7)
  ax.grid(alpha=0.25)
  ax.set_aspect("equal")

  # --- 3. a step response, PD + T-N, at the training rates -------------------------
  core.reset("knees_bent")
  core.set_base(mode="fixed", pos=[0.0, 0.0, 0.95])
  core.step_n(200)
  ts, qs, tgts, taus = [], [], [], []
  j = "L_knee_joint"
  k = core.act_names.index(j)
  target = core.c.default_q(j)
  for i in range(600):
    if i == 100:
      target = core.c.default_q(j) + 0.5
      core.set_target({j: target})
    core.step_n(1)
    ts.append(core.d.time)
    qs.append(float(core.d.qpos[core.qadr[j]]))
    tgts.append(target)
    taus.append(float(core._tau[k]))
  ts = np.asarray(ts) - ts[0]
  ax = axes[2]
  ax.plot(ts, tgts, "--", color="#888", lw=1.2, label="target [rad]")
  ax.plot(ts, qs, color="#4c78a8", lw=1.4, label="q [rad]")
  ax2 = ax.twinx()
  ax2.plot(ts, taus, color="#f58518", lw=1.0, alpha=0.8, label="torque [N*m]")
  ax2.set_ylabel("torque [N*m]")
  ax.set_xlabel("time [s]")
  ax.set_ylabel("angle [rad]")
  g = core.c.gains(j)
  ax.set_title(
    f"L_knee +0.5 rad step, PD+T-N as in training\n"
    f"kp {g['kp']} kd {g['kd']} effort {g['effort']} N*m, 200 Hz physics / 50 Hz control",
    fontsize=9,
  )
  h1, l1 = ax.get_legend_handles_labels()
  h2, l2 = ax2.get_legend_handles_labels()
  ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="lower right")
  ax.grid(alpha=0.25)

  fig.suptitle(
    f"pygviewer P0/P1 verification - {c.variant}, contract {c.contract_sha[:12]}", fontsize=10
  )
  fig.tight_layout()
  os.makedirs(os.path.dirname(OUT), exist_ok=True)
  fig.savefig(OUT, dpi=130)
  core.stop()
  print("wrote", OUT)
  print(f"  fixed-base drift over 2 s : {drift:.3e} m")
  print(f"  ankle worst error fitted  : {np.abs(gf - tgt).max():.4f} rad")
  print(f"  ankle worst error as-is   : {np.abs(gr - tgt).max():.4f} rad")


if __name__ == "__main__":
  main()
