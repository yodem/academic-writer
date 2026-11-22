"""Coverage gate for the nightly Lemida watch: did the scan look at everything it had to, in this run?

`watch-lemida` writes `REG/logs/lemida-coverage-<YYYY-MM-DD>.json` (see `check`'s docstring for the shape) and
writes into it the `run_id` the nightly script passed to the watch. `courses.py lemida-coverage-check --run-id <id>`
reads that file and exits 1, printing every gap, when the report belongs to another run (stale), its schema is
missing or malformed, the watch did not visit an active course, left an assignment unhandled, did not open
a listed notification, or left an open hand-in unchecked or confirmed-but-open. Python decides; the watch only reports what it did.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import chores
import courses

NOTIFICATIONS_URL = "https://lemida.biu.ac.il/message/output/popup/notifications.php"


def coverage_path(registry: courses.Registry, day: str) -> Path:
    return registry.directory / "logs" / f"lemida-coverage-{day}.json"


def _next_day(day: str) -> str:
    try:
        return (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    except ValueError:
        return day


def _run_id_of(path: Path) -> Any:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data.get("run_id") if isinstance(data, dict) else None


def resolve_coverage_path(registry: courses.Registry, day: str, run_id: str) -> tuple[Path, str]:
    """The coverage file of this run and its date: `day`'s, or the next day's when the watch ran past midnight."""
    path = coverage_path(registry, day)
    rolled = coverage_path(registry, _next_day(day))
    if rolled.is_file() and _run_id_of(rolled) == run_id and _run_id_of(path) != run_id:
        # the watch ran past midnight and dated its file by its own clock: this run's report is the next day's file
        return rolled, _next_day(day)
    return path, day


def today(registry: courses.Registry) -> str:
    zone = registry.term.get("timezone", "Asia/Jerusalem")
    return datetime.now(ZoneInfo(zone)).strftime("%Y-%m-%d")


def _is_id_list(value: Any) -> bool:
    return isinstance(value, list) and all(
        (isinstance(item, int) and not isinstance(item, bool)) or isinstance(item, str) for item in value)


def _ids(value: Any) -> set[str]:
    return {str(item) for item in (value or [])}


def _lemida_id_chore(registry: courses.Registry, slug: str) -> None:
    chores.add_chore(
        registry, course=slug, kind="manual", ref=f"lemida-id-{slug}",
        title=f"Lemida: no course id for {slug}",
        text=(f"The nightly Lemida watch could not scan {slug}: its course JSON has no lemida_course_id. "
              "Find the Lemida course id (the id= in course/view.php?id=N) and set it in the course JSON."),
    )


def _course_gaps(slug: str, entry: Any) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{slug}: coverage entry is not an object"]
    gaps: list[str] = []
    if entry.get("visited") is not True:
        gaps.append(f"{slug}: not visited by the watch")
    assign_ok = True
    for key in ("new_assign_modules", "assign_handled"):
        if not _is_id_list(entry.get(key)):
            gaps.append(f"{slug}: {key} is missing or not a list of ids")
            assign_ok = False
    if assign_ok:
        missing = sorted(_ids(entry["new_assign_modules"]) - _ids(entry["assign_handled"]), key=_sort_key)
        for module in missing:
            gaps.append(f"{slug}: new assign module {module} not handled")
    return gaps


def _notification_gaps(notifications: Any) -> list[str]:
    if not isinstance(notifications, dict):
        return ["notifications section missing or not an object"]
    gaps: list[str] = []
    if notifications.get("page") != NOTIFICATIONS_URL:
        gaps.append(f"notifications.page is not {NOTIFICATIONS_URL}")
    if notifications.get("complete") is not True:
        gaps.append("notifications.complete is not true: the watch did not scroll to the end of the list")
    lists_ok = True
    for key in ("listed", "opened"):
        if not _is_id_list(notifications.get(key)):
            gaps.append(f"notifications.{key} is missing or not a list of ids")
            lists_ok = False
    if lists_ok:
        unopened = sorted(_ids(notifications["listed"]) - _ids(notifications["opened"]), key=_sort_key)
        gaps.extend(f"notification {note} listed but not opened" for note in unopened)
        if not _is_id_list(notifications.get("marked_read")):
            gaps.append("notifications.marked_read is missing or not a list of ids")
        else:
            # an unopened one must stay unread (it is already a gap above); every opened one must be marked read
            opened = _ids(notifications["listed"]) & _ids(notifications["opened"])
            unread = sorted(opened - _ids(notifications["marked_read"]), key=_sort_key)
            gaps.extend(f"notification {note} opened but not marked read in Lemida" for note in unread)
    return gaps


def _event_gaps(events: Any) -> list[str]:
    """`events` is the watch's read of the Lemida upcoming-events calendar: every listed event must have its chore."""
    if not isinstance(events, dict):
        return ["events section missing or not an object"]
    gaps: list[str] = []
    if events.get("complete") is not True:
        gaps.append("events.complete is not true: the watch did not read the Lemida upcoming events")
    lists_ok = True
    for key in ("listed", "handled"):
        if not _is_id_list(events.get(key)):
            gaps.append(f"events.{key} is missing or not a list of ids")
            lists_ok = False
    if lists_ok:
        missing = sorted(_ids(events["listed"]) - _ids(events["handled"]), key=_sort_key)
        gaps.extend(f"event {event} listed but has no chore" for event in missing)
    return gaps


