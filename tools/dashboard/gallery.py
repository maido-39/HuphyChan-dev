"""Build a thumbnail gallery of every figure in docs/img and docs/mujoco/assets.

The figures live in two directories and are only reachable through a raw file listing, so a
figure is findable only if you already know its filename. This walks both, writes 320 px
thumbnails next to a static page, and carries the caption used in the archived videos where
one exists. Run again after adding figures.
  .venv/bin/python3 tools/dashboard/gallery.py
"""
import html, json, os, re, subprocess
from pathlib import Path

REPO = Path('/home/syaro/MikuchanRemote/Human-Pygmalion')
DIRS = [REPO / 'docs' / 'img', REPO / 'docs' / 'mujoco' / 'assets']
OUT = REPO / 'tools' / 'dashboard' / 'gallery.html'
THUMB = REPO / 'tools' / 'dashboard' / 'thumbs'
THUMB.mkdir(exist_ok=True)

# captions written for the YouTube archive clips - reuse them so the gallery says what a
# figure shows, not just its filename
CAPS = {}
for src in (REPO / 'tools/robot_model/archive_batch2.py', REPO / 'tools/robot_model/archive_videos.py'):
    if src.exists():
        for f, c in re.findall(r"\{[AI]\}/([\w.]+\.png)',\s*'([^']+)'", src.read_text()):
            CAPS.setdefault(f, c)

# which doc embeds this figure -> a link back to the analysis
USED = {}
for md in REPO.glob('docs/**/*.md'):
    try:
        t = md.read_text()
    except Exception:
        continue
    for f in re.findall(r'([\w.\-]+\.png)', t):
        USED.setdefault(f, set()).add(md.relative_to(REPO).as_posix())

rows = []
for d in DIRS:
    for p in sorted(d.glob('*.png')):
        rel = p.relative_to(REPO).as_posix()
        th = THUMB / (rel.replace('/', '__'))
        if not th.exists() or th.stat().st_mtime < p.stat().st_mtime:
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(p),
                            '-vf', 'scale=320:-2', str(th)], check=False)
        rows.append(dict(name=p.name, rel=rel, thumb='thumbs/' + th.name,
                         cap=CAPS.get(p.name, ''), docs=sorted(USED.get(p.name, []))[:3],
                         mtime=p.stat().st_mtime, kb=p.stat().st_size // 1024))
rows.sort(key=lambda r: -r['mtime'])

cards = []
for r in rows:
    docs = ' · '.join(f'<a href="/{d}">{html.escape(d.split("/")[-1])}</a>' for d in r['docs']) or '<i>문서 미참조</i>'
    cards.append(f'''<div class="c" data-n="{html.escape(r['name'].lower())}" data-cap="{html.escape(r['cap'].lower())}">
<a href="/{r['rel']}" target="_blank"><img loading="lazy" src="{r['thumb']}"></a>
<div class="m"><b>{html.escape(r['name'])}</b><span class="p">{r['rel'].rsplit('/',1)[0]}</span>
<p>{html.escape(r['cap'])}</p><div class="d">{docs}</div><span class="p">{r['kb']} KB</span></div></div>''')

OUT.write_text(f'''<!doctype html><meta charset=utf-8><title>Pygmalion — 그림 갤러리</title>
<style>body{{background:#14161a;color:#e6e6ea;font:14px system-ui,sans-serif;margin:0;padding:18px}}
h1{{font-size:19px;margin:0 0 4px}}.sub{{color:#8b93a1;font-size:12px;margin-bottom:14px}}
#q{{width:100%;max-width:520px;padding:9px 12px;border-radius:8px;border:1px solid #2c313a;background:#1b1f26;color:#e6e6ea;font-size:14px}}
.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px;margin-top:16px}}
.c{{background:#1b1f26;border:1px solid #262b33;border-radius:10px;overflow:hidden}}
.c img{{width:100%;display:block;background:#fff}}
.m{{padding:9px 11px}}.m b{{font-size:13px;word-break:break-all}}
.m p{{color:#c3c9d4;font-size:12px;margin:6px 0;line-height:1.45}}
.p{{color:#79808d;font-size:11px;display:block;margin-top:3px}}
.d{{font-size:11px}}.d a{{color:#5aa9ff;text-decoration:none;margin-right:6px}}
a{{color:#5aa9ff}}</style>
<h1>Pygmalion — 그림 갤러리</h1>
<div class=sub>{len(rows)}장 · docs/img + docs/mujoco/assets · 최신순 · 캡션은 아카이브 영상에서 가져옴 · <a href="/tools/dashboard/">대시보드</a></div>
<input id=q placeholder="파일명 또는 캡션 검색 (예: pla, fea, abrp, wrench)">
<div class=g id=g>{''.join(cards)}</div>
<script>const q=document.getElementById('q');q.oninput=()=>{{const v=q.value.toLowerCase();
document.querySelectorAll('.c').forEach(c=>{{c.style.display=(c.dataset.n.includes(v)||c.dataset.cap.includes(v))?'':'none'}})}};</script>''')
print(f'wrote {OUT} ({len(rows)} figures, {len(CAPS)} captions)')
