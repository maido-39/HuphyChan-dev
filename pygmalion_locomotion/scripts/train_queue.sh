#!/bin/bash
# 학습 큐 러너 — scripts/train_queue.txt 의 각 줄(= train.py 인자)을 위→아래 순서로,
# GPU가 비면(다른 train.py 없음) 하나씩 실행한다. 각 run에 in-training 영상 + accumulator 자동 연결.
# 큐에 추가: train_queue.txt 에 한 줄 append. 이미 끝난 건 train_queue.done 에 기록되어 재실행 안 함.
#   사용: setsid nohup bash scripts/train_queue.sh > /tmp/train_queue.log 2>&1 &
set -u
cd "$(dirname "$0")/.."
source /home/syaro/MikuchanRemote/Human-Pygmalion/sim/miniforge3/etc/profile.d/conda.sh
conda activate pygmalion
export OMNI_KIT_ACCEPT_EULA=YES PYTHONDONTWRITEBYTECODE=1

QF="scripts/train_queue.txt"
DONE="scripts/train_queue.done"
touch "$DONE"

echo "[queue] runner started $(date)"
while true; do
  [ -f "$QF" ] || { sleep 60; continue; }
  next=""
  while IFS= read -r line; do
    line="${line%%$'\r'}"
    [ -z "$line" ] && continue
    case "$line" in \#*) continue ;; esac
    grep -qxF -- "$line" "$DONE" || { next="$line"; break; }
  done < "$QF"
  if [ -z "$next" ]; then sleep 60; continue; fi   # 대기 큐 비었으면 append 감시

  # GPU가 빌 때까지(다른 train.py 끝날 때까지) 대기
  while pgrep -f "scripts/train.py" >/dev/null 2>&1; do sleep 30; done
  sleep 10
  for p in $(pgrep -f "bin/isaacsim"); do kill -9 "$p" 2>/dev/null; done
  sleep 3

  exp="pygmalion_flat"; echo "$next" | grep -qi "Rough" && exp="pygmalion_rough"
  rname=$(echo "$next" | grep -oE 'run_name[= ]+[^ ]+' | awk '{print $NF}')
  ts=$(date +%H%M%S)
  logf="/tmp/queue_${rname}_${ts}.txt"
  echo "[queue] >>> RUN ($exp/$rname): python scripts/train.py $next  -> $logf  $(date)"
  python -u scripts/train.py $next --headless > "$logf" 2>&1 &
  tpid=$!

  # run dir 생기면 accumulator 연결
  RUN=""
  for i in $(seq 1 90); do
    RUN=$(ls -dt logs/rsl_rl/$exp/*"$rname" 2>/dev/null | head -1)
    [ -n "$RUN" ] && [ -d "$RUN/videos/train" ] && break
    kill -0 "$tpid" 2>/dev/null || break
    sleep 8
  done
  RUN=$(ls -dt logs/rsl_rl/$exp/*"$rname" 2>/dev/null | head -1)
  if [ -n "$RUN" ]; then
    nohup bash scripts/accumulate_train_videos.sh "$RUN" 30 >/dev/null 2>&1 &
    echo "[queue] accumulator linked: $RUN"
  fi

  wait "$tpid"
  echo "$next" >> "$DONE"
  echo "[queue] <<< DONE ($rname) $(date)"
done
