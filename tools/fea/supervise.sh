#!/usr/bin/env bash
# Keeps autorun.sh alive no matter what kills it (including me: a broad pkill
# while cleaning up solver processes took the whole campaign down twice on
# 2026-08-16). Detached with setsid so it does not belong to any shell session.
#
# Start:  setsid nohup tools/fea/supervise.sh >> ~/pyg_fea/work/supervise.log 2>&1 &
# Stop:   touch ~/pyg_fea/work/STOP
cd /home/syaro/MikuchanRemote/Human-Pygmalion
W=/home/syaro/pyg_fea/work
mkdir -p "$W"
exec 8>/tmp/pyg_supervise.lock
flock -n 8 || { echo "supervisor already running"; exit 0; }
rm -f "$W/STOP"
n=0
while [ ! -f "$W/STOP" ]; do
  n=$((n+1))
  echo "[$(date +%m-%d\ %H:%M:%S)] supervisor: starting autorun (attempt $n)"
  setsid tools/fea/autorun.sh >> "$W/autorun.log" 2>&1
  code=$?
  echo "[$(date +%m-%d\ %H:%M:%S)] supervisor: autorun exited with $code - restarting in 20 s"
  sleep 20
done
echo "[$(date +%m-%d\ %H:%M:%S)] supervisor: STOP file present, exiting"
