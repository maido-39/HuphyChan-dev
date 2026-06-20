# -*- coding: utf-8 -*-
"""개인 학습용 — PDF 한 페이지에서 Figure 영역을 잘라 이미지로 저장하는 유틸.
docs/assets/refs/ (gitignore·로컬 전용)에 저장하면 노트에 ![](assets/refs/...)로 바로 보임.

  # bbox 모르면 먼저 페이지 미리보기 PNG를 떠서 좌표 확인:
  python scripts/crop_figure.py preview refs/pdfs/paper.pdf 3            # -> 3페이지 전체 PNG
  # 좌표(point 단위, 좌상단 원점) 알면 잘라내기:
  python scripts/crop_figure.py crop refs/pdfs/paper.pdf 3  60 120 540 430  fig2.png

저장 위치: docs/assets/refs/ 아래. (출처는 노트 캡션에 직접 기입)
"""
from __future__ import annotations
import sys
from pathlib import Path

REFS = Path(__file__).resolve().parents[1].parent / "docs" / "assets" / "refs"


def _doc(p):
    import fitz  # PyMuPDF
    path = p if Path(p).is_absolute() else (REFS / p if not str(p).startswith("docs") else Path(p))
    return fitz.open(str(path))


def preview(pdf, page):
    import fitz
    doc = _doc(pdf); pg = doc[int(page)]
    out = REFS / f"_preview_p{page}.png"
    pg.get_pixmap(dpi=120).save(str(out))
    print(f"page size (pt): {pg.rect.width:.0f} x {pg.rect.height:.0f}")
    print(f"-> {out}  (좌표 확인 후 crop)")


def crop(pdf, page, x0, y0, x1, y1, out):
    import fitz
    doc = _doc(pdf); pg = doc[int(page)]
    clip = fitz.Rect(float(x0), float(y0), float(x1), float(y1))
    dst = REFS / out
    pg.get_pixmap(clip=clip, dpi=200).save(str(dst))
    print(f"✓ -> {dst}  (노트에 ![설명 + 출처](assets/refs/{out}) 로 임베드)")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == "preview":
        preview(a[1], a[2])
    elif a[0] == "crop":
        crop(a[1], a[2], a[3], a[4], a[5], a[6], a[7])
    else:
        print(__doc__)
