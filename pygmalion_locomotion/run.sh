#!/usr/bin/env bash
# Convenience runner: activate the `pygmalion` conda env and run a python script from the
# workspace root (so logs/ and usd/ relative paths resolve). Usage:
#   ./run.sh scripts/train.py --task Pygmalion-Velocity-Flat-v0 --headless --num_envs 512
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA="$HERE/../sim/miniforge3/etc/profile.d/conda.sh"
# shellcheck disable=SC1090
source "$CONDA"
conda activate pygmalion
export OMNI_KIT_ACCEPT_EULA=YES   # accept Omniverse EULA non-interactively (headless)
cd "$HERE"
exec python "$@"
