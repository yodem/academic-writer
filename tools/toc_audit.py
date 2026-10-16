#!/usr/bin/env python3
"""Audit Trove table-of-contents structure for course books.

Rules: every page 1..pageCount starts exactly one entry; each title is
"Title - hint" with a non-empty hint; pages strictly increase; the first
level is 1 and a level never rises by more than 1.

Importable: audit_toc, load_toc_json, fetch_toc, registry_dir, load_registry,
audit_book, format_report.
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


def load_registry(reg: Path | None = None) -> list[dict]:
    """Course records (dicts with slug); skips term.json, links.json, slugless files."""
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
            out.append(data)
    return out


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


def registered_source_titles(course: dict) -> list[str]:
    """Titles of the course's finished non-media sources: each must sit under the readings index."""
    return [str(s["title"]) for s in course.get("sources", [])
            if s.get("title") and s.get("kind") != "media" and s.get("status") == "done"
            and isinstance(s.get("trove"), dict) and s["trove"].get("book_id")]


def source_parent_problems(toc: list[dict], sources: list[str]) -> list[dict]:
    """Same rule as courses.py check-source: a source is a level-2 entry under the level-1 readings index."""
    parent = next((i for i, e in enumerate(toc) if e.get("level", 1) == 1 and _label(e.get("title", "")) == READINGS_ENTRY), None)
    children: list[dict] = []
    if parent is not None:
        for e in toc[parent + 1:]:
            if e.get("level", 1) <= 1:
                break
            if e.get("level") == 2:
                children.append(e)
    out = []
    for title in sources:
        if parent is None:
            out.append({"title": title, "reason": f"no level-1 entry {READINGS_ENTRY!r}"})
        elif not any(_is_source(e.get("title", ""), title) for e in children):
            at = next((e for e in toc if _is_source(e.get("title", ""), title)), None)
            out.append({"title": title, "page": at.get("page") if at else None,
                        "reason": f"not a level-2 entry under {READINGS_ENTRY!r}" if at else "no ToC entry"})
    return out


def audit_toc(toc: list[dict], page_count: int, course_name: str | None = None, sources: list[str] | None = None) -> dict:
    """Return {missing, duplicate, no_hint, out_of_order, level_gap, source_parent, ok}.

    sources: titles of registered sources; each must be a level-2 entry under the readings index
    (source_parent lists the ones that are not), matching courses.py check-source.

    missing: pages with no entry starting there; duplicate: pages with >1 entry;
    no_hint: titles lacking " - hint"; out_of_order: (index, prev_page, page)
    where the page decreases; level_gap: (index, level) violating level rules.
    """
    counts: dict[int, int] = {}
    for e in toc:
        counts[e.get("page")] = counts.get(e.get("page"), 0) + 1
    missing = [p for p in range(1, page_count + 1) if counts.get(p, 0) == 0]
    duplicate = sorted(p for p, n in counts.items() if n > 1)
    no_hint = [{"index": i, "page": e.get("page"), "title": e.get("title", "")}
               for i, e in enumerate(toc) if not has_hint(e.get("title", ""), course_name)]
    # Tree order: siblings ascend by page and a child starts after its parent, so a
    # lesson page appended at the end of the book may still nest under its index.
    out_of_order = []
    last_at: dict[int, int] = {}  # level -> page of the latest entry at that level
    for i, e in enumerate(toc):
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
               sources: list[str] | None = None) -> dict:
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
    return "\n".join(lines)


def run(args) -> tuple[list[dict], int]:
    results: list[dict] = []
    if args.toc_json:
        toc, n, bid = load_toc_json(args.toc_json)
        results.append(audit_book(Path(args.toc_json).name, toc, n, bid))
    elif args.book:
        toc, n, bid = fetch_toc(args.book)
        results.append(audit_book(args.book, toc, n, bid))
    else:
        courses = load_registry()
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
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    results, code = run(args)
    if args.json:
        print(json.dumps({"ok": code == 0, "books": results}, ensure_ascii=False, indent=2))
    elif results:
        print(format_report(results))
    return code


if __name__ == "__main__":
    sys.exit(main())
