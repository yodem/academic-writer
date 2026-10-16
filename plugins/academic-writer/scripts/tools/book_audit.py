#!/usr/bin/env python3
"""Audit that page 1 of every course book carries the registry facts.

Course books are plain Trove books (no manuscript): page 1 is the course index and the only place outside the
registry that names the course's Lemida id, NotebookLM notebook and Drive folder.

Usage: python3 tools/book_audit.py [--course slug] [--json] [--pages-dir DIR]
Exit 0 only if every audited book passes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SKIP_FILES = {"term.json", "links.json"}
NO_LEMIDA = "למדה: אין"


_COURSES = str(Path(__file__).resolve().parents[1] / "src" / "scripts" / "courses")


def registry_dir() -> Path:
    """Term directory, resolved exactly as courses.py does (root + ACADEMIC_TERM / sole term)."""
    if _COURSES not in sys.path:
        sys.path.append(_COURSES)
    import courses
    return courses.registry_dir()


def load_courses(reg: Path | None = None) -> list[dict]:
    reg = reg or registry_dir()
    courses = []
    for p in sorted(reg.glob("*.json")):
        if p.name in SKIP_FILES:
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("slug"):
            courses.append(data)
    return courses


def lemida_line(course: dict) -> str:
    lid = course.get("lemida_course_id")
    return NO_LEMIDA if lid is None else f"למדה: מזהה {lid}"


def drive_link(course: dict) -> str:
    return f"https://drive.google.com/drive/folders/{course.get('drive_folder_id')}"


def render_ids_block(course: dict) -> str:
    """The id lines page 1 must carry (Hebrew labels, as the course index writes them)."""
    return "\n".join([
        f"- תיקיית Drive: {drive_link(course)}",
        f"- מחברת NotebookLM: {course.get('notebook_id')}",
        f"- {lemida_line(course)}",
    ])


def required_items(course: dict) -> dict[str, str]:
    lid = course.get("lemida_course_id")
    return {
        "lemida_id": NO_LEMIDA if lid is None else str(lid),
        "notebook_id": str(course.get("notebook_id")),
        "drive_link": str(course.get("drive_folder_id")),
    }


def check_page(course: dict, page: str) -> list[str]:
    return [k for k, v in required_items(course).items() if v not in page]


def fetch_page1(course: dict, pages_dir: Path | None) -> str | None:
    if pages_dir is not None:
        f = pages_dir / f"{course['slug']}.md"
        return f.read_text(encoding="utf-8") if f.is_file() else None
    book = course.get("book_id")
    if not book:
        return None
    try:
        r = subprocess.run(["trove", "items", "get", book, "--page", "1", "--no-session"],
                           capture_output=True, text=True, timeout=60)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def audit(courses: list[dict], pages_dir: Path | None = None) -> list[dict]:
    results = []
    for c in courses:
        page = fetch_page1(c, pages_dir)
        if page is None:
            results.append({"slug": c["slug"], "book_id": c.get("book_id"), "ok": False, "missing": ["page1_unavailable"]})
            continue
        missing = check_page(c, page)
        results.append({"slug": c["slug"], "book_id": c.get("book_id"), "ok": not missing, "missing": missing})
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--course", help="audit one course slug")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--pages-dir", type=Path, help="offline mode: read <slug>.md instead of calling trove")
    args = ap.parse_args(argv)
    courses = load_courses()
    if args.course:
        courses = [c for c in courses if c["slug"] == args.course]
        if not courses:
            print(f"unknown course: {args.course}", file=sys.stderr)
            return 2
    results = audit(courses, args.pages_dir)
    failed = [r for r in results if not r["ok"]]
    if args.json:
        print(json.dumps({"ok": not failed, "results": results}, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(f"{'PASS' if r['ok'] else 'FAIL'} {r['slug']}"
                  + ("" if r["ok"] else f" missing: {', '.join(r['missing'])}"))
        print(f"{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
