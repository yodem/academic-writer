"""Render Trove pages to a PDF that PageIndex has to structure by itself (phase 3, arm D).

    pilib render-trove <trove-id> --book-id ID --title T [--author A] [--pages a-b] [--drop-pages x,y]

Text only: base64/data-URI images become "[diagram]", HTML tags and comments are dropped, markdown `#` lines
become visible headings, and NO PDF outline exists (bookmark-level: none on every heading), so PageIndex
builds the tree from the layout alone. Each Trove page starts on a new PDF page (a long one spills over
several). Hebrew runs RTL (`dir=auto` per paragraph, so mixed Hebrew/Latin/Greek works), A4, one column.

The sidecar `<out>.pagemap.json` = {"trove_id", "pdf_to_trove": [Trove page of PDF page 1, 2, ...]} is read
from WeasyPrint's rendered document: every Trove page is a <section id="tp-N">, and the anchor of that id
sits on exactly the PDF page where the section starts, so the map is exact. `verify` then re-extracts the
PDF with PyPDF2 and compares each Trove page's words (niqqud stripped) with the text of its PDF pages.
"""
from __future__ import annotations

import html
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from .trove_source import trove_env

NIQQUD = re.compile("[֑-ׇ]")  # cantillation + points (U+0591-U+05C7)
HEBREW = re.compile("[א-ת]")
LATINISH = re.compile("[A-Za-zͰ-Ͽἀ-῿]")
GUIDE_RE = re.compile(r"^#\s*(מדריך קריאה|Reading Guide|How to read)", re.I)

CSS = """
@page { size: A4; margin: 2cm 1.8cm; }
body { font-family: "Noto Serif", "Noto Serif Hebrew", "Liberation Serif", "FreeSerif"; font-size: 11pt; line-height: 1.5; }
section { break-before: page; padding-top: 3.5cm; }  /* chapter-opener sink: a one-line heading flush at the page top
   recurs on every page and PageIndex drops it as a running header (SY came back as a flat "pages" tree) */
h1, h2, h3, h4, h5, h6 { bookmark-level: none; font-weight: bold; margin: 0.9em 0 0.4em; break-after: avoid; text-align: start; }
h1 { font-size: 15pt; } h2 { font-size: 13pt; } h3, h4, h5, h6 { font-size: 11.5pt; }
p { margin: 0 0 0.55em; text-align: start; }
"""


def trove(*args: str) -> str:
    out = subprocess.run(["trove", *args, "--no-session"], capture_output=True, text=True, env=trove_env())
    if out.returncode != 0:
        raise SystemExit(f"trove {' '.join(args)} failed: {out.stderr.strip()[:400]}")
    return out.stdout


def parse_pages(spec: str | None) -> set[int]:
    out: set[int] = set()
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return out


def fetch_pages(trove_id: str, pages: str | None) -> dict[int, str]:
    doc = json.loads(trove("items", "read", f"{trove_id}:{pages or 'all'}", "--json"))
    item = doc["items"][0]
    if doc.get("truncatedItemIds") or item.get("truncated"):
        raise SystemExit(f"{trove_id}: Trove truncated the read; pass a smaller --pages range")
    return {int(p["pageNum"]): p.get("content") or "" for p in item["pages"]}


IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
COMMENT = re.compile(r"<!--.*?-->", re.S)
TAG = re.compile(r"</?[A-Za-z][^>]*>")
DATA_URI = re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]+")


def clean(text: str) -> str:
    """Trove markdown -> plain markdown-ish text: no images, no HTML."""
    text = IMG.sub("[diagram]", text)
    text = DATA_URI.sub("[diagram]", text)
    text = COMMENT.sub("", text)
    text = TAG.sub("", text)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def is_guide(text: str) -> bool:
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    return bool(GUIDE_RE.match(first.strip()))


def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"\[([^\]]+)\]\((?:https?://|#)[^)]*\)", r"\1", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![*\w])", r"<em>\1</em>", s)
    return s.replace("`", "")


def body_html(text: str) -> str:
    out: list[str] = []
    for block in re.split(r"\n\s*\n", text.strip("\n")):
        lines = [ln.rstrip() for ln in block.split("\n") if ln.strip()]
        i = 0
        while i < len(lines) and (m := re.match(r"(#{1,6})\s+(.*)", lines[i])):
            lvl = len(m.group(1))
            out.append(f'<h{lvl} dir="auto">{inline(m.group(2))}</h{lvl}>')
            i += 1
        rest = lines[i:]
        if rest:
            out.append('<p dir="auto">' + "<br>".join(inline(ln) for ln in rest) + "</p>")
    return "\n".join(out)


def build_html(pages: dict[int, str], title: str, lang: str) -> str:
    secs = []
    for n in sorted(pages):
        body = body_html(pages[n]) or "<p>&nbsp;</p>"
        secs.append(f'<section id="tp-{n}">\n{body}\n</section>')
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"<style>{CSS}</style></head><body>\n" + "\n".join(secs) + "\n</body></html>")


