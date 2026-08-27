#!/bin/bash
# P1 low-speed deadband A/B (2026-08-27).
#
#   bundleP1_AB = the confirmed bundleD1_AB recipe + PYG_LOWSPEED_DEADBAND=0.05, i.e. the ONE
#   variable is stand_still_penalty.cmd_deadband 0.3 -> 0.05. Everything else (checkpoint,
#   batch, iters, env toggles) is byte-identical to bundleD1_AB, so D1 IS the control and no
#   second arm is launched.
#
#   Why: the fc 121-command grid measured 0 % achievement at cmd 0.25 m/s on both ankleAB and
#   ankleRP. At 0.25 the standing penalty (deadband 0.3) AND air_time (threshold 0.5) are both
#   gated off, so the 0.05-0.3 m/s band pays every one-way walking cost with +0.34/step of
#   tracking margin - action_rate_l2 alone reverses it. Research:
#   docs/reward_research/2026-08-27_low_speed_command_research.md (P1).
#
# Holds the shared GPU lock (mkdir-atomic) for the WHOLE run; two other coders run Isaac/smoke
# jobs on this machine. A lock whose owner pid is dead is reclaimed after a grace period.
set -u
REPO=/home/syaro/MikuchanRemote/Human-Pygmalion
LOCK=/home/syaro/pyg_fea/locks/gpu.lock
NAME=bundleP1_AB
cd "$REPO/mujoco-sim/mjlab" || exit 1

D=$(ls -d logs/rsl_rl/pygmalion_velocity/*_ankleAB_c3)
CK=model_31999.pt
[ -f "$D/$CK" ] || { echo "!! $D/$CK missing"; exit 2; }

# ---- polite lock wait, with stale-owner reclaim -------------------------------------------
waited=0
until mkdir "$LOCK" 2>/dev/null; do
  own=$(cat "$LOCK/owner" 2>/dev/null)
  opid=${own%% *}
  if [ -n "$opid" ] && ! kill -0 "$opid" 2>/dev/null; then
    # owner process is gone; give it a grace period, re-check, then reclaim
    echo "STALE gpu.lock: owner '$own' pid $opid not running; 60 s grace"
    sleep 60
    own2=$(cat "$LOCK/owner" 2>/dev/null); opid2=${own2%% *}
    if [ "$own2" = "$own" ] && ! kill -0 "$opid2" 2>/dev/null; then
      echo "RECLAIM stale gpu.lock from '$own'"; rm -rf "$LOCK"; continue
    fi
  fi
  [ $((waited % 300)) -eq 0 ] && echo "WAIT gpu.lock held by $own (${waited}s)"
  sleep 15; waited=$((waited + 15))
done
echo "$$ ${NAME}-train $(date -Is)" > "$LOCK/owner"
trap 'rm -rf "$LOCK"; echo RELEASED' EXIT
echo "LOCK acquired after ${waited}s"
free -m | head -2
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv

COMMON="PYG_V2=1 PYG_INIT_BENT=1 PYG_ARM_ABD_DEG=15 PYG_INERTIAL_DR=1 PYG_ANKLE_MODE=AB \
        PYG_DR_START_ITER=0 PYG_DR_END_ITER=1 PYG_TN=1 PYG_MOTOR_MEAS=1 PYG_SOFT_LANDING=1"
RECIPE="PYG_INIT_MID=1 PYG_KNEE_EXT=1 PYG_KNEE_EXT_W=2.0 PYG_KNEE_EXT_DEG=25 PYG_SOFT_LANDING_MODE=half"
P1="PYG_LOWSPEED_DEADBAND=0.05"

echo "== launch $NAME  $(date +%H:%M:%S)"
env $COMMON $RECIPE $P1 .venv/bin/python3 analysis/train_wandb_video.py \
    Mjlab-Velocity-Flat-Pygmalion --video True --video-interval 8000 --video-length 500 \
    --env.scene.num-envs 16384 --agent.max-iterations 800 --agent.run-name "$NAME" \
    --agent.logger wandb --agent.resume True --agent.load-run "$(basename "$D")" \
    --agent.load-checkpoint "$CK" > "logs/${NAME}.log" 2>&1
echo "== train exit $? $(date +%H:%M:%S)"
