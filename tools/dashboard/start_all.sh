#!/bin/bash
# Bring up every service the dashboard links to (idempotent: skips ports already listening).
# Usage: bash tools/dashboard/start_all.sh        -> http://192.168.20.177:8890/tools/dashboard/
R=/home/syaro/MikuchanRemote/Human-Pygmalion; M=$R/mujoco-sim/mjlab; cd $R
up(){ ss -ltn | grep -q ":$1 "; }
up 8890 || (nohup python3 -m http.server 8890 --directory $R > /dev/null 2>&1 &)
pgrep -f "dashboard/statu[s].py" >/dev/null || (nohup python3 tools/dashboard/status.py > /dev/null 2>&1 &)
up 8892 || (nohup python3 -m http.server 8892 --directory $R/tools/collision_viewer > /dev/null 2>&1 &)
up 8891 || (nohup python3 -m http.server 8891 --directory $R/tools/assembly_viewer > /dev/null 2>&1 &)
up 6006 || (cd $M && nohup .venv/bin/tensorboard --logdir logs/rsl_rl/pygmalion_velocity --port 6006 --bind_all > analysis/out/tensorboard.log 2>&1 &)
up 8089 || bash $M/analysis/viser_live.sh AB 8089
up 8090 || bash $M/analysis/viser_live.sh RP 8090
# pygviewer: sim<->real comparison viewer (viser 8094 + REST/WS API 8095). CPU only.
up 8094 || (cd $R && CUDA_VISIBLE_DEVICES="" setsid nohup $M/.venv/bin/python3 tools/pygviewer/run.py \
  --variant LegOnly-AB --port 8094 --api-port 8095 > tools/pygviewer/logs/pygviewer.log 2>&1 < /dev/null &)
pgrep -f "gpu_sample[r].sh" >/dev/null || (cd $M && nohup bash analysis/gpu_sampler.sh analysis/out/gpu_usage.csv > /dev/null 2>&1 &)
pgrep -f "review_loo[p].sh" >/dev/null || (cd $M && nohup bash analysis/review_loop.sh > analysis/out/review_loop.log 2>&1 &)
sleep 2; ss -ltn | grep -E ":(8890|8891|8892|6006|8089|8090|8094|8095) " | awk '{print $4}'
