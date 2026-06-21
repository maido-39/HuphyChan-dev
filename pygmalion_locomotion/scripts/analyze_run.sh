#!/bin/bash
# STANDARD per-experiment motor + structural analysis (run for EVERY measured policy).
# Produces, into docs/assets/<tag>_*:
#   1) torque utilization      (analyze_motor_util)  -> %rated / %peak
#   2) SPEED / max-rotation     (analyze_motor_speed) -> %speed-limit + torque-speed operating points
#   3) connection structural    (analyze_link_loads)  -> per-link |F|/|M|
#
# Usage: bash scripts/analyze_run.sh <tag> <clipped.npz> [unclipped.npz] [title]
set -u
cd /home/syaro/MikuchanRemote/Human-Pygmalion/pygmalion_locomotion
source /home/syaro/MikuchanRemote/Human-Pygmalion/sim/miniforge3/etc/profile.d/conda.sh
conda activate pygmalion

TAG="${1:?tag}"; CLIP="${2:?clipped npz}"; UNCLIP="${3:-}"; TITLE="${4:-$1}"
OUT=../docs/assets

echo "=== [1/3] 토크 활용률 (util) ==="
if [ -n "$UNCLIP" ]; then
  python scripts/analyze_motor_util.py --clipped "$CLIP" --unclipped "$UNCLIP" --tag "$TAG" --title "$TITLE" --out "$OUT"
else
  python scripts/analyze_motor_util.py --clipped "$CLIP" --tag "$TAG" --title "$TITLE" --out "$OUT"
fi
echo "=== [2/3] 최대회전 속도 + 토크-속도 (speed) ==="
python scripts/analyze_motor_speed.py --npz "$CLIP" --tag "$TAG" --title "$TITLE" --out "$OUT"
echo "=== [3/3] 연결부 구조하중 (structural) ==="
python scripts/analyze_link_loads.py --npz "$CLIP" --tag "$TAG" --title "$TITLE" --out "$OUT"

echo "-> docs/assets/${TAG}_motor_util.png · ${TAG}_torque_speed.png · ${TAG}_link_loads.png (+ .md/.json)"
