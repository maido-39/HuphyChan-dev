#!/bin/bash
# 2-스테이지 전이 학습: ① 평지(height_scan 포함, 전체 DR)로 보행 폴리시 확립 →
# ② rough terrain을 평지 가중치에서 이어받아(--init_checkpoint) 미세조정.
# 각 스테이지에 학습-중 영상 + accumulator 자동 연결.
#   실행: setsid nohup bash scripts/transfer_flat_to_rough.sh > /tmp/transfer.log 2>&1 &
set -u
cd "$(dirname "$0")/.."
source /home/syaro/MikuchanRemote/Human-Pygmalion/sim/miniforge3/etc/profile.d/conda.sh
conda activate pygmalion
export OMNI_KIT_ACCEPT_EULA=YES PYTHONDONTWRITEBYTECODE=1

FENV=16384; FITER=800
RENV=8192;  RITER=1000

acc() {  # $1=exp $2=run_name  -> run dir 생기면 accumulator
  local exp="$1" rname="$2" RUN=""
  for i in $(seq 1 90); do
    RUN=$(ls -dt logs/rsl_rl/$exp/*"$rname" 2>/dev/null | head -1)
    [ -n "$RUN" ] && [ -d "$RUN/videos/train" ] && break
    sleep 8
  done
  RUN=$(ls -dt logs/rsl_rl/$exp/*"$rname" 2>/dev/null | head -1)
  [ -n "$RUN" ] && nohup bash scripts/accumulate_train_videos.sh "$RUN" 30 >/dev/null 2>&1 &
  echo "[xfer] accumulator: ${RUN:-none}"
}

# GPU 빌 때까지 대기
while pgrep -f "scripts/train.py" >/dev/null 2>&1; do sleep 30; done; sleep 8
for p in $(pgrep -f "bin/isaacsim"); do kill -9 "$p" 2>/dev/null; done; sleep 3

echo "[xfer] ===== STAGE 1: 평지 teacher (height_scan + 전체 DR) $(date) ====="
python -u scripts/train.py --task Pygmalion-Velocity-Flat-v0 --device cuda:0 \
  --num_envs $FENV --max_iterations $FITER --headless --run_name flat_teacher > /tmp/xfer_flat.txt 2>&1 &
fpid=$!
acc pygmalion_flat flat_teacher
wait "$fpid"
FRUN=$(ls -dt logs/rsl_rl/pygmalion_flat/*flat_teacher 2>/dev/null | head -1)
FCKPT=$(ls "$FRUN"/model_*.pt 2>/dev/null | sed -E 's/.*model_([0-9]+)\.pt/\1 &/' | sort -n | tail -1 | cut -d' ' -f2-)
echo "[xfer] STAGE1 완료. flat checkpoint = $FCKPT"
for p in $(pgrep -f "bin/isaacsim"); do kill -9 "$p" 2>/dev/null; done; sleep 5

if [ -z "$FCKPT" ] || [ ! -f "$FCKPT" ]; then echo "[xfer] ERROR: flat checkpoint 없음 — 중단"; exit 1; fi

echo "[xfer] ===== STAGE 2: rough (평지 가중치 이어받기) $(date) ====="
python -u scripts/train.py --task Pygmalion-Velocity-Rough-v0 --device cuda:0 \
  --num_envs $RENV --max_iterations $RITER --headless --run_name rough_from_flat \
  --init_checkpoint "$FCKPT" > /tmp/xfer_rough.txt 2>&1 &
rpid=$!
acc pygmalion_rough rough_from_flat
wait "$rpid"
echo "[xfer] ===== ALL DONE $(date) ====="
