#!/bin/bash
# Overnight chain: stage-3 (flat, ankle-offload reward) -> stage-4 (rough transfer).
# Robust: kills lingerers, checks stage-3 produced a checkpoint before stage-4, logs timestamps.
set -u
cd /home/syaro/MikuchanRemote/Human-Pygmalion/pygmalion_locomotion
source /home/syaro/MikuchanRemote/Human-Pygmalion/sim/miniforge3/etc/profile.d/conda.sh
conda activate pygmalion
export OMNI_KIT_ACCEPT_EULA=YES PYTHONDONTWRITEBYTECODE=1
find source -name "*.pyc" -delete 2>/dev/null
for p in $(pgrep -f "scripts/train.py"); do kill -9 "$p" 2>/dev/null; done
for p in $(pgrep -f "bin/isaacsim"); do kill -9 "$p" 2>/dev/null; done
sleep 3

STAGE2=logs/rsl_rl/pygmalion_flat/2026-06-21_01-52-57_flat_wide_dr/model_1499.pt

echo "=== STAGE-3 (flat, ankle-offload) START $(date '+%H:%M:%S') ==="
python -u scripts/train.py --task Pygmalion-Velocity-Flat-v0 --device cuda:0 --num_envs 16384 \
  --max_iterations 2500 --headless --video --run_name stage3_ankle_offload \
  --init_checkpoint "$STAGE2" > logs/stage3_ankle_offload.log 2>&1
echo "=== STAGE-3 exit $? $(date '+%H:%M:%S') ==="

S3=$(ls -t logs/rsl_rl/pygmalion_flat/*_stage3_ankle_offload/model_*.pt 2>/dev/null | head -1)
if [ -n "$S3" ]; then
  echo "=== STAGE-4 (rough transfer from $S3) START $(date '+%H:%M:%S') ==="
  python -u scripts/train.py --task Pygmalion-Velocity-Rough-v0 --device cuda:0 --num_envs 8192 \
    --max_iterations 2000 --headless --video --run_name stage4_rough \
    --init_checkpoint "$S3" > logs/stage4_rough.log 2>&1
  echo "=== STAGE-4 exit $? $(date '+%H:%M:%S') ==="
else
  echo "=== stage-3 produced NO checkpoint -> skip stage-4 ==="
fi
echo "=== OVERNIGHT CHAIN DONE $(date '+%H:%M:%S') ==="
