#!/bin/bash
# Evaluator A/B for the P1 low-speed deadband fix (2026-08-27).
#
#   arms      : bundleP1_AB (cmd_deadband 0.05) vs bundleD1_AB (0.3, the control)
#   scenarios : forward (N) linear commands 0.0 / 0.25 / 0.5 / 1.6 m/s
#   32 episodes per command, 20 s each - never a single rollout (eval_raw_stats.py docstring).
#
# ONE SCENARIO PER INVOCATION with max_parallel_envs=8: a 32-parallel evaluator run hit 13.6 GB
# RSS on this box and started swapping. Holds the shared GPU lock for the whole sweep.
#
#   run_p1_eval.sh                # both arms, all four speeds
#   run_p1_eval.sh 0.25 1.6       # a subset of speeds
set -u
REPO=/home/syaro/MikuchanRemote/Human-Pygmalion
LOCK=/home/syaro/pyg_fea/locks/gpu.lock
OUT=/tmp/claude-1000/-home-syaro-MikuchanRemote-Human-Pygmalion/7cf260d0-6741-4ceb-8d7b-8d7f9cd34c83/scratchpad
cd "$REPO/mujoco-sim/mjlab" || exit 1
mkdir -p "$OUT"

SPEEDS=${*:-"0.0 0.25 0.5 1.6"}

# Both arms share every env toggle except PYG_LOWSPEED_DEADBAND - that is the single variable.
COMMON="PYG_V2=1 PYG_INIT_BENT=1 PYG_ARM_ABD_DEG=15 PYG_INERTIAL_DR=1 PYG_ANKLE_MODE=AB \
        PYG_DR_START_ITER=0 PYG_DR_END_ITER=1 PYG_TN=1 PYG_MOTOR_MEAS=1 PYG_SOFT_LANDING=1 \
        PYG_INIT_MID=1 PYG_KNEE_EXT=1 PYG_KNEE_EXT_W=2.0 PYG_KNEE_EXT_DEG=25 \
        PYG_SOFT_LANDING_MODE=half"

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
echo "$$ p1_eval $(date -Is)" > "$LOCK/owner"
trap 'rm -rf "$LOCK"; echo RELEASED' EXIT
echo "LOCK acquired after ${waited}s"

run_one () {                       # run_one <arm> <checkpoint> <deadband-env> <speed>
  local ARM="$1" CK="$2" DB="$3" S="$4"
  local TAG="${ARM}_lin${S}"
  local CFG="$OUT/evalcfg_${TAG}.json"
  local ROOT="logs/eval/p1ab/${ARM}/lin_${S}"
  if [ -f "$ROOT/summary.json" ]; then echo "   skip $TAG (already done)"; return 0; fi
  python3 - "$CFG" "$CK" "$S" "$ROOT" <<'PY'
import json, sys
cfg_path, ck, speed, root = sys.argv[1:5]
json.dump({
  "checkpoint": ck,
  "task_id": "Mjlab-Velocity-Flat-Pygmalion",
  "envs_per_command": 32,
  "max_parallel_envs": 8,          # 32-parallel hit 13.6 GB RSS and swapped this box
  "episode_length_s": 20.0,        # >= the 15 s dwell standard; a stall needs time to show
  "warmup_s": 2.0,
  "seed": 0,
  "output_root": root,
  "save_plots": False,             # the A/B is read from raw.npz, not the per-scenario plots
  "commands": {"linear_speeds": [float(speed)], "directions": ["N"], "angular_speeds": []},
}, open(cfg_path, "w"), indent=1)
PY
  echo "== $TAG  $(date +%H:%M:%S)"
  env $COMMON $DB .venv/bin/python3 -m mjlab.tasks.velocity.scripts.evaluate \
      --config-file "$CFG" > "$OUT/eval_${TAG}.log" 2>&1
  local rc=$?
  echo "   rc=$rc  $(grep -c . "$OUT/eval_${TAG}.log") log lines"
  [ $rc -ne 0 ] && tail -15 "$OUT/eval_${TAG}.log"
  return 0
}

P1D=$(ls -d logs/rsl_rl/pygmalion_velocity/*_bundleP1_AB 2>/dev/null | tail -1)
D1D=$(ls -d logs/rsl_rl/pygmalion_velocity/*_bundleD1_AB 2>/dev/null | tail -1)
P1CK="$P1D/model_32798.pt"
D1CK="$D1D/model_32798.pt"
for f in "$P1CK" "$D1CK"; do [ -f "$f" ] || { echo "!! missing $f"; exit 2; }; done
echo "P1 $P1CK"; echo "D1 $D1CK"

for S in $SPEEDS; do
  run_one bundleP1_AB "$P1CK" "PYG_LOWSPEED_DEADBAND=0.05" "$S"
  run_one bundleD1_AB "$D1CK" "PYG_LOWSPEED_DEADBAND=" "$S"
done
echo "== eval sweep done $(date +%H:%M:%S)"
