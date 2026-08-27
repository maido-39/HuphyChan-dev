#!/usr/bin/env bash
# Re-measure the RP (serial) GRF rollout with the WELDED upper body held at mjlab's actual pose.
#
# The bug: the port held the five welded upper-body joints at 0, but mjlab bakes a 15 deg arm
# abduction into the arm body quat before deleting those joints. Measured on the compiled
# models, that put each 2.843 kg arm's COM 66.8 mm too far inboard. Every row of the
# 2026-08-27 contact sweep - including the published 4/8 and 8/4 recommendations - was run
# that way.
#
# Order: the CONTROL runs first. PYG_ARM_ABD_DEG=0 must reproduce the committed b7_pos4vel8
# row exactly; if it does, the only thing that changed in the script is the arm pose, and the
# treatment rows can be compared against the published numbers directly. Same discipline the
# sweep itself used (`base` re-run byte-identical to the committed baseline).
set -u
REPO=/home/syaro/MikuchanRemote/Human-Pygmalion
LOCK=/home/syaro/pyg_fea/locks/gpu.lock
WORK=/home/syaro/pyg_fea/work/contact_sweep
PY=/home/syaro/isaacsim_venv/bin/python3
USD=/home/syaro/pyg_fea/usd/pygmalion_v3_printed.usd
export OMNI_KIT_ACCEPT_EULA=YES

waited=0
until mkdir "$LOCK" 2>/dev/null; do
  o=$(cat $LOCK/owner 2>/dev/null)
  [ $((waited % 300)) -eq 0 ] && echo "WAIT gpu.lock held by $o (${waited}s)"
  sleep 15; waited=$((waited + 15))
done
echo "$$ rp_armfix $(date -Is)" > "$LOCK/owner"
trap 'rm -rf "$LOCK"; echo RELEASED' EXIT
echo "LOCK acquired after ${waited}s"
free -m | head -2
cd "$REPO" || exit 1

run () {   # $1 = tag, $2 = iters, $3 = abduction deg
  echo "== $1  iters $2  arm_abd $3 deg  $(date +%H:%M:%S)"
  PYG_TAG="$1" PYG_ITERS="$2" PYG_ARM_ABD_DEG="$3" nice -n 10 \
    $PY tools/sim2sim/isaac_grf_rollout.py "$USD" 45 > "$WORK/$1.log" 2>&1
  python3 - "$1" <<'PYEOF'
import json, sys
d = json.load(open('/home/syaro/pyg_fea/work/contact_sweep/'
                   f'isaac_grf_pygmalion_v3_printed_{sys.argv[1]}.json'))
if not d.get('ok'):
    print('   FAILED', d.get('error', '')[:300]); sys.exit(0)
i = d['isaac']
print(f"   iters {d['knobs'].get('runtime_solver_iters')} abd {d.get('arm_abduction_deg')} "
      f"fell {d['fell']} vx_err {d['vx_err']:.6f} peak {i['peak_BW_med']:.4f} "
      f"rate {i['rate_BWs_med']:.4f} strikes {i['strikes_per_s_per_env']} "
      f"duty {i['duty']:.4f} support {d['support_check']['mean_total_Fz_BW']}")
PYEOF
}

run ctl_abd0_i4x8  4,8 0
run abd15_i4x8     4,8 15
run abd15_i8x4     8,4 15
echo DONE
