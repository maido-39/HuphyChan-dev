#!/bin/bash
# Continuously validate the policy at every 6000-iter checkpoint and refresh the
# progression note, until 60000 is covered. Runs progression.sh (measures new
# checkpoints) + progression_analyze.py (updates trends/note) on a poll loop.
# Detached + CPU-isolated -> extends the trend to 60000 as training completes.
#
# Usage: setsid bash analysis/progression_watch.sh </dev/null >/dev/null 2>&1 &
set -uo pipefail
ROOT=~/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab
cd "$ROOT"; export PATH="$HOME/.local/bin:$PATH"
DOCS=~/MikuchanRemote/Human-Pygmalion/docs/mujoco
LOG=analysis/out/progression.log
while true; do
  bash analysis/progression.sh 2400
  CUDA_VISIBLE_DEVICES="" uv run python analysis/progression_analyze.py \
    --out "$DOCS/assets" --note "$DOCS/2026-07-01_training_progression.md" >> "$LOG" 2>&1
  CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl uv run python analysis/progression_montage.py \
    --out "$DOCS/assets" >> "$LOG" 2>&1
  if [ -f analysis/out/prog/prog_60000.npz ]; then
    echo "[prog-watch] 60000 covered — done $(date)" >> "$LOG"; break
  fi
  sleep 900   # re-check every 15 min for new 6000-multiple checkpoints
done
