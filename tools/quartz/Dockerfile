# Quartz static-site generator for the Human-Pygmalion docs/ folder.
#
# The image carries a fully-installed Quartz. Nothing from docs/ is baked in --
# docs/ arrives at runtime as a read-only bind mount at /app/content, so the
# image never has write access to the research notes.
#
# Build:  docker build -t pygmalion-docs-quartz /path/to/tools/quartz
# (or just use run.sh, which does build + run idempotently)

FROM node:22-slim

# Upstream requires node >=22 and npm >=10.9.2 (package.json "engines").
# node:22-slim ships both. git is needed to clone Quartz itself; the
# @quartz-community/* plugins come from the npm registry.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app/quartz

# Pinned so a rebuild six months from now produces the same site. Quartz has no
# release tags on main; this is the commit verified against these docs.
# Override with --build-arg QUARTZ_REF=<sha> to move forward deliberately.
ARG QUARTZ_REPO=https://github.com/jackyzha0/quartz.git
ARG QUARTZ_REF=075afd3f712da0088a07f5284a7b3aba37dd61b6
RUN git init -q . \
 && git remote add origin "${QUARTZ_REPO}" \
 && git fetch -q --depth 1 origin "${QUARTZ_REF}" \
 && git checkout -q FETCH_HEAD \
 && git log -1 --format='quartz %H %ci'

RUN npm ci --no-audit --no-fund

# The config must land before install-plugins: that script reads
# quartz.config.yaml to decide which @quartz-community/* packages to pull in.
# Note `npm ci` does NOT trigger it -- "prebuild" only fires for `npm run build`,
# and we invoke the CLI directly as `npx quartz build`.
COPY quartz.config.yaml /app/quartz/quartz.config.yaml
RUN npm run install-plugins

COPY serve.mjs /app/serve.mjs
COPY prepare_content.mjs /app/prepare_content.mjs
COPY entrypoint.sh /app/entrypoint.sh
# Baked in so the image is self-contained; run.sh bind-mounts over it so the
# landing page can be edited without an image rebuild. /app/landing is a normal
# writable directory, so unlike a mount into the read-only NFS content dir this
# one is visible to readdir -- though entrypoint.sh copies it by explicit path
# anyway.
COPY overlay/index.md /app/landing/index.md
RUN chmod +x /app/entrypoint.sh \
 && mkdir -p /app/content /app/merged /app/out/a /app/out/b \
 && ln -sfn /app/out/a /app/public

ENV PORT=8080 \
    HOST=0.0.0.0 \
    PUBLIC_DIR=/app/public \
    RAW_DIR=/app/content \
    CONTENT_DIR=/app/content \
    MERGED_DIR=/app/merged \
    LANDING_PAGE=/app/landing/index.md \
    REBUILD_POLL_SECONDS=60 \
    NODE_OPTIONS=--max-old-space-size=2048

EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=10s --start-period=180s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||8080)+'/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

ENTRYPOINT ["/app/entrypoint.sh"]
