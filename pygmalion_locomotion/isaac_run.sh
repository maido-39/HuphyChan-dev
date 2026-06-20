#!/usr/bin/env bash
# Safe runner for Isaac Sim python scripts.
#  - activates the `pygmalion` conda env + accepts the Omniverse EULA
#  - runs with a hard timeout that ALSO sends SIGKILL (Isaac Sim ignores SIGTERM and otherwise
#    becomes a zombie holding the GPU -> next launch fails with "No device could be created")
#  - after exit, kills any leftover isaacsim PID still holding the GPU
#
# Usage:
#   ./isaac_run.sh [TIMEOUT_SECONDS] scripts/<script>.py [args...]
#   ./isaac_run.sh 600 scripts/train.py --task Pygmalion-Velocity-Flat-v0 --headless --num_envs 1024
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/../sim/miniforge3/etc/profile.d/conda.sh"
conda activate pygmalion
export OMNI_KIT_ACCEPT_EULA=YES
cd "$HERE"

# optional leading timeout (seconds); default 0 = no timeout
TIMEOUT=0
case "${1:-}" in (''|*[!0-9]*) : ;; (*) TIMEOUT="$1"; shift ;; esac

# warn if the GPU already has leftover compute apps
leftover=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | tr -d ' ')
[ -n "$leftover" ] && echo "[isaac_run] WARNING: GPU already busy (pids: $leftover) — consider 'kill -9'."

if [ "$TIMEOUT" -gt 0 ]; then
  timeout --kill-after=20 --signal=TERM "$TIMEOUT" python "$@"
  rc=$?
else
  python "$@"
  rc=$?
fi

# cleanup: SIGKILL any isaacsim process still alive (zombie holding the GPU)
for p in $(pgrep -f "isaacsim|simulation_app" 2>/dev/null); do
  kill -9 "$p" 2>/dev/null && echo "[isaac_run] reaped leftover isaac pid $p"
done
exit $rc
