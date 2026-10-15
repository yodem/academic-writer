#!/usr/bin/env python3
"""Deterministic ToC builder for course books: one hinted entry per page.

Dry-run by default (reads pages, writes plans under <registry>/toc-work/).
--apply runs `trove items enrich --toc` only when toc_audit passes on the plan.
Never edits page content.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.toc_audit import (audit_book, audit_toc, fetch_toc, has_hint,  # noqa: E402
                             load_registry, load_toc_json, registry_dir)

HINT_MAX = 160
LOAD_MAX = 240
LOAD_RE = re.compile(r"^>\s*Load this page when:\s*(.*)$", re.I)
PAGE_MARK_RE = re.compile(r"\s*·\s*pp?\.\s*[\w\-–]+\s*$")
LESSON_RE = re.compile(r"^שיעור\s+\d+")
GUIDE_RE = re.compile(r"Reading guide|מדריך קריאה|מדריך לקריאה", re.I)


def extract_heading(text: str) -> str:
    for line in text.splitlines():
        m = re.match(r"^#{1,6}\s+(.*\S)\s*$", line)
        if m:
            title = PAGE_MARK_RE.sub("", m.group(1)).strip()
            return title.replace(" - ", " – ")
    return ""


def _cut(s: str, limit: int) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= limit:
        return s.rstrip(".")
    cut = s[: limit - 1]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > limit // 2 else cut).rstrip(" ,;:") + "…"


def _first_sentence(s: str) -> str:
    return re.split(r"(?<=[.!?])\s", s.strip(), maxsplit=1)[0]


def extract_hint(text: str) -> str:
    """`Load this page when:` text if present, else first sentence of first paragraph."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = LOAD_RE.match(line.strip())
        if m:
            buf = [m.group(1)]
            for nxt in lines[i + 1:]:
                if nxt.startswith(">") and nxt.strip(">").strip():
                    buf.append(nxt.lstrip("> ").strip())
                else:
                    break
            hint = " ".join(buf).strip()
            if hint:
                return _cut(hint, LOAD_MAX)
    seen_heading = False
    para: list[str] = []
    for line in lines:
        s = line.strip()
        if not seen_heading:
            seen_heading = bool(re.match(r"^#{1,6}\s", s))
            continue
        if not s:
            if para:
                break
            continue
        if re.match(r"^(#{1,6}\s|>|[-*+]\s|\||```|\d+[.)]\s)", s) or re.fullmatch(r"\*\*[^*]+\*\*|_[^_]+_", s):
            if para:
                break
            continue
        para.append(s)
    if para:
        return _cut(_first_sentence(" ".join(para)), HINT_MAX)
    return ""


def merge_existing(entries: list[dict]) -> dict:
    """Collapse same-page entries: shallowest title/level, merged hints."""
    best = min(entries, key=lambda e: e.get("level", 1))  # min is stable: first of ties
    head, _, hint = str(best.get("title", "")).partition(" - ")
    hints = [hint.strip()] if hint.strip() else []
    for e in entries:
        if e is best:
            continue
        h = str(e.get("title", "")).partition(" - ")[2].strip()
        if h and h not in hints:
            hints.append(h)
    merged = "; ".join(hints)
    if len(entries) > 1 and len(merged) > LOAD_MAX:
        merged = _cut(merged, LOAD_MAX)
    return {"title": head.strip(), "hint": merged, "level": best.get("level", 1)}


def classify(heading: str) -> str:
    if heading == "תמלולי שיעורים":
        return "lessons_index"
    if heading == "חומרי קריאה":
        return "readings_index"
    if heading.startswith("Course · Changelog"):
        return "changelog"
    if LESSON_RE.match(heading):
        return "lesson"
    if GUIDE_RE.search(heading):
        return "guide"
    return "other"


def build_plan(page_count: int, existing: list[dict], get_page, hints: dict | None = None) -> dict:
    """Return {toc, needs_hint, counts}. get_page(n) -> markdown text."""
    hints = {int(k): str(v).strip() for k, v in (hints or {}).items()}
    by_page: dict[int, list[dict]] = {}
    for e in existing:
        p = e.get("page")
        if isinstance(p, int) and 1 <= p <= page_count:
            by_page.setdefault(p, []).append(e)
    toc, needs, state = [], [], None
    counts = {"pages": page_count, "reused": 0, "derived": 0, "supplied": 0, "needs_hint": 0, "merged": 0}
    prev_level = 0
    for p in range(1, page_count + 1):
        text = get_page(p)
        heading = extract_heading(text)
        kind = classify(heading)
        ex = merge_existing(by_page[p]) if p in by_page else None
        if ex and len(by_page[p]) > 1:
            counts["merged"] += 1
        title = (ex or {}).get("title") or heading or f"Page {p}"
        if p in hints and hints[p]:
            hint, src = hints[p], "supplied"
        elif ex and ex["hint"]:
            hint, src = ex["hint"], "reused"
        else:
            hint, src = extract_hint(text), "derived"
        # level
        if p == 1:
            default = 1
        elif kind in ("lessons_index", "readings_index", "changelog"):
            default = 1
        elif kind == "lesson":
            default = 2
        elif kind == "guide":
            default = 2
        elif state == "readings":
            default = 3
        elif state == "lessons":
            default = 2
        else:
            default = prev_level or 1
        level = ex["level"] if ex else default
        level = max(1, min(level, prev_level + 1))
        if p == 1 or kind in ("changelog",):
            state = None
        elif kind in ("lessons_index", "lesson"):
            state = "lessons"
        elif kind in ("readings_index", "guide"):
            state = "readings"
        if hint:
            counts[src] += 1
            toc.append({"title": f"{title} - {hint}", "page": p, "level": level})
        else:
            counts["needs_hint"] += 1
            toc.append({"title": title, "page": p, "level": level})
            needs.append({"page": p, "title": title, "first_800_chars": text[:800]})
        prev_level = level
    return {"toc": toc, "needs_hint": needs, "counts": counts}


