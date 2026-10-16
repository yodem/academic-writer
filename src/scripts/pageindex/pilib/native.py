"""Index a book from its own table of contents: the tree IS the table of contents, no PDF, no layout guessing.

The tree is built deterministically from `[{title, page, level}]` (the hinted ToC the ingest skills write to
Trove) and the page texts exactly as Trove stores them. Page numbers are therefore Trove page numbers and the
library needs no page map. Summaries are optional (see summarize.py); the run is one JSON object on stdout.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone

from . import __version__
from . import library as lib
from . import summarize as sm
from .config import index_settings
from .errors import IndexFailure
from .meter import LLMMeter

HINT_SEP = " - "
HINT_MIN_SHARE = 0.5          # a ToC counts as hinted when more than this share of its titles carry "Title - hint"
SUMMARY_MODES = ("gemini", "hints", "none")
KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")


# ----------------------------------------------------------------------------- the table of contents

def toc_sha(toc: list) -> str:
    rows = [[str(e.get("title", "")), e.get("page"), e.get("level", 1)] for e in toc if isinstance(e, dict)]
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()


def pages_sha(pages: list) -> str:
    return hashlib.sha256(json.dumps(pages, ensure_ascii=False).encode("utf-8")).hexdigest()


def hinted_count(toc: list) -> int:
    return sum(1 for e in toc if isinstance(e, dict) and HINT_SEP in str(e.get("title", "")))


def is_hinted(toc: list) -> bool:
    return bool(toc) and hinted_count(toc) > HINT_MIN_SHARE * len(toc)


def normalize_toc(raw, n_pages: int):
    """Keep entries with a title and a page inside the book; order by page (stable); level defaults to 1.
    Returns (entries, dropped)."""
    entries, dropped = [], 0
    for item in raw or []:
        if not isinstance(item, dict):
            dropped += 1
            continue
        page, level = item.get("page"), item.get("level")
        title = str(item.get("title") or "").strip()
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= n_pages or not title:
            dropped += 1
            continue
        if isinstance(level, bool) or not isinstance(level, int) or level < 1:
            level = 1
        entries.append({"title": title, "page": page, "level": level})
    entries.sort(key=lambda e: e["page"])
    return entries, dropped


def build_structure(entries: list, n_pages: int) -> list:
    """Nested nodes from the ToC. A node spans from its page to the page before the next entry of the same or a
    higher level (the last one to the end of the book) and always includes its children, so a boundary page
    shared with the next entry is in both ranges (inclusive, as PageIndex counts). An entry that shares its page
    with the next one keeps that single page."""
    roots: list = []
    stack: list = []  # (level, node)

    def close(node, next_page):
        # a node ends before the next entry of its level, but never before its last child: a page shared by the
        # end of one entry and the start of the next belongs to both
        end = max(node["start_index"], min(next_page - 1, n_pages))
        node["end_index"] = max([end] + [child["end_index"] for child in node["nodes"]])

    for entry in entries:
        while stack and stack[-1][0] >= entry["level"]:
            close(stack.pop()[1], entry["page"])
        node = {"title": entry["title"], "start_index": entry["page"], "end_index": entry["page"], "nodes": []}
        (stack[-1][1]["nodes"] if stack else roots).append(node)
        stack.append((entry["level"], node))
    for _, node in stack:
        close(node, n_pages + 1)

    counter = [0]

    def finish(nodes):
        out = []
        for node in nodes:
            item = {"node_id": f"{counter[0]:04d}", "title": node["title"],
                    "start_index": node["start_index"], "end_index": node["end_index"]}
            counter[0] += 1
            if node["nodes"]:
                item["nodes"] = finish(node["nodes"])
            out.append(item)
        return out

    return finish(roots)


def apply_hints(structure: list) -> int:
    """`--summaries hints`: the hint in "Title - hint" becomes the node's summary. Free, no model."""
    count = 0
    for _, node in sm.walk(structure):
        _, sep, hint = node["title"].partition(HINT_SEP)
        if sep and hint.strip():
            node[sm.summary_field(node)] = hint.strip()
            count += 1
    return count


