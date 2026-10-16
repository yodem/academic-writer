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
import sys
import tempfile
import time
import uuid
from datetime import datetime
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
# A version that is neither CURRENT nor the newest complete one before it is only removed once this long after it was
# completed (the indexed_at in its meta.json; for an unfinished one, after the time in its name, when it was started).
# A run that is still going, or a slow publisher that has not moved the pointer yet, therefore never loses its folder.
PRUNE_GRACE_SECONDS = 3600
clock = time.time           # seconds since the epoch; tests replace it
LEGACY_FILES = ("tree.json", "pages.json", "meta.json", "pagemap.json", "source.pdf")


# ---------------------------------------------------------------- one indexer per book

LOCK_NAME = ".index.lock"
LOCK_STALE_SECONDS = 7200      # a holder this old is taken over even if its pid answers (the pid may have been reused)
LOCK_UNREADABLE_SECONDS = 10   # a lock file nobody can read is a creator still writing it; after this long it is dead
BUSY_MESSAGE = "this book is being indexed by another process \u2014 try again when it finishes"
_held: set = set()


class BookBusy(Exception):
    """Another process (or this one) is already indexing this book."""

    def __init__(self):
        super().__init__(BUSY_MESSAGE)


def _pid_alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, ValueError, TypeError):
        return False
    return True


def _read_token(path: Path):
    try:
        token = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return token if isinstance(token, dict) and isinstance(token.get("nonce"), str) else None


def _holder_dead(path: Path) -> bool:
    token = _read_token(path)
    if token is None:
        try:
            return clock() - path.stat().st_mtime >= LOCK_UNREADABLE_SECONDS
        except FileNotFoundError:
            return True
    started = token.get("started")
    return not _pid_alive(token.get("pid")) or (isinstance(started, (int, float)) and clock() - started >= LOCK_STALE_SECONDS)


def _take_over(path: Path) -> None:
    """Remove a dead holder's lock by an atomic rename. If what was moved is not the lock that was judged dead (someone
    took the slot in between), put it back."""
    seen = _read_token(path)
    trash = path.with_name(f"{path.name}.dead.{uuid.uuid4().hex[:8]}")
    try:
        os.rename(path, trash)
    except FileNotFoundError:
        return
    if _read_token(trash) != seen:
        try:
            os.link(trash, path)
        except OSError:
            pass
    try:
        trash.unlink()
    except OSError:
        pass


class book_lock:
    """Exclusive, fail-fast lock for everything that writes one book: books/<id>/.index.lock, created with O_EXCL and
    holding {pid, nonce, started}. A live holder means BookBusy at once (never a wait). A dead holder (no such pid, or
    older than LOCK_STALE_SECONDS) is taken over. Only the owner's nonce releases it. Readers do not take it."""

    def __init__(self, book_id: str):
        self.book_id = book_id
        self.nonce = uuid.uuid4().hex

    def __enter__(self):
        container = book_dir(self.book_id)
        if self.book_id in _held:
            raise BookBusy()
        container.mkdir(parents=True, exist_ok=True)
        self.path = container / LOCK_NAME
        token = {"pid": os.getpid(), "nonce": self.nonce, "started": clock()}
        for _ in range(5):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                if not _holder_dead(self.path):
                    raise BookBusy()
                _take_over(self.path)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(token, f)
            _held.add(self.book_id)
            return self
        raise BookBusy()

    def __exit__(self, *exc):
        _held.discard(self.book_id)
        token = _read_token(self.path)
        if token is not None and token.get("nonce") == self.nonce:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        return False


def require_lock(book_id: str) -> None:
    if book_id not in _held:
        raise RuntimeError(f"writing book {book_id!r} without holding its lock")


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
    """A fresh, empty version folder. Nothing points at it until publish_version. Needs the book lock."""
    require_lock(book_id)
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
    so a reader sees the previous book or this one, whole. Then tidy up (errors there never undo the publish).
    Needs the book lock, which is why no other publisher can move the pointer or prune while this runs."""
    require_lock(book_id)
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
    # The pointer has moved: from here on the version is published and must never be deleted. Tidying up is best
    # effort; a failure is reported on stderr and the run goes on.
    try:
        for name in LEGACY_FILES:  # the flat files of a book from before versions are superseded
            try:
                (container / name).unlink()
            except FileNotFoundError:
                pass
        prune_versions(book_id)
    except Exception as error:
        print(f"note: tidying the old versions of {book_id} failed: {type(error).__name__}: {error}", file=sys.stderr)


def discard_unpublished(book_id: str, version: Path) -> None:
    """Remove a version this run created, unless CURRENT already points at it (the failure came after publishing).
    Called with the book lock held, so the pointer cannot have moved on for any other reason."""
    try:
        if current_name(book_id) == version.name:
            return
    except Exception:
        return  # cannot tell what the pointer says: keep the folder
    shutil.rmtree(version, ignore_errors=True)


def completed_at(version: Path) -> float:
    """When a version was completed (meta.json's indexed_at), else when it was started (the time in its name)."""
    try:
        meta = json.loads((version / "meta.json").read_text(encoding="utf-8"))
        return datetime.fromisoformat(meta["indexed_at"]).timestamp()
    except Exception:
        pass
    try:
        return int(version.name.split("-")[0]) / 1e9
    except ValueError:
        return clock()


def prune_versions(book_id: str) -> None:
    """Keep the current version and the newest complete one before it, always. Any other version goes once
    PRUNE_GRACE_SECONDS have passed since it was completed (or started, when it never finished).
    Needs the book lock; CURRENT is read here, under it, never passed in."""
    require_lock(book_id)
    current = current_name(book_id)
    versions = book_dir(book_id) / "v"
    if current is None or not versions.is_dir():
        return
    entries = sorted(d for d in versions.iterdir() if d.is_dir() and not d.is_symlink() and VERSION_RE.fullmatch(d.name))
    older = [d for d in entries if d.name < current and (d / "meta.json").is_file()]
    keep = {current, older[-1].name if older else None}
    now = clock()
    for d in entries:
        if d.name not in keep and now - completed_at(d) >= PRUNE_GRACE_SECONDS:
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
