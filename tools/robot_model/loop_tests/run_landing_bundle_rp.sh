#!/bin/bash
# RP arm of the confirmed landing recipe (docs/103 §4a) — treatment vs its OWN control.
#   D1_RP  = INIT_MID + KNEE_EXT(2.0@25) + SOFT_LANDING_MODE=half
#            (half = foot_impact_velocity weight x0.5, no loading-rate term - which is what
#             bundleD1_AB actually trained with: the loading-rate term was dead on a sign bug)
#   CTL_RP = same warm-start, none of the three  (so the AB->RP transfer is judged
#            against an RP baseline of equal batch and equal extra iterations, not
#            against ankleRP_c3 which had a different schedule)
set -euo pipefail
cd /home/syaro/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab
D=$(ls -d logs/rsl_rl/pygmalion_velocity/*_ankleRP_c3)
CK=model_31999.pt
[ -f "$D/$CK" ] || { echo "!! $D/$CK missing"; exit 2; }
COMMON="PYG_V2=1 PYG_INIT_BENT=1 PYG_ARM_ABD_DEG=15 PYG_INERTIAL_DR=1 PYG_ANKLE_MODE=RP \
        PYG_DR_START_ITER=0 PYG_DR_END_ITER=1 PYG_TN=1 PYG_MOTOR_MEAS=1 PYG_SOFT_LANDING=1"
launch () {
  local NAME="$1"; shift
  echo "== launch $NAME  $(date +%H:%M:%S)"
  env $COMMON "$@" nohup .venv/bin/python3 analysis/train_wandb_video.py \
      Mjlab-Velocity-Flat-Pygmalion --video True --video-interval 8000 --video-length 500 \
      --env.scene.num-envs 16384 --agent.max-iterations 800 --agent.run-name "$NAME" \
      --agent.logger wandb --agent.resume True --agent.load-run "$(basename $D)" \
      --agent.load-checkpoint "$CK" > "logs/${NAME}.log" 2>&1 &
  echo "   pid $! -> logs/${NAME}.log"
}
launch "bundleCTL_RP"
sleep 25          # stagger the model compile so the two runs don't collide
launch "bundleD1_RP" PYG_INIT_MID=1 PYG_KNEE_EXT=1 PYG_KNEE_EXT_W=2.0 PYG_KNEE_EXT_DEG=25 \
                     PYG_SOFT_LANDING_MODE=half
