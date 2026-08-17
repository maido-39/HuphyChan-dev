#!/usr/bin/env bash
# Unattended campaign driver, hardened after five different stalls (2026-08-16).
#
# ROOT CAUSES OBSERVED, AND WHAT STOPS EACH ONE HERE:
#  1. broad `pkill -f run_link_env / autorun` killed the driver itself
#     -> supervise.sh runs it under setsid (PPID 1); nothing in a shell session
#        can take it down, and cleanup uses PID-targeted kills only.
#  2. one link failing forever = infinite loop, no other work ever ran
#     -> per-link attempt budget (MAX_TRY); after that the link is SKIPPED and
#        the campaign moves on, and stages 2/3 still run on whatever solved.
#  3. a hung solve held the single global ccx lock, so every other link waited
#     -> hang detector: if the job's .sta/.frd stops growing for STALL_MIN
#        minutes the solver PID is killed and the link is retried coarser.
#  4. stale `flock` waiters from killed runs grabbed the lock later and ran
#     dead jobs -> waiters older than 3 h are cleared at the start of a pass.
#  5. disk filled with .frd (30-50 MB each) -> old unit-case results of solved
#     links are pruned when free space drops below MIN_FREE_GB.
#  6. OOM on a too-large mesh -> node budget check; over MAX_NODES the link is
#     coarsened before solving instead of dying in the solver.
# A heartbeat file lets the supervisor detect a driver that is alive but stuck.
set -u
cd /home/syaro/MikuchanRemote/Human-Pygmalion
PY=mujoco-sim/mjlab/.venv/bin/python3
W=/home/syaro/pyg_fea/work
SPEC=tools/fea/link_specs.json
STATE=$W/state.json
HB=$W/heartbeat
MAX_TRY=3
STALL_MIN=25
MIN_FREE_GB=25
MAX_NODES=260000          # 15 GB box: 161k-287k solved fine, 392k died in the solver
export PYG_MAX_NODES=260000
export PYG_CCX_THREADS=4  # fewer threads = less peak memory per solve
mkdir -p "$W"
# single-instance guard by PID file: a plain flock fd is inherited by every
# child, so an orphaned `sleep` kept the lock held after the parent died and no
# restart could ever take over (2026-08-16).
PIDF=$W/autorun.pid
if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF" 2>/dev/null)" 2>/dev/null \
   && tr '\0' ' ' < /proc/"$(cat "$PIDF")"/cmdline 2>/dev/null | grep -q autorun.sh; then
  echo "autorun already running (pid $(cat "$PIDF"))"; exit 0
fi
echo $$ > "$PIDF"

log() { echo "[$(date +%m-%d\ %H:%M:%S)] $*"; date +%s > "$HB"; }

