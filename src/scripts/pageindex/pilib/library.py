"""The PageIndex library: books indexed once, read by `aw library` through pilib.

Layout (root = $AW_LIBRARY, default ~/aw-library):
    books/<book_id>/CURRENT      one line: the name of the current version folder (written by temp file + rename)
    books/<book_id>/v/<version>/ a complete book, never changed after it is published:
        source.pdf   the PDF that was indexed (only for PDF indexing)
        tree.json    PageIndex tree (node summaries when asked for; never page text)
        pages.json   page texts, one string per page (Trove text for Trove books, PyPDF2 for PDFs)
        meta.json    provenance: origin (trove id or file), indexer settings, timings (written last)
    books/<book_id>/summaries.json  summary cache (key -> text), so a re-index only pays for changed nodes
    A book from before versions keeps tree.json, pages.json and meta.json flat in books/<book_id>/ and is read from
    there until it is indexed again. There is no catalog file: `catalog` and `list` scan the books every time.

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


# ---------------------------------------------------------------- versions: one pointer, complete books

VERSION_RE = re.compile(r"[A-Za-z0-9_-]+")
PRUNE_GRACE_SECONDS = 120   # a superseded complete version is kept at least this long (a slow publisher may still point at it)
STALE_SECONDS = 3600        # an unreferenced or unfinished version (a crashed run) is removed after this long
LEGACY_FILES = ("tree.json", "pages.json", "meta.json", "pagemap.json", "source.pdf")


def current_name(book_id: str):
    """The version named by books/<id>/CURRENT, or None when the book has no pointer (a flat legacy book)."""
    pointer = book_dir(book_id) / "CURRENT"
    if pointer.is_symlink():
        raise BookIdError(f"the version pointer of {book_id!r} is a symbolic link; refusing to use it")
    try:
        name = pointer.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    if not VERSION_RE.fullmatch(name):
        raise BookIdError(f"the version pointer of {book_id!r} is not a version name")
    return name


def version_dir(book_id: str, name: str) -> Path:
    container = book_dir(book_id)
    versions = container / "v"
    if versions.is_symlink() or (container / "v" / name).is_symlink():
        raise BookIdError(f"a version folder of {book_id!r} is a symbolic link; refusing to use it")
    path = versions / name
    if path.resolve() != container.resolve() / "v" / name:
        raise BookIdError(f"a version folder of {book_id!r} resolves outside the book; refusing to use it")
    return path


def data_dir(book_id: str):
    """The folder holding the current tree.json, pages.json and meta.json of a book, or None when it is not indexed.
    Layout: books/<id>/CURRENT names books/<id>/v/<version>/; a book from before versions keeps its files flat in
    books/<id>/ and is read from there until it is re-indexed."""
    container = book_dir(book_id)
    name = current_name(book_id)
    if name is not None:
        path = version_dir(book_id, name)
        return path if path.is_dir() and ((path / "meta.json").is_file() or (path / "tree.json").is_file()) else None
    if (container / "meta.json").is_file() or (container / "tree.json").is_file():
        return container
    return None


def new_version(book_id: str) -> Path:
    """A fresh, empty version folder. Nothing points at it until publish_version."""
    container = book_dir(book_id)
    versions = container / "v"
    if versions.is_symlink():
        raise BookIdError(f"a version folder of {book_id!r} is a symbolic link; refusing to use it")
    versions.mkdir(parents=True, exist_ok=True)
    name = f"{time.time_ns():020d}-{uuid.uuid4().hex[:8]}"
    path = version_dir(book_id, name)
    path.mkdir()
    return path


def publish_version(book_id: str, version: Path) -> None:
    """Point CURRENT at a finished version: write the pointer to a temporary file and rename it over CURRENT (atomic),
    so a reader sees the previous book or this one, whole. Then tidy up (errors there never undo the publish)."""
    container = book_dir(book_id)
    if version.parent != container / "v":
        raise BookIdError("the version to publish is not inside the book folder")
    if (container / "CURRENT").is_symlink():
        raise BookIdError(f"the version pointer of {book_id!r} is a symbolic link; refusing to use it")
    tmp = container / f".CURRENT.{uuid.uuid4().hex[:8]}"
    tmp.write_text(version.name + "\n", encoding="utf-8")
    try:
        os.replace(tmp, container / "CURRENT")
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    try:
        for name in LEGACY_FILES:  # the flat files of a book from before versions are superseded
            try:
                (container / name).unlink()
            except FileNotFoundError:
                pass
        prune_versions(book_id)
    except OSError:
        pass


def prune_versions(book_id: str) -> None:
    """Keep the current version and the newest complete one before it. A newer, unreferenced or unfinished version may
    belong to a run that is still going, so those (and a just-superseded one) are only removed once they are old."""
    current = current_name(book_id)
    versions = book_dir(book_id) / "v"
    if current is None or not versions.is_dir():
        return
    entries = sorted(d for d in versions.iterdir() if d.is_dir() and not d.is_symlink() and VERSION_RE.fullmatch(d.name))
    older = [d for d in entries if d.name < current and (d / "meta.json").is_file()]
    keep = {current, older[-1].name if older else None}
    now = time.time()
    for d in entries:
        if d.name in keep:
            continue
        superseded = d.name < current and (d / "meta.json").is_file()
        if now - d.stat().st_mtime >= (PRUNE_GRACE_SECONDS if superseded else STALE_SECONDS):
            shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------- the catalog: always scanned, never cached

def book_ids() -> list:
    books = root() / "books"
    if not books.is_dir():
        return []
    out = []
    for d in sorted(books.iterdir()):
        if not (valid_id(d.name) and d.is_dir() and not d.is_symlink()):
            continue
        try:
            if data_dir(d.name) is not None:
                out.append(d.name)
        except BookIdError:
            continue
    return out


def book_entry(book_id: str):
    """The catalog entry of one book: from its meta.json, with the tree filling what an older meta lacks."""
    d = data_dir(book_id)
    if d is None:
        return None
    try:
        meta = read_json(d / "meta.json") or {}
        tree = None
        entry = {k: meta[k] for k in CATALOG_FIELDS if k in meta} if isinstance(meta, dict) else {}
        if not isinstance(meta, dict) or len(entry) < len(CATALOG_FIELDS):
            meta = meta if isinstance(meta, dict) else {}
            tree = read_json(d / "tree.json") or {}
            structure = tree.get("structure") or []
            fill = {"title": tree.get("title") or meta.get("title") or book_id, "author": tree.get("author") or "",
                    "n_pages": meta.get("n_pages", tree.get("n_pages")), "toc_source": tree.get("toc_source"),
                    "node_count": sum(1 for _ in iter_nodes(structure)),
                    "top": [n["title"][:160] for n in structure[:60]]}
            entry = {k: entry[k] if k in entry else fill[k] for k in CATALOG_FIELDS}
    except (ValueError, KeyError, TypeError):
        return None
    return {k: entry[k] for k in CATALOG_FIELDS}


def catalog() -> dict:
    """Every indexed book with its latest meta, found by scanning books/*/ (through each CURRENT) on every call.
    There is no catalog file to go stale or to lose an entry when indexers run at the same time."""
    books = {}
    for book_id in book_ids():
        entry = book_entry(book_id)
        if entry is not None:
            books[book_id] = entry
    return {"books": books}


def iter_nodes(nodes):
    for node in nodes or []:
        yield node
        yield from iter_nodes(node.get("nodes"))


def load_tree(book_id: str) -> dict:
    d = data_dir(book_id)
    tree = read_json(d / "tree.json") if d else None
    if tree is None:
        raise SystemExit(f"book not indexed: {book_id}")
    return tree


def load_pages(book_id: str) -> list[str]:
    d = data_dir(book_id)
    pages = read_json(d / "pages.json") if d else None
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
