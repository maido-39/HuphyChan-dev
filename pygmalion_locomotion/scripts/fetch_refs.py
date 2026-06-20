# -*- coding: utf-8 -*-
"""개인 연구자료용 — 오픈액세스 논문 PDF를 docs/assets/refs/pdfs/ 로 다운로드.
arXiv / PMC-OA / OpenReview / 공개 URL 만. (제한 소스는 사용자가 직접 PDF 제공)

  python scripts/fetch_refs.py arxiv:2107.04034 arxiv:2201.08117
  python scripts/fetch_refs.py https://openreview.net/pdf?id=XXXX
  python scripts/fetch_refs.py https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8093456/pdf/
"""
from __future__ import annotations
import sys, re
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parents[1].parent / "docs" / "assets" / "refs" / "pdfs"
HDR = {"User-Agent": "Mozilla/5.0 (personal research use)"}


def to_url(token: str) -> tuple[str, str]:
    m = re.fullmatch(r"arxiv:([\w.\-/]+)", token, re.I)
    if m:
        aid = m.group(1)
        return f"https://arxiv.org/pdf/{aid}.pdf", f"arxiv_{aid.replace('/', '_')}.pdf"
    name = re.sub(r"[^\w.\-]+", "_", token.split("/")[-1] or token)[:60] or "ref"
    if not name.endswith(".pdf"):
        name += ".pdf"
    return token, name


def main(tokens: list[str]):
    OUT.mkdir(parents=True, exist_ok=True)
    if len(tokens) > 30:
        print("⚠ 한 번에 30개 이하로 — 대량 일괄 금지 (여러 번 나눠서)"); return
    for tok in tokens:
        url, name = to_url(tok)
        dst = OUT / name
        try:
            r = requests.get(url, headers=HDR, timeout=60); r.raise_for_status()
            if b"%PDF" not in r.content[:1024]:
                print(f"✗ {tok}: PDF 아님(접근제한일 수 있음) — 사용자가 직접 받아 {OUT}/ 에 두세요"); continue
            dst.write_bytes(r.content)
            print(f"✓ {tok} -> {dst}  ({len(r.content)//1024} KB)")
        except Exception as e:
            print(f"✗ {tok}: {e} — 제한 소스면 직접 받아 {OUT}/ 에 두세요")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(0)
    main(sys.argv[1:])
