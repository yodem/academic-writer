"""Coverage gate for the nightly Lemida watch: did the scan look at everything it had to?

`watch-lemida` writes `REG/logs/lemida-coverage-<YYYY-MM-DD>.json` (see `check`'s docstring for the shape).
`courses.py lemida-coverage-check` reads that file and exits 1, printing every gap, when the watch skipped
an active course, left an assignment unhandled or did not open a listed notification. Python decides; the
watch only reports what it did.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import chores
import courses


def coverage_path(registry: courses.Registry, day: str) -> Path:
    return registry.directory / "logs" / f"lemida-coverage-{day}.json"


def today(registry: courses.Registry) -> str:
    zone = registry.term.get("timezone", "Asia/Jerusalem")
    return datetime.now(ZoneInfo(zone)).strftime("%Y-%m-%d")


def _ids(value: Any) -> set[str]:
    return {str(item) for item in (value or [])}


def _lemida_id_chore(registry: courses.Registry, slug: str) -> None:
    chores.add_chore(
        registry, course=slug, kind="manual", ref=f"lemida-id-{slug}",
        title=f"Lemida: no course id for {slug}",
        text=(f"The nightly Lemida watch could not scan {slug}: its course JSON has no lemida_course_id. "
              "Find the Lemida course id (the id= in course/view.php?id=N) and set it in the course JSON."),
    )


def check(registry: courses.Registry, day: str) -> list[str]:
    """Return the gaps of the coverage file for `day` (empty = clean). Adds a manual chore per active course without a Lemida id.

    The file is `{"date", "courses": {slug: {"visited": bool, "new_assign_modules": [ids], "assign_handled": [ids]}},
    "notifications": {"page": url, "listed": [ids], "opened": [ids]}}`."""
    path = coverage_path(registry, day)
    if not path.is_file():
        return [f"coverage file missing: {path}"]
    data = json.loads(path.read_text(encoding="utf-8"))
    covered = data.get("courses") or {}
    gaps: list[str] = []
    for slug in sorted(registry.active_courses()):
        course = registry.courses[slug]
        if not course.get("lemida_course_id"):
            gaps.append(f"{slug}: no lemida_course_id (a manual chore was added)")
            _lemida_id_chore(registry, slug)
            continue
        entry = covered.get(slug) or {}
        if not entry.get("visited"):
            gaps.append(f"{slug}: not visited by the watch")
        missing = sorted(_ids(entry.get("new_assign_modules")) - _ids(entry.get("assign_handled")), key=_sort_key)
        for module in missing:
            gaps.append(f"{slug}: new assign module {module} not handled")
    notifications = data.get("notifications") or {}
    unopened = sorted(_ids(notifications.get("listed")) - _ids(notifications.get("opened")), key=_sort_key)
    for note in unopened:
        gaps.append(f"notification {note} listed but not opened")
    return gaps


def _sort_key(value: str) -> tuple[int, Any]:
    return (0, int(value)) if value.isdigit() else (1, value)
