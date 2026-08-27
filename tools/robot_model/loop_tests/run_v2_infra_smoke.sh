#!/bin/bash
# V2 training-infrastructure smoke test (docs/103 §4 step 7, scaled down).
# Turns on the three new PYG_* switches AT ONCE and asks only "do they run, do they
# fire, and do they leave the reward stack alive" - not "do they train a better gait".
#   V3 PYG_GATED_CURRICULUM=1  promotion by report card instead of by iteration count
#   V4 PYG_ENTROPY_ANNEAL=1    entropy_coef 0.01 -> 0.002 across the run's window
#   V9 PYG_CRITIC_DR_OBS=1     DR draw (friction/mass/CoM/push) into the CRITIC group
#
# The dwell numbers are deliberately tiny (40/120 instead of 800/3000) so a 300-iter
# run actually crosses several stages; the production values are the defaults in
# env_cfgs.py and must NOT be taken from here.
#
# NOTE the launcher: V9 grows the critic input, so a normal resume would die on the
# critic's first-layer shape. analysis/train_actor_warmstart.py is the established
# answer (actor-only load, critic starts fresh) - the same reason it exists for the
# flat->rough transfer.
set -euo pipefail
cd /home/syaro/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab
D=$(ls -d logs/rsl_rl/pygmalion_velocity/*_ankleAB_c3)
CK=model_31999.pt
[ -f "$D/$CK" ] || { echo "!! $D/$CK missing"; exit 2; }
NAME="${1:-v2infra_smoke}"
ITERS="${2:-300}"
ENVS="${3:-1024}"

COMMON="PYG_V2=1 PYG_INIT_BENT=1 PYG_ARM_ABD_DEG=15 PYG_INERTIAL_DR=1 PYG_ANKLE_MODE=AB \
        PYG_DR_START_ITER=0 PYG_DR_END_ITER=1 PYG_TN=1 PYG_MOTOR_MEAS=1 PYG_SOFT_LANDING=1 \
        PYG_CMD_VY_STAGES=1 PYG_FRESH_STEPS=1"
RECIPE="PYG_INIT_MID=1 PYG_SOFT_LANDING_MODE=half PYG_KNEE_EXT=1 PYG_KNEE_EXT_W=2.0 PYG_KNEE_EXT_DEG=25"
NEW="PYG_GATED_CURRICULUM=1 PYG_GATE_MIN_DWELL=40 PYG_GATE_MAX_DWELL=120 PYG_GATE_WINDOW=20 \
     PYG_GATE_MIN_EPISODES=64 \
     PYG_ENTROPY_ANNEAL=1 PYG_ENTROPY_ANNEAL_START=0 PYG_ENTROPY_ANNEAL_END=$((ITERS-1)) \
     PYG_ENTROPY_LOG_EVERY=25 \
     PYG_CRITIC_DR_OBS=1"

echo "== launch $NAME  ${ITERS} iter x ${ENVS} env  $(date +%H:%M:%S)"
env $COMMON $RECIPE $NEW nohup .venv/bin/python3 analysis/train_actor_warmstart.py \
    Mjlab-Velocity-Flat-Pygmalion --video True --video-interval 150 --video-length 200 \
    --env.scene.num-envs "$ENVS" --agent.max-iterations "$ITERS" --agent.run-name "$NAME" \
    --agent.logger tensorboard --agent.resume True --agent.load-run "$(basename $D)" \
    --agent.load-checkpoint "$CK" > "logs/${NAME}.log" 2>&1 &
echo "   pid $! -> mujoco-sim/mjlab/logs/${NAME}.log"
