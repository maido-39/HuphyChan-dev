#!/bin/bash
# =====================================================================================================
# THE ONLY sanctioned way to launch ANY training (incl. config/tests). The protocol CANNOT be skipped:
#   (1) TRAIN with video ON  -> OVERVIEW video (multi-robot density / terrain) + accumulate
#   (2) CLOSE-UP play video  -> single-robot near camera (gait detail)   [BOTH, user 2026-06-22]
#   (3) formatted REPORT     -> make_run_report.py (OBS/repro + embed both videos + plots)
# The PreToolUse hook blocks DIRECT `python ... train.py` so this launcher is the only path.
# Usage: run_training.sh <task> <run_name> <max_iter> <num_envs> [extra train args...]
# =====================================================================================================
set -uo pipefail
ROOT=/home/syaro/MikuchanRemote/Human-Pygmalion/pygmalion_locomotion
cd "$ROOT" || exit 1
source /home/syaro/MikuchanRemote/Human-Pygmalion/sim/miniforge3/etc/profile.d/conda.sh && conda activate pygmalion

TASK="${1:?task}"; RUN="${2:?run_name}"; ITER="${3:?max_iter}"; ENVS="${4:?num_envs}"; shift 4 || true
EXTRA="$*"
LOG="logs/${RUN}.log"
find source -name '*.pyc' -delete 2>/dev/null

echo "[run_training] (1/3) TRAIN (video ON) task=$TASK run=$RUN iter=$ITER envs=$ENVS extra=$EXTRA"
# NEVER pass --no_video. ENABLE_VIDEO is the whole point.
python scripts/train.py --task "$TASK" --num_envs "$ENVS" --max_iterations "$ITER" --headless \
  --run_name "$RUN" $EXTRA > "$LOG" 2>&1
echo "[run_training] train exit=$? "

D=$(ls -dt logs/rsl_rl/*/*"_${RUN}" 2>/dev/null | head -1)
if [ -z "$D" ]; then echo "[run_training] ERROR no run dir for $RUN"; exit 2; fi
CK="$D/model_$(ls "$D"/model_*.pt 2>/dev/null | sed 's/.*model_//;s/\.pt//' | sort -n | tail -1).pt"

# (2) CLOSE-UP single-robot play video (separate camera in play.py)
case "$TASK" in
  *AsimovReward*) PLAYTASK="Pygmalion-Velocity-Flat-AsimovReward-Play-v0" ;;
  *G1ImpactStableAsymObs*) PLAYTASK="Pygmalion-Velocity-Flat-G1ImpactStableAsymObs-Play-v0" ;;
  *G1Vanilla*) PLAYTASK="Pygmalion-Velocity-Flat-G1Vanilla-Play-v0" ;;
  *OursG1cond*) PLAYTASK="Pygmalion-Velocity-Flat-OursG1cond-Play-v0" ;;
  *G1Impact*) PLAYTASK="Pygmalion-Velocity-Flat-G1Impact-Play-v0" ;;
  *Rough*) PLAYTASK="Pygmalion-Velocity-Rough-Forefoot-Play-v0" ;;
  *)       PLAYTASK="Pygmalion-Velocity-Flat-Play-v0" ;;
esac
echo "[run_training] (2/4) CLOSE-UP play  task=$PLAYTASK ckpt=$CK"
python scripts/play.py --task "$PLAYTASK" --checkpoint "$CK" --num_envs 1 --video --video_length 350 --headless \
  >> "$LOG" 2>&1
echo "[run_training] play exit=$? "

# (3) MEASURE for §7 motor-utilization: per-joint torque & speed RMS/p95/MAX vs the SPEC lines read from THIS
#     run's config (rated/peak/velocity_limit -> gear-ratio/effort auto-matched via the yaml) + saturation% +
#     time-series. ALWAYS done after training (user 2026-06-22: §7 무조건 학습 끝나고 자동).
echo "[run_training] (3/4) MEASURE motor-util  task=$PLAYTASK"
python scripts/measure.py --task "$PLAYTASK" --checkpoint "$CK" --tag "$RUN" --headless >> "$LOG" 2>&1
echo "[run_training] measure exit=$? "
MNPZ="logs/measure/${RUN}.npz"; MARG=""; [ -f "$MNPZ" ] && MARG="--measure_npz $MNPZ"

# (4) formatted report (overview + close-up + TB + §7 motor-util; §4 vs parent if warm-started -> forefoot_pushoff 구조)
echo "[run_training] (4/4) REPORT (+ §7 motor util RMS/p95/peak)"
PARENT=""
PCK=$(printf '%s' "$EXTRA" | grep -oE 'logs/rsl_rl/[^ ]+/model_[0-9]+\.pt' | head -1)
[ -n "$PCK" ] && PARENT="--parent_run $(dirname "$PCK")"
python scripts/make_run_report.py --run "$D" --log "$LOG" $PARENT $MARG >> "$LOG" 2>&1
echo "[run_training] report exit=$?  ALL DONE -> $D"
