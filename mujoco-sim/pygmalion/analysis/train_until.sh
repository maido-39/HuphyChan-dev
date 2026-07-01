#!/bin/bash
# Auto-resume training "babysitter": keep Pygmalion training going until it
# reaches TARGET iterations, resuming from the latest checkpoint whenever a run
# ends or crashes ("끝나도 이어서"). rsl_rl's learn() is additive and load()
# restores the global iter, and checkpoints are named with the global iter, so
# we resume with max-iterations = (TARGET - latest_iter) to land exactly on TARGET.
#
# Usage: nohup analysis/train_until.sh [task] [target_iter] [num_envs] &
set -uo pipefail
ROOT=~/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab
cd "$ROOT"
export PATH="$HOME/.local/bin:$PATH"

TASK="${1:-Mjlab-Velocity-Flat-Pygmalion}"
TARGET="${2:-60000}"
ENVS="${3:-4096}"
EXP=logs/rsl_rl/pygmalion_velocity
LOG=analysis/out/train_until.log
mkdir -p analysis/out
echo "[train_until] start target=$TARGET task=$TASK envs=$ENVS $(date)" | tee -a "$LOG"

while true; do
  # Don't double-launch: wait while any training of this task is running
  # (e.g. the currently-active run reaching its own max first).
  if pgrep -f "train $TASK" >/dev/null 2>&1; then
    echo "[train_until] a training is running; wait 120s $(date)" >> "$LOG"
    sleep 120; continue
  fi

  # Latest checkpoint across all run dirs, by global iter in the filename.
  latest=$(ls "$EXP"/*/model_*.pt 2>/dev/null \
    | sed -E 's#.*/model_([0-9]+)\.pt#\1 &#' | sort -n | tail -1)
  iter=$(echo "$latest" | awk '{print $1}')
  ckpt=$(echo "$latest" | awk '{print $2}')
  if [ -z "${iter:-}" ]; then
    echo "[train_until] no checkpoint found under $EXP; abort $(date)" | tee -a "$LOG"
    exit 1
  fi
  if [ "$iter" -ge "$TARGET" ]; then
    echo "[train_until] DONE iter=$iter >= target=$TARGET $(date)" | tee -a "$LOG"
    break
  fi

  # +1: rsl_rl learn(N) runs range(cur, cur+N) -> last it = cur+N-1, so to land a
  # checkpoint exactly on TARGET we ask for one more iteration.
  remaining=$((TARGET - iter + 1))
  rundir=$(basename "$(dirname "$ckpt")")
  echo "[train_until] resume run=$rundir ckpt=model_$iter.pt  +$remaining -> $TARGET  $(date)" | tee -a "$LOG"
  # logger=wandb so the continued run is visible in wandb (account logged in via
  # ~/.netrc). Detached (setsid, no controlling terminal) so it can't be SIGSTOP'd
  # like the earlier interactive runs.
  uv run train "$TASK" --env.scene.num-envs "$ENVS" \
    --agent.resume True --agent.load-run "$rundir" --agent.load-checkpoint "model_$iter.pt" \
    --agent.max-iterations "$remaining" --agent.logger wandb >> "$LOG" 2>&1
  echo "[train_until] train process exited code=$? $(date)" | tee -a "$LOG"
  sleep 15
done
