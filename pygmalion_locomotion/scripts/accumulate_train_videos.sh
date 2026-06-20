#!/bin/bash
# Watch a training run's videos/train/ folder and continuously (re)build ONE accumulated video
# of all in-training clips, each stamped with its training step in the bottom-right corner.
# Runs in PARALLEL with training so the accumulated progress video grows as training proceeds.
#
#   bash scripts/accumulate_train_videos.sh logs/rsl_rl/<exp>/<run> [interval_s]
#
# Output: <run>/videos/accumulated_progress.mp4  (rebuilt every interval as new clips appear)
set -u
RUN="${1:?usage: accumulate_train_videos.sh <run_dir> [interval_s]}"
RUN="$(realpath "$RUN")"   # absolute -> concat demuxer resolves clip paths correctly
INT="${2:-30}"
VDIR="$RUN/videos/train"
OUT="$RUN/videos/accumulated_progress.mp4"
TMP="$RUN/videos/.acc_tmp"
mkdir -p "$TMP"

last_count=-1
while true; do
  # clips sorted by numeric step
  mapfile -t clips < <(ls "$VDIR"/rl-video-step-*.mp4 2>/dev/null \
      | sed -E 's/.*step-([0-9]+)\.mp4/\1 &/' | sort -n | cut -d' ' -f2-)
  n=${#clips[@]}
  if [ "$n" -eq 0 ]; then sleep "$INT"; continue; fi
  if [ "$n" -ne "$last_count" ]; then
    : > "$TMP/list.txt"
    for c in "${clips[@]}"; do
      step=$(echo "$c" | grep -oE 'step-[0-9]+' | grep -oE '[0-9]+')
      cap="$TMP/cap_$(printf '%08d' "$step").mp4"
      # caption each clip once (skip if already captioned and source unchanged)
      if [ ! -f "$cap" ] || [ "$c" -nt "$cap" ]; then
        ffmpeg -y -i "$c" -vf \
          "drawtext=text='step ${step}':x=w-tw-16:y=h-th-16:fontsize=34:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=12" \
          -c:v libx264 -pix_fmt yuv420p "$cap" </dev/null >/dev/null 2>&1
      fi
      echo "file '$cap'" >> "$TMP/list.txt"
    done
    ffmpeg -y -f concat -safe 0 -i "$TMP/list.txt" -c:v libx264 -pix_fmt yuv420p "$OUT" </dev/null >/dev/null 2>&1
    echo "[accumulate] $n clips (latest step ${step}) -> $OUT"
    last_count="$n"
  fi
  sleep "$INT"
done
