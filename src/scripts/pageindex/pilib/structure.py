"""The fallback for a book with no hinted table of contents: PageIndex's own structure detection.

The Trove text is rendered to a throw-away PDF (one Trove page starts each PDF page, Hebrew right to left),
PageIndex Flash detects the structure and writes the summaries, and the page numbers of the resulting tree
are mapped back to Trove pages. The page texts stored in the library are Trove's own text, never a re-read of
the PDF, so what an agent reads is exactly what Trove holds. Needs the structure tier (PageIndex and WeasyPrint).
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from . import native
from . import render_trove as rt
from .config import index_settings, pageindex_commit
from .errors import IndexFailure
from .meter import CallCapExceeded, LLMMeter

MISSING = "this book has no hinted table of contents and the structure helper is not installed"
MIN_WORD_OVERLAP = 0.9  # a rendered page that shares fewer words with its Trove text than this is reported


def load_helpers():
    """The two heavy imports, only here. Returns the page_index_flash function."""
    try:
        from pageindex.flash.api import page_index_flash
    except Exception as error:
        raise IndexFailure("structure_helper_missing", MISSING, detail=f"PageIndex could not be loaded: {type(error).__name__}")
    try:
        import weasyprint  # noqa: F401
    except Exception as error:  # ImportError, or OSError when the system libraries (pango) are missing
        raise IndexFailure("structure_helper_missing", MISSING, detail=f"WeasyPrint could not be loaded: {type(error).__name__}")
    return page_index_flash


def remap(nodes: list, mapping: list) -> None:
    last = len(mapping)
    for node in nodes:
        node.pop("text", None)
        start = mapping[min(max(int(node["start_index"]), 1), last) - 1]
        end = mapping[min(max(int(node["end_index"]), 1), last) - 1]
        node["start_index"], node["end_index"] = start, max(start, end)
        remap(node.get("nodes") or [], mapping)


def index_by_structure(*, command: str, book_id: str, title: str, author: str, pages_by_number: dict, raw_toc: list,
                       origin: dict, mode: str = "gemini", model: str = None, max_calls: int = None,
                       concurrency: int = None, dry_run: bool = False) -> dict:
    started = time.monotonic()
    settings = index_settings()
    model = model or settings["summaryModel"]
    max_calls = settings["maxCalls"] if max_calls is None else max_calls
    concurrency = settings["concurrency"] if concurrency is None else concurrency
    if mode not in native.SUMMARY_MODES:
        raise IndexFailure("bad_input", f"--summaries must be one of {', '.join(native.SUMMARY_MODES)}")
    warnings = ["this book has no hinted table of contents, so PageIndex detected its structure"]
    if mode == "hints":
        warnings.append("--summaries hints needs a hinted table of contents; no summaries were written")
        mode = "none"
    page_index_flash = load_helpers()
    pages, gaps = native.page_list(pages_by_number)
    if gaps:
        warnings.append(f"{len(gaps)} page numbers are missing in Trove (first: {gaps[0]}); they are stored as empty pages")
    stats = {"reused": 0, "generated": 0, "failed": 0, "empty": 0, "expected_calls": None, "input_chars": 0}
    if dry_run:
        warnings.append("the number of model calls is only known after the structure has been detected")
        usage = LLMMeter(max_calls).summary()
        return native.build_result(command=command, book_id=book_id, title=title, origin=origin, structure=[],
                                   n_pages=len(pages), mode=mode, model=model, stats=stats, usage=usage,
                                   started=started, warnings=warnings, source="flash-structure", fallback=True,
                                   dry_run=True, toc_entries=len(raw_toc or []),
                                   hinted_entries=native.hinted_count(raw_toc or []))
    if mode == "gemini":
        native.require_key(model)
    dropped = sorted(n for n, text in pages_by_number.items() if rt.is_guide(text))
    cleaned = {n: rt.clean(t) for n, t in pages_by_number.items() if n not in dropped}
    if not cleaned:
        raise IndexFailure("empty_book", "no pages are left after removing the reading guide")
    gemini = mode == "gemini"
    meter = LLMMeter(max_calls)
    flash_args = {"summary": gemini, "optimize": "full" if gemini else False, "use_embedded_toc": False}
    if gemini:
        flash_args.update(summary_model=model, optimize_model=model, summary_concurrency=concurrency,
                          summary_reasoning_effort="low")
    with tempfile.TemporaryDirectory(prefix="pilib-") as tmp:
        pdf = Path(tmp) / "book.pdf"
        mapping = rt.render(cleaned, title, pdf)
        check = rt.verify(pdf, cleaned, mapping)
        try:
            if gemini:
                with meter:
                    result = page_index_flash(str(pdf), **flash_args)
            else:
                result = page_index_flash(str(pdf), **flash_args)
        except CallCapExceeded:
            raise IndexFailure("call_cap", f"stopped at the model call cap ({max_calls}); raise --max-calls and run again",
                               **native.usage_fields(meter.summary()))
    structure = result.get("structure") or []
    if not structure:
        raise IndexFailure("empty_tree", f"PageIndex found no structure in this book (toc_source={result.get('toc_source')})")
    remap(structure, mapping)
    usage = meter.summary()
    if check["min_word_overlap"] < MIN_WORD_OVERLAP:
        warnings.append(f"Trove page {check['worst_trove_page']} shares only {check['min_word_overlap']:.0%} of its words "
                        "with the rendered page; check its page numbers")
    with_summary = sum(1 for _, n in native.sm.walk(structure) if (n.get("summary") or n.get("prefix_summary") or "").strip())
    stats["generated"] = with_summary
    out = native.build_result(command=command, book_id=book_id, title=title, origin=origin, structure=structure,
                              n_pages=len(pages), mode=mode, model=model, stats=stats, usage=usage, started=started,
                              warnings=warnings, source="flash-structure", fallback=True, dry_run=False,
                              toc_entries=len(raw_toc or []), hinted_entries=native.hinted_count(raw_toc or []))
    render_check = {k: check[k] for k in ("pdf_pages", "trove_pages", "min_word_overlap", "mean_word_overlap", "worst_trove_page")}
    native.write_book(result=out, structure=structure, pages=pages, author=author, origin=origin,
                      toc_source=f"flash-{result.get('toc_source') or 'detected'}", usage=usage, mode=mode, model=model,
                      stats=stats, extra_indexer={"mode": "flash-structure", "pageindex_commit": pageindex_commit(),
                                                  "optimize": flash_args["optimize"], "dropped_pages": dropped,
                                                  "render_check": render_check},
                      page_text_source="origin", doc_name=result.get("doc_name") or title)
    return out
