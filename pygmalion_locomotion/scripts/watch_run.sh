#!/bin/bash
# ACTIVE run watcher — notifies the agent (by EXITING with a STATUS=... line) when a training run
# completes, hangs, errors, or diverges, so problems are caught WITHOUT waiting on the process exit
# (which never fires if the run hangs — e.g. stage-5 hung in atexit). Monitors the LOG FILE only,
# so there is NO pgrep/pkill -> NO self-kill. The run's own run_in_background still covers clean exit.
#
# Usage: bash scripts/watch_run.sh <logfile> [maxiter=2500] [check_seconds=900]
# Exits with one of: STATUS=DONE | STATUS=STALL | STATUS=ERROR | STATUS=DIVERGE | STATUS=TIMEOUT | STATUS=NOLOG
set -u
cd /home/syaro/MikuchanRemote/Human-Pygmalion/pygmalion_locomotion
LOG="${1:?logfile}"; MAXIT="${2:-2500}"; EVERY="${3:-900}"
prev=0; stall=0; peak=0; iter="?"; reward=0

for _ in $(seq 1 24); do          # up to 24 checks (24 * 15min = 6h ceiling)
  sleep "$EVERY"
  [ -f "$LOG" ] || { echo "STATUS=NOLOG $LOG"; exit 0; }
  lines=$(wc -l < "$LOG")
  iter=$(grep -aoE "iteration [0-9]+/$MAXIT" "$LOG" | tail -1 | grep -oE "[0-9]+" | head -1); iter="${iter:-?}"
  reward=$(grep -aE "Mean reward:" "$LOG" | tail -1 | grep -oE "[-0-9.]+" | tail -1); reward="${reward:-0}"

  if grep -qaE "Traceback|CUDA out of memory|RuntimeError|Segmentation fault" "$LOG"; then
    echo "STATUS=ERROR iter=$iter (check $LOG)"; exit 0; fi
  if grep -qaE "iteration ${MAXIT}/${MAXIT}" "$LOG"; then
    echo "STATUS=DONE iter=$iter reward=$reward"; exit 0; fi

  if [ "$lines" -eq "$prev" ]; then stall=$((stall + 1)); else stall=0; fi
  if [ "$stall" -ge 2 ]; then
    echo "STATUS=STALL iter=$iter reward=$reward (log frozen ~$((EVERY * 2 / 60))min)"; exit 0; fi

  peak=$(awk -v r="$reward" -v p="$peak" 'BEGIN{print (r>p)?r:p}')
  div=$(awk -v r="$reward" -v p="$peak" -v it="$iter" 'BEGIN{print (it+0>150 && p>5 && r<0.5*p)?1:0}')
  if [ "$div" = "1" ]; then
    echo "STATUS=DIVERGE iter=$iter reward=$reward peak=$peak"; exit 0; fi
  prev=$lines
done
echo "STATUS=TIMEOUT iter=$iter reward=$reward"; exit 0