def _submission_gaps(registry: courses.Registry, section: Any, only: Iterable[str] | None) -> list[str]:
    """`submissions` is the watch's read of what Lemida shows for each open hand-in (`tasks.open_handins`): every one
    must have a well-formed row that equals it (task, course, cmid, type) and carries an `error` or its type's evidence,
    and a row that proves a hand-in submitted must already have closed its task."""
    import tasks
    if not isinstance(section, dict):
        return ["submissions section missing or not an object"]
    gaps: list[str] = []
    if section.get("complete") is not True:
        gaps.append("submissions.complete is not true: the watch did not check every open hand-in")
    checked = section.get("checked")
    if not isinstance(checked, list):
        gaps.append("submissions.checked is missing or not a list")
        return gaps
    good: dict[str, list[dict[str, Any]]] = {}
    for index, row in enumerate(checked):
        problem = tasks.row_problem(row)
        if problem:
            name = row.get("task") if isinstance(row, dict) else None
            gaps.append(f"submissions.checked[{index}]{f' (task {name})' if isinstance(name, str) and name else ''}: {problem}")
        else:
            good.setdefault(row["task"], []).append(row)
    for handin in tasks.open_handins(registry.directory, only)["handins"]:
        rows = good.get(handin["task"], [])
        exact = [r for r in rows if tasks.row_matches(r, handin)]
        label = f"{handin['course']}: hand-in {handin['task']} ({handin['title']}) not checked in Lemida"
        if not rows:
            gaps.append(label)
        elif not exact:
            gaps.append(f"{label}: its row does not match course {handin['course']}, cmid {handin['cmid']}, type {handin['type']}")
        elif not any(tasks.row_evidence(r) for r in exact):
            gaps.append(f"{label}: its row has neither an error nor the {handin['type']} evidence fields")
        elif any(tasks.confirmed(r) for r in exact if tasks.row_evidence(r)):
            gaps.append(f"{handin['course']}: hand-in {handin['task']} confirmed but not closed: run sync-submissions")
    return gaps


def check(registry: courses.Registry, day: str, run_id: str, only: Iterable[str] | None = None) -> list[str]:
    """Return the gaps of the coverage file for `day` and `run_id` (empty = clean).

    `only` limits the course checks to the named slugs (still active-only; a named unknown slug is a gap).
    Adds a manual chore per checked active course without a Lemida id.

    The file is `{"date": day, "run_id": run_id,
                  "courses": {slug: {"visited": true, "new_assign_modules": [ids], "assign_handled": [ids]}},
                  "notifications": {"page": NOTIFICATIONS_URL, "complete": true, "listed": [ids], "opened": [ids],
                                    "marked_read": [ids]},
                  "events": {"complete": true, "listed": [event ids], "handled": [event ids]},
                  "submissions": {"complete": true,
                                  "checked": [{"task": id, "course": slug, "cmid": id, "type": "assign|quiz|forum", "url": url,
                                               "status"?, "team_status"?, "quiz_review_links"?, "my_user_id"?, "author_ids"?, "error"?}]}}`.
    Every section is validated before any set comparison: a missing or malformed one is a gap."""
    path, day = resolve_coverage_path(registry, day, run_id)
    if not path.is_file():
        return [f"coverage file missing: {path}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"coverage file unreadable: {path}: {exc}"]
    if not isinstance(data, dict):
        return [f"coverage file is not a JSON object: {path}"]

    gaps: list[str] = []
    if data.get("date") != day:
        gaps.append(f"coverage file dated {data.get('date')!r}, expected {day} (stale report)")
    report_run = data.get("run_id")
    if not isinstance(report_run, str) or not report_run:
        gaps.append("coverage file has no run_id")
    elif report_run != run_id:
        gaps.append(f"stale report: run_id {report_run} is not this run ({run_id})")

    active = registry.active_courses()
    if only is None:
        slugs = sorted(active)
    else:
        slugs = []
        requested = sorted(set(only))
        if not requested:
            gaps.append("--courses named no course: nothing was checked")
        for slug in requested:
            if slug not in registry.courses:
                gaps.append(f"{slug}: unknown course (not in the registry)")
            elif slug in active:
                slugs.append(slug)

    covered = data.get("courses")
    if not isinstance(covered, dict):
        gaps.append("courses section missing or not an object")
        covered = {}
    for slug in slugs:
        course = registry.courses[slug]
        absent = course.get("lemida_absent")
        if isinstance(absent, str) and absent.strip() and not course.get("lemida_course_id"):
            continue  # the student marked this course as having no Lemida page (the value says why)
        if not course.get("lemida_course_id"):
            gaps.append(f"{slug}: no lemida_course_id (a manual chore was added)")
            _lemida_id_chore(registry, slug)
            continue
        if slug not in covered:
            gaps.append(f"{slug}: not visited by the watch")
            continue
        gaps.extend(_course_gaps(slug, covered[slug]))

    if "notifications" not in data:
        gaps.append("notifications section missing or not an object")
    else:
        gaps.extend(_notification_gaps(data["notifications"]))
    gaps.extend(_event_gaps(data.get("events")))
    gaps.extend(_submission_gaps(registry, data.get("submissions"), only if only is None else slugs))
    return gaps


def _sort_key(value: str) -> tuple[int, Any]:
    return (0, int(value)) if value.isdigit() else (1, value)
