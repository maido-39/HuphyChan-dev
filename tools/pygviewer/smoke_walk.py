#!/usr/bin/env python3
"""P2 acceptance runs: does the viewer's policy path stand, walk, and agree with mjlab?

    CUDA_VISIBLE_DEVICES="" mujoco-sim/mjlab/.venv/bin/python3 tools/pygviewer/smoke_walk.py \
        --policy <name> [--seconds 15] [--vx 0.6]

Two checks, both against numbers produced OUTSIDE this tool:

  stand  vel-0 command for `--seconds`, then compare base height and knee angles with
         analysis/out/legonly_ab_v2_vel0_vx0.npz, which analysis/gait_kinematics_probe.py
         produced from the SAME checkpoint inside the mjlab env.  Tolerance 0.02.
  walk   vx command for `--seconds`; must not fall, and the mean forward speed must track.
         The checkpoint is mid-training, so the bar is "it stands and walks", not a
         converged gait.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mujoco
import numpy as np

from pygviewer import CACHE_DIR, REPO
from pygviewer.contract import load_contract
from pygviewer.sim_core import SimCore

REF_NPZ = f"{REPO}/mujoco-sim/mjlab/analysis/out/legonly_ab_v2_vel0_vx0.npz"


def run(policy_name, seconds, vx, warm=2.0):
  pc = json.load(open(f"{CACHE_DIR}/{policy_name}.policy_contract.json"))
  core = SimCore(load_contract(CACHE_DIR, pc["variant"]), realtime=False)
  core.load_policy(onnx=pc["onnx"], policy_contract=pc)
  core.set_base(mode="free", ground=True)
  core.reset("knees_bent")
  core.submit({"op": "mode", "value": "policy_sim"})
  # The trainer ramps a new command in; a step command from standstill is not what the
  # policy ever saw, and judging it on the transient would be judging the wrong thing.
  n = int(seconds / core.dt)
  ramp = int(warm / core.dt)
  log = dict(t=[], z=[], x=[], vx=[], vx_world=[], qL=[], qR=[], closure=[])
  reset_closure = core.closure_mm()
  jL = core.names.index("L_knee_joint")
  jR = core.names.index("R_knee_joint")
  fell = False
  for i in range(n):
    if i % core.decimation == 0:
      core.cmd = np.array([vx * min(1.0, i / max(ramp, 1)), 0.0, 0.0])
    core.step_n(1)
    if i % core.decimation == 0:
      q = core.d.qpos
      log["t"].append(core.d.time)
      log["z"].append(float(q[2]))
      log["x"].append(float(q[0]))
      # base-FRAME forward speed: that is what the tracking reward and the run notes use.
      # World-frame vx differs whenever the robot yaws, which it does.
      qw = core.d.qpos[core.free_adr + 3 : core.free_adr + 7]
      R = np.zeros(9)
      mujoco.mju_quat2Mat(R, qw)
      log["vx"].append(float((R.reshape(3, 3).T @ core.d.qvel[0:3])[0]))
      log["vx_world"].append(float(core.d.qvel[0]))
      log["qL"].append(float(q[core.qadr["L_knee_joint"]]))
      log["qR"].append(float(q[core.qadr["R_knee_joint"]]))
      log["closure"].append(core.closure_mm())
    if core.d.qpos[2] < 0.45:
      fell = True
      break
  core.stop()
  return {k: np.asarray(v) for k, v in log.items()} | {
    "fell": fell, "reset_closure_mm": reset_closure}


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--policy", required=True)
  ap.add_argument("--seconds", type=float, default=15.0)
  ap.add_argument("--vx", type=float, default=0.6)
  a = ap.parse_args()

  print(f"=== stand (cmd vx=0, {a.seconds:.0f} s) ===")
  st = run(a.policy, a.seconds, 0.0)
  m = st["t"] >= 4.0
  z, qL, qR = st["z"][m].mean(), st["qL"][m].mean(), st["qR"][m].mean()
  print(f"  fell={st['fell']}  base_z {z:+.4f}  L_knee {qL:+.4f}  R_knee {qR:+.4f}  "
        f"closure worst {st['closure'].max():.4f} mm  "
        f"(at reset {st['reset_closure_mm']:.2f} mm - the env resets the same way, see "
        f"docs/121)")
  if os.path.exists(REF_NPZ):
    d = np.load(REF_NPZ)
    rm = d["time"] >= 4.0
    rz, rL, rR = d["base_z"][rm].mean(), d["q_L_knee_joint"][rm].mean(), d["q_R_knee_joint"][rm].mean()
    print(f"  mjlab gait probe reference (same checkpoint): base_z {rz:+.4f}  "
          f"L_knee {rL:+.4f}  R_knee {rR:+.4f}")
    print(f"  delta: base_z {z - rz:+.4f}  L_knee {qL - rL:+.4f}  R_knee {qR - rR:+.4f}  "
          f"(bar 0.02)")

  print(f"=== walk (cmd vx={a.vx}, {a.seconds:.0f} s) ===")
  wk = run(a.policy, a.seconds, a.vx)
  m = wk["t"] >= 4.0
  vx_mean = wk["vx"][m].mean()
  travelled = wk["x"][-1] - wk["x"][0]
  print(f"  fell={wk['fell']}  vx(base frame) mean(t>=4s) {vx_mean:+.3f} m/s  "
        f"err {abs(vx_mean - a.vx):.3f}  vx(world) {wk['vx_world'][m].mean():+.3f}")
  print(f"  travelled {travelled:+.2f} m in {wk['t'][-1]:.1f} s  "
        f"base_z mean {wk['z'][m].mean():.3f}  closure worst {wk['closure'].max():.4f} mm")


if __name__ == "__main__":
  main()
