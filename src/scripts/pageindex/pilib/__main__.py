"""pilib: the PageIndex library tool shipped with academic-writer.

Read side (stdlib only, any Python 3.9+; the JSON shapes are what `aw library` parses, keep them stable):
    pilib list | catalog [--shelf shelf.json]
    pilib tree <book-id> [--max-title N] [--depth N] [--node ID]       # tree without text, for tree search
    pilib read <book-id> <pages> [--json]       # e.g. 12-14,20 ; at most 10 pages per call; with --json also `all`
    pilib meta <book-id>                        # JSON: book_id, title, n_pages, origin, trove_id, pagemap
    pilib verify-library --min-books N [--no-summary | --require-summary]
    pilib health [--require core|structure]     # JSON: which tier this machine can run

Index side (run on the machine that holds the library; every command prints ONE JSON object on stdout):
    pilib index-trove <trove-id> [--book-id ID] [--summaries gemini|hints|none] [--no-fallback]
                      [--max-calls N] [--model M] [--concurrency N] [--dry-run]
                                        # tree from the book's hinted table of contents in Trove (Trove page numbers);
                                        # no hinted table of contents -> PageIndex structure detection (structure tier)
    pilib index-md --pages pages.md --toc toc.json --book-id ID --title T [--author A] [--summaries ...]
                                        # the same, from a local reading document and a table of contents file
    pilib index-pdf <pdf> --book-id ID --title T [--author A] [--summaries none|gemini]
                                        # an original PDF with PageIndex Flash (structure tier)
    pilib export-trove <trove-id> --book-id ID [--author A]            # Trove -> PDF with the hinted outline -> Flash
    pilib render-trove <trove-id> --book-id ID --title T [...]         # Trove text -> outline-less PDF + pagemap.json
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

from . import __version__
from . import library as lib
from .errors import IndexFailure, scrub

MAX_READ_PAGES = 10
TIER_RANK = {"read": 0, "core": 1, "structure": 2}


def probe(name: str):
    """Import `name`; None when it is not usable here."""
    import importlib
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def distribution_version(name: str):
    try:
        from importlib import metadata
        return metadata.version(name)
    except Exception:
        module = sys.modules.get(name)
        return getattr(module, "__version__", None) if module else None


def cmd_health(a):
    from .config import pageindex_commit
    r = lib.root()
    r.mkdir(parents=True, exist_ok=True)
    probe_file = r / ".health"
    probe_file.write_text("ok")
    probe_file.unlink()
    with contextlib.redirect_stdout(sys.stderr):
        has_litellm = distribution_version("litellm") is not None or probe("litellm") is not None
        has_pageindex = probe("pageindex.flash.api") is not None
        has_weasyprint = probe("weasyprint") is not None
    tier = "structure" if has_pageindex and has_weasyprint and has_litellm else "core" if has_litellm else "read"
    out = {"ok": True, "pilib_version": __version__, "python": ".".join(str(n) for n in sys.version_info[:3]),
           "tier": tier, "pageindex_commit": pageindex_commit() if has_pageindex else None,
           "litellm": distribution_version("litellm") if has_litellm else None, "pageindex": has_pageindex,
           "weasyprint": has_weasyprint, "library": str(r), "books": len(lib.catalog()["books"])}
    if a.require and TIER_RANK[tier] < TIER_RANK[a.require]:
        out["ok"] = False
        out["error"] = f"this machine can run the {tier} tier, not the {a.require} tier"
        print(json.dumps(out))
        sys.exit(1)
    print(json.dumps(out))


def run_index(command: str, fn, a) -> None:
    """Run one index command: stdout carries exactly one JSON object, stderr the human text, exit 1 on failure."""
    try:
        with contextlib.redirect_stdout(sys.stderr):  # a library's own prints must not break the JSON
            result = fn(a)
    except IndexFailure as failure:
        print(json.dumps({"ok": False, "command": command, "code": failure.code_name, "error": failure.message,
                          **failure.extra}, ensure_ascii=False))
        print(f"ERROR library index: {failure.message}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        message = scrub(f"{type(error).__name__}: {error}")
        print(json.dumps({"ok": False, "command": command, "code": "internal", "error": message}, ensure_ascii=False))
        print(f"ERROR library index: {message}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False))


def cmd_index_trove(a):
    from .native import index_trove
    run_index("index-trove", index_trove, a)


def cmd_index_md(a):
    from .native import index_md
    run_index("index-md", index_md, a)


def cmd_index_pdf(a):
    from .index import index_pdf, index_pdf_full
    if a.summaries == "gemini":
        meta = index_pdf_full(Path(a.pdf), a.book_id, a.title, a.author or "", model=a.model,
                              summary_concurrency=a.concurrency, max_calls=a.max_calls)
    else:
        meta = index_pdf(Path(a.pdf), a.book_id, a.title, a.author or "")
    print(json.dumps(meta, ensure_ascii=False))


def cmd_export_trove(a):
    from .index import index_pdf
    from .trove_export import export
    pdf = lib.book_dir(a.book_id) / "source.pdf"
    info, texts = export(a.trove_id, pdf)
    meta = index_pdf(pdf, a.book_id, info["title"], a.author or "",
                     origin={"trove": info}, require_outline=True, page_text=texts)
    print(json.dumps({"export": info, "index": meta}, ensure_ascii=False))


def cmd_render_trove(a):
    from .render_trove import run
    info = run(a.trove_id, a.book_id, a.title, a.author or "", a.pages, a.drop_pages,
               Path(a.out).expanduser() if a.out else None)
    print(json.dumps(info, ensure_ascii=False))


def shelf_ids(path: str | None) -> list[str] | None:
    if not path:
        return None
    data = json.loads(Path(path).read_text())
    return data["books"] if isinstance(data, dict) else data


def cmd_catalog(a):
    books = lib.catalog()["books"]
    ids = shelf_ids(a.shelf)
    if ids is not None:
        books = {k: v for k, v in books.items() if k in ids}
    print(json.dumps(books, ensure_ascii=False, indent=1))


def cmd_list(_):
    for book_id, b in sorted(lib.catalog()["books"].items()):
        print(f"{book_id}\t{b['n_pages']} pp\t{b['toc_source']}\t{b['title']}")


def slim(nodes, max_title):
    out = []
    for n in nodes or []:
        item = {"node_id": n.get("node_id"), "title": n["title"][:max_title],
                "start_index": n["start_index"], "end_index": n["end_index"]}
        summ = (n.get("summary") or n.get("prefix_summary") or "").strip()
        if summ:
            item["summary"] = summ[:400]
        if n.get("nodes"):
            item["nodes"] = slim(n["nodes"], max_title)
        out.append(item)
    return out


def cmd_tree(a):
    from .treeview import view
    tree = lib.load_tree(a.book_id)
    structure, note = view(slim(tree["structure"], a.max_title), depth=a.depth, node=a.node)
    out = {"book_id": a.book_id, "title": tree["title"], "n_pages": tree["n_pages"], "structure": structure}
    if note:
        out["note"] = note
    print(json.dumps(out, ensure_ascii=False))


def cmd_read(a):
    pages = lib.load_pages(a.book_id)
    wanted = lib.parse_ranges(a.pages, len(pages))
    if not wanted:
        raise SystemExit(f"no pages in range {a.pages!r} (book has {len(pages)})")
    if a.json:  # machine-readable: no per-call page cap, `all` allowed
        out = {"book_id": a.book_id,
               "pages": [{"page": p, "content": pages[p - 1].rstrip()} for p in wanted]}
        print(json.dumps(out, ensure_ascii=False))
        return
    if len(wanted) > MAX_READ_PAGES:
        raise SystemExit(f"asked for {len(wanted)} pages; at most {MAX_READ_PAGES} per read")
    for p in wanted:
        print(f"── Page {p} ──")
        print(pages[p - 1].rstrip())


def cmd_meta(a):
    d = lib.book_dir(a.book_id)
    meta = lib.read_json(d / "meta.json")
    if meta is None:
        raise SystemExit(f"book not indexed: {a.book_id}")
    side = lib.read_json(d / "pagemap.json")
    pagemap = side.get("pdf_to_trove") if isinstance(side, dict) else None
    origin = meta.get("origin") or {}
    trove_id = (origin.get("trove") or {}).get("trove_id") or (side or {}).get("trove_id")
    n_pages = meta.get("n_pages")
    if n_pages is None:
        n_pages = lib.catalog()["books"].get(a.book_id, {}).get("n_pages")
    print(json.dumps({"book_id": a.book_id, "title": meta.get("title"), "n_pages": n_pages,
                      "origin": origin, "trove_id": trove_id, "pagemap": pagemap},
                     ensure_ascii=False))


def cmd_verify(a):
    problems, ok_books = [], 0
    for book_id in sorted(lib.catalog()["books"]):
        d = lib.book_dir(book_id)
        tree, pages, meta = (lib.read_json(d / f) for f in ("tree.json", "pages.json", "meta.json"))
        if not (tree and pages and meta):
            problems.append(f"{book_id}: missing tree/pages/meta")
            continue
        n = len(pages)
        nodes = list(lib.iter_nodes(tree["structure"]))
        bad = [x.get("node_id") for x in nodes
               if not (isinstance(x.get("start_index"), int) and isinstance(x.get("end_index"), int)
                       and 1 <= x["start_index"] <= x["end_index"] <= n)]
        llm = [x.get("node_id") for x in nodes if a.no_summary and ("summary" in x or "prefix_summary" in x)]
        if not nodes:
            problems.append(f"{book_id}: empty tree")
        if bad:
            problems.append(f"{book_id}: {len(bad)} nodes with bad page ranges, e.g. {bad[:3]}")
        if llm:
            problems.append(f"{book_id}: {len(llm)} nodes carry LLM summaries")
        if a.require_summary:
            n_sum = sum(1 for x in nodes if (x.get("summary") or x.get("prefix_summary") or "").strip())
            if nodes and n_sum < 0.8 * len(nodes):
                problems.append(f"{book_id}: only {n_sum}/{len(nodes)} nodes carry a summary (< 80%)")
                continue
        elif meta["indexer"].get("llm_calls") != 0:
            problems.append(f"{book_id}: indexer made LLM calls")
        if not (bad or llm or not nodes):
            ok_books += 1
            print(f"ok {book_id}: {n} pages, {len(nodes)} nodes, toc_source={tree['toc_source']}")
    if ok_books < a.min_books:
        problems.append(f"only {ok_books} valid books (< {a.min_books})")
    for p in problems:
        print("FAIL", p, file=sys.stderr)
    sys.exit(1 if problems else 0)


def add_model_flags(s, summaries_default: str, choices=("gemini", "hints", "none")):
    from .config import index_settings
    settings = index_settings()
    s.add_argument("--summaries", choices=choices, default=summaries_default)
    s.add_argument("--model", default=settings["summaryModel"])
    s.add_argument("--max-calls", type=int, default=settings["maxCalls"])
    s.add_argument("--concurrency", type=int, default=settings["concurrency"])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pilib", description="The PageIndex library tool of academic-writer.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("health", help="which tier this machine can run (JSON)")
    s.add_argument("--require", choices=("core", "structure")); s.set_defaults(fn=cmd_health)
    s = sub.add_parser("index-trove", help="index a Trove book from its hinted table of contents")
    s.add_argument("trove_id"); s.add_argument("--book-id"); s.add_argument("--title"); s.add_argument("--author")
    s.add_argument("--no-fallback", action="store_true", help="never use PageIndex structure detection")
    s.add_argument("--dry-run", action="store_true", help="plan only: no library write, no model call")
    add_model_flags(s, "gemini"); s.set_defaults(fn=cmd_index_trove)
    s = sub.add_parser("index-md", help="index a reading document with a table of contents file")
    s.add_argument("--pages", required=True); s.add_argument("--toc", required=True)
    s.add_argument("--book-id", required=True); s.add_argument("--title", required=True); s.add_argument("--author")
    s.add_argument("--page-marker", default=r"# \S", help="regex that starts a page (default: a level-1 heading)")
    s.add_argument("--dry-run", action="store_true", help="plan only: no library write, no model call")
    add_model_flags(s, "gemini"); s.set_defaults(fn=cmd_index_md)
    s = sub.add_parser("index-pdf", help="index a PDF with PageIndex Flash")
    s.add_argument("pdf"); s.add_argument("--book-id", required=True); s.add_argument("--title", required=True)
    s.add_argument("--author"); add_model_flags(s, "none", choices=("none", "gemini")); s.set_defaults(fn=cmd_index_pdf)
    s = sub.add_parser("export-trove"); s.add_argument("trove_id"); s.add_argument("--book-id", required=True)
    s.add_argument("--author"); s.set_defaults(fn=cmd_export_trove)
    s = sub.add_parser("render-trove"); s.add_argument("trove_id"); s.add_argument("--book-id", required=True)
    s.add_argument("--title", required=True); s.add_argument("--author"); s.add_argument("--pages")
    s.add_argument("--drop-pages"); s.add_argument("--out"); s.set_defaults(fn=cmd_render_trove)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    s = sub.add_parser("catalog"); s.add_argument("--shelf"); s.set_defaults(fn=cmd_catalog)
    s = sub.add_parser("tree"); s.add_argument("book_id"); s.add_argument("--max-title", type=int, default=400)
    s.add_argument("--depth", type=int); s.add_argument("--node")
    s.set_defaults(fn=cmd_tree)
    s = sub.add_parser("read"); s.add_argument("book_id"); s.add_argument("pages")
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_read)
    s = sub.add_parser("meta"); s.add_argument("book_id"); s.set_defaults(fn=cmd_meta)
    s = sub.add_parser("verify-library"); s.add_argument("--min-books", type=int, default=1)
    g = s.add_mutually_exclusive_group()
    g.add_argument("--no-summary", action="store_true"); g.add_argument("--require-summary", action="store_true")
    s.set_defaults(fn=cmd_verify)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