links() { $PY -c "
import json;d=json.load(open('$SPEC'))
print(' '.join(k for k,v in d.items() if isinstance(v,dict) and 'envelope' in v))"; }

tries() { $PY -c "
import json,os
s=json.load(open('$STATE')) if os.path.exists('$STATE') else {}
print(s.get('$1',{}).get('tries',0))"; }

setstate() { $PY -c "
import json,os
s=json.load(open('$STATE')) if os.path.exists('$STATE') else {}
e=s.setdefault('$1',{}); e['tries']=e.get('tries',0)+$2; e['status']='$3'
e['when']='$(date +%H:%M:%S)'
json.dump(s,open('$STATE','w'),indent=1)"; }

coarsen() { $PY - "$1" <<'EOF'
import json,sys
L=sys.argv[1]; p='tools/fea/link_specs.json'
d=json.load(open(p)); m=d[L]['mesh']
m['size_far']=round(m['size_far']*1.35,2)
m['refine']=[[x,y,z,r,round(s*1.3,2)] for (x,y,z,r,s) in m.get('refine',[])]
json.dump(d,open(p,'w'),indent=1)
print(f'size_far -> {m["size_far"]}')
EOF
}

housekeeping() {
  # stale lock waiters (killed runs leave flock processes behind)
  for pid in $(ps -eo pid,etimes,args | awk '/flock \/tmp\/pyg_ccx/ && !/awk/ && $2>10800 {print $1}'); do
    kill "$pid" 2>/dev/null && log "housekeeping: cleared stale lock waiter $pid"
  done
  # disk: prune unit-case results of links that already produced an envelope
  free=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
  if [ "${free:-999}" -lt "$MIN_FREE_GB" ]; then
    for L in $(links); do
      [ -f "$W/$L/envelope_P99.json" ] && rm -f "$W/$L"/*_u*.frd 2>/dev/null
    done
    log "housekeeping: pruned solved unit results (free was ${free}G)"
  fi
}

hang_guard() {   # $1 = link, $2 = pid of the run
  local L="$1" pid="$2" last=0 same=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep 300
    local cur
    cur=$(du -sb "$W/$L" 2>/dev/null | cut -f1)
    if [ "${cur:-0}" -le "${last:-0}" ]; then
      same=$((same+5))
      if [ "$same" -ge "$STALL_MIN" ]; then
        log "hang detected on $L (no output for ${same} min) - killing solver"
        for p in $(ps -eo pid,args | awk -v l="$L" '/ccx -i/ && $0 ~ l && !/awk/ {print $1}'); do
          kill -9 "$p" 2>/dev/null
        done
        kill "$pid" 2>/dev/null
        return
      fi
    else
      same=0
    fi
    last=$cur
  done
}

uptodate() {   # $1 = link : result exists AND was produced from this link's
               # current spec section (a hash, so editing another link's entry
               # no longer invalidates everything - that re-ran a finished L1)
  $PY - "$1" <<'EOF'
import json,hashlib,os,re,sys
L=sys.argv[1]
res=f'/home/syaro/pyg_fea/work/{L}/envelope_P99.json'
if not os.path.exists(res): print('no'); raise SystemExit
spec=json.load(open('tools/fea/link_specs.json'))[L]
h=hashlib.sha1(json.dumps(spec,sort_keys=True).encode()).hexdigest()[:12]
rev=re.search(r"ANALYSIS_REV = '([^']+)'",open('tools/fea/run_link_env.py').read()).group(1)
d=json.load(open(res))
print('yes' if d.get('spec_hash')==h and d.get('analysis_rev')==rev else 'no')
EOF
}

pass=0
while true; do
  pass=$((pass+1))
  housekeeping
  todo=0
  for L in $(links); do
    RES="$W/$L/envelope_P99.json"
    [ "$(uptodate "$L")" = "yes" ] && continue
    t=$(tries "$L")
    if [ "${t:-0}" -ge "$MAX_TRY" ]; then continue; fi
    todo=$((todo+1))
    log "STAGE1 $L (pass $pass, try $((t+1))/$MAX_TRY)"
    rm -f "$W/$L"/*_u*.frd "$W/$L"/*_u*.inp 2>/dev/null
    timeout 10800 $PY tools/fea/run_link_env.py "$L" >> "$W/${L}_run.log" 2>&1 &
    runpid=$!
    hang_guard "$L" "$runpid" &
    guard=$!
    wait "$runpid"; rc=$?
    kill "$guard" 2>/dev/null
    if [ "$(uptodate "$L")" = "yes" ]; then
      setstate "$L" 1 done
      log "STAGE1 $L DONE $($PY -c "
import json;d=json.load(open('$RES'))
o=d.get('over_allowable',{}).get('SF>2.0',{})
print('raw %.1f MPa SF %.2f | design %.1f SF %.2f | over SF>2: %s nodes'%(
 d['max_vM'],d['SF'],d.get('max_vM_design',d['max_vM']),
 d.get('SF_design',d['SF']),o.get('nodes_design','?')))" 2>/dev/null)"
      $PY tools/fea/merge_setup.py >> "$W/merge.log" 2>&1
    elif [ "$rc" -eq 0 ] && [ -f "$RES" ]; then
      # solved fine, but the spec changed while it was running -> not a failure,
      # and it must not eat a retry: just redo it against the current spec
      setstate "$L" 0 superseded
      log "STAGE1 $L SUPERSEDED (spec edited mid-run) - will redo with the current spec"
    else
      setstate "$L" 1 "failed(rc=$rc)"
      log "STAGE1 $L FAILED rc=$rc: $(tail -3 "$W/${L}_run.log" | tr -d '\r' | tail -1 | cut -c1-110)"
      # only a mesh/solver failure justifies coarsening; a setup/selector error
      # would just get a worse mesh for no reason
      if tail -20 "$W/${L}_run.log" | grep -qE "jacobian|mesh attempt|solve ok=False|MemoryError|Killed|cannot be tied"; then
        [ "$((t+1))" -lt "$MAX_TRY" ] && coarsen "$L" | while read -r l; do log "   $l"; done
        rm -f "$W/$L/${L}_mesh.inp"
      else
        log "   (setup-level error - mesh left unchanged)"
      fi
    fi
  done

  # STAGE1P: the `peak` tier. docs/62 defines three tiers (RMS / in-DR P99 / peak) and
  # the campaign only ever solved P99 - the red team caught it. Runs once per link after
  # its P99 result is current, so the driver carries this work instead of a human.
  for L in $(links); do
    [ "$(uptodate "$L")" = "yes" ] || continue
    PK="$W/$L/envelope_peak.json"
    [ -f "$PK" ] && [ "$PK" -nt "$W/$L/envelope_P99.json" ] && continue
    log "STAGE1P $L (peak tier)"
    timeout 10800 $PY tools/fea/run_link_env.py "$L" --peak >> "$W/${L}_peak.log" 2>&1 \
      && log "STAGE1P $L DONE $($PY -c "
import json;d=json.load(open('$PK'))
print('raw %.1f SF %.2f | design %.1f SF %.2f'%(d['max_vM'],d['SF'],
 d.get('max_vM_design',d['max_vM']),d.get('SF_design',d['SF'])))" 2>/dev/null)" \
      || log "STAGE1P $L FAILED"
  done

  # stages 2 and 3 run on whatever solved - never gated on a failing link
  $PY tools/fea/verdicts.py > "$W/verdicts.md" 2>>"$W/verdicts.log" && log "STAGE2 verdict table refreshed"
  for L in $(links); do
    [ -f "$W/$L/envelope_P99.json" ] || continue
    OUT="$W/$L/lightweight.json"
    [ -f "$OUT" ] && [ "$OUT" -nt "$W/$L/envelope_P99.json" ] && continue   # opt is keyed on the result file
    log "STAGE3 $L lightweighting"
    timeout 5400 $PY tools/fea/lightweight.py "$L" >> "$W/${L}_opt.log" 2>&1 \
      && log "STAGE3 $L DONE $($PY -c "
import json;d=json.load(open('$OUT'))
print(' '.join('%s:%s%%'%(k,v['removable_pct']) for k,v in d['levels'].items()))" 2>/dev/null)" \
      || log "STAGE3 $L FAILED"
  done

  if [ "$todo" -eq 0 ]; then
    log "idle - all links either solved or at the attempt cap; sleeping 10 min"
    sleep 600
  else
    sleep 20
  fi
done
