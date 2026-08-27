#!/usr/bin/env bash
# Build the v3 closed-loop USD and roll the AB policy on it, holding the shared GPU lock.
#
# WHY v3 AND NOT THE v4 LOOP USD AUTHORED YESTERDAY: bundleD1_AB trained on
# pygmalion_v3_printed_loop.xml (35.34745 kg, BW 346.76 N) - PYG_MODEL_V4 was never set for it
# (pygmalion_constants.py: the loop branch picks v3 unless _V4). The v4 loop build is 31.32 kg.
# A 4 kg mass difference is exactly the kind of thing that masqueraded as a contact problem in
# the RP port. So the model is rebuilt from the v3 loop URDF, and the anchors come from the v3
# loop MJCF.
#
# The lock is a directory taken with mkdir - the one atomic create across processes.
set -u
REPO=/home/syaro/MikuchanRemote/Human-Pygmalion
LOCK=/home/syaro/pyg_fea/locks/gpu.lock
WORK=/home/syaro/pyg_fea/work
PY=/home/syaro/isaacsim_venv/bin/python3
URDF=$REPO/pygmalion_locomotion/assets/pygmalion_v2/pygmalion_v3_printed_loop.urdf
MJCF=$REPO/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/pygmalion_v3_printed_loop.xml
USD=/home/syaro/pyg_fea/usd/pygmalion_v3_printed_loop.usd
export OMNI_KIT_ACCEPT_EULA=YES

waited=0
until mkdir "$LOCK" 2>/dev/null; do
  [ $((waited % 300)) -eq 0 ] && echo "WAIT gpu.lock held by $(cat $LOCK/owner 2>/dev/null) (${waited}s)"
  sleep 15; waited=$((waited + 15))
done
echo "$$ ab_rollout $(date)" > "$LOCK/owner"
trap 'rm -rf "$LOCK"; echo RELEASED' EXIT
echo "LOCK acquired after ${waited}s"
free -m | head -2
cd "$REPO" || exit 1

if [ ! -f "$USD" ] || [ "${PYG_REBUILD:-0}" = "1" ]; then
  echo "STEP 1 urdf -> usd (v3 loop skeleton)"
  nice -n 10 $PY tools/sim2sim/urdf_to_usd.py "$URDF" "$USD" "$WORK/urdf_to_usd_loop_v3.json" \
    > "$WORK/urdf_to_usd_loop_v3.log" 2>&1
  python3 -c "import json;d=json.load(open('$WORK/urdf_to_usd_loop_v3.json'));print('  ok',d['ok'],d.get('n_links'),'links',d.get('n_revolute'),'revolute',d.get('total_mass_kg'),'kg',d.get('error','')[:200])" || exit 1

  echo "STEP 2 author the 4 loop-closure spherical joints (pure pxr)"
  PYG_LOOP_RES="$WORK/author_loop_usd_v3.json" nice -n 10 python3 \
    tools/sim2sim/author_loop_usd.py "$USD" "$MJCF" > "$WORK/author_loop_usd_v3.log" 2>&1
  tail -8 "$WORK/author_loop_usd_v3.log"
else
  echo "STEP 1-2 skipped: $USD exists (PYG_REBUILD=1 to force)"
fi

run () {   # $1 = tag, $2 = iters "pos,vel", $3 = seconds
  echo "== rollout $1  iters $2  ${3}s  $(date +%H:%M:%S)"
  PYG_TAG="$1" PYG_ITERS="$2" nice -n 10 $PY tools/sim2sim/isaac_grf_rollout_ab.py "$USD" "$3" \
    > "$WORK/ab_rollout/isaac_ab_$1.log" 2>&1
  python3 - "$1" <<'PYEOF'
import json, sys
d = json.load(open(f'/home/syaro/pyg_fea/work/ab_rollout/isaac_ab_{sys.argv[1]}.json'))
if not d.get('ok'):
    print('   FAILED', d.get('error', '')[:300]); sys.exit(0)
i = d['isaac']
print('   iters', d['knobs'].get('runtime_solver_iters'), 'fell', d['fell'],
      'vx_err', round(d['vx_err'], 4), 'peak', round(i.get('peak_BW_med', 0), 3),
      'rate', round(i.get('rate_BWs_med', 0), 1), 'strikes/s', i['strikes_per_s_per_env'],
      'support', d['support_check']['mean_total_Fz_BW'],
      'drift_max_mm', d['loop_drift_mm']['all_max'])
PYEOF
}

mkdir -p "$WORK/ab_rollout"
run i4x8   4,8   45
run i32x16 32,16 45
run i8x4   8,4   45
echo DONE
