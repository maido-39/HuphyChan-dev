#!/usr/bin/env bash
# Container entrypoint: serve the built site immediately, then keep it fresh by
# polling the content mount and rebuilding when anything actually changed.
#
# WHY POLLING AND NOT --serve's WATCHER
# Quartz watches the content dir with chokidar (quartz/build.ts:159), i.e.
# inotify. docs/ is an NFS mount written to by this host and others; inotify on
# NFS does not fire for remote writes and is unreliable for local ones through
# the client cache. Quartz passes no `usePolling` option, and CHOKIDAR_USEPOLLING
# is a webpack/vite convention that chokidar itself ignores -- so there is no
# configuration that makes the built-in watcher work here. A fingerprint poll is
# the honest mechanism.
#
# WHY WE BUILD FROM A MIRROR (/app/merged), NOT THE MOUNT
# Two things have to be true of the built tree that cannot be true of docs/:
# the site must open on the briefing rather than the older catalog page, and one
# note's stray `---` must not fail the whole build. docs/ is read-only by design,
# and Docker cannot even mount a file at a new path underneath a read-only mount
# (runc refuses the container: `make mountpoint ...: read-only file system`).
# prepare_content.mjs builds a writable symlink mirror instead -- see that file.
#
# WHY DOUBLE-BUFFERED OUTPUT
# `quartz build` starts with rm(output, {recursive:true}) (build.ts:79). Building
# straight into the served directory would blank the site for the whole build.
# So we build into the idle buffer and flip a symlink, which is a single atomic
# rename: readers never see a partial site.

set -uo pipefail

CONTENT="${CONTENT_DIR:-/app/content}"     # read-only docs mount (source of truth)
MERGED="${MERGED_DIR:-/app/merged}"        # symlink farm Quartz actually builds from
LANDING="${LANDING_PAGE:-/app/landing/index.md}"
POLL="${REBUILD_POLL_SECONDS:-60}"
MIN_PAGES="${MIN_PAGES:-50}"

log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }

if [[ ! -d "$CONTENT" ]] || [[ -z "$(ls -A "$CONTENT" 2>/dev/null)" ]]; then
  log "FATAL: content mount '$CONTENT' is missing or empty."
  log "       Expected a read-only bind mount of the docs/ folder."
  exit 1
fi
[[ -f "$LANDING" ]] || log "WARNING: no landing page at '$LANDING'; site root will be a folder listing"

# ---------------------------------------------------------------------------
# Rebuild the symlink farm. Dot-entries (.trash, .obsidian, .briefing_state.json)
# are deliberately left out: globby skips dotfiles anyway, and .trash holds
# notes the author deleted in Obsidian -- publishing those would be wrong.
# ---------------------------------------------------------------------------
refresh_merged() {
  node /app/prepare_content.mjs 2>&1 | sed 's/^/  /'
  return "${PIPESTATUS[0]}"
}

# ---------------------------------------------------------------------------
# Change detection.
#
# Hashes (path, mtime, size) of every non-mp4 file. mp4s are excluded from the
# build entirely (quartz.config.yaml ignorePatterns) and served straight off the
# mount, so a new video needs no rebuild -- and stat-ing 189 large files over
# NFS every poll would be pure waste.
# ---------------------------------------------------------------------------
fingerprint() {
  find "$CONTENT" -type f ! -name '*.mp4' -printf '%p\t%T@\t%s\n' 2>/dev/null \
    | sort | md5sum | cut -d' ' -f1
}

# ---------------------------------------------------------------------------
# Build into the idle buffer, then flip.
# ---------------------------------------------------------------------------
build() {
  local current target t0 rc pages
  current="$(readlink /app/public || echo /app/out/a)"
  if [[ "$current" == "/app/out/a" ]]; then target=/app/out/b; else target=/app/out/a; fi

  t0=$(date +%s)
  if ! refresh_merged; then
    log "content preparation FAILED; keeping the previously served site at $current"
    return 1
  fi
  log "build -> $target"
  ( cd /app/quartz && npx quartz build -d "$MERGED" -o "$target" ) 2>&1 \
    | grep -vE 'unicodeTextInMathMode|found invalid date' | sed 's/^/  quartz| /'
  rc=${PIPESTATUS[0]}

  if [[ $rc -ne 0 ]]; then
    log "build FAILED (rc=$rc); keeping the previously served site at $current"
    return 1
  fi

  # A silently-empty build is the dangerous failure here: if globby ever stops
  # following the symlink farm, index.html alone would still be produced and a
  # naive check would happily flip to a one-page site. Demand a page count.
  pages=$(find "$target" -name '*.html' | wc -l)
  if [[ ! -f "$target/index.html" ]] || [[ "$pages" -lt "$MIN_PAGES" ]]; then
    log "build produced only $pages html pages (min $MIN_PAGES) or no index.html; refusing to flip"
    return 1
  fi

  # ln -sfn + mv -T == atomic replace of the symlink (rename(2)).
  ln -sfn "$target" /app/public.swap && mv -Tf /app/public.swap /app/public
  log "build OK in $(( $(date +%s) - t0 ))s; $pages pages; now serving $target"
  return 0
}

# ---------------------------------------------------------------------------
# Boot: server first (so the port is up and health checks have something to
# talk to), then the initial build, then the poll loop.
# ---------------------------------------------------------------------------
node /app/serve.mjs &
SERVER_PID=$!

shutdown() {
  log "signal received, stopping"
  kill "$SERVER_PID" 2>/dev/null
  exit 0
}
trap shutdown SIGTERM SIGINT

LAST=""
if build; then LAST="$(fingerprint)"; fi

log "watching $CONTENT every ${POLL}s for changes"
while true; do
  # `kill -0` rather than `wait`: we want the loop to keep polling while the
  # server runs, and to die loudly if the server dies.
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    log "FATAL: server process $SERVER_PID exited"
    exit 1
  fi

  sleep "$POLL" &
  wait $! 2>/dev/null

  NOW="$(fingerprint)"
  if [[ -n "$NOW" && "$NOW" != "$LAST" ]]; then
    log "content changed"
    if build; then LAST="$NOW"; fi
  fi
done
