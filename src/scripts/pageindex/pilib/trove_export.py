"""Download a book from Trove and render it as a PDF PageIndex can index (`pilib export-trove`).

Kept as the Flash-on-outline variant; the default for a Trove book is the native tree in native.py.
Needs reportlab and the DejaVu font, which the install tiers do not include.


Page i of the PDF is Trove page i (so page numbers match Trove exactly), and the Trove table of contents,
hints included ("title - hint"), becomes the PDF outline. Flash then builds its tree from that outline.
Both benchmark arms therefore search the same pages and the same hints; only the retrieval engine differs.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from . import trove_source

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
WIDTH = 595.0          # A4 width in points; height grows to fit a long page
MARGIN = 40.0
FONT_SIZE = 9.0
LEADING = 11.5
WRAP = 110


def fetch(trove_id: str):
    book = trove_source.fetch(trove_id)
    return book["toc"], book["pages"], book["title"]


def render(toc: list[dict], pages: dict[int, str], out_pdf: Path) -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(TTFont("DejaVu", FONT))
    n = max(pages) if pages else 0
    by_page: dict[int, list[dict]] = {}
    for entry in toc:
        by_page.setdefault(int(entry["page"]), []).append(entry)

    c = canvas.Canvas(str(out_pdf), pageCompression=1)
    c.setTitle(out_pdf.stem)
    prev_level = -1
    for p in range(1, n + 1):
        lines: list[str] = []
        for raw in (pages.get(p) or "").splitlines():
            lines.extend(textwrap.wrap(raw, WRAP, replace_whitespace=False, drop_whitespace=True) or [""])
        height = max(842.0, 2 * MARGIN + LEADING * (len(lines) + 1))
        c.setPageSize((WIDTH, height))
        key = f"p{p}"
        c.bookmarkPage(key)
        for entry in by_page.get(p, []):
            level = max(0, int(entry.get("level", 1)) - 1)
            level = min(level, prev_level + 1)  # outline levels may only deepen one step at a time
            c.addOutlineEntry(entry["title"], key, level=level, closed=True)
            prev_level = level
        c.setFont("DejaVu", FONT_SIZE)
        y = height - MARGIN
        for line in lines:
            c.drawString(MARGIN, y, line)
            y -= LEADING
        c.showPage()
    c.save()


def export(trove_id: str, out_pdf: Path) -> dict:
    toc, pages, title = fetch(trove_id)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    render(toc, pages, out_pdf)
    hinted = sum(1 for e in toc if " - " in e.get("title", ""))
    texts = [pages.get(p, "") for p in range(1, max(pages) + 1)]
    return {"trove_id": trove_id, "title": title, "trove_pages": len(pages), "toc_entries": len(toc),
            "hinted_entries": hinted}, texts