def with_summaries_last(structure: list) -> list:
    """Keep each node's keys in the order PageIndex writes them: id, title, range, summary, children."""
    out = []
    for node in structure:
        item = {k: v for k, v in node.items() if k not in ("nodes", "summary", "prefix_summary")}
        for key in ("summary", "prefix_summary"):
            if key in node:
                item[key] = node[key]
        if node.get("nodes"):
            item["nodes"] = with_summaries_last(node["nodes"])
        out.append(item)
    return out


# ----------------------------------------------------------------------------- one run

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def page_list(pages: dict):
    """{number: text} -> list of text for pages 1..N (a gap becomes an empty page); (list, gaps)."""
    if not pages:
        raise IndexFailure("empty_book", "the book has no pages")
    n = max(pages)
    gaps = [p for p in range(1, n + 1) if p not in pages]
    return [pages.get(p, "") for p in range(1, n + 1)], gaps


def require_key(model: str) -> None:
    if model.startswith("gemini/") and not any(os.environ.get(v) for v in KEY_VARS):
        raise IndexFailure("missing_key", "no Gemini key is set in the environment (GEMINI_API_KEY); "
                           "use --summaries hints or --summaries none to index without the model")


def load_cache(book_id: str) -> dict:
    data = lib.read_json(lib.book_dir(book_id) / "summaries.json") or {}
    entries = data.get("entries") if isinstance(data, dict) else None
    return entries if isinstance(entries, dict) else {}


def save_cache(book_id: str, model: str, entries: dict) -> None:
    lib.write_json(lib.book_dir(book_id) / "summaries.json", {"version": 1, "model": model, "entries": entries})


def run_summaries(book_id: str, structure: list, pages: list, mode: str, model: str, max_calls: int,
                  concurrency: int, dry_run: bool, use_cache: bool = True):
    """Returns (stats, meter_summary). Writes the cache sidecar for the gemini mode (also on an abort)."""
    meter = LLMMeter(max_calls)
    stats = {"nodes": sum(1 for _ in sm.walk(structure)), "reused": 0, "generated": 0, "failed": 0, "empty": 0,
             "expected_calls": 0, "input_chars": 0}
    if mode == "hints":
        stats["generated"] = apply_hints(structure)
        return stats, meter.summary()
    if mode != "gemini":
        return stats, meter.summary()
    if not dry_run:
        require_key(model)
        if not os.environ.get("GEMINI_API_KEY") and os.environ.get("GOOGLE_API_KEY"):
            os.environ["GEMINI_API_KEY"] = os.environ["GOOGLE_API_KEY"]  # the name LiteLLM's gemini provider reads
    cache = load_cache(book_id) if use_cache else {}
    if dry_run:
        stats, _ = sm.summarize(structure, pages, model, meter, concurrency, cache, dry_run=True)
        return stats, meter.summary()
    try:
        import litellm
        litellm.suppress_debug_info = True
    except ImportError:
        raise IndexFailure("core_helper_missing", "the summary helper (litellm) is not installed; "
                           "use --summaries hints or --summaries none, or install the built-in helper")
    try:
        with meter:
            stats, used = sm.summarize(structure, pages, model, meter, concurrency, cache)
    except IndexFailure as failure:
        partial = failure.extra.pop("partial", None)
        if partial:
            save_cache(book_id, model, {**cache, **partial})
        failure.extra.update(usage_fields(meter.summary()))
        raise
    save_cache(book_id, model, used)
    return stats, meter.summary()


def usage_fields(usage: dict) -> dict:
    """The model-use fields of the stdout JSON (the meter's llm_* names are the ones stored in meta.json)."""
    return {"calls": usage["llm_calls"], "failures": usage["llm_failures"], "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"], "reasoning_tokens": usage["reasoning_tokens"],
            "cost_usd": usage["cost_usd"], "cost_unknown_calls": usage["cost_unknown_calls"], "call_cap": usage["call_cap"]}