def trove_get_page(book_id: str, page: int) -> str:
    r = subprocess.run(["trove", "items", "get", f"{book_id}:{page}", "--no-session"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"trove items get {book_id}:{page} failed: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def book_version(book_id: str) -> int:
    r = subprocess.run(["trove", "items", "history", book_id, "--json", "--no-session"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"trove items history failed: {r.stderr.strip() or r.stdout.strip()}")
    return int(json.loads(r.stdout)["currentVersion"])


def gate(plan_toc: list[dict], page_count: int) -> dict:
    """audit_toc on the planned ToC; callers must refuse to apply unless ok."""
    return audit_toc(plan_toc, page_count)


def apply_plan(book_id: str, plan_toc: list[dict], page_count: int, planned_version: int,
               before_entries: int, run=subprocess.run, version_fn=book_version) -> tuple[int, str]:
    audit = gate(plan_toc, page_count)
    if not audit["ok"]:
        return 1, "refused: planned ToC fails audit " + json.dumps(
            {k: v for k, v in audit.items() if k != "ok" and v}, ensure_ascii=False)[:600]
    now = version_fn(book_id)
    if now != planned_version:
        return 1, f"refused: book version changed {planned_version} -> {now}; rerun"
    r = run(["trove", "items", "enrich", book_id, "--toc", json.dumps(plan_toc, ensure_ascii=False),
             "--no-session"], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        return 1, f"enrich failed: {(r.stderr or r.stdout).strip()}"
    return 0, f"applied: entries {before_entries} -> {len(plan_toc)}, pages {page_count}"


def course_hints(hints: dict, slug: str) -> dict:
    if any(not str(k).isdigit() for k in hints):  # keyed by slug
        return hints.get(slug, {})
    return hints


def process_course(c: dict, work: Path, hints: dict, apply: bool, out=print) -> int:
    slug, bid = c["slug"], c.get("book_id")
    if not bid:
        out(f"{slug}: no book_id in registry")
        return 1
    existing, n, _ = fetch_toc(bid)
    version = book_version(bid)
    plan = build_plan(n, existing, lambda p: trove_get_page(bid, p), course_hints(hints, slug))
    work.mkdir(parents=True, exist_ok=True)
    (work / f"{slug}.plan.json").write_text(json.dumps(
        {"slug": slug, "book_id": bid, "version": version, "page_count": n,
         "counts": plan["counts"], "toc": plan["toc"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    nh = work / f"{slug}.needs-hint.json"
    if plan["needs_hint"]:
        nh.write_text(json.dumps(plan["needs_hint"], ensure_ascii=False, indent=2), encoding="utf-8")
    elif nh.exists():
        nh.unlink()
    c_ = plan["counts"]
    out(f"{slug}: pages={c_['pages']} reused={c_['reused']} derived={c_['derived']} "
        f"supplied={c_['supplied']} merged={c_['merged']} needs-hint={c_['needs_hint']} "
        f"(entries before={len(existing)} after={len(plan['toc'])})")
    if apply:
        code, msg = apply_plan(bid, plan["toc"], n, version, len(existing))
        out(f"{slug}: {msg}")
        return code
    return 3 if plan["needs_hint"] else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build one hinted ToC entry per page for course books (dry-run by default).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="every course in the registry")
    g.add_argument("--course", help="one course slug")
    ap.add_argument("--hints", help='JSON file: {"<page>": "hint"} (single course) or {"<slug>": {"<page>": "hint"}}')
    ap.add_argument("--apply", action="store_true", help="write the ToC to Trove (only if the audit passes)")
    args = ap.parse_args(argv)
    courses = load_registry()
    if args.course:
        courses = [c for c in courses if c["slug"] == args.course]
        if not courses:
            print(f"no course with slug {args.course!r} in {registry_dir()}", file=sys.stderr)
            return 2
    hints = json.loads(Path(args.hints).read_text(encoding="utf-8")) if args.hints else {}
    work = registry_dir() / "toc-work"
    codes = []
    for c in courses:  # sequential: low-RAM host
        try:
            codes.append(process_course(c, work, hints, args.apply))
        except Exception as exc:  # noqa: BLE001
            print(f"{c['slug']}: ERROR {exc}", file=sys.stderr)
            codes.append(1)
    return 1 if 1 in codes else 3 if 3 in codes else 0


if __name__ == "__main__":
    sys.exit(main())
