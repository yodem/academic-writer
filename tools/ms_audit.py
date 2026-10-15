#!/usr/bin/env python3
"""Audit that every course manuscript's instructions carry the registry facts.

Usage: python3 tools/ms_audit.py [--course slug] [--json] [--instructions-dir DIR]
Exit 0 only if every audited manuscript passes.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

TOC_RULE = 'ToC rule: one entry per page, "Title - hint", nested, in page order.'
LESSON_RULE = (
    "Lesson recordings: the 'תמלולי שיעורים' entry page explains the course; "
    "each lesson page ('שיעור NN · <date>') sits under it in the sidebar "
    "(written by /academic-writer:lesson-notes)."
)
DEFAULT_REGISTRY = Path.home() / ".academic-writer" / "courses" / "תשפ״ז"
SKIP_FILES = {"term.json", "links.json"}


def registry_dir() -> Path:
    env = os.environ.get("ACADEMIC_COURSES_DIR")
    return Path(env) if env else DEFAULT_REGISTRY


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


def lemida_token(course: dict) -> str:
    lid = course.get("lemida_course_id")
    return "none" if lid is None else str(lid)


def drive_link(course: dict) -> str:
    return f"https://drive.google.com/drive/folders/{course.get('drive_folder_id')}"


def render_instructions_block(course: dict) -> str:
    """Canonical block the audit requires; T10 writes exactly this."""
    return "\n".join([
        f"Lemida course id: {lemida_token(course)}",
        f"NotebookLM id: {course.get('notebook_id')}",
        f"Drive folder: {drive_link(course)}",
        TOC_RULE,
        LESSON_RULE,
    ])


def required_items(course: dict) -> dict[str, str]:
    return {
        "lemida_id": lemida_token(course),
        "notebook_id": str(course.get("notebook_id")),
        "drive_link": drive_link(course),
        "toc_rule": TOC_RULE,
    }


def check_instructions(course: dict, instructions: str) -> list[str]:
    return [k for k, v in required_items(course).items() if v not in instructions]


def fetch_instructions(course: dict, instructions_dir: Path | None) -> str | None:
    if instructions_dir is not None:
        f = instructions_dir / f"{course['slug']}.txt"
        return f.read_text(encoding="utf-8") if f.is_file() else None
    mid = course.get("manuscript_id")
    if not mid:
        return None
    try:
        r = subprocess.run(["trove", "ms", "show", mid, "--json", "--no-session"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return None
        return json.loads(r.stdout).get("instructions") or ""
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def audit(courses: list[dict], instructions_dir: Path | None = None) -> list[dict]:
    results = []
    for c in courses:
        text = fetch_instructions(c, instructions_dir)
        if text is None:
            results.append({"slug": c["slug"], "manuscript_id": c.get("manuscript_id"),
                            "ok": False, "missing": ["instructions_unavailable"]})
            continue
        missing = check_instructions(c, text)
        results.append({"slug": c["slug"], "manuscript_id": c.get("manuscript_id"),
                        "ok": not missing, "missing": missing})
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--course", help="audit one course slug")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--instructions-dir", type=Path,
                    help="offline mode: read <slug>.txt instead of calling trove")
    args = ap.parse_args(argv)
    courses = load_courses()
    if args.course:
        courses = [c for c in courses if c["slug"] == args.course]
        if not courses:
            print(f"unknown course: {args.course}", file=sys.stderr)
            return 2
    results = audit(courses, args.instructions_dir)
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