def build_result(*, command: str, book_id: str, title: str, origin: dict, structure: list, n_pages: int,
                 mode: str, model: str, stats: dict, usage: dict, started: float, warnings: list, source: str,
                 fallback: bool, dry_run: bool, toc_entries: int, hinted_entries: int) -> dict:
    nodes = list(sm.walk(structure))
    with_summary = sum(1 for _, n in nodes if (n.get("summary") or n.get("prefix_summary") or "").strip())
    seconds = round(time.monotonic() - started, 2)
    result = {"ok": True, "command": command, "dry_run": dry_run, "book_id": book_id, "trove_id": (origin.get("trove") or {}).get("trove_id"),
              "title": title, "source": source, "fallback": fallback, "summaries": mode,
              "model": model if mode == "gemini" else None, "n_pages": n_pages, "toc_entries": toc_entries,
              "hinted_entries": hinted_entries, "nodes": len(nodes), "nodes_with_summary": with_summary,
              "summaries_reused": stats.get("reused", 0), "summaries_generated": stats.get("generated", 0),
              "summary_failures": stats.get("failed", 0), "expected_calls": stats.get("expected_calls", 0),
              "input_chars": stats.get("input_chars", 0), **usage_fields(usage),
              "seconds": seconds, "library": str(lib.root()), "indexed_at": None if dry_run else now(),
              "warnings": warnings}
    return result


def write_book(*, result: dict, structure: list, pages: list, author: str, origin: dict, toc_source: str,
               usage: dict, mode: str, model: str, stats: dict, extra_indexer: dict, page_text_source: str,
               doc_name: str) -> None:
    """Write the book as a new complete version folder, then publish it by an atomic rename of the CURRENT pointer
    (lib.publish_version). A failure at any point leaves the previous book exactly as it was; nothing of the
    previous generation (a page map) is carried into the new version. The summary cache lives beside the versions."""
    book_id, title = result["book_id"], result["title"]
    nodes = list(sm.walk(structure))
    tree = {"book_id": book_id, "doc_name": doc_name, "title": title, "author": author, "n_pages": len(pages),
            "toc_source": toc_source, "structure": with_summaries_last(structure)}
    indexer = {"pilib_version": __version__, "summaries": mode, "summary_model": model if mode == "gemini" else None,
               "summaries_reused": stats.get("reused", 0), "summaries_generated": stats.get("generated", 0),
               "summary_failures": stats.get("failed", 0), **extra_indexer, **usage}
    meta = {"book_id": book_id, "title": title, "author": author, "origin": origin, "indexer": indexer,
            "n_pages": len(pages), "node_count": len(nodes), "nodes_with_summary": result["nodes_with_summary"],
            "toc_source": toc_source, "page_text_source": page_text_source, "seconds": result["seconds"],
            "indexed_at": result["indexed_at"], "top": [n["title"][:160] for n in tree["structure"][:60]]}
    version = lib.new_version(book_id)
    try:
        lib.write_json(version / "pages.json", pages)
        lib.write_json(version / "tree.json", tree)
        lib.write_json(version / "meta.json", meta)  # last: a version folder without meta.json is unfinished
        lib.publish_version(book_id, version)
    except BaseException:
        lib.discard_unpublished(book_id, version)  # only if the pointer never moved to it
        raise


def check_book_id(book_id: str) -> None:
    try:
        lib.book_dir(book_id)
    except lib.BookIdError as error:
        raise IndexFailure("bad_input", str(error))


