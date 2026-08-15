#!/usr/bin/env bash
# Unattended campaign driver (2026-08-16, user asleep):
#   stage 1  envelope analysis of every link that has an 'envelope' spec
#   stage 2  SF>1 / >1.5 / >2 verdict table
#   stage 3  stress-driven lightweighting study per link, re-verified
# Restarts itself on any single-link failure and coarsens that link's mesh so
# the campaign keeps moving instead of stalling on one model.
#
# Run:  nohup tools/fea/autorun.sh > ~/pyg_fea/work/autorun.log 2>&1 &
set -u
cd /home/syaro/MikuchanRemote/Human-Pygmalion
PY=mujoco-sim/mjlab/.venv/bin/python3
W=/home/syaro/pyg_fea/work
SPEC=tools/fea/link_specs.json
mkdir -p "$W"
exec 9>/tmp/pyg_autorun.lock
flock -n 9 || { echo "autorun already running"; exit 0; }

log() { echo "[$(date +%m-%d\ %H:%M:%S)] $*"; }

links() { $PY - <<'EOF'
import json
d=json.load(open('tools/fea/link_specs.json'))
print(' '.join(k for k,v in d.items() if isinstance(v,dict) and 'envelope' in v))
EOF
}

coarsen() {  # $1 = link ; grow the far mesh size by 30 % so the next try is lighter
  $PY - "$1" <<'EOF'
import json,sys
L=sys.argv[1]; p='tools/fea/link_specs.json'
d=json.load(open(p)); m=d[L]['mesh']
m['size_far']=round(m['size_far']*1.3,2)
m['refine']=[[x,y,z,r,round(s*1.25,2)] for (x,y,z,r,s) in m.get('refine',[])]
json.dump(d,open(p,'w'),indent=1)
print(f'coarsened {L} -> size_far {m["size_far"]}')
EOF
}

pass=0
while true; do
  pass=$((pass+1))
  todo=0
  for L in $(links); do
    RES="$W/$L/envelope_P99.json"
    if [ -f "$RES" ] && [ "$RES" -nt "$SPEC" ]; then continue; fi
    todo=$((todo+1))
    log "STAGE1 $L (pass $pass) - solving"
    rm -f "$W/$L"/*_u*.frd "$W/$L"/*_u*.inp 2>/dev/null
    if timeout 14400 $PY tools/fea/run_link_env.py "$L" >> "$W/${L}_run.log" 2>&1; then
      log "STAGE1 $L DONE $($PY -c "
import json;d=json.load(open('$RES'))
print('max %.1f MPa  SF %.2f  filtered %.1f (SF %.2f)'%(d['max_vM'],d['SF'],d.get('max_vM_filtered',float('nan')),d.get('SF_filtered',float('nan'))))" 2>/dev/null)"
      $PY tools/fea/merge_setup.py >> "$W/merge.log" 2>&1
    else
      log "STAGE1 $L FAILED - coarsening and retrying next pass"
      coarsen "$L" | while read -r l; do log "   $l"; done
      rm -f "$W/$L/${L}_mesh.inp"
    fi
  done

  if [ "$todo" -eq 0 ]; then
    log "STAGE1 complete for all links"
    if $PY tools/fea/verdicts.py >> "$W/verdicts.log" 2>&1; then
      log "STAGE2 verdict table written"
    else
      log "STAGE2 verdict table FAILED (see verdicts.log)"
    fi
    if [ -f tools/fea/lightweight.py ]; then
      for L in $(links); do
        OUT="$W/$L/lightweight.json"
        if [ -f "$OUT" ] && [ "$OUT" -nt "$SPEC" ]; then continue; fi
        log "STAGE3 $L - lightweighting study"
        timeout 10800 $PY tools/fea/lightweight.py "$L" >> "$W/${L}_opt.log" 2>&1 \
          && log "STAGE3 $L DONE" || log "STAGE3 $L FAILED"
      done
    fi
    log "all stages idle - sleeping 10 min"
    sleep 600
  else
    sleep 30
  fi
done
