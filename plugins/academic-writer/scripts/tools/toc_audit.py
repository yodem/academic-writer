#!/usr/bin/env python3
"""Audit Trove table-of-contents structure for course books.

Rules: every page 1..pageCount starts exactly one entry; each title is
"Title - hint" with a non-empty hint; pages strictly increase; the first
level is 1 and a level never rises by more than 1.

Importable: audit_toc, load_toc_json, fetch_toc, registry_dir, load_registry,
audit_book, format_report, missing_from.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SKIP_FILES = {"term.json", "links.json"}

_COURSES = str(Path(__file__).resolve().parents[1] / "src" / "scripts" / "courses")


def registry_dir() -> Path:
    """Term directory, resolved exactly as courses.py does (root + ACADEMIC_TERM / sole term)."""
    if _COURSES not in sys.path:
        sys.path.append(_COURSES)
    import courses
    return courses.registry_dir()


def load_registry(reg: Path | None = None, include_finished: bool = False) -> list[dict]:
    """Active course records (dicts with slug); skips term.json, links.json, slugless files and finished courses."""
    reg = reg or registry_dir()
    out = []
    for p in sorted(reg.glob("*.json")):
        if p.name in SKIP_FILES:
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("slug"):
            if include_finished or not (_finished(data) or _term_finished(reg)):
                out.append(data)
    return out


def _finished(record: dict) -> bool:
    return str(record.get("status", "")) == "finished"


def _term_finished(reg: Path) -> bool:
    try:
        return _finished(json.loads((reg / "term.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return False


def has_hint(title: str, course_name: str | None = None) -> bool:
    """True when the title is "Title - hint". A course name that itself contains " - " is not a hint:
    "Course · <name>" alone fails even though it splits on " - "."""
    head, sep, hint = str(title).partition(" - ")
    if course_name and " ".join(str(title).removeprefix("Course · ").split()) == " ".join(course_name.split()):
        return False
    return bool(sep) and bool(hint.strip()) and bool(head.strip())


READINGS_ENTRY = "חומרי קריאה"


def _norm(value: object) -> str:
    return " ".join(str(value).replace("״", '"').replace("׳", "'").split())


def _label(title: object) -> str:
    return _norm(str(title).split(" - ", 1)[0])


def _is_source(entry_title: object, source_title: str) -> bool:
    t, want = _norm(entry_title), _norm(source_title)
    return t == want or t.startswith(want + " - ")


def registered_source_titles(course: dict) -> list[dict]:
    """The course's finished non-media sources as {"title", "page"}; page is the registered Trove page when the
    source lives in this course book, None for a pointer to its own book."""
    out = []
    for s in course.get("sources", []):
        trove = s.get("trove")
        if not (s.get("title") and s.get("kind") != "media" and s.get("status") == "done"
                and isinstance(trove, dict) and trove.get("book_id")):
            continue
        same = str(trove["book_id"]) == str(course.get("book_id"))
        out.append({"title": str(s["title"]), "page": trove.get("page") if same else None})
    return out


def source_parent_problems(toc: list[dict], sources: list) -> list[dict]:
    """Same rule as courses.py check-source: a source stored in this book (page given) is the level-2 entry
    at its registered page, titled with the source title, under the level-1 readings index; a pointer
    (page None) is a level-2 entry with that title. Plain strings mean title-only (pointer)."""
    parent = next((i for i, e in enumerate(toc) if e.get("level", 1) == 1 and _label(e.get("title", "")) == READINGS_ENTRY), None)
    children: list[dict] = []
    if parent is not None:
        for e in toc[parent + 1:]:
            if e.get("level", 1) <= 1:
                break
            if e.get("level") == 2:
                children.append(e)
    out = []
    for src in sources:
        title, page = (src, None) if isinstance(src, str) else (src["title"], src.get("page"))
        if parent is None:
            out.append({"title": title, "page": page, "reason": f"no level-1 entry {READINGS_ENTRY!r}"})
            continue
        ok = any(_is_source(e.get("title", ""), title) and (page is None or e.get("page") == page) for e in children)
        if not ok:
            at = next((e for e in toc if _is_source(e.get("title", ""), title) and (page is None or e.get("page") == page)), None)
            out.append({"title": title, "page": page if page is not None else (at.get("page") if at else None),
                        "reason": f"not a level-2 entry under {READINGS_ENTRY!r}" if at else "no ToC entry"
                        + (f" at page {page}" if page is not None else "")})
    return out


CROSS_REFERENCE_BLOCKS = ("מקורות ראשוניים", "מקורות משניים", "מטלות")
# Blocks whose entries are the only ones on their pages, so they do count toward missing.
COVERING_BLOCKS = ("מטלות",)


def _cross_reference_entries(toc: list[dict], prefixes: tuple = CROSS_REFERENCE_BLOCKS) -> set[int]:
    """Indices of a cross-reference block: a level-1 entry titled "מקורות ראשוניים"/"מקורות משניים"/"מטלות" and every
    entry under it up to the next level-1 entry. assignment_toc.py builds these, and they repeat source start
    pages on purpose (task entries under "מטלות" share a start page), so duplicate and out_of_order skip them. They still need a hint and a level."""
    out: set[int] = set()
    in_block = False
    for i, e in enumerate(toc):
        if e.get("level", 1) <= 1:
            in_block = _label(e.get("title", "")).startswith(prefixes)
        if in_block:
            out.add(i)
    return out


def audit_toc(toc: list[dict], page_count: int, course_name: str | None = None, sources: list | None = None) -> dict:
    """Return {missing, duplicate, no_hint, out_of_order, level_gap, source_parent, ok}.

    sources: titles of registered sources; each must be a level-2 entry under the readings index
    (source_parent lists the ones that are not), matching courses.py check-source.

    missing: pages with no entry starting there; duplicate: pages with >1 entry;
    no_hint: titles lacking " - hint"; out_of_order: (index, prev_page, page)
    where the page decreases; level_gap: (index, level) violating level rules.
    Cross-reference blocks (see _cross_reference_entries) are exempt from duplicate and out_of_order
    and do not count toward missing, except COVERING_BLOCKS ("מטלות"), whose pages they alone cover.
    """
    exempt = _cross_reference_entries(toc)
    covering = _cross_reference_entries(toc, COVERING_BLOCKS)
    counts: dict[int, int] = {}
    for i, e in enumerate(toc):
        if i not in exempt:
            counts[e.get("page")] = counts.get(e.get("page"), 0) + 1
    covered = set(counts) | {toc[i].get("page") for i in covering}
    missing = [p for p in range(1, page_count + 1) if p not in covered]
    duplicate = sorted(p for p, n in counts.items() if n > 1)
    no_hint = [{"index": i, "page": e.get("page"), "title": e.get("title", "")}
               for i, e in enumerate(toc) if not has_hint(e.get("title", ""), course_name)]
    # Tree order: siblings ascend by page and a child starts after its parent, so a
    # lesson page appended at the end of the book may still nest under its index.
    out_of_order = []
    last_at: dict[int, int] = {}  # level -> page of the latest entry at that level
    for i, e in enumerate(toc):
        if i in exempt:
            continue
        lvl, page = e.get("level", 1), e["page"]
        parent = last_at.get(lvl - 1, 0) if lvl > 1 else 0
        sibling = last_at.get(lvl, 0)
        if page <= parent or page <= sibling:
            out_of_order.append({"index": i, "prev_page": max(parent, sibling), "page": page})
        last_at[lvl] = page
        for deeper in [k for k in last_at if k > lvl]:
            del last_at[deeper]
    level_gap = []
    prev = 0
    for i, e in enumerate(toc):
        lvl = e.get("level", 1)
        if lvl - prev > 1:
            level_gap.append({"index": i, "page": e.get("page"), "level": lvl, "prev_level": prev})
        prev = lvl
    result = {"missing": missing, "duplicate": duplicate, "no_hint": no_hint,
              "out_of_order": out_of_order, "level_gap": level_gap,
              "source_parent": source_parent_problems(toc, sources) if sources else []}
    result["ok"] = not any(result[k] for k in
                           ("missing", "duplicate", "no_hint", "out_of_order", "level_gap", "source_parent"))
    return result


def missing_from(before: list[dict], after: list[dict]) -> list[dict]:
    """Entries of the saved ToC `before` whose (title, level) no longer appears in `after`, in saved order.
    Guards against a re-split that drops a merged entry; added entries are fine."""
    live = {(e.get("title", ""), e.get("level", 1)) for e in after}
    out, seen = [], set()
    for e in before:
        key = (e.get("title", ""), e.get("level", 1))
        if key not in live and key not in seen:
            seen.add(key)
            out.append({"title": key[0], "level": key[1]})
    return out


def load_toc_json(path: str | Path) -> tuple[list[dict], int, str]:
    """Read a saved `trove items toc --json` file -> (toc, pageCount, label)."""
    return parse_toc_payload(json.loads(Path(path).read_text(encoding="utf-8")), str(path))


def parse_toc_payload(data: dict, label: str = "") -> tuple[list[dict], int, str]:
    item = data["items"][0] if "items" in data else data
    toc = item.get("toc") or []
    return toc, int(item.get("pageCount") or 0), item.get("id") or label


def fetch_toc(book_id: str) -> tuple[list[dict], int, str]:
    """Read-only live fetch via the trove CLI."""
    r = subprocess.run(["trove", "items", "toc", book_id, "--json", "--no-session"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"trove items toc {book_id} failed: {r.stderr.strip() or r.stdout.strip()}")
    return parse_toc_payload(json.loads(r.stdout), book_id)


def audit_book(label: str, toc: list[dict], page_count: int, book_id: str = "", course_name: str | None = None,
               sources: list | None = None) -> dict:
    res = audit_toc(toc, page_count, course_name, sources)
    res.update(label=label, book_id=book_id, pages=page_count, entries=len(toc))
    return res


def format_report(results: list[dict]) -> str:
    cols = ("missing", "duplicate", "no_hint", "out_of_order", "level_gap")
    w = max([len(r["label"]) for r in results] + [5])
    lines = [f"{'book':<{w}} {'pages':>5} {'entries':>7} " + " ".join(f"{c[:7]:>7}" for c in cols) + "  status"]
    for r in results:
        err = r.get("error")
        lines.append(f"{r['label']:<{w}} {r['pages']:>5} {r['entries']:>7} "
                     + " ".join(f"{len(r[c]):>7}" for c in cols)
                     + ("  ERROR" if err else "  ok" if r["ok"] else "  FAIL"))
    tot = {c: sum(len(r[c]) for r in results) for c in cols}
    lines.append(f"{'TOTAL':<{w}} {'':>5} {'':>7} " + " ".join(f"{tot[c]:>7}" for c in cols))
    for r in results:
        if r.get("error"):
            lines.append(f"{r['label']}: ERROR {r['error']}")
            continue
        if r["missing"]:
            lines.append(f"{r['label']}: missing pages {r['missing']}")
        if r["duplicate"]:
            lines.append(f"{r['label']}: duplicate start pages {r['duplicate']}")
        for v in r["no_hint"]:
            lines.append(f"{r['label']}: no hint at entry {v['index']} (p.{v['page']}): {v['title']!r}")
        for v in r["out_of_order"]:
            lines.append(f"{r['label']}: out of order at entry {v['index']}: p.{v['prev_page']} -> p.{v['page']}")
        for v in r.get("source_parent", []):
            lines.append(f"{r['label']}: source {v['title']!r} {v['reason']}")
        for v in r["level_gap"]:
            lines.append(f"{r['label']}: level gap at entry {v['index']} (p.{v['page']}): {v['prev_level']} -> {v['level']}")
        for v in r.get("dropped", []):
            lines.append(f"{r['label']}: dropped since the snapshot: {v['title']!r} (level {v['level']})")
    return "\n".join(lines)


def _check_keep_from(result: dict, toc: list[dict], snapshot: str | Path) -> None:
    """Record entries of the saved snapshot that the live ToC dropped; a dropped entry fails the book."""
    result["dropped"] = missing_from(load_toc_json(snapshot)[0], toc)
    if result["dropped"]:
        result["ok"] = False


def run(args) -> tuple[list[dict], int]:
    results: list[dict] = []
    keep_from = getattr(args, "keep_from", None)
    if args.toc_json:
        toc, n, bid = load_toc_json(args.toc_json)
        results.append(audit_book(Path(args.toc_json).name, toc, n, bid))
    elif args.book:
        toc, n, bid = fetch_toc(args.book)
        results.append(audit_book(args.book, toc, n, bid))
        if keep_from:
            _check_keep_from(results[-1], toc, keep_from)
    else:
        # --all works on active courses only; a finished course is reached by naming it with --include-finished --course SLUG
        courses = load_registry(include_finished=bool(args.include_finished and args.course))
        if args.course:
            courses = [c for c in courses if c["slug"] == args.course]
            if not courses:
                print(f"no course with slug {args.course!r} in {registry_dir()}", file=sys.stderr)
                return [], 2
        for c in courses:
            bid = c.get("book_id")
            if not bid:
                results.append({"label": c["slug"], "book_id": "", "pages": 0, "entries": 0, "missing": [],
                                "duplicate": [], "no_hint": [], "out_of_order": [], "level_gap": [],
                                "ok": False, "error": "no book_id in registry"})
                continue
            try:
                toc, n, _ = fetch_toc(bid)
                results.append(audit_book(c["slug"], toc, n, bid, c.get("name"), registered_source_titles(c)))
                if keep_from:
                    _check_keep_from(results[-1], toc, keep_from)
            except Exception as exc:  # noqa: BLE001 - report per book, keep going
                results.append({"label": c["slug"], "book_id": bid, "pages": 0, "entries": 0, "missing": [],
                                "duplicate": [], "no_hint": [], "out_of_order": [], "level_gap": [],
                                "ok": False, "error": str(exc)})
    return results, (0 if results and all(r["ok"] for r in results) else 1)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit Trove ToC structure for course books.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="every course in the registry")
    g.add_argument("--course", help="one course slug from the registry")
    g.add_argument("--book", help="a Trove book id")
    g.add_argument("--toc-json", help="a saved `trove items toc --json` file (no network)")
    ap.add_argument("--keep-from", metavar="TOC_JSON",
                    help="with --course or --book: fail if a title in this saved toc --json is gone from the live ToC")
    ap.add_argument("--include-finished", action="store_true",
                    help="with --course SLUG: audit that one finished course too (never with --all)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    if args.include_finished and not args.course:
        ap.error("--include-finished needs --course SLUG (a finished course is never swept in by --all)")
    if args.keep_from and not (args.course or args.book):
        ap.error("--keep-from needs --course or --book")
    results, code = run(args)
    if args.json:
        print(json.dumps({"ok": code == 0, "books": results}, ensure_ascii=False, indent=2))
    elif results:
        print(format_report(results))
    return code


if __name__ == "__main__":
    sys.exit(main())