def words(text: str) -> list[str]:
    return re.findall(r"\w+", NIQQUD.sub("", text).replace("־", " "), re.U)


def _bigrams(w: list[str]) -> Counter:
    return Counter(zip(w, w[1:]))


def overlap(trove_text: str, pdf_text: str) -> tuple[float, float]:
    """Fraction of the Trove page's words (and adjacent word pairs) found in the PDF text (multiset)."""
    a, b = words(trove_text), words(pdf_text)
    if not a:
        return 1.0, 1.0
    uni = sum((Counter(a) & Counter(b)).values()) / len(a)
    ba = _bigrams(a)
    bi = sum((ba & _bigrams(b)).values()) / max(1, sum(ba.values()))
    return uni, bi


def pdf_texts(pdf: Path) -> list[str]:
    from PyPDF2 import PdfReader
    return [(p.extract_text() or "") for p in PdfReader(str(pdf)).pages]


def render(pages: dict[int, str], title: str, out_pdf: Path) -> list[int]:
    """Render the pages; return pdf_to_trove (Trove page for each PDF page)."""
    from weasyprint import HTML

    letters = "".join(pages.values())
    lang = "he" if len(HEBREW.findall(letters)) > len(LATINISH.findall(letters)) else "en"
    doc = HTML(string=build_html(pages, title, lang)).render()
    anchor_page: dict[int, int] = {}  # Trove page -> index of the PDF page it starts on
    for i, pg in enumerate(doc.pages):
        for name in pg.anchors:
            if name.startswith("tp-"):
                anchor_page.setdefault(int(name[3:]), i)  # a section's id is repeated on its continuation pages
    missing = sorted(set(pages) - set(anchor_page))
    if missing:
        raise SystemExit(f"anchors lost for Trove pages {missing[:10]}")
    starts = sorted((i, n) for n, i in anchor_page.items())
    if len({i for i, _ in starts}) != len(starts) or starts[0][0] != 0:
        raise SystemExit("two Trove pages share a PDF page, or the first does not start on PDF page 1")
    mapping: list[int] = []
    for i in range(len(doc.pages)):
        mapping.append(max(n for j, n in starts if j <= i))
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc.write_pdf(str(out_pdf))
    return mapping


def verify(pdf: Path, pages: dict[int, str], mapping: list[int], min_he: float = 0.9) -> dict:
    texts = pdf_texts(pdf)
    if len(texts) != len(mapping):
        raise SystemExit(f"pagemap has {len(mapping)} entries but the PDF has {len(texts)} pages")
    per: dict[int, str] = {}
    for t, n in zip(texts, mapping):
        per[n] = per.get(n, "") + "\n" + t
    if set(per) != set(pages):
        raise SystemExit(f"Trove pages missing from the map: {sorted(set(pages) - set(per))[:10]}")
    rows = {}
    for n in sorted(pages):
        uni, bi = overlap(pages[n], per[n])
        rows[n] = {"words": round(uni, 3), "bigrams": round(bi, 3),
                   "hebrew": len(HEBREW.findall(pages[n])) > len(LATINISH.findall(pages[n]))}
    he = [r["words"] for r in rows.values() if r["hebrew"]]
    worst = min(rows.items(), key=lambda kv: kv[1]["words"])
    return {"pdf_pages": len(texts), "trove_pages": len(pages), "min_word_overlap": worst[1]["words"],
            "worst_trove_page": worst[0], "mean_word_overlap": round(sum(r["words"] for r in rows.values()) / len(rows), 4),
            "min_bigram_overlap": min(r["bigrams"] for r in rows.values()),
            "hebrew_pages": len(he), "hebrew_min": min(he) if he else None, "pages": rows}


def run(trove_id: str, book_id: str, title: str, author: str = "", pages_spec: str | None = None,
        drop_spec: str | None = None, out: Path | None = None) -> dict:
    raw = fetch_pages(trove_id, pages_spec)
    drop = parse_pages(drop_spec)
    dropped = sorted(n for n, t in raw.items() if n in drop or is_guide(t))
    pages = {n: clean(t) for n, t in raw.items() if n not in dropped}
    if not pages:
        raise SystemExit("no pages left after dropping")
    out = out or Path("~/aw-library-src").expanduser() / f"{book_id}.pdf"
    mapping = render(pages, title, out)
    side = out.with_suffix(".pagemap.json")
    side.write_text(json.dumps({"trove_id": trove_id, "book_id": book_id, "title": title, "author": author,
                                "trove_pages": [min(pages), max(pages)], "dropped_pages": dropped,
                                "pdf_to_trove": mapping}, ensure_ascii=False))
    v = verify(out, pages, mapping)
    out.with_suffix(".verify.json").write_text(json.dumps(v, ensure_ascii=False, indent=1))
    v.pop("pages")
    return {"book_id": book_id, "pdf": str(out), "pagemap": str(side), "dropped_pages": dropped, **v}
