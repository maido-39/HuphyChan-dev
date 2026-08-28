#!/bin/bash
# ============================================================================
# measure_v2s1.sh -- post-training structural-load measurement harness for the
# V2 velocity run `v2s1` (P1 + P2 continuation). THE core deliverable: hardware
# design loads. Run this the moment v2s1_p2 finishes so loads are measured
# immediately (this is a CPU harness; it holds the shared gpu.lock only so it
# cannot collide with another coder's GPU job on this box, and nice -n 10 keeps
# it off the training scheduler's back).
#
# Sequence (each stage guarded by gpu.lock, nice -n 10, CPU-only):
#   (a) analysis/measure_full.py  fc (clean) + fcp (push)  over the FULL FINAL
#       curriculum box  -- 0.25-grid axis sweeps + 2D faces + corners + random,
#       750-step (15 s) dwell per command  (measure_full docstring / user rule
#       2026-07-11: full box, >=15 s dwell).  The box is READ FROM THE RUN, not
#       env defaults: the gated curriculum (commands_vel_gated) IGNORES the
#       per-stage `step` field and advances on performance, so the authoritative
#       box is the last-logged Curriculum/command_vel/* in the run's tfevents.
#   (b) impact_probe_multi.py  200 Hz, 24 env, DR-off (PROBE_NODR=1), BW from
#       the loaded model  -- foot-strike peak/rate (physics-substep resolved).
#   (c) built-in evaluator (mjlab.tasks.velocity.scripts.evaluate), ONE SCENARIO
#       PER INVOCATION, max_parallel_envs=8  -- a 32-parallel run swapped this
#       box once; the per-scenario RSS bound is max_parallel_envs, kept at 8.
#   (d) analysis/actuator_eval.py on the fc tag  -- §7 motor utilisation
#       (RMS/P99/peak vs RobStride rated/peak, TN-envelope saturation %).
#
# The env toggles below are v2s1's EXACT training flags. load_env_cfg reads them
# and PYG_INIT_BENT/INIT_MID/ANKLE_MODE/MODEL_V4 change the default pose and the
# model geometry -- the action origin -- so omitting any one INVALIDATES the
# rollout (the policy is pose/obs-dependent).
#
# Usage:
#   measure_v2s1.sh [--dry-run] [RUN_DIR] [CHECKPOINT]
#     --dry-run    extract PYG_BOX + print every command that WOULD run; launch
#                  nothing (no lock, no GPU, no rollout). For validation.
#     RUN_DIR      default: newest logs/.../*v2s1_p2* run (falls back to *v2s1_p1*)
#     CHECKPOINT   default: highest settled model_*.pt in RUN_DIR
#   Stage subset (normal mode): env STAGES="a b c d" measure_v2s1.sh ...
#
#   # when v2s1_p2 finishes:
#   nohup bash tools/robot_model/loop_tests/measure_v2s1.sh \
#       > /home/syaro/pyg_fea/work/measure_v2s1.log 2>&1 &
# ============================================================================
set -u

REPO=/home/syaro/MikuchanRemote/Human-Pygmalion
MJ="$REPO/mujoco-sim/mjlab"
PY="$MJ/.venv/bin/python3"
LOCK=/home/syaro/pyg_fea/locks/gpu.lock
WORK=/home/syaro/pyg_fea/work
TAG=v2s1
STAGES=${STAGES:-"a b c d"}
cd "$MJ" || { echo "!! cannot cd $MJ"; exit 1; }

DRY=0
POS=()
for a in "$@"; do
  case "$a" in
    --dry-run|-n) DRY=1 ;;
    *) POS+=("$a") ;;
  esac
done

