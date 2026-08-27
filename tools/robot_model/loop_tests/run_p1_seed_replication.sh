#!/bin/bash
# Seed replication for the P1 low-speed deadband (2026-08-27, planner option B).
#
# THE QUESTION: P1's 200 Hz loading rate came out 2.2-2.8x bundleD1_AB's (20.6 -> 46-58 BW/s)
# with peak force and touchdown rate unchanged. Nothing so far separates "the deadband causes
# stiff landing" from "a +800 iter continuation lands wherever the seed puts it". Three runs
# settle it:
#   bundleP1s2_AB / bundleP1s3_AB : recipe + PYG_LOWSPEED_DEADBAND=0.05, seeds 2 and 3
#   bundleD1s2_AB                 : recipe WITHOUT the deadband, seed 2 = the control's own
#                                   variance floor (bundleD1_AB itself is the default seed 42)
#
# VERDICT RULE (planner): sets {D1, D1s2} vs {P1, P1s2, P1s3}. If min(P1 set) still exceeds
# max(D1 set) by >1.5x the deadband owns the stiff landing; if the sets overlap or the gap
# falls under 1.5x, seed variance owns it.
#
# The 200 Hz probe is the ONLY judgement metric here - tracking behaviour is already known from
# the evaluator sweep, so the full evaluator is skipped. A fall during a probe is reportable.
#
# Holds the shared GPU lock for the WHOLE ~2 h sequence rather than per run: releasing between
# runs would let another coder's job interleave and stall the sequence for an unbounded time,
# and this box runs one training at a time regardless.
set -u
REPO=/home/syaro/MikuchanRemote/Human-Pygmalion
LOCK=/home/syaro/pyg_fea/locks/gpu.lock
cd "$REPO/mujoco-sim/mjlab" || exit 1
SPEC=analysis/out/watchdog_runs.json
SRC=$(ls -d logs/rsl_rl/pygmalion_velocity/*_ankleAB_c3)
CK=model_31999.pt
[ -f "$SRC/$CK" ] || { echo "!! $SRC/$CK missing"; exit 2; }

COMMON="PYG_V2=1 PYG_INIT_BENT=1 PYG_ARM_ABD_DEG=15 PYG_INERTIAL_DR=1 PYG_ANKLE_MODE=AB \
        PYG_DR_START_ITER=0 PYG_DR_END_ITER=1 PYG_TN=1 PYG_MOTOR_MEAS=1 PYG_SOFT_LANDING=1 \
        PYG_INIT_MID=1 PYG_KNEE_EXT=1 PYG_KNEE_EXT_W=2.0 PYG_KNEE_EXT_DEG=25 \
        PYG_SOFT_LANDING_MODE=half"

waited=0
until mkdir "$LOCK" 2>/dev/null; do
  own=$(cat "$LOCK/owner" 2>/dev/null); opid=${own%% *}
  if [ -n "$opid" ] && ! kill -0 "$opid" 2>/dev/null; then
    echo "STALE gpu.lock: owner '$own' pid $opid not running; 60 s grace"; sleep 60
    o2=$(cat "$LOCK/owner" 2>/dev/null); p2=${o2%% *}
    if [ "$o2" = "$own" ] && ! kill -0 "$p2" 2>/dev/null; then
      echo "RECLAIM stale gpu.lock from '$own'"; rm -rf "$LOCK"; continue; fi
  fi
  [ $((waited % 300)) -eq 0 ] && echo "WAIT gpu.lock held by $own (${waited}s)"
  sleep 15; waited=$((waited + 15))
done
echo "$$ p1_seed_replication $(date -Is)" > "$LOCK/owner"
trap 'rm -rf "$LOCK"; echo RELEASED' EXIT
echo "LOCK acquired after ${waited}s  $(date -Is)"

wd () {   # wd <run> <enabled true|false> [deadband]
  python3 - "$SPEC" "$1" "$2" "${3:-}" <<'PY'
import collections, json, sys
spec, run, en, db = sys.argv[1:5]
d = json.load(open(spec), object_pairs_hook=collections.OrderedDict)
if run in d:
    d[run]["enabled"] = (en == "true")
else:
    env = collections.OrderedDict([
        ("PYG_V2","1"),("PYG_INIT_BENT","1"),("PYG_ARM_ABD_DEG","15"),("PYG_INERTIAL_DR","1"),
        ("PYG_ANKLE_MODE","AB"),("PYG_DR_START_ITER","0"),("PYG_DR_END_ITER","1"),
        ("PYG_TN","1"),("PYG_MOTOR_MEAS","1"),("PYG_SOFT_LANDING","1"),("PYG_INIT_MID","1"),
        ("PYG_KNEE_EXT","1"),("PYG_KNEE_EXT_W","2.0"),("PYG_KNEE_EXT_DEG","25"),
        ("PYG_SOFT_LANDING_MODE","half")])
    if db:
        env["PYG_LOWSPEED_DEADBAND"] = db
    d[run] = collections.OrderedDict([
        ("enabled", en == "true"), ("total_iters", 32799), ("num_envs", 16384),
        ("task", "Mjlab-Velocity-Flat-Pygmalion"), ("env", env)])
json.dump(d, open(spec, "w"), indent=1); open(spec, "a").write("\n")
print(f"   watchdog[{run}].enabled={en}")
PY
}

one () {   # one <name> <seed> [deadband-env]
  local NAME="$1" SEED="$2" DB="${3:-}"
  local DBVAL=""; [ -n "$DB" ] && DBVAL="${DB#*=}"
  wd "$NAME" true "$DBVAL"
  echo "== TRAIN $NAME seed=$SEED ${DB:-（no deadband）}  $(date +%H:%M:%S)"
  env $COMMON ${DB:-PYG_DUMMY=0} .venv/bin/python3 analysis/train_wandb_video.py \
      Mjlab-Velocity-Flat-Pygmalion --video True --video-interval 8000 --video-length 500 \
      --env.scene.num-envs 16384 --agent.max-iterations 800 --agent.run-name "$NAME" \
      --agent.seed "$SEED" --agent.logger wandb --agent.resume True \
      --agent.load-run "$(basename "$SRC")" --agent.load-checkpoint "$CK" \
      > "logs/${NAME}.log" 2>&1
  echo "   train exit $? $(date +%H:%M:%S)"
  wd "$NAME" false
  local D; D=$(ls -d logs/rsl_rl/pygmalion_velocity/*_"$NAME" 2>/dev/null | tail -1)
  if [ -z "$D" ] || [ ! -f "$D/model_32798.pt" ]; then
    echo "   !! $NAME did not reach model_32798.pt - skipping probe"; return 0; fi
  echo "== PROBE $NAME  $(date +%H:%M:%S)"
  env $COMMON ${DB:-PYG_DUMMY=0} PROBE_NODR=1 CUDA_VISIBLE_DEVICES="" nice -n 5 \
      .venv/bin/python3 ../../tools/robot_model/loop_tests/impact_probe_multi.py \
      "$D" "$D/model_32798.pt" "$NAME" 1.6 24 2>&1 \
      | grep -aE "^\[multi\] resets|^MULTI|Traceback|Error"
}

one bundleP1s2_AB 2 PYG_LOWSPEED_DEADBAND=0.05
one bundleP1s3_AB 3 PYG_LOWSPEED_DEADBAND=0.05
one bundleD1s2_AB 2
echo "== seed replication done $(date -Is)"
