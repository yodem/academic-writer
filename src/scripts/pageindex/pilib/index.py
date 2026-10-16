"""Index a PDF into the library with PageIndex Flash (needs the structure tier).

Flash builds the tree from PDF layout and the embedded outline (bookmarks). With summary=False and
optimize=False it makes zero model calls. Page text is stored the way PageIndex's local client stores it
(PyPDF2, pageindex/local_api.py _extract_page_texts), because that is what its retrieval agent reads.
"""
from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from . import library as lib
from .config import index_settings, pageindex_commit
from .meter import CallCapExceeded, LLMMeter


def page_texts(pdf: Path) -> list[str]:
    import PyPDF2
    reader = PyPDF2.PdfReader(str(pdf))
    return [(page.extract_text() or "") for page in reader.pages]


def strip_llm_fields(nodes) -> None:
    for node in lib.iter_nodes(nodes):
        for key in ("summary", "prefix_summary", "text"):
            node.pop(key, None)


def published(build, book_id: str, *args, **kwargs) -> dict:
    """Run `build(version, ...)` in a fresh version folder and publish it; a failure removes the folder."""
    try:
        with lib.book_lock(book_id):
            version = lib.new_version(book_id)
            try:
                meta = build(version, *args, **kwargs)
                lib.publish_version(book_id, version)
            except BaseException:
                lib.discard_unpublished(book_id, version)  # only if the pointer never moved to it
                raise
    except lib.BookBusy as busy:
        raise SystemExit(f"{book_id}: {busy}")
    return meta


def index_pdf(pdf: Path, book_id: str, *args, **kwargs) -> dict:
    return published(_index_pdf, book_id, pdf, book_id, *args, **kwargs)


def index_pdf_full(pdf: Path, book_id: str, *args, **kwargs) -> dict:
    return published(_index_pdf_full, book_id, pdf, book_id, *args, **kwargs)


def _index_pdf(version: Path, pdf: Path, book_id: str, title: str, author: str = "", origin: dict | None = None,
              require_outline: bool = False, page_text: list[str] | None = None) -> dict:
    """page_text: when the PDF was rendered from another source (a Trove export), store that source's
    page text instead of re-extracting it, so both arms read identical text. Re-extracting a rendered
    Hebrew PDF with PyPDF2 reverses it (the renderer draws logical-order text left to right)."""
    from pageindex.flash.api import page_index_flash

    src = version / "source.pdf"
    shutil.copyfile(pdf, src)

    t0 = time.monotonic()
    result = page_index_flash(str(src), summary=False, optimize=False, use_embedded_toc=True)
    t_tree = time.monotonic() - t0
    pages = page_text if page_text is not None else page_texts(src)
    t_total = time.monotonic() - t0

    toc_source = result.get("toc_source")
    if require_outline and toc_source not in ("bookmarks", "hybrid"):
        raise SystemExit(f"{book_id}: Flash ignored the outline (toc_source={toc_source}); refusing")
    structure = result.get("structure") or []
    strip_llm_fields(structure)
    nodes = list(lib.iter_nodes(structure))
    if not nodes:
        raise SystemExit(f"{book_id}: empty tree (toc_source={toc_source})")

    tree = {"book_id": book_id, "doc_name": result.get("doc_name"), "title": title, "author": author,
            "n_pages": len(pages), "toc_source": toc_source, "structure": structure}
    meta = {"book_id": book_id, "title": title, "author": author, "origin": origin or {"file": str(pdf)},
            "indexer": {"pageindex_commit": pageindex_commit(), "mode": "flash", "summary": False,
                        "optimize": False, "use_embedded_toc": True, "llm_calls": 0},
            "n_pages": len(pages), "node_count": len(nodes), "toc_source": toc_source,
            "page_text_source": "origin" if page_text is not None else "pypdf2",
            "seconds_tree": round(t_tree, 2), "seconds_total": round(t_total, 2),
            "indexed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    lib.write_json(version / "tree.json", tree)
    lib.write_json(version / "pages.json", pages)
    lib.write_json(version / "meta.json", meta)
    return meta


DEFAULT_FULL_MODEL = index_settings()["summaryModel"]
MAX_LLM_CALLS = index_settings()["maxCalls"]


def _index_pdf_full(version: Path, pdf: Path, book_id: str, title: str, author: str = "", model: str = DEFAULT_FULL_MODEL,
                   summary_concurrency: int = 16, reasoning_effort: str = "low",
                   max_calls: int = MAX_LLM_CALLS) -> dict:
    """PageIndex flash on the ORIGINAL pdf with its full pipeline: layout tree (embedded outline when
    present), LLM node summaries and the optimizer's merge+expand, all on `model` (needs the model's API
    key in the environment, e.g. GEMINI_API_KEY). Keeps summary/prefix_summary on the nodes."""
    from pageindex.flash.api import page_index_flash

    settings = {"mode": "flash", "summary": True, "summary_model": model, "optimize": "full",
                "optimize_model": model, "use_embedded_toc": True, "summary_concurrency": summary_concurrency,
                "summary_reasoning_effort": reasoning_effort}
    src = version / "source.pdf"
    shutil.copyfile(pdf, src)

    t0 = time.monotonic()
    meter = LLMMeter(max_calls)
    try:
        with meter:
            result = page_index_flash(str(src), **{k: v for k, v in settings.items() if k != "mode"})
    except CallCapExceeded as e:
        raise SystemExit(f"{book_id}: aborted, {e} (summary: {json.dumps(meter.summary())})")
    seconds = time.monotonic() - t0
    if meter.exceeded:
        raise SystemExit(f"{book_id}: aborted, call cap {max_calls} reached")
    pages = page_texts(src)

    toc_source = result.get("toc_source")
    structure = result.get("structure") or []
    for node in lib.iter_nodes(structure):
        node.pop("text", None)
    nodes = list(lib.iter_nodes(structure))
    if not nodes:
        raise SystemExit(f"{book_id}: empty tree (toc_source={toc_source})")
    n_sum = sum(1 for n in nodes if (n.get("summary") or n.get("prefix_summary") or "").strip())

    tree = {"book_id": book_id, "doc_name": result.get("doc_name"), "title": title, "author": author,
            "n_pages": len(pages), "toc_source": toc_source, "optimize": result.get("optimize"),
            "structure": structure}
    meta = {"book_id": book_id, "title": title, "author": author, "origin": {"file": str(pdf)},
            "indexer": {"pageindex_commit": pageindex_commit(), **settings, **meter.summary()},
            "n_pages": len(pages), "node_count": len(nodes), "nodes_with_summary": n_sum,
            "toc_source": toc_source, "page_text_source": "pypdf2", "seconds": round(seconds, 1),
            "indexed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    lib.write_json(version / "tree.json", tree)
    lib.write_json(version / "pages.json", pages)
    lib.write_json(version / "meta.json", meta)
    return meta