def index_from_toc(*, command: str, book_id: str, title: str, author: str, pages_by_number: dict, raw_toc: list,
                   origin: dict, mode: str = "gemini", model: str = None, max_calls: int = None,
                   concurrency: int = None, dry_run: bool = False, reuse: bool = True, source: str = "trove-toc",
                   toc_source: str = "trove-toc", page_text_source: str = "origin", warnings: list = None) -> dict:
    """The native indexer. Raises IndexFailure; on success returns the stdout JSON object."""
    started = time.monotonic()
    check_book_id(book_id)
    settings = index_settings()
    model = model or settings["summaryModel"]
    max_calls = settings["maxCalls"] if max_calls is None else max_calls
    concurrency = settings["concurrency"] if concurrency is None else concurrency
    if mode not in SUMMARY_MODES:
        raise IndexFailure("bad_input", f"--summaries must be one of {', '.join(SUMMARY_MODES)}")
    warnings = list(warnings or [])
    pages, gaps = page_list(pages_by_number)
    if gaps:
        warnings.append(f"{len(gaps)} page numbers are missing in Trove (first: {gaps[0]}); they are stored as empty pages")
    entries, dropped = normalize_toc(raw_toc, len(pages))
    if dropped:
        warnings.append(f"{dropped} table of contents entries were ignored (no title, or a page outside the book)")
    if not entries:
        raise IndexFailure("no_toc", "the table of contents has no usable entries")
    structure = build_structure(entries, len(pages))
    stats, usage = run_summaries(book_id, structure, pages, mode, model, max_calls, concurrency, dry_run, reuse)
    result = build_result(command=command, book_id=book_id, title=title, origin=origin, structure=structure,
                          n_pages=len(pages), mode=mode, model=model, stats=stats, usage=usage, started=started,
                          warnings=warnings, source=source, fallback=False, dry_run=dry_run,
                          toc_entries=len(raw_toc or []), hinted_entries=hinted_count(raw_toc or []))
    if dry_run:
        return result
    write_book(result=result, structure=structure, pages=pages, author=author, origin=origin, toc_source=toc_source,
               usage=usage, mode=mode, model=model, stats=stats,
               extra_indexer={"mode": "native-toc", "pageindex_commit": None}, page_text_source=page_text_source,
               doc_name=title)
    return result


# ----------------------------------------------------------------------------- sources

def index_trove(a) -> dict:
    from . import structure as fallback
    from .trove_source import fetch

    book_id = a.book_id or a.trove_id
    check_book_id(book_id)
    book = fetch(a.trove_id)
    title, author = a.title or book["title"], a.author or book["author"]
    pages_list, _ = page_list(book["pages"])
    toc = book["toc"]
    origin = {"trove": {"trove_id": a.trove_id, "title": title, "trove_pages": len(pages_list),
                        "toc_entries": len(toc), "hinted_entries": hinted_count(toc), "toc_sha": toc_sha(toc),
                        "pages_sha": pages_sha(pages_list)}}
    common = dict(book_id=book_id, title=title, author=author, pages_by_number=book["pages"], raw_toc=toc,
                  origin=origin, mode=a.summaries, model=a.model, max_calls=a.max_calls, concurrency=a.concurrency,
                  dry_run=a.dry_run)
    if is_hinted(toc):
        return index_from_toc(command="index-trove", **common)
    if a.no_fallback:
        raise IndexFailure("no_hinted_toc", "this book has no hinted table of contents (--no-fallback was given)")
    return fallback.index_by_structure(command="index-trove", **common)


def split_pages(markdown: str, marker: str) -> dict:
    """Pages of a reading document: a page starts at each line matching `marker` (default: a level-1 heading)."""
    start = re.compile(marker)
    pages, current = {}, None
    for line in markdown.replace("\r\n", "\n").split("\n"):
        if start.match(line):
            current = len(pages) + 1
            pages[current] = line + "\n"
        elif current is not None:
            pages[current] += line + "\n"
    return {n: text.rstrip("\n") for n, text in pages.items()}


def index_md(a) -> dict:
    from pathlib import Path
    try:
        markdown = Path(a.pages).read_text(encoding="utf-8")
        toc = json.loads(Path(a.toc).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise IndexFailure("bad_input", f"cannot read the pages or the table of contents: {error}")
    if isinstance(toc, dict):
        toc = toc.get("toc")
    if not isinstance(toc, list):
        raise IndexFailure("bad_input", "the table of contents file must be a JSON list of {title, page, level}")
    pages = split_pages(markdown, a.page_marker)
    if not pages:
        raise IndexFailure("empty_book", f"no page starts with the page marker {a.page_marker!r}")
    page_values = [pages[n] for n in sorted(pages)]
    origin = {"md": {"pages": len(pages), "toc_entries": len(toc), "hinted_entries": hinted_count(toc),
                     "toc_sha": toc_sha(toc), "pages_sha": pages_sha(page_values)}}
    return index_from_toc(command="index-md", book_id=a.book_id, title=a.title, author=a.author or "",
                          pages_by_number=pages, raw_toc=toc, origin=origin, mode=a.summaries, model=a.model,
                          max_calls=a.max_calls, concurrency=a.concurrency, dry_run=a.dry_run,
                          source="markdown-toc", toc_source="markdown-toc")
