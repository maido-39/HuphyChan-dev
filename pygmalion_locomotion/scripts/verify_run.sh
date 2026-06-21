#!/bin/bash
# ★ DEBUGGING LOOP (user-mandated 2026-06-21): after EVERY training launch, confirm the implemented
# features ACTUALLY APPLIED in the real run — never assume. (The video env_spacing was "implemented" but
# never took effect; this script exists so that can't happen silently again.) Checks the run's
# params/env.yaml + videos + repro, and EXTRACTS A VIDEO FRAME so the robot count / camera can be eyeballed.
#
# Usage: bash scripts/verify_run.sh <run_dir>   (run dir = logs/rsl_rl/<group>/<timestamp>_<name>)
set -u
cd /home/syaro/MikuchanRemote/Human-Pygmalion/pygmalion_locomotion
RUN="${1:?run_dir}"
Y="$RUN/params/env.yaml"
echo "=================== verify_run: $(basename "$RUN") ==================="
[ -f "$Y" ] || echo "  ⚠ NO env.yaml at $Y (run may still be building)"

echo "-- VIDEO (fewer robots / 2x length / accumulate) --"
grep -aoE "env_spacing: [0-9.]+" "$Y" 2>/dev/null | head -1 | sed 's/^/  /'   # flat should be 30.0 (8 was too many)
echo "  clips: $(ls "$RUN"/videos/train/*.mp4 2>/dev/null | wc -l)"
[ -f "$RUN/videos/accumulated_progress.mp4" ] && echo "  accumulated_progress.mp4: YES" || echo "  accumulated_progress.mp4: ⚠ MISSING"

echo "-- COMMANDS / DR (env.yaml) --"
grep -aoE "lin_vel_x: \[[^]]*\]|ang_vel_z: \[[^]]*\]" "$Y" 2>/dev/null | sed 's/^/  /' | head
grep -aoE "(static|dynamic)_friction_range: \[[^]]*\]" "$Y" 2>/dev/null | sed 's/^/  /' | head -2

echo "-- REWARD terms present (env.yaml) --"
echo -n "  "; grep -aoE "power_cot|forefoot_cop|ankle_pushoff|joint_overrating_penalty|torque_soft_limit_ankle|dof_acc_l2|track_lin_vel" "$Y" 2>/dev/null | sort -u | tr '\n' ' '; echo

echo "-- REPRO config backup --"
echo "  backed-up files: $(ls "$RUN"/repro/ 2>/dev/null | wc -l)"

echo "-- VIDEO FRAME for eyeball (robot count / camera) --"
CLIP=$(ls -t "$RUN"/videos/train/*.mp4 2>/dev/null | head -1)
if [ -n "$CLIP" ]; then
  OUT="/tmp/verify_$(basename "$RUN")_frame.png"
  ffmpeg -y -i "$CLIP" -vf "select=eq(n\,25)" -vframes 1 "$OUT" 2>/dev/null && echo "  -> Read $OUT (count the robots; should be FEW)"
else
  echo "  (no clip yet — re-run after the first video_interval)"
fi
echo "====================================================================="
