// Static file server for the Quartz-rendered Human-Pygmalion docs.
//
// Why not `npx quartz build --serve`? Two reasons specific to this deployment:
//
//  1. HOT RELOAD IS DEAD ON NFS. Quartz's serve mode watches the content dir
//     with chokidar (build.ts:159), which uses inotify. docs/ lives on an NFS
//     mount (192.168.20.202:/volume5/ARIL-Mount-REMOTE) and inotify does not
//     see writes made by other hosts. Quartz passes no `usePolling` option and
//     does not read CHOKIDAR_USEPOLLING (that is a webpack/vite convention, not
//     a chokidar one), so there is no env knob to fix it. entrypoint.sh does a
//     poll-and-rebuild loop instead, and this server just serves the output.
//
//  2. NO 3.3 GB COPY. 189 mp4 files make up 3.3 GB of the 3.7 GB docs folder.
//     They are excluded from the Quartz build (quartz.config.yaml
//     ignorePatterns) and served here straight from the read-only source mount,
//     with HTTP Range support so the browser can seek. Quartz's own server is
//     serve-handler with `symlinks` left at its default of false, so neither
//     symlinking nor copying was an option there.
//
// Resolution order for a request path P:
//     public/P  ->  public/P.html  ->  public/P/index.html
//                -> content/P  (raw, read-only: the ignored mp4s)
//                -> basename lookup in the content filename index
//                -> public/404.html
//
// The basename lookup is the safety net for Obsidian-style bare embeds
// (`![[foo.mp4]]` with no folder) that Quartz's link resolver placed at the
// wrong directory depth.

import http from "node:http"
import fs from "node:fs"
import fsp from "node:fs/promises"
import path from "node:path"

const PORT = parseInt(process.env.PORT ?? "8080", 10)
const HOST = process.env.HOST ?? "0.0.0.0"
const PUBLIC_DIR = process.env.PUBLIC_DIR ?? "/app/public"
const RAW_DIR = process.env.RAW_DIR ?? "/app/content"
const INDEX_TTL_MS = 5 * 60 * 1000

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".htm": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".canvas": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".xml": "application/xml; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".md": "text/plain; charset=utf-8",
  ".csv": "text/csv; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".avif": "image/avif",
  ".ico": "image/x-icon",
  ".mp4": "video/mp4",
  ".webm": "video/webm",
  ".pdf": "application/pdf",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".otf": "font/otf",
  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ".npz": "application/octet-stream",
  ".kdenlive": "application/xml; charset=utf-8",
}

const mimeFor = (fp) => MIME[path.extname(fp).toLowerCase()] ?? "application/octet-stream"

// Korean filenames can be stored NFD on the NFS server while browsers send NFC
// (or the reverse). Normalise both sides of every comparison.
const nfc = (s) => s.normalize("NFC")

/**
 * Reproduce Quartz's asset slug so the fallback index can be looked up by the
 * URL the rendered page actually asks for.
 *
 * Quartz slugifies the *stem* and re-appends the extension verbatim
 * (@quartz-community/utils path.js: slugifyFilePath -> _sluggify). So the file
 * `20260811 022118 Huphy 1.0 - ... (slowed 4x).mp4` is embedded as
 * `20260811-022118-huphy-1.0---...-(slowed-4x).mp4`. 24 of the 189 mp4s have
 * spaces in their names, and one of those is embedded in a note, so a plain
 * case-insensitive basename match is not enough.
 */
