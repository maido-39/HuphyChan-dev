#!/bin/bash
# Curriculum: FLAT (with DR) -> ROUGH (stairs/slopes), fine-tuning the rough policy from the
# flat policy weights (--init_checkpoint). Both envs share obs (flat keeps height_scan) so the
# transfer is valid. In-training video stays ON for both phases.
#   bash scripts/curriculum_train.sh [flat_iters] [rough_iters] [num_envs]
set -u
cd /home/syaro/MikuchanRemote/Human-Pygmalion/pygmalion_locomotion
source /home/syaro/MikuchanRemote/Human-Pygmalion/sim/miniforge3/etc/profile.d/conda.sh && conda activate pygmalion
export OMNI_KIT_ACCEPT_EULA=YES PYTHONDONTWRITEBYTECODE=1
FI="${1:-400}"; RI="${2:-1000}"; NE="${3:-16384}"

echo "[curriculum] ===== PHASE A: FLAT (DR) $(date +%H:%M:%S) ====="
python -u scripts/train.py --task Pygmalion-Velocity-Flat-v0 --device cuda:0 --num_envs "$NE" \
  --max_iterations "$FI" --headless --run_name gpu_flat_curric
for p in $(pgrep -f "bin/isaacsim"); do kill -9 "$p" 2>/dev/null; done; sleep 5

FRUN=$(ls -dt logs/rsl_rl/pygmalion_flat/*gpu_flat_curric 2>/dev/null | head -1)
FCKPT=$(ls -t "$FRUN"/model_*.pt 2>/dev/null | head -1)
echo "[curriculum] flat done -> init rough from: $FCKPT"
if [ -z "$FCKPT" ]; then echo "[curriculum] ERROR no flat checkpoint"; exit 1; fi

echo "[curriculum] ===== PHASE B: ROUGH (init from flat) $(date +%H:%M:%S) ====="
python -u scripts/train.py --task Pygmalion-Velocity-Rough-v0 --device cuda:0 --num_envs "$NE" \
  --max_iterations "$RI" --headless --init_checkpoint "$FCKPT" --run_name gpu_rough_curric
echo "[curriculum] ===== DONE $(date +%H:%M:%S) ====="
