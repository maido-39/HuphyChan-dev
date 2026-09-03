// Build the tree Quartz actually compiles from: /app/merged.
//
// It is a symlink mirror of the read-only docs mount, plus two edits that must
// not be made to docs/ itself.
//
// WHY A MIRROR AT ALL. docs/ is bind-mounted read-only on purpose, and Docker
// cannot mount a file at a path that does not already exist underneath it --
// runc fails the container outright with `make mountpoint ...: read-only file
// system`. Mounting over a path that DOES exist works, but then the real file
// is shadowed and silently unpublished. A writable mirror lets us add and fix
// files without either hazard, and without touching the research notes.
//
// 1. LANDING PAGE. docs/index.md already exists -- a hand-maintained "LLM Wiki
//    카탈로그" -- but it predates the live briefing and does not link to it.
//    The site is supposed to open on the briefing, so the mirror's index.md is
//    our landing page and the original catalog is republished, unmodified, as
//    wiki-catalog.md and linked from it. Nothing is lost; three notes link to
//    [[index]] and land on a page whose first link is the catalog.
//
// 2. FRONTMATTER-TRAP REPAIR. Quartz's frontmatter parser (note-properties)
//    accepts a `---` delimiter after leading blank lines. Obsidian does not --
//    it requires column 1, line 1 -- so a note that opens with a blank line and
//    then `---` renders as a horizontal rule in the vault but is swallowed as
//    YAML by Quartz. docs/docs/90_paper_material_map.md does exactly that, and
//    the YAML parser then dies on `- **ICRA 2026...` ("unidentified alias
//    *ICRA"), which fails the ENTIRE build, not just that page. The mirror gets
//    a repaired copy in which that one delimiter line becomes `***` -- a
//    thematic break that renders identically and means nothing to YAML.
//
// Everything else is a symlink: Quartz reads markdown with readFile and copies
// assets with fs.copyFile (plugins/emitters/assets.ts), both of which follow
// symlinks, and globby defaults to followSymbolicLinks:true.

import fs from "node:fs"
import fsp from "node:fs/promises"
import path from "node:path"

const CONTENT = process.env.CONTENT_DIR ?? "/app/content"
const MERGED = process.env.MERGED_DIR ?? "/app/merged"
const LANDING = process.env.LANDING_PAGE ?? "/app/landing/index.md"

const CATALOG_SLUG = "wiki-catalog.md" // where docs/index.md gets republished

const stats = { dirs: 0, links: 0, repaired: 0, skipped: 0 }
const repairedFiles = []

/**
 * Does this markdown file open with blank line(s) followed by a `---` that
 * Quartz will mistake for a frontmatter fence? Only the first 512 bytes are
 * read -- this runs over NFS for every file on every rebuild.
 */
async function frontmatterTrapLine(fp) {
  let fh
  try {
    fh = await fsp.open(fp, "r")
    const buf = Buffer.alloc(512)
    const { bytesRead } = await fh.read(buf, 0, 512, 0)
    const head = buf.subarray(0, bytesRead).toString("utf8")
    const lines = head.split("\n")
    if (lines.length === 0) return -1
    if (lines[0].trim() === "---") return -1 // legitimate frontmatter, leave alone
    for (let i = 0; i < Math.min(lines.length, 10); i++) {
      const t = lines[i].trim()
      if (t === "") continue
      return t === "---" ? i : -1 // first non-blank line: trap only if it is `---`
    }
    return -1
  } catch {
    return -1
  } finally {
    await fh?.close()
  }
}

async function repair(src, dest, lineIdx) {
  const text = await fsp.readFile(src, "utf8")
  const lines = text.split("\n")
  if (lines[lineIdx]?.trim() === "---") lines[lineIdx] = "***"
  await fsp.writeFile(dest, lines.join("\n"), "utf8")
  stats.repaired++
  repairedFiles.push(path.relative(CONTENT, src))
}

async function mirror(srcDir, destDir) {
  await fsp.mkdir(destDir, { recursive: true })
  stats.dirs++
  const entries = await fsp.readdir(srcDir, { withFileTypes: true })
  for (const e of entries) {
    // Dot entries are skipped outright. .trash holds notes the author deleted
    // in Obsidian -- publishing those would be wrong -- and globby ignores
    // dotfiles anyway, so mirroring them would only cost time.
    if (e.name.startsWith(".")) {
      stats.skipped++
      continue
    }
    const src = path.join(srcDir, e.name)
    const dest = path.join(destDir, e.name)
    if (e.isDirectory()) {
      await mirror(src, dest)
    } else if (e.isFile() || e.isSymbolicLink()) {
      if (e.name.toLowerCase().endsWith(".md")) {
        const trap = await frontmatterTrapLine(src)
        if (trap >= 0) {
          await repair(src, dest, trap)
          continue
        }
      }
      await fsp.symlink(src, dest)
      stats.links++
    }
  }
}

const t0 = Date.now()
await fsp.rm(MERGED, { recursive: true, force: true })
await mirror(CONTENT, MERGED)

if (fs.existsSync(LANDING)) {
  const mergedIndex = path.join(MERGED, "index.md")
  // docs/index.md is mirrored as a symlink into the read-only mount. Writing
  // through it would follow the link and fail with EROFS, so republish it under
  // its own slug first, then drop the link before writing our landing page.
  if (fs.existsSync(mergedIndex)) {
    const catalog = path.join(MERGED, CATALOG_SLUG)
    if (!fs.existsSync(catalog)) {
      await fsp.symlink(path.join(CONTENT, "index.md"), catalog)
      console.log(`prepare: republished docs/index.md as ${CATALOG_SLUG}`)
    }
    await fsp.rm(mergedIndex, { force: true })
  }
  await fsp.copyFile(LANDING, mergedIndex)
} else {
  console.warn(`prepare: no landing page at ${LANDING}; site root falls back to docs/index.md`)
}

console.log(
  `prepare: ${stats.links} links, ${stats.dirs} dirs, ${stats.repaired} repaired, ` +
    `${stats.skipped} dot-entries skipped in ${Date.now() - t0}ms`,
)
for (const f of repairedFiles) console.log(`prepare: repaired frontmatter trap in ${f}`)
