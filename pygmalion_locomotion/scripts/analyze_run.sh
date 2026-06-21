#!/bin/bash
# STANDARD per-experiment motor + structural analysis (run for EVERY measured policy).
# Produces, into docs/assets/<tag>_*:
#   0) motor torque/speed VIZ   (analyze_motor_timeseries) -> per-joint avg/max bars + rated/peak/limit
#      spec lines + %saturation + TIME-SERIES grids (how torque/speed are used over time) -- EMBED these
#   1) torque utilization      (analyze_motor_util)  -> %rated / %peak (clip vs unclip)
#   2) SPEED / max-rotation     (analyze_motor_speed) -> torque-speed operating-point envelope
#   3) connection structural    (analyze_link_loads)  -> per-link |F|/|M|
#
# Usage: bash scripts/analyze_run.sh <tag> <clipped.npz> [unclipped.npz] [title]
set -u
cd /home/syaro/MikuchanRemote/Human-Pygmalion/pygmalion_locomotion
source /home/syaro/MikuchanRemote/Human-Pygmalion/sim/miniforge3/etc/profile.d/conda.sh
conda activate pygmalion

TAG="${1:?tag}"; CLIP="${2:?clipped npz}"; UNCLIP="${3:-}"; TITLE="${4:-$1}"
OUT=../docs/assets

echo "=== [1/4] 모터 토크·속도 바(avg/max+스펙선+포화%) + 시계열 (motorviz) ==="
python scripts/analyze_motor_timeseries.py --npz "$CLIP" --tag "$TAG" --title "$TITLE" --out "$OUT"
echo "=== [2/4] 토크 활용률 (util, clip vs unclip) ==="
if [ -n "$UNCLIP" ]; then
  python scripts/analyze_motor_util.py --clipped "$CLIP" --unclipped "$UNCLIP" --tag "$TAG" --title "$TITLE" --out "$OUT"
else
  python scripts/analyze_motor_util.py --clipped "$CLIP" --tag "$TAG" --title "$TITLE" --out "$OUT"
fi
echo "=== [3/4] 최대회전 속도 + 토크-속도 envelope (speed) ==="
python scripts/analyze_motor_speed.py --npz "$CLIP" --tag "$TAG" --title "$TITLE" --out "$OUT"
echo "=== [4/4] 연결부 구조하중 (structural) ==="
python scripts/analyze_link_loads.py --npz "$CLIP" --tag "$TAG" --title "$TITLE" --out "$OUT"

echo "-> docs/assets/${TAG}_{torque,speed,torque_ts,speed_ts,motor_util,torque_speed,link_loads}.png (+ .md/.json)"
