#!/usr/bin/env bash
# Build and validate the closed-loop (AB) ankle USD, start to finish, holding the shared GPU lock
# for the whole sequence.
#
# The lock is a directory, taken with mkdir because that is the one filesystem operation that is
# atomic across processes - test-then-create loses a race that this cannot. Another coder's contact
# sweeps take the same lock, so this waits politely rather than fighting for the GPU, and releases
# on any exit path including a crash.
#
# Order matters: the MJCF-importer probe runs LAST because it is expected to take the process down,
# and a segfault must not be able to cost us the conversion and validation that came before it.
set -u
REPO=/home/syaro/MikuchanRemote/Human-Pygmalion
LOCK=/home/syaro/pyg_fea/locks/gpu.lock
WORK=/home/syaro/pyg_fea/work
PY=/home/syaro/isaacsim_venv/bin/python3
URDF=$REPO/pygmalion_locomotion/assets/pygmalion_v2/pygmalion_v4_printed_loop.urdf
USD=/home/syaro/pyg_fea/usd/pygmalion_v4_printed_loop.usd
export OMNI_KIT_ACCEPT_EULA=YES

waited=0
until mkdir "$LOCK" 2>/dev/null; do
  [ $((waited % 300)) -eq 0 ] && echo "WAIT gpu.lock held by $(cat $LOCK/owner 2>/dev/null) (${waited}s)"
  sleep 15; waited=$((waited + 15))
done
echo "$$ abusd $(date)" > "$LOCK/owner"
trap 'rm -rf "$LOCK"; echo RELEASED' EXIT
echo "LOCK acquired after ${waited}s"
free -m | head -2

cd "$REPO" || exit 1

echo "STEP 1/4 urdf -> usd (serial skeleton: cranks and rods as dead-end branches)"
nice -n 10 $PY tools/sim2sim/urdf_to_usd.py "$URDF" "$USD" "$WORK/urdf_to_usd_loop.json" \
  > "$WORK/urdf_to_usd_loop.log" 2>&1
python3 -c "import json;d=json.load(open('$WORK/urdf_to_usd_loop.json'));print('  ok',d['ok'],d.get('n_links'),'links',d.get('n_revolute'),'revolute',d.get('total_mass_kg'),'kg',d.get('error',''))" || exit 1

echo "STEP 2/4 author the 4 loop-closure spherical joints (pure pxr, no app)"
nice -n 10 python3 tools/sim2sim/author_loop_usd.py "$USD" > "$WORK/author_loop_usd.log" 2>&1
tail -8 "$WORK/author_loop_usd.log"

echo "STEP 3/4 static cross-engine validation in IsaacSim"
nice -n 10 $PY tools/sim2sim/xengine_loop_isaac_side.py > "$WORK/xengine_loop_isaac.log" 2>&1
python3 -c "import json;d=json.load(open('$WORK/xengine_loop_isaac.json'));print('  ok',d['ok'],d.get('n_dof'),'dof',d.get('error',''))"

echo "STEP 4/4 MJCF importer probe (expected to crash - run last on purpose)"
nice -n 10 $PY tools/sim2sim/mjcf_import_probe.py > "$WORK/mjcf_import_probe.log" 2>&1
echo "  probe exit=$?"
python3 -c "import json;d=json.load(open('$WORK/mjcf_import_probe.json'));print('  stage',d.get('stage'),'ok',d.get('ok'),d.get('error',''))"

echo DONE
