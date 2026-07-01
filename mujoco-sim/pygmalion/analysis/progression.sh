#!/bin/bash
# Measure the policy at every 6000-iter checkpoint (flat, wide-DR) so we can
# track how the analysed loads evolve over training. Re-runnable: skips
# checkpoints already measured and picks up new ones (36k..60k) as they appear.
# CPU-isolated -> runs alongside GPU training without disturbing it.
#
# Usage: nohup analysis/progression.sh [steps] &
set -uo pipefail
ROOT=~/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab
cd "$ROOT"; export PATH="$HOME/.local/bin:$PATH"
TASK=Mjlab-Velocity-Flat-Pygmalion
STEPS="${1:-2400}"
OUT=analysis/out/prog; mkdir -p "$OUT"
LOG=analysis/out/progression.log
RUN=logs/rsl_rl/pygmalion_velocity/2026-06-30_20-12-31
echo "[prog] start steps=$STEPS $(date)" | tee -a "$LOG"
for it in 3000 6000 9000 12000 15000 18000 21000 24000 27000 30000 33000 36000 39000 42000 45000 48000 51000 54000 57000 60000; do
  ckpt=$(ls logs/rsl_rl/pygmalion_velocity/*/model_${it}.pt 2>/dev/null | head -1)
  if [ -z "$ckpt" ]; then echo "[prog] $it: no checkpoint yet, skip" | tee -a "$LOG"; continue; fi
  if [ -f "$OUT/prog_${it}.npz" ]; then echo "[prog] $it: already measured, skip" | tee -a "$LOG"; continue; fi
  echo "[prog] measure iter $it <- $ckpt $(date)" | tee -a "$LOG"
  CUDA_VISIBLE_DEVICES="" uv run python analysis/measure_loads.py --run-dir "$RUN" \
    --task "$TASK" --checkpoint "$ckpt" --tag "prog_${it}" --out-dir "$OUT" \
    --wide-dr --steps "$STEPS" --warmup 100 >> "$LOG" 2>&1
  echo "[prog] iter $it done exit=$? $(date)" | tee -a "$LOG"
done
echo "[prog] ALL DONE $(date)" | tee -a "$LOG"
