#!/bin/bash
# CPU-isolated load measurement (CUDA_VISIBLE_DEVICES="") -- safe to run while a
# GPU training is in progress; never contends for VRAM. Reads the latest settled
# checkpoint and sweeps a multi-direction command schedule (see measure_loads.py).
#
# Usage: analysis/measure_loads.sh <run_dir> <task> <tag> [steps_per_cmd]
#   run_dir : logs/rsl_rl/pygmalion_velocity/<timestamp>
#   task    : Mjlab-Velocity-Flat-Pygmalion | Mjlab-Velocity-Rough-Pygmalion
#   tag     : output basename (flat / rough)
set -euo pipefail
ROOT=~/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab
cd "$ROOT"
export PATH="$HOME/.local/bin:$PATH"

RUN_DIR="${1:?usage: measure_loads.sh <run_dir> <task> <tag> [steps_per_cmd]}"
TASK="${2:?task}"
TAG="${3:?tag}"
SPC="${4:-150}"

CUDA_VISIBLE_DEVICES="" uv run python analysis/measure_loads.py \
  --run-dir "$RUN_DIR" --task "$TASK" --tag "$TAG" --steps-per-cmd "$SPC" --warmup 120
