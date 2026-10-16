"""The PageIndex library: books indexed once, read by `aw library` through pilib.

Layout (root = $AW_LIBRARY, default ~/aw-library):
    catalog.json                 one entry per book: title, author, pages, toc_source, top-level headings
    books/<book_id>/source.pdf   the PDF that was indexed (only for PDF indexing)
    books/<book_id>/tree.json    PageIndex tree (node summaries when asked for; never page text)
    books/<book_id>/pages.json   page texts, one string per page (Trove text for Trove books, PyPDF2 for PDFs)
    books/<book_id>/meta.json    provenance: origin (trove id or file), indexer settings, timings
    books/<book_id>/summaries.json  summary cache (key -> text), so a re-index only pays for changed nodes

Books are indexed once; an article's shelf.json lists the book ids it may search.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def root() -> Path:
    return Path(os.environ.get("AW_LIBRARY", Path.home() / "aw-library")).expanduser()


def book_dir(book_id: str) -> Path:
    if not book_id or "/" in book_id or book_id.startswith("."):
        raise ValueError(f"bad book id: {book_id!r}")
    return root() / "books" / book_id


def write_json(path: Path, data) -> None:
    """Atomic write: a reader never sees a half-written tree or catalog."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def catalog() -> dict:
    return read_json(root() / "catalog.json", {"books": {}})


def update_catalog(book_id: str, entry: dict) -> None:
    cat = catalog()
    cat["books"][book_id] = entry
    write_json(root() / "catalog.json", cat)


def iter_nodes(nodes):
    for node in nodes or []:
        yield node
        yield from iter_nodes(node.get("nodes"))


def load_tree(book_id: str) -> dict:
    tree = read_json(book_dir(book_id) / "tree.json")
    if tree is None:
        raise SystemExit(f"book not indexed: {book_id}")
    return tree


def load_pages(book_id: str) -> list[str]:
    pages = read_json(book_dir(book_id) / "pages.json")
    if pages is None:
        raise SystemExit(f"book has no page text: {book_id}")
    return pages


def parse_ranges(spec: str, n_pages: int) -> list[int]:
    """'5-7,12' -> [5, 6, 7, 12] (1-based, clipped to the book)."""
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if part == "all":
            return list(range(1, n_pages + 1))
        a, _, b = part.partition("-")
        lo, hi = int(a), int(b or a)
        if lo > hi:
            lo, hi = hi, lo
        out.extend(p for p in range(lo, hi + 1) if 1 <= p <= n_pages and p not in out)
    return out
