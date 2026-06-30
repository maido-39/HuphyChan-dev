#!/bin/bash
# PERIODIC MID-TRAINING review timer. Sleeps once, emits a metrics SNAPSHOT + classification, then exits
# -> this WAKES the agent to REVIEW mid-training (instead of blindly waiting for completion). The agent
# evaluates the snapshot against academic health benchmarks, decides continue / refine / (conservatively)
# stop, and RE-ARMS this watcher. CONSERVATIVE BY DESIGN: this script only REPORTS; it never kills a run
# (transient early abnormality often recovers). Monitors the LOG only -> no pgrep/pkill -> no self-kill.
#
# Usage: bash scripts/watch_run.sh <logfile> [maxiter=2500] [sleep_seconds=1800]
# Exit line: STATUS=RUNNING|DONE|ERROR|NOLOG  iter=.. reward=.. noise_std=.. error_vel=.. ep_len=.. vloss=..
set -u
cd /home/syaro/MikuchanRemote/Human-Pygmalion/pygmalion_locomotion
LOG="${1:?logfile}"; MAXIT="${2:-2500}"; EVERY="${3:-1800}"

sleep "$EVERY"
[ -f "$LOG" ] || { echo "STATUS=NOLOG $LOG"; exit 0; }

last() { grep -aE "$1" "$LOG" | tail -1 | grep -oE "$2" | tail -1; }
iter=$(grep -aoE "iteration [0-9]+/$MAXIT" "$LOG" | tail -1 | grep -oE "[0-9]+" | head -1); iter="${iter:-?}"
reward=$(last "Mean reward:" "[-0-9.]+"); reward="${reward:-?}"
noise=$(last "Mean action noise std:" "[0-9.]+"); noise="${noise:-?}"
eplen=$(last "Mean episode length:" "[0-9.]+"); eplen="${eplen:-?}"
errvel=$(grep -aoE "error_vel_xy: [0-9.]+" "$LOG" | tail -1 | grep -oE "[0-9.]+"); errvel="${errvel:-?}"
vloss=$(last "Value function loss:" "[0-9.]+"); vloss="${vloss:-?}"

if grep -qaE "Traceback|CUDA out of memory|RuntimeError|Segmentation fault" "$LOG"; then
  echo "STATUS=ERROR iter=$iter (check $LOG tail)"; exit 0; fi
if grep -qaE "iteration ${MAXIT}/${MAXIT}" "$LOG"; then
  echo "STATUS=DONE iter=$iter reward=$reward noise_std=$noise error_vel=$errvel ep_len=$eplen vloss=$vloss"; exit 0; fi

echo "STATUS=RUNNING iter=$iter reward=$reward noise_std=$noise error_vel=$errvel ep_len=$eplen vloss=$vloss"
exit 0
