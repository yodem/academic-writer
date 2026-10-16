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
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path


ID_RE = re.compile(r"[A-Za-z0-9._#:-]+")
CATALOG_FIELDS = ("title", "author", "n_pages", "toc_source", "node_count", "top")


class BookIdError(ValueError):
    """A book id, or a book folder, that is not safe to use."""


def root() -> Path:
    return Path(os.environ.get("AW_LIBRARY", Path.home() / "aw-library")).expanduser()


def valid_id(book_id) -> bool:
    return (isinstance(book_id, str) and ID_RE.fullmatch(book_id) is not None
            and ".." not in book_id and not book_id.startswith("."))


def book_dir(book_id: str) -> Path:
    """books/<id> under the library root. The id is checked, and the folder must really be inside the root:
    a symbolic link (the folder itself, or `books`) that leads elsewhere is refused, for reads and writes alike."""
    if not valid_id(book_id):
        raise BookIdError(f"bad book id: {book_id!r}")
    path = root() / "books" / book_id
    if path.is_symlink():
        raise BookIdError(f"book folder {book_id!r} is a symbolic link; refusing to use it")
    if path.resolve() != root().resolve() / "books" / book_id:
        raise BookIdError(f"book folder {book_id!r} resolves outside the library; refusing to use it")
    return path


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


# ---------------------------------------------------------------- the catalog is derived from the books

def book_ids() -> list:
    books = root() / "books"
    if not books.is_dir():
        return []
    return sorted(d.name for d in books.iterdir()
                  if valid_id(d.name) and d.is_dir() and not d.is_symlink() and (d / "meta.json").is_file())


def book_entry(book_id: str):
    """The catalog entry of one book: from its meta.json, with the tree filling what an older meta lacks."""
    d = book_dir(book_id)
    try:
        meta = read_json(d / "meta.json") or {}
    except ValueError:
        return None
    if not isinstance(meta, dict):
        return None
    entry = {k: meta[k] for k in CATALOG_FIELDS if k in meta}
    if len(entry) < len(CATALOG_FIELDS):
        try:
            tree = read_json(d / "tree.json") or {}
        except ValueError:
            tree = {}
        structure = tree.get("structure") or []
        fill = {"title": tree.get("title") or meta.get("title") or book_id, "author": tree.get("author") or "",
                "n_pages": meta.get("n_pages", tree.get("n_pages")), "toc_source": tree.get("toc_source"),
                "node_count": sum(1 for _ in iter_nodes(structure)),
                "top": [n["title"][:160] for n in structure[:60]]}
        entry = {k: entry[k] if k in entry else fill[k] for k in CATALOG_FIELDS}
    else:
        entry = {k: entry[k] for k in CATALOG_FIELDS}
    return entry


def scan_catalog() -> dict:
    books = {}
    for book_id in book_ids():
        entry = book_entry(book_id)
        if entry is not None:
            books[book_id] = entry
    return books


def rebuild_catalog() -> dict:
    """Rescan books/*/meta.json and write catalog.json (atomically). The file is only a cache: catalog() notices
    a cache that missed a book, or is older than a book, and scans again, so two indexers cannot lose an entry."""
    scanned = time.time_ns()
    books = scan_catalog()
    try:
        write_json(root() / "catalog.json", {"scanned_ns": scanned, "books": books})
    except OSError:
        pass
    return {"books": books}


def catalog() -> dict:
    try:
        cached = read_json(root() / "catalog.json")
    except ValueError:
        cached = None
    ids = book_ids()
    if isinstance(cached, dict) and isinstance(cached.get("books"), dict) and isinstance(cached.get("scanned_ns"), int):
        scanned = cached["scanned_ns"]
        if set(cached["books"]) == set(ids) and all((book_dir(i) / "meta.json").stat().st_mtime_ns < scanned for i in ids):
            return {"books": cached["books"]}
    if not root().exists():
        return {"books": {}}
    return rebuild_catalog()


# ---------------------------------------------------------------- publishing a book as one unit

def new_staging(book_id: str) -> Path:
    book_dir(book_id)  # validates the id and the folder
    path = root() / ".staging" / f"{book_id}.{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True)
    return path


def drop_staging(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass


def publish_book(staging: Path, book_id: str) -> None:
    """Replace books/<id> by the finished staging folder: the old folder is renamed aside, the new one renamed in
    and the old one removed. If the new one cannot be moved in, the old one is put back and the error is raised,
    so a reader sees the previous book or the new book, never a mixture."""
    dest = book_dir(book_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    aside = None
    if dest.exists():
        aside = staging.parent / f"{book_id}.old.{uuid.uuid4().hex[:8]}"
        os.rename(dest, aside)
    try:
        os.rename(staging, dest)
    except BaseException:
        if aside is not None:
            os.rename(aside, dest)
        raise
    if aside is not None:
        shutil.rmtree(aside, ignore_errors=True)
    rebuild_catalog()
    try:
        staging.parent.rmdir()
    except OSError:
        pass


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
