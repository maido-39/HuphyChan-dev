#!/bin/bash
# Measure stage-3 (corrected + ankle-offload policy) clipped+unclipped, then re-launch stage-4
# rough transfer (with the now-matched 256 net). Robust + timestamped.
set -u
cd /home/syaro/MikuchanRemote/Human-Pygmalion/pygmalion_locomotion
source /home/syaro/MikuchanRemote/Human-Pygmalion/sim/miniforge3/etc/profile.d/conda.sh
conda activate pygmalion
export OMNI_KIT_ACCEPT_EULA=YES PYTHONDONTWRITEBYTECODE=1
find source -name "*.pyc" -delete 2>/dev/null
S3=logs/rsl_rl/pygmalion_flat/2026-06-21_03-46-50_stage3_ankle_offload/model_2499.pt

echo "=== MEASURE stage-3 CLIPPED $(date '+%H:%M:%S') ==="
python -u scripts/measure.py --task Pygmalion-Velocity-Flat-Play-v0 --checkpoint "$S3" \
  --duration 25 --headless --tag stage3_clip > logs/measure_stage3_clip.log 2>&1
echo "clip exit $? $(date '+%H:%M:%S')"
echo "=== MEASURE stage-3 UNCLIPPED $(date '+%H:%M:%S') ==="
python -u scripts/measure.py --task Pygmalion-Velocity-Flat-Play-v0 --checkpoint "$S3" \
  --effort_scale 5 --duration 25 --headless --tag stage3_unclip > logs/measure_stage3_unclip.log 2>&1
echo "unclip exit $? $(date '+%H:%M:%S')"

echo "=== STAGE-4 rough (transfer, matched 256 net) $(date '+%H:%M:%S') ==="
python -u scripts/train.py --task Pygmalion-Velocity-Rough-v0 --device cuda:0 --num_envs 8192 \
  --max_iterations 2000 --headless --video --run_name stage4_rough \
  --init_checkpoint "$S3" > logs/stage4_rough.log 2>&1
echo "=== stage-4 exit $? $(date '+%H:%M:%S') DONE ==="
