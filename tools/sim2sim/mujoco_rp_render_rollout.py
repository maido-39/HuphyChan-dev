#!/usr/bin/env python3
"""MuJoCo (mjlab) rollout of bundleD1_RP at a constant 1.6 m/s, dumping qpos_full
for the sim2sim side-by-side render.

Reuses analysis/measure_loads.py with COMMAND_SCHEDULE monkey-patched to a single
forward command (the measure_full.py pattern). Produces:
  analysis/out/<tag>.npz        (qpos_full, cmd_*, time, GRF_*_foot_link_*, tau_*)
  analysis/out/<tag>_model.mjb  (compiled model for the renderer)

Run (CPU, no GPU lock needed):
  cd mujoco-sim/mjlab
  env PYG_V2=1 PYG_INIT_BENT=1 PYG_INIT_MID=1 PYG_ARM_ABD_DEG=15 PYG_ANKLE_MODE=RP \
      PYG_TN=1 PYG_MOTOR_MEAS=1 CUDA_VISIBLE_DEVICES="" \
      nice -n 10 .venv/bin/python3 ../../tools/sim2sim/mujoco_rp_render_rollout.py
"""
import os, sys

MJ = "/home/syaro/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab"
os.chdir(MJ)
sys.path.insert(0, os.path.join(MJ, "analysis"))

RUN = "logs/rsl_rl/pygmalion_velocity/2026-08-26_15-45-16_bundleD1_RP"
STEPS = int(os.environ.get("PYG_RENDER_STEPS", "900"))   # 900 = 18 s at 50 Hz
TAG = os.environ.get("PYG_RENDER_TAG", "sim2sim_rp_mj")

import measure_loads
measure_loads.COMMAND_SCHEDULE = [(1.6, 0.0, 0.0)]        # constant forward 1.6 m/s

sys.argv = ["measure_loads",
            "--run-dir", RUN,
            "--tag", TAG,
            "--device", "cpu",
            "--steps-per-cmd", str(STEPS),
            "--out-dir", "analysis/out"]
print(f"[mj-render-rollout] tag={TAG} steps={STEPS} run={RUN}")
measure_loads.main()
print("[mj-render-rollout] done")
