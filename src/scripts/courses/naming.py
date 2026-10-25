"""Chicago author-date names for course sources: the display name everywhere, and the Drive filename.

A source's metadata is either structured (authors, year, title, journal or place/publisher) or a citation string
already recorded on its ref. Nothing is guessed: a source with neither keeps a cleaned file stem and is flagged
`needs_citation`. Hebrew metadata is written as given.

Pure functions, stdlib only. The caller keeps the `taken` set and adds each returned filename to it.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

DRIVE_NAME_LIMIT = 200


def _sentence(text: str) -> str:
    """Text ending in one sentence-final mark (a period is added unless ? or ! is already there)."""
    text = text.strip()
    return text if text.endswith((".", "?", "!")) else text + "."


def _straight_name(name: str) -> str:
    """'Last, First' becomes 'First Last' for the second and later authors."""
    if "," in name:
        last, first = [part.strip() for part in name.split(",", 1)]
        return f"{first} {last}".strip()
    return name.strip()


def _inverted_name(name: str) -> str:
    """'First Last' becomes 'Last, First' for the first author; names already in 'Last, First' stay."""
    name = name.strip()
    if "," in name or " " not in name:
        return name
    first, last = name.rsplit(" ", 1)
    return f"{last}, {first}"


def _authors(names: list[str]) -> str:
    names = [name for name in (str(n).strip() for n in names) if name]
    if not names:
        return ""
    lead = _inverted_name(names[0])
    if len(names) == 1:
        return lead
    if len(names) == 2:
        return f"{lead}, and {_straight_name(names[1])}"
    return f"{lead}, et al."


def _has_citation(meta: dict[str, Any]) -> bool:
    return bool(meta.get("raw")) or bool(meta.get("authors") and meta.get("title"))


def _clean_stem(stem: str) -> str:
    """Drop the 8-hex sha prefix a source file carries and turn separators into spaces."""
    stem = re.sub(r"^[0-9a-f]{8}-", "", stem)
    return " ".join(stem.replace("-", " ").replace("_", " ").split())


def chicago_bibliography(meta: dict[str, Any]) -> str:
    """Chicago author-date bibliography entry, ending in a period. Empty when there is no citation data."""
    if meta.get("raw"):
        return _sentence(str(meta["raw"]))
    if not _has_citation(meta):
        return ""
    authors = _authors(list(meta.get("authors") or []))
    year = str(meta.get("year") or "n.d.").strip()
    title = str(meta.get("title") or "").strip()
    if meta.get("journal"):
        quoted = f'"{title.rstrip(". ")}."' if not title.endswith(("?", "!")) else f'"{title}"'
        venue = str(meta["journal"]).strip()
        if meta.get("volume"):
            venue += f" {meta['volume']}"
        if meta.get("issue"):
            venue += f" ({meta['issue']})"
        if meta.get("pages"):
            venue += f": {meta['pages']}"
        head = f"{authors}. {year}. {quoted}" if authors else f"{quoted} {year}."
        return f"{head} {_sentence(venue)}"
    place = str(meta.get("place") or "").strip()
    publisher = str(meta.get("publisher") or "").strip()
    imprint = f"{place}: {publisher}" if place and publisher else (publisher or place)
    if authors:
        head = f"{authors}. {year}. {_sentence(title)}"
    else:
        head = f"{_sentence(title)} {year}."
    return f"{head} {_sentence(imprint)}" if imprint else head


def display_name(meta: dict[str, Any]) -> str:
    """The Chicago bibliography entry without its trailing period, or the cleaned file stem when there is no citation."""
    if _has_citation(meta):
        return chicago_bibliography(meta).rstrip(".")
    return str(meta.get("stem") or meta.get("title") or "untitled").strip()


def _fit(base: str, ext: str, suffix: str = "") -> str:
    """Trim base at a word boundary so that base + suffix + ext fits the Drive name limit."""
    limit = DRIVE_NAME_LIMIT - len(ext) - len(suffix)
    if len(base) > limit:
        cut = base[:limit]
        if " " in cut:
            cut = cut[:cut.rfind(" ")]
        base = cut
    return base.rstrip(" .,;:-") or "untitled"


def drive_filename(meta: dict[str, Any], ext: str, taken: set[str]) -> str:
    """Filesystem-safe Chicago name plus extension, unique against `taken` (adds ' (2)', ' (3)' ... on a clash)."""
    ext = "." + ext.lstrip(".") if ext else ""
    base = display_name(meta).replace("/", "-").replace("\\", "-")
    base = " ".join(base.split())
    base = _fit(base, ext)
    name = base + ext
    n = 2
    while name in taken:
        suffix = f" ({n})"
        name = _fit(base, ext, suffix) + suffix + ext
        n += 1
    return name


def meta_from_ref(ref: dict[str, Any]) -> dict[str, Any]:
    """Metadata from a registry ref: structured fields under `meta`, and its `citation` string as `raw`."""
    meta: dict[str, Any] = dict(ref.get("meta") or {}) if isinstance(ref.get("meta"), dict) else {}
    citation = " ".join(str(ref.get("citation") or "").split())
    if citation:
        meta["raw"] = citation
    meta["needs_citation"] = not (meta.get("raw") or (meta.get("authors") and meta.get("title") and meta.get("year")))
    return meta


def meta_from_source(source: dict[str, Any]) -> dict[str, Any]:
    """Metadata from a source entry: its `ref` or `citation`, else its `title`, plus the cleaned file stem as fallback."""
    ref = source.get("ref") if isinstance(source.get("ref"), dict) else {"citation": source.get("citation", "")}
    meta = meta_from_ref(ref)
    if not meta.get("raw") and not meta.get("title") and source.get("title"):
        meta["title"] = " ".join(str(source["title"]).split())
    file_name = str(source.get("name") or source.get("path") or source.get("file") or "")
    meta["stem"] = _clean_stem(Path(file_name).stem) if file_name else ""
    meta["needs_citation"] = not (meta.get("raw") or (meta.get("authors") and meta.get("title") and meta.get("year")))
    return meta