function quartzSlugBasename(name) {
  const ext = path.extname(name)
  const stem = ext ? name.slice(0, name.length - ext.length) : name
  const slug = stem
    .replace(/\s/g, "-")
    .replace(/&/g, "-and-")
    .replace(/%/g, "-percent")
    .replace(/\?/g, "")
    .replace(/#/g, "")
    .replace(/[<>:"|*]/g, "")
    .toLowerCase()
  return slug + ext.toLowerCase()
}

// ---------------------------------------------------------------- name index
/** @type {Map<string, string>} basename key (NFC, lowercased/slugified) -> absolute path */
let nameIndex = new Map()
let nameIndexBuiltAt = 0
let nameIndexBuilding = null

async function buildNameIndex() {
  const map = new Map()
  const walk = async (dir) => {
    let entries
    try {
      entries = await fsp.readdir(dir, { withFileTypes: true })
    } catch {
      return
    }
    for (const e of entries) {
      const full = path.join(dir, e.name)
      if (e.isDirectory()) {
        await walk(full)
      } else if (e.isFile()) {
        const name = nfc(e.name)
        // Two keys per file: the plain lowercased name, and the name as Quartz
        // would have slugified it into the page's src attribute.
        // First writer wins, so the shallowest match is kept (walk is
        // breadth-ish by directory order; ties are arbitrary but stable).
        for (const key of new Set([name.toLowerCase(), quartzSlugBasename(name)])) {
          if (!map.has(key)) map.set(key, full)
        }
      }
    }
  }
  await walk(RAW_DIR)
  nameIndex = map
  nameIndexBuiltAt = Date.now()
  console.log(`[index] ${map.size} filenames indexed from ${RAW_DIR}`)
}

async function ensureNameIndex() {
  if (Date.now() - nameIndexBuiltAt < INDEX_TTL_MS) return
  if (nameIndexBuilding) return nameIndexBuilding
  nameIndexBuilding = buildNameIndex().finally(() => {
    nameIndexBuilding = null
  })
  return nameIndexBuilding
}

// ---------------------------------------------------------------- resolution
async function statFile(fp) {
  try {
    const st = await fsp.stat(fp)
    return st.isFile() ? st : null
  } catch {
    return null
  }
}

/** Reject anything that escapes `root` after normalisation. */
function safeJoin(root, rel) {
  const full = path.normalize(path.join(root, rel))
  const rootWithSep = root.endsWith(path.sep) ? root : root + path.sep
  return full === root || full.startsWith(rootWithSep) ? full : null
}

async function resolve(urlPath) {
  const rel = decodeURIComponent(urlPath).replace(/^\/+/, "")
  const relNfc = nfc(rel)

  const inPublic = safeJoin(PUBLIC_DIR, relNfc)
  if (inPublic) {
    const candidates =
      relNfc === "" || relNfc.endsWith("/")
        ? [path.join(inPublic, "index.html")]
        : [inPublic, inPublic + ".html", path.join(inPublic, "index.html")]
    for (const c of candidates) {
      const st = await statFile(c)
      if (st) return { file: c, st }
    }
  }

  // Ignored-by-Quartz files (the mp4s) come straight off the read-only mount.
  const inRaw = safeJoin(RAW_DIR, relNfc)
  if (inRaw) {
    const st = await statFile(inRaw)
    if (st) return { file: inRaw, st }
  }

  // Last resort: Obsidian bare-embed rescue by filename.
  const base = path.basename(relNfc).toLowerCase()
  if (base && path.extname(base)) {
    await ensureNameIndex()
    const hit = nameIndex.get(base)
    if (hit) {
      const st = await statFile(hit)
      if (st) return { file: hit, st, viaIndex: true }
    }
  }

  return null
}

// ------------------------------------------------------------------- serving
function sendRange(req, res, file, st, type) {
  const range = req.headers.range
  if (!range) return false
  const m = /^bytes=(\d*)-(\d*)$/.exec(range.trim())
  if (!m) return false

  const size = st.size
  let start = m[1] === "" ? null : parseInt(m[1], 10)
  let end = m[2] === "" ? null : parseInt(m[2], 10)

  if (start === null && end === null) return false
  if (start === null) {
    // suffix range: last N bytes
    start = Math.max(0, size - end)
    end = size - 1
  } else if (end === null || end >= size) {
    end = size - 1
  }
  if (Number.isNaN(start) || Number.isNaN(end) || start > end || start >= size) {
    res.writeHead(416, { "Content-Range": `bytes */${size}` })
    res.end()
    return true
  }

  res.writeHead(206, {
    "Content-Type": type,
    "Content-Length": end - start + 1,
    "Content-Range": `bytes ${start}-${end}/${size}`,
    "Accept-Ranges": "bytes",
    "Cache-Control": "no-cache",
  })
  if (req.method === "HEAD") return res.end(), true
  fs.createReadStream(file, { start, end }).pipe(res)
  return true
}

const server = http.createServer(async (req, res) => {
  const started = Date.now()
  let status = 200
  try {
    if (req.method !== "GET" && req.method !== "HEAD") {
      status = 405
      res.writeHead(405, { Allow: "GET, HEAD" })
      return res.end()
    }

    const urlPath = (req.url ?? "/").split("?")[0].split("#")[0]
    const hit = await resolve(urlPath)

    if (!hit) {
      // Extensionless miss -> maybe the caller wants the folder page.
      status = 404
      const notFound = path.join(PUBLIC_DIR, "404.html")
      const st404 = await statFile(notFound)
      if (st404) {
        res.writeHead(404, { "Content-Type": "text/html; charset=utf-8" })
        return req.method === "HEAD" ? res.end() : fs.createReadStream(notFound).pipe(res)
      }
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" })
      return res.end("404 Not Found\n")
    }

    const type = mimeFor(hit.file)
    // HTML is rebuilt in place by the poll loop -> never let a proxy or the
    // browser pin a stale page. Media is immutable enough to cache briefly.
    const cache = type.startsWith("text/html") ? "no-cache" : "public, max-age=300"

    if (sendRange(req, res, hit.file, hit.st, type)) {
      status = 206
      return
    }

    res.writeHead(200, {
      "Content-Type": type,
      "Content-Length": hit.st.size,
      "Accept-Ranges": "bytes",
      "Cache-Control": cache,
      "Content-Disposition": "inline",
      "Last-Modified": hit.st.mtime.toUTCString(),
    })
    if (req.method === "HEAD") return res.end()
    fs.createReadStream(hit.file).pipe(res)
  } catch (err) {
    status = 500
    console.error(`[500] ${req.url}: ${err?.message ?? err}`)
    if (!res.headersSent) res.writeHead(500, { "Content-Type": "text/plain" })
    res.end("500 Internal Server Error\n")
  } finally {
    res.on("finish", () => {
      if (status >= 400) console.log(`[${status}] ${req.url} (${Date.now() - started}ms)`)
    })
  }
})

server.listen(PORT, HOST, () => {
  console.log(`[serve] http://${HOST}:${PORT}  public=${PUBLIC_DIR}  raw=${RAW_DIR}`)
  ensureNameIndex().catch((e) => console.error("[index] failed:", e))
})

for (const sig of ["SIGTERM", "SIGINT"]) {
  process.on(sig, () => {
    console.log(`[serve] ${sig}, shutting down`)
    server.close(() => process.exit(0))
    setTimeout(() => process.exit(0), 3000).unref()
  })
}
