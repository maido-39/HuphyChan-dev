#!/bin/bash
# 200 Hz multi-env foot-strike probe for the P1 low-speed deadband arm (2026-08-27).
#
# Settles whether P1's +21 % loading rate on the 50 Hz evaluator was real or aliasing. The
# evaluator samples dF/dt at the 50 Hz control tick, but this robot's landing spike is 15-25 ms
# wide, so that instrument shares a known bias (see bundleE1_AB §4). This probe reads the
# ContactSensor inside the sim.step hook, so every physics substep (200 Hz) is sampled.
#
# Two conditions, both against the existing bundleD1_AB reference:
#   PROBE_NODR=1 -> DR events dropped  = the evaluator's clean condition (D1: 1.224 BW / 21.0 BW/s)
#   PROBE_NODR=0 -> play-mode DR kept  = robustness
# CPU-only (the script pins device='cpu'), but it holds the shared GPU lock anyway so it cannot
# collide with another coder's Isaac job on this box.
set -u
REPO=/home/syaro/MikuchanRemote/Human-Pygmalion
LOCK=/home/syaro/pyg_fea/locks/gpu.lock
cd "$REPO/mujoco-sim/mjlab" || exit 1
mkdir -p /home/syaro/pyg_fea/work/impact_multi /home/syaro/pyg_fea/work/impact_multi_nodr

D=$(ls -d logs/rsl_rl/pygmalion_velocity/*_bundleP1_AB | tail -1)
CK="$D/model_32798.pt"
[ -f "$CK" ] || { echo "!! $CK missing"; exit 2; }

waited=0
until mkdir "$LOCK" 2>/dev/null; do
  own=$(cat "$LOCK/owner" 2>/dev/null); opid=${own%% *}
  if [ -n "$opid" ] && ! kill -0 "$opid" 2>/dev/null; then
    echo "STALE gpu.lock: owner '$own' pid $opid not running; 60 s grace"; sleep 60
    own2=$(cat "$LOCK/owner" 2>/dev/null); opid2=${own2%% *}
    if [ "$own2" = "$own" ] && ! kill -0 "$opid2" 2>/dev/null; then
      echo "RECLAIM stale gpu.lock from '$own'"; rm -rf "$LOCK"; continue
    fi
  fi
  [ $((waited % 300)) -eq 0 ] && echo "WAIT gpu.lock held by $own (${waited}s)"
  sleep 15; waited=$((waited + 15))
done
echo "$$ p1_impact_probe $(date -Is)" > "$LOCK/owner"
trap 'rm -rf "$LOCK"; echo RELEASED' EXIT
echo "LOCK acquired after ${waited}s"

# EXACT training flags of bundleP1_AB - load_env_cfg reads these, and PYG_INIT_BENT/INIT_MID
# move default_joint_pos, which is the action origin: omitting them invalidates the rollout.
COMMON="PYG_V2=1 PYG_INIT_BENT=1 PYG_ARM_ABD_DEG=15 PYG_INERTIAL_DR=1 PYG_ANKLE_MODE=AB \
        PYG_DR_START_ITER=0 PYG_DR_END_ITER=1 PYG_TN=1 PYG_MOTOR_MEAS=1 PYG_SOFT_LANDING=1 \
        PYG_INIT_MID=1 PYG_KNEE_EXT=1 PYG_KNEE_EXT_W=2.0 PYG_KNEE_EXT_DEG=25 \
        PYG_SOFT_LANDING_MODE=half PYG_LOWSPEED_DEADBAND=0.05"

for NODR in 1 0; do
  echo "== bundleP1_AB PROBE_NODR=$NODR  $(date +%H:%M:%S)"
  env $COMMON PROBE_NODR=$NODR CUDA_VISIBLE_DEVICES="" nice -n 5 .venv/bin/python3 \
      ../../tools/robot_model/loop_tests/impact_probe_multi.py "$D" "$CK" bundleP1_AB 1.6 24 \
      2>&1 | grep -aE "^\[multi\]|^MULTI|Traceback|Error"
done
echo "== probe done $(date +%H:%M:%S)"
