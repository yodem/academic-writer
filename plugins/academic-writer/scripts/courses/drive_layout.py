"""Drive folder layout for course sources: kind folders, Chicago file names, and the reorg plan.

Every course's Drive root holds these folders, and nothing else is classified:
    00 כללי/                 the syllabus and the opening
    שיעורים/שיעור NN/        recordings and transcripts, numbered by lesson order
    קריאות/<citation>/       readings, one folder per source named by its Chicago entry
    מטלות/מטלה N/            assignments, numbered by the course's task order
    לא ממוין/                everything else, until the student sorts it

The folder comes from registry data only (lesson key, task links, origin, title). Names come from naming.py.
Pure functions: the caller runs rclone and writes the registry. Standard library only.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import naming

GENERAL_DIR = "00 כללי"
LESSONS_DIR = "שיעורים"
READINGS_DIR = "קריאות"
TASKS_DIR = "מטלות"
UNSORTED_DIR = "לא ממוין"
SYLLABUS_RE = re.compile(r"סילבוס|פתיחה|syllabus", re.IGNORECASE)


def _segment(name: str) -> str:
    """One folder or file name segment: no path separators, whitespace collapsed."""
    return " ".join(name.replace("/", "-").replace("\\", "-").split()) or "untitled"


def _meta(source: dict[str, Any]) -> dict[str, Any]:
    """Citation metadata for a source. Without a citation the display name is its cleaned title (else its file stem)."""
    meta = naming.meta_from_source(source)
    title = " ".join(str(source.get("title") or "").split())
    if title and not meta.get("raw") and not meta.get("authors"):
        meta["stem"] = title
    return meta


def display_title(source: dict[str, Any]) -> str:
    """The name a source carries in NotebookLM and in its Drive file: its Chicago entry, else its cleaned title."""
    return naming.display_name(_meta(source))


def lesson_number(course: dict[str, Any], lesson_key: str) -> int:
    """1-based position of a lesson among the course's lessons, ordered by key (the key starts with the date)."""
    keys = {str(item.get("lesson_key", item.get("key", ""))) for item in course.get("lessons", [])}
    keys.discard("")
    keys.add(lesson_key)
    return sorted(keys).index(lesson_key) + 1


def task_number(course: dict[str, Any], task_id: str) -> int | None:
    """1-based position of a task in the course's task list, or None when the course does not hold it."""
    for index, task in enumerate(course.get("tasks") or [], start=1):
        if task.get("id") == task_id:
            return index
    return None


def folder_for(course: dict[str, Any], source: dict[str, Any]) -> str:
    """Drive folder (relative to the course root) a source belongs in. Deterministic from the registry."""
    lesson_key = source.get("lesson_key")
    if lesson_key:
        return f"{LESSONS_DIR}/שיעור {lesson_number(course, str(lesson_key)):02d}"
    if source.get("kind") == "media":
        return UNSORTED_DIR
    for task_id in source.get("tasks") or []:
        number = task_number(course, str(task_id))
        if number is not None:
            return f"{TASKS_DIR}/מטלה {number}"
    if source.get("origin") == "library" or source.get("ref") or source.get("kind") == "reading":
        return f"{READINGS_DIR}/{_segment(display_title(source))}"
    if SYLLABUS_RE.search(str(source.get("title") or "")):
        return GENERAL_DIR
    return UNSORTED_DIR


def drive_path_for(course: dict[str, Any], source: dict[str, Any], taken: dict[str, set[str]]) -> str:
    """Folder plus Chicago file name for a source. `taken` maps each folder to the names already in it; the new name is added."""
    folder = folder_for(course, source)
    names = taken.setdefault(folder, set())
    ext = Path(str(source.get("file") or source.get("name") or "")).suffix
    name = naming.drive_filename(_meta(source), ext, names)
    names.add(name)
    return f"{folder}/{name}"


def _listed_path(item: dict[str, Any]) -> str:
    return str(item.get("Path") or item.get("Name") or "")


def _current_path(source: dict[str, Any], paths: set[str]) -> str | None:
    """Where a source's file sits now: its recorded drive_path, else its legacy name at the Drive root."""
    recorded = source.get("drive_path")
    if recorded and recorded in paths:
        return str(recorded)
    legacy = Path(str(source.get("file") or "")).name
    if legacy and legacy in paths:
        return legacy
    return None


def plan_reorg(course: dict[str, Any], listing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Moves that put each listed source into its kind folder under its Chicago name.

    `listing` is `rclone lsjson -R --files-only` output. A source with no file in the listing is skipped; a
    file already at its target is not moved. Each step is {id, old, new, sha256}.
    """
    files = {_listed_path(item): item for item in listing if not item.get("IsDir")}
    taken: dict[str, set[str]] = {}
    for path in files:
        folder, _, name = path.rpartition("/")
        taken.setdefault(folder, set()).add(name)
    matched: list[tuple[dict[str, Any], str]] = []
    for source in course.get("sources", []):
        old = _current_path(source, set(files))
        if old is None:
            continue
        matched.append((source, old))
        folder, _, name = old.rpartition("/")
        taken.get(folder, set()).discard(name)  # a source does not collide with its own file
    plan: list[dict[str, Any]] = []
    for source, old in matched:
        new = drive_path_for(course, source, taken)
        if new != old:
            plan.append({"id": str(files[old].get("ID", "")), "old": old, "new": new, "sha256": source.get("sha256", "")})
    return plan


def apply_reorg(plan: list[dict[str, Any]], remote: str, root_id: str, log: Path,
                runner: Callable[..., Any] = subprocess.run) -> list[dict[str, Any]]:
    """Run each planned move server-side (rclone moveto keeps the file id) and log it to `log` as JSON lines.

    A failed move raises; the steps already logged stay logged, so the run can be undone from the log.
    """
    done: list[dict[str, Any]] = []
    log.parent.mkdir(parents=True, exist_ok=True)
    for step in plan:
        runner(["rclone", "moveto", f"{remote}:{step['old']}", f"{remote}:{step['new']}", "--drive-root-folder-id", str(root_id)],
               check=True, text=True, capture_output=True)
        entry = {"old": step["old"], "new": step["new"], "id": step["id"], "sha256": step.get("sha256", ""),
                 "at": datetime.now(timezone.utc).isoformat()}
        with log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        done.append(entry)
    return done
