#!/usr/bin/env bash
# Build the image and (re)start the docs site container. Idempotent: run it
# again after editing quartz.config.yaml / serve.mjs / the landing page and it
# rebuilds the image and swaps the container in place.
#
#   ./run.sh              build + (re)start
#   ./run.sh --no-build   restart the container using the existing image
#   ./run.sh --stop       stop and remove the container
#   ./run.sh --logs       follow the container log
#   ./run.sh --status     one-line health summary
#
# Env overrides:  PORT (default 8300), DOCS_DIR, IMAGE, CONTAINER,
#                 REBUILD_POLL_SECONDS (default 60)

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

PORT="${PORT:-8300}"
DOCS_DIR="${DOCS_DIR:-$REPO_ROOT/docs}"
IMAGE="${IMAGE:-pygmalion-docs-quartz:latest}"
CONTAINER="${CONTAINER:-pygmalion-docs-quartz}"
POLL="${REBUILD_POLL_SECONDS:-60}"
OVERLAY_INDEX="$HERE/overlay/index.md"

die() { echo "ERROR: $*" >&2; exit 1; }

lan_ip() {
  ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}' \
    || hostname -I | awk '{print $1}'
}

case "${1:-}" in
  --stop)
    docker rm -f "$CONTAINER" >/dev/null 2>&1 && echo "stopped and removed $CONTAINER" \
      || echo "$CONTAINER was not running"
    exit 0
    ;;
  --logs)
    exec docker logs -f --tail 100 "$CONTAINER"
    ;;
  --status)
    if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
      echo "$CONTAINER: NOT RUNNING"; exit 1
    fi
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$PORT/" || echo 000)
    pages=$(docker exec "$CONTAINER" sh -c 'find "$(readlink /app/public)" -name "*.html" | wc -l' 2>/dev/null || echo '?')
    last=$(docker logs --tail 300 "$CONTAINER" 2>&1 | grep 'build OK' | tail -1 || echo 'no successful build logged')
    echo "$CONTAINER: RUNNING  http://$(lan_ip):$PORT/ -> HTTP $code  pages=$pages"
    echo "  last build: $last"
    exit 0
    ;;
esac

[[ -d "$DOCS_DIR" ]] || die "docs directory not found: $DOCS_DIR"
[[ -f "$OVERLAY_INDEX" ]] || die "landing page not found: $OVERLAY_INDEX"
command -v docker >/dev/null || die "docker not found on PATH"
docker info >/dev/null 2>&1 || die "cannot talk to the docker daemon (is the user in the 'docker' group?)"

# Refuse to squat on a port something else already owns. Our own container is
# fine -- it is about to be replaced.
if ss -ltn "sport = :$PORT" 2>/dev/null | grep -q LISTEN; then
  owner="$(docker ps --format '{{.Names}} {{.Ports}}' | grep ":$PORT->" | awk '{print $1}' || true)"
  [[ "$owner" == "$CONTAINER" ]] \
    || die "port $PORT is already in use by '${owner:-a non-docker process}'. Set PORT=<other> and retry."
fi

if [[ "${1:-}" != "--no-build" ]]; then
  echo "==> building $IMAGE"
  nice -n 10 docker build -t "$IMAGE" "$HERE"
fi

echo "==> (re)starting $CONTAINER on port $PORT"
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true

# --memory / --cpus: a GPU training run usually owns this box. The site build is
# pure CPU+RAM, and these caps keep it from competing for the whole machine.
# docs/ is mounted read-only -- the container can never modify the research notes.
# The landing page goes to /app/landing (a normal directory in the image), NOT
# into /app/content: Docker cannot create a mountpoint at a new path underneath a
# read-only mount, and mounting over docs/index.md would silently unpublish the
# real catalog page. prepare_content.mjs merges it into the build tree instead.
docker run -d \
  --name "$CONTAINER" \
  --restart unless-stopped \
  --memory=4g --memory-swap=4g --cpus=3 \
  -e "REBUILD_POLL_SECONDS=$POLL" \
  -v "$DOCS_DIR:/app/content:ro" \
  -v "$OVERLAY_INDEX:/app/landing/index.md:ro" \
  -p "0.0.0.0:$PORT:8080" \
  "$IMAGE" >/dev/null

echo "==> waiting for the first site build (takes a couple of minutes over NFS)"
for _ in $(seq 1 120); do
  if curl -sf -o /dev/null --max-time 3 "http://127.0.0.1:$PORT/"; then
    echo
    echo "  LAN     http://$(lan_ip):$PORT/"
    echo "  local   http://127.0.0.1:$PORT/"
    echo "  logs    $HERE/run.sh --logs"
    echo "  status  $HERE/run.sh --status"
    exit 0
  fi
  sleep 5
done

echo "site did not answer within 10 minutes; last log lines:" >&2
docker logs --tail 40 "$CONTAINER" >&2
exit 1