# ---- resolve RUN_DIR --------------------------------------------------------
RUN_DIR="${POS[0]:-}"
if [ -z "$RUN_DIR" ]; then
  RUN_DIR=$(ls -d logs/rsl_rl/pygmalion_velocity/*v2s1_p2* 2>/dev/null | sort | tail -1)
  [ -z "$RUN_DIR" ] && RUN_DIR=$(ls -d logs/rsl_rl/pygmalion_velocity/*v2s1_p1* 2>/dev/null | sort | tail -1)
fi
# accept absolute, mjlab-relative (logs/...), or repo-relative (mujoco-sim/mjlab/logs/...)
RUN_DIR="${RUN_DIR#$REPO/}"; RUN_DIR="${RUN_DIR#mujoco-sim/mjlab/}"
{ [ -z "$RUN_DIR" ] || [ ! -d "$RUN_DIR" ]; } && { echo "!! run dir not found: '$RUN_DIR' (cwd $MJ)"; exit 2; }

# ---- resolve CHECKPOINT (highest settled model_*.pt, mtime > 10 s) ----------
CK="${POS[1]:-}"
if [ -z "$CK" ]; then
  CK=$("$PY" - "$RUN_DIR" <<'PY'
import sys, time, glob, os, re
rd = sys.argv[1]; now = time.time(); best = None; bs = -1
for f in glob.glob(os.path.join(rd, "model_*.pt")):
    m = re.match(r"model_(\d+)\.pt$", os.path.basename(f))
    if not m: continue
    if now - os.path.getmtime(f) < 10.0: continue   # skip files still flushing
    s = int(m.group(1))
    if s > bs: bs, best = s, f
print(best or "")
PY
)
fi
[ -z "$CK" ] || [ ! -f "$CK" ] && { echo "!! checkpoint not found in $RUN_DIR (got '$CK')"; exit 2; }

# ---- extract the FINAL curriculum box from the run's tfevents ---------------
# Authoritative: gated curriculum ignores stage `step`, so read the last-logged
# Curriculum/command_vel/* scalars. Fallback: final velocity_stage in env.yaml
# (an UPPER BOUND -- only equals the achieved box if the run reached it).
PYG_BOX=$("$PY" - "$RUN_DIR" <<'PY'
import sys, glob, os
rd = sys.argv[1]

def from_tfevents(rd):
    try:
        from tensorboard.backend.event_processing import event_accumulator
    except Exception as e:
        print(f"[box] no tensorboard event_accumulator: {e}", file=sys.stderr); return None
    ev = sorted(glob.glob(os.path.join(rd, "events.out.tfevents.*")))
    if not ev:
        print("[box] no tfevents", file=sys.stderr); return None
    ea = event_accumulator.EventAccumulator(ev[-1], size_guidance={event_accumulator.SCALARS: 0})
    ea.Reload()
    tags = ea.Tags().get("scalars", [])
    need = {k: f"Curriculum/command_vel/{k}" for k in
            ("lin_vel_x_min","lin_vel_x_max","lin_vel_y_min","lin_vel_y_max",
             "ang_vel_z_min","ang_vel_z_max","stage")}
    if not all(t in tags for t in need.values()):
        print("[box] curriculum tags absent in tfevents", file=sys.stderr); return None
    v = {k: ea.Scalars(t)[-1].value for k, t in need.items()}
    vx_lo, vx_hi = v["lin_vel_x_min"], v["lin_vel_x_max"]
    vy = max(abs(v["lin_vel_y_min"]), abs(v["lin_vel_y_max"]))
    wz = max(abs(v["ang_vel_z_min"]), abs(v["ang_vel_z_max"]))
    print(f"[box] SOURCE=tfevents  stage={v['stage']:.0f}  "
          f"vx[{vx_lo:.2f},{vx_hi:.2f}] vy+-{vy:.2f} wz+-{wz:.2f}", file=sys.stderr)
    return (vx_lo, vx_hi, vy, wz)

def from_env_yaml(rd):
    import yaml
    p = os.path.join(rd, "params", "env.yaml")
    if not os.path.exists(p): return None
    # tolerant loader: env.yaml has python tuple/name tags
    class L(yaml.SafeLoader): pass
    L.add_multi_constructor("tag:yaml.org,2002:python/tuple",
                            lambda ld, sfx, node: tuple(ld.construct_sequence(node)))
    L.add_multi_constructor("tag:yaml.org,2002:python/name:", lambda ld, sfx, node: None)
    L.add_multi_constructor("tag:yaml.org,2002:python/object", lambda ld, sfx, node: None)
    d = yaml.load(open(p), Loader=L)
    stages = d["curriculum"]["command_vel"]["params"]["velocity_stages"]
    s = stages[-1]
    vx_lo, vx_hi = s["lin_vel_x"]
    vy = max(abs(x) for x in s["lin_vel_y"]); wz = max(abs(x) for x in s["ang_vel_z"])
    print(f"[box] SOURCE=env.yaml FINAL-STAGE (UPPER BOUND, verify run reached it)  "
          f"vx[{vx_lo:.2f},{vx_hi:.2f}] vy+-{vy:.2f} wz+-{wz:.2f}", file=sys.stderr)
    return (vx_lo, vx_hi, vy, wz)

box = from_tfevents(rd) or from_env_yaml(rd)
if not box:
    print("[box] FAILED to determine curriculum box", file=sys.stderr); sys.exit(3)
print("%g,%g,%g,%g" % box)
PY
)
[ -z "$PYG_BOX" ] && { echo "!! could not extract PYG_BOX"; exit 3; }
export PYG_BOX

# ---- v2s1 EXACT training flags (load_env_cfg reconstructs the model/pose) ----
COMMON="PYG_V2=1 PYG_INIT_BENT=1 PYG_ARM_ABD_DEG=15 PYG_INERTIAL_DR=1 \
        PYG_ANKLE_MODE=AB PYG_TN=1 PYG_MOTOR_MEAS=1 PYG_SOFT_LANDING=1 \
        PYG_INIT_MID=1 PYG_KNEE_EXT=1 PYG_KNEE_EXT_W=2.0 PYG_KNEE_EXT_DEG=25 \
        PYG_SOFT_LANDING_MODE=half PYG_CRITIC_DR_OBS=1 PYG_MODEL_V4=1 \
        PYG_CMD_VY_STAGES=1 PYG_GATED_CURRICULUM=1"
TASK=Mjlab-Velocity-Flat-Pygmalion

echo "================ measure_v2s1 plan ================"
echo "RUN_DIR    = $RUN_DIR"
echo "CHECKPOINT = $CK"
echo "PYG_BOX    = $PYG_BOX   (vx_lo,vx_hi,vy_abs,wz_abs -> measure_full grid)"
echo "TASK       = $TASK"
echo "STAGES     = $STAGES"
echo "=================================================="

# evaluator scenario list -- one scenario per invocation, covering the box.
# fmt: <kind> <value> <direction>   (kind=lin uses direction; kind=ang: cw+ccw)
EVAL_SCENARIOS=(
  "lin 0.5 N"  "lin 1.0 N"  "lin 1.5 N"  "lin 2.0 N"  "lin 2.5 N"   # forward incl vx_hi
  "lin 0.5 S"  "lin 1.0 S"  "lin 2.0 S"                             # backward incl vx_lo
  "lin 1.0 E"  "lin 1.0 W"                                          # lateral +-vy
  "lin 1.0 NE" "lin 1.0 SW"                                         # diagonal
  "ang 1.0 -"                                                       # yaw +-wz (cw+ccw)
)

# ---------------------------------------------------------------------------
if [ "$DRY" -eq 1 ]; then
  echo
  echo "==== DRY RUN: commands that WOULD run (nothing launched) ===="
  echo
  echo "# (a) measure_full.py  fc (clean):"
  echo "  PYG_BOX=\"$PYG_BOX\" $COMMON CUDA_VISIBLE_DEVICES=\"\" nice -n 10 $PY \\"
  echo "      analysis/measure_full.py --task $TASK --run-dir $RUN_DIR \\"
  echo "      --checkpoint $CK --tag ${TAG}_fc --device cpu"
  echo
  echo "# (a) measure_full.py  fcp (in-DR push):"
  echo "  PYG_BOX=\"$PYG_BOX\" $COMMON CUDA_VISIBLE_DEVICES=\"\" nice -n 10 $PY \\"
  echo "      analysis/measure_full.py --task $TASK --run-dir $RUN_DIR \\"
  echo "      --checkpoint $CK --tag ${TAG}_fcp --device cpu --push"
  echo
  echo "# (b) impact_probe_multi.py  200 Hz, 24 env, DR-off:"
  echo "  $COMMON PROBE_NODR=1 CUDA_VISIBLE_DEVICES=\"\" nice -n 10 $PY \\"
  echo "      ../../tools/robot_model/loop_tests/impact_probe_multi.py \\"
  echo "      $RUN_DIR $CK $TAG 1.6 24"
  echo
  echo "# (c) evaluator, one scenario/invocation, max_parallel_envs=8:"
  for sc in "${EVAL_SCENARIOS[@]}"; do
    set -- $sc
    if [ "$1" = "lin" ]; then NM="lin_${2}_${3}"; else NM="ang_${2} (cw+ccw)"; fi
    echo "    - $1 $2 $3   -> logs/eval/$TAG/$NM"
  done
  echo "  (each: $COMMON $PY -m mjlab.tasks.velocity.scripts.evaluate --config-file <cfg.json>,"
  echo "   envs_per_command=32 max_parallel_envs=8 episode_length_s=20 warmup_s=2 seed=0)"
  echo
  echo "# (d) actuator_eval.py  §7 motor utilisation on the fc tag:"
  echo "  cd analysis && $PY actuator_eval.py --tags ${TAG}_fc --labels flat"
  echo
  echo "==== end dry run ===="
  exit 0
fi

# ---- gpu.lock (stale-owner reclaim, same protocol as run_p1_*.sh) ----------
acquire_lock() {
  local waited=0
  until mkdir "$LOCK" 2>/dev/null; do
    local own opid; own=$(cat "$LOCK/owner" 2>/dev/null); opid=${own%% *}
    if [ -n "$opid" ] && ! kill -0 "$opid" 2>/dev/null; then
      echo "STALE gpu.lock: owner '$own' pid $opid not running; 60 s grace"; sleep 60
      local own2 opid2; own2=$(cat "$LOCK/owner" 2>/dev/null); opid2=${own2%% *}
      if [ "$own2" = "$own" ] && ! kill -0 "$opid2" 2>/dev/null; then
        echo "RECLAIM stale gpu.lock from '$own'"; rm -rf "$LOCK"; continue
      fi
    fi
    [ $((waited % 300)) -eq 0 ] && echo "WAIT gpu.lock held by $own (${waited}s)"
    sleep 15; waited=$((waited + 15))
  done
  echo "$$ measure_v2s1 $(date -Is)" > "$LOCK/owner"
  trap 'rm -rf "$LOCK"; echo RELEASED' EXIT
  echo "LOCK acquired after ${waited}s"
}

mkdir -p "$WORK/impact_multi" "$WORK/impact_multi_nodr"
acquire_lock

run_stage() { case " $STAGES " in *" $1 "*) return 0;; *) echo "-- skip stage $1"; return 1;; esac; }

# ---- (a) full-box load measurement: fc (clean) + fcp (push) ----------------
if run_stage a; then
  echo "== (a) measure_full fc  $(date +%H:%M:%S)  box=$PYG_BOX"
  env PYG_BOX="$PYG_BOX" $COMMON CUDA_VISIBLE_DEVICES="" nice -n 10 "$PY" \
      analysis/measure_full.py --task "$TASK" --run-dir "$RUN_DIR" \
      --checkpoint "$CK" --tag "${TAG}_fc" --device cpu
  echo "   fc rc=$?"
  echo "== (a) measure_full fcp (push)  $(date +%H:%M:%S)"
  env PYG_BOX="$PYG_BOX" $COMMON CUDA_VISIBLE_DEVICES="" nice -n 10 "$PY" \
      analysis/measure_full.py --task "$TASK" --run-dir "$RUN_DIR" \
      --checkpoint "$CK" --tag "${TAG}_fcp" --device cpu --push
  echo "   fcp rc=$?"
fi

# ---- (b) 200 Hz multi-env foot-strike probe, DR-off ------------------------
if run_stage b; then
  echo "== (b) impact_probe_multi 24 env DR-off  $(date +%H:%M:%S)"
  env $COMMON PROBE_NODR=1 CUDA_VISIBLE_DEVICES="" nice -n 10 "$PY" \
      ../../tools/robot_model/loop_tests/impact_probe_multi.py \
      "$RUN_DIR" "$CK" "$TAG" 1.6 24 2>&1 | grep -aE "^\[multi\]|^MULTI|Traceback|Error"
  echo "   impact rc=${PIPESTATUS[0]}"
fi

# ---- (c) built-in evaluator, ONE scenario per invocation, max_parallel 8 ---
if run_stage c; then
  echo "== (c) evaluator sweep  $(date +%H:%M:%S)"
  for sc in "${EVAL_SCENARIOS[@]}"; do
    set -- $sc; KIND="$1"; VAL="$2"; DIR="$3"
    if [ "$KIND" = "lin" ]; then
      NAME="lin_${VAL}_${DIR}"; LIN="[$VAL]"; ANG="[]"; DIRS="[\"$DIR\"]"
    else
      NAME="ang_${VAL}"; LIN="[]"; ANG="[$VAL]"; DIRS="[]"
    fi
    ROOT="logs/eval/$TAG/$NAME"
    if [ -f "$ROOT/summary.json" ]; then echo "   skip $NAME (done)"; continue; fi
    CFG="$WORK/evalcfg_${TAG}_${NAME}.json"
    cat > "$CFG" <<JSON
{
  "checkpoint": "$CK",
  "task_id": "$TASK",
  "envs_per_command": 32,
  "max_parallel_envs": 8,
  "episode_length_s": 20.0,
  "warmup_s": 2.0,
  "seed": 0,
  "output_root": "$ROOT",
  "save_plots": false,
  "commands": {"linear_speeds": $LIN, "directions": $DIRS, "angular_speeds": $ANG}
}
JSON
    echo "   -- $NAME  $(date +%H:%M:%S)"
    env $COMMON CUDA_VISIBLE_DEVICES="" nice -n 10 "$PY" \
        -m mjlab.tasks.velocity.scripts.evaluate --config-file "$CFG" \
        > "$WORK/eval_${TAG}_${NAME}.log" 2>&1
    echo "      rc=$?  ($(grep -c . "$WORK/eval_${TAG}_${NAME}.log") log lines)"
  done
fi

# ---- (d) §7 motor utilisation on the fc tag --------------------------------
if run_stage d; then
  echo "== (d) actuator_eval (§7 motor util) on ${TAG}_fc  $(date +%H:%M:%S)"
  if [ -f "analysis/out/${TAG}_fc.npz" ]; then
    ( cd analysis && CUDA_VISIBLE_DEVICES="" nice -n 10 "$PY" \
        actuator_eval.py --tags "${TAG}_fc" --labels flat )
    echo "   actuator_eval rc=$?"
  else
    echo "   !! analysis/out/${TAG}_fc.npz missing -- run stage (a) first"
  fi
fi

echo "== measure_v2s1 done  $(date +%H:%M:%S)"
