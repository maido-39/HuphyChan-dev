# `docs/` as a browsable website (Quartz)

Publishes the `docs/` folder — 425 notes, ~540 pages — as a searchable wiki on
the LAN, using [Quartz](https://quartz.jzhao.xyz/). Obsidian wikilinks,
transclusions, callouts, LaTeX and `.canvas` files all render.

**`docs/` is mounted read-only. The site can never modify a research note.**

| | |
|---|---|
| URL (LAN) | <http://192.168.20.177:8300/> |
| URL (local) | <http://127.0.0.1:8300/> |
| Container | `pygmalion-docs-quartz`, `--restart unless-stopped` (survives session end and reboot) |
| Landing page | the live briefing, transcluded |
| Freshness | edits to `docs/` appear within ~90 s (60 s poll + ~25 s build) |

## Use it

```bash
tools/quartz/run.sh              # build image + (re)start container. Idempotent.
tools/quartz/run.sh --status     # is it up, how many pages, when did it last build
tools/quartz/run.sh --logs       # follow the container log
tools/quartz/run.sh --stop       # stop and remove
PORT=8400 tools/quartz/run.sh    # run on a different port
```

Re-run `run.sh` after editing anything in this directory. Nothing here needs to
be re-run after editing `docs/` — that is picked up automatically.

## How it works

```
docs/  ──(bind mount, read-only)──▶  /app/content
                                        │
                        prepare_content.mjs builds a symlink mirror
                                        ▼
                                    /app/merged  ──▶  npx quartz build  ──▶  /app/out/{a,b}
                                                                                  │
                     serve.mjs  ◀── /app/public (symlink, flipped atomically) ─────┘
                         │
                         └── falls back to /app/content for anything the build skipped (the mp4s)
```

* **`Dockerfile`** — `node:22-slim` + Quartz pinned at commit `075afd3`. Quartz
  is cloned and `npm ci`-ed into the image; nothing from `docs/` is baked in.
* **`quartz.config.yaml`** — site config. Every deviation from Quartz's shipped
  default is marked `# CHANGED:` with the reason.
* **`prepare_content.mjs`** — builds the tree Quartz compiles from.
* **`entrypoint.sh`** — poll-and-rebuild loop plus the atomic output swap.
* **`serve.mjs`** — the HTTP server.
* **`overlay/index.md`** — the landing page.

### Five decisions worth knowing about

**1. The mp4s are never copied.** 189 video files are 3.3 GB of the 3.7 GB
`docs/` folder; everything else is 0.30 GB. They are excluded from the build
(`ignorePatterns`) and streamed straight off the read-only mount by `serve.mjs`,
with HTTP Range support so seeking works. Embeds still play. This is why a
rebuild takes ~25 s instead of many minutes, and why the site adds ~300 MB of
disk rather than 3.7 GB.

**2. Hot reload is a poll loop, not a file watcher.** `docs/` is on NFS
(`192.168.20.202:/volume5/ARIL-Mount-REMOTE`). Quartz watches content with
chokidar, i.e. inotify, which does not see writes made by other hosts and is
unreliable through the NFS client cache. Quartz passes no `usePolling` option,
and `CHOKIDAR_USEPOLLING` is a webpack/vite convention that chokidar itself
ignores — so no configuration fixes it. `entrypoint.sh` fingerprints
`(path, mtime, size)` of every non-mp4 file every 60 s and rebuilds on change.
Tune with `REBUILD_POLL_SECONDS`.

**3. Output is double-buffered.** `quartz build` begins by deleting its output
directory, so building into the live directory would blank the site for the
duration. Builds go to the idle buffer of `/app/out/{a,b}`; `/app/public` is a
symlink flipped with a single atomic rename. A failed build keeps serving the
last good site, and a build that yields fewer than `MIN_PAGES` (50) pages is
rejected rather than published.

**4. The landing page comes from the mirror, not from `docs/`.** `docs/index.md`
already exists — the hand-maintained "LLM Wiki 카탈로그" — but it predates the
live briefing and does not link to it. The site is supposed to open on the
briefing, so `overlay/index.md` becomes the site root and the original catalog is
republished unmodified at **`/wiki-catalog`**, linked from the landing page.

Note for anyone tempted to skip the mirror: Docker *cannot* mount a file at a new
path underneath a read-only mount — runc refuses to start the container with
`make mountpoint ...: read-only file system`. Mounting *over* an existing file
does work, but then the real file is silently unpublished.

**5. One note is repaired in the mirror.** `docs/docs/90_paper_material_map.md`
opens with a blank line and then `---`. Obsidian requires a frontmatter fence at
line 1 column 1 and renders this as a horizontal rule; Quartz's parser is more
permissive, reads the rest of the note as YAML, and dies on `- **ICRA 2026...`
(`unidentified alias "*ICRA"`) — which fails the **entire** build, not just that
page. The mirror gets a copy with that one line changed to `***`, an identically
rendering thematic break that means nothing to YAML. `docs/` is untouched.

## Editing the site

* **Content** — edit `docs/` as usual; the site follows within ~90 s.
* **Landing page** — edit `overlay/index.md`, then `run.sh --no-build` (it is
  bind-mounted, so no image rebuild is needed).
* **Theme, plugins, ignore rules** — edit `quartz.config.yaml`, then `run.sh`.
* **Upgrading Quartz** — bump `QUARTZ_REF` in the `Dockerfile` and rebuild. It is
  pinned deliberately: Quartz v5's plugins are all at `0.x` and upstream `main`
  moves fast.

## Known limits

* **Page titles are filenames.** Almost no note has frontmatter, so Quartz falls
  back to the filename — the same thing Obsidian does. The note's own `#`
  heading still renders as the first line of the body.
* **~5% of internal links 404**, and they 404 in Obsidian too: they point at
  files outside `docs/` (the agent memory notes, e.g. `pyg-no-dr-gating`) or at
  notes that were never written. Measured over 822 links on a 60-page sample;
  media embeds were 254 checked / 4 broken, all four referencing files absent
  from `docs/`.
* **`.trash/` is not published.** Four notes deleted in Obsidian stay deleted.
* **`baseUrl` is hardcoded** to `192.168.20.177:8300` in `quartz.config.yaml`.
  It only affects absolute URLs in the RSS feed and sitemap; if this host's IP
  changes, page-to-page navigation still works.
* **No authentication.** Anyone on the LAN can read every note. There is no
  write path — the mount is read-only — but treat it as public-to-the-office.
