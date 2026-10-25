"""Drive folder layout for course sources: kind folders, Chicago file names, and the reorg plan.

Every course's Drive root holds these folders, and nothing outside them is left at the root:
    00 כללי/                 the syllabus and the opening
    שיעורים/שיעור NN/        recordings, transcripts and lesson handouts, numbered by lesson order
    קריאות/<citation>/       readings, one folder per source named `Author, Short Title (Year)`
    מטלות/מטלה N/            assignments, numbered by the course's task order
    לא ממוין/                everything else, until the student sorts it

The folder comes from the registry (lesson key, task links, origin, title) and, for unregistered files, from the
file name. Names come from naming.py. Root folders named `שיעור N` / `מטלה N` move under their kind folder.
Pure functions: the caller runs rclone and writes the registry. Standard library only.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote

import naming

GENERAL_DIR = "00 כללי"
LESSONS_DIR = "שיעורים"
READINGS_DIR = "קריאות"
TASKS_DIR = "מטלות"
UNSORTED_DIR = "לא ממוין"
SYLLABUS_RE = re.compile(r"סילבוס|פתיחה|syllabus", re.IGNORECASE)
LESSON_RE = re.compile(r"שיעור\s*(\d+)|lesson\s*(\d+)", re.IGNORECASE)
TASK_RE = re.compile(r"מטלה\s*(\d+)")
LEGACY_LESSON_DIR_RE = re.compile(r"^שיעור\s*(\d+)$")
LEGACY_TASK_DIR_RE = re.compile(r"^מטלה\s*(\d+)$")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,5}$")
PREFIX_RES = (re.compile(r"^[0-9a-f]{8}-"), re.compile(r"^\d{6,8} - "), re.compile(r"^lemida-cm\d+ - "))
DOC_EXTS = {".pdf", ".docx", ".doc", ".md", ".epub", ".txt"}
MEDIA_EXTS = {".mp3", ".m4a", ".mp4", ".opus", ".wav"}
SLIDE_EXTS = {".pptx", ".ppt", ".key"}
SLIDES_DIR = "שיעורים/שקפים"


def _segment(name: str) -> str:
    """One folder or file name segment: no path separators, whitespace collapsed."""
    return " ".join(name.replace("/", "-").replace("\\", "-").split()) or "untitled"


def _clean(text: str) -> str:
    """Display text: the hash, Lemida-id and lemida-cm prefixes removed, whitespace collapsed."""
    changed = True
    while changed:
        changed = False
        for pattern in PREFIX_RES:
            stripped = pattern.sub("", text, count=1)
            if stripped != text:
                text, changed = stripped, True
    return " ".join(text.split()) or "untitled"


def _file_name(source: dict[str, Any]) -> str:
    return Path(str(source.get("file") or source.get("name") or source.get("path") or "")).name


def _stem(name: str) -> str:
    """A file name as a display string: unquoted, extension dropped, prefixes removed."""
    return _clean(EXT_RE.sub("", unquote(name)))


def _label(source: dict[str, Any]) -> str:
    """What a source is called: its cleaned title, else its cleaned file stem."""
    title = " ".join(unquote(str(source.get("title") or "")).split())
    return _clean(title) if title else _stem(_file_name(source))


def _meta(source: dict[str, Any]) -> dict[str, Any]:
    """Citation metadata for a source. Without a citation the display name is its label."""
    meta = naming.meta_from_source(source)
    if not meta.get("raw") and not meta.get("authors"):
        meta["stem"] = _label(source)
    return meta


def _surname(name: str) -> str:
    name = name.strip()
    return name.split(",", 1)[0].strip() if "," in name else (name.split()[-1] if name.split() else name)


def _short_name(meta: dict[str, Any]) -> str:
    """`Author, Short Title (Year)` from the structured fields; empty when there are no author and title."""
    authors = [str(a).strip() for a in meta.get("authors") or [] if str(a).strip()]
    title = " ".join(str(meta.get("title") or "").split())
    if not authors or not title:
        return ""
    lead = _surname(authors[0])
    if len(authors) == 2:
        lead = f"{lead} and {_surname(authors[1])}"
    elif len(authors) > 2:
        lead = f"{lead} et al."
    short = title.split(":", 1)[0].strip().rstrip(".") or title
    return f"{lead}, {short} ({meta.get('year') or 'n.d.'})"


def display_title(source: dict[str, Any]) -> str:
    """The NotebookLM and Trove title: the full Chicago author-date entry, else the cleaned title or file stem."""
    return naming.display_name(_meta(source))


def drive_name(source: dict[str, Any]) -> str:
    """The file and folder name: `Author, Short Title (Year)` for a structured citation, else the display title."""
    meta = _meta(source)
    return _short_name(meta) or naming.display_name(meta)


def lesson_keys(course: dict[str, Any]) -> set[str]:
    keys = {str(item.get("lesson_key", item.get("key", ""))) for item in course.get("lessons", [])}
    keys.discard("")
    return keys


def lesson_number(course: dict[str, Any], lesson_key: str) -> int:
    """1-based position of a lesson among the course's lessons, ordered by key (the key starts with the date)."""
    keys = lesson_keys(course) | {lesson_key}
    return sorted(keys).index(lesson_key) + 1


def task_number(course: dict[str, Any], task_id: str) -> int | None:
    """1-based position of a task in the course's task list, or None when the course does not hold it."""
    for index, task in enumerate(course.get("tasks") or [], start=1):
        if task.get("id") == task_id:
            return index
    return None


def _lesson_folder(number: int) -> str:
    return f"{LESSONS_DIR}/שיעור {number:02d}"


def _task_folder(number: int) -> str:
    return f"{TASKS_DIR}/מטלה {number}"


def _lesson_by_date(course: dict[str, Any], name: str) -> str | None:
    """The lesson folder of the course lesson whose key starts with the date in a file name, if any."""
    match = DATE_RE.search(unquote(name))
    if not match:
        return None
    keys = sorted(key for key in lesson_keys(course) if key.startswith(match.group(0)))
    return _lesson_folder(lesson_number(course, keys[0])) if keys else None


def folder_for(course: dict[str, Any], source: dict[str, Any]) -> str:
    """Drive folder (relative to the course root) a source belongs in. Registry data first, then the name."""
    lesson_key = source.get("lesson_key")
    if lesson_key:
        return _lesson_folder(lesson_number(course, str(lesson_key)))
    label = _label(source)
    ext = Path(_file_name(source)).suffix.lower()
    if source.get("kind") == "media" or (not source.get("kind") and ext in MEDIA_EXTS):
        match = LESSON_RE.search(label)
        if match:
            return _lesson_folder(int(match.group(1) or match.group(2)))
        return _lesson_by_date(course, _file_name(source)) or UNSORTED_DIR
    if ext in SLIDE_EXTS:
        match = LESSON_RE.search(label)
        return _lesson_folder(int(match.group(1) or match.group(2))) if match else SLIDES_DIR
    for task_id in source.get("tasks") or []:
        number = task_number(course, str(task_id))
        if number is not None:
            return _task_folder(number)
    if source.get("origin") == "library" or source.get("ref") or source.get("kind") == "reading":
        return f"{READINGS_DIR}/{_segment(drive_name(source))}"
    match = LESSON_RE.search(label)
    if match:
        return _lesson_folder(int(match.group(1) or match.group(2)))
    match = TASK_RE.search(label)
    if match:
        return _task_folder(int(match.group(1)))
    if SYLLABUS_RE.search(label):
        return GENERAL_DIR
    if ext in DOC_EXTS:
        return f"{READINGS_DIR}/{_segment(drive_name(source))}"
    return UNSORTED_DIR


def drive_path_for(course: dict[str, Any], source: dict[str, Any], taken: dict[str, set[str]], name: str | None = None) -> str:
    """Folder plus file name for a source. `name` (a file name) sets the extension; default is the source's own file.

    `taken` maps each folder to the names already in it; the new name is added to it.
    """
    folder = folder_for(course, source)
    names = taken.setdefault(folder, set())
    ext = Path(name or _file_name(source)).suffix
    file_name = naming.drive_filename({"stem": drive_name(source)}, ext, names)
    names.add(file_name)
    return f"{folder}/{file_name}"


def _match_key(name: str) -> str:
    return _stem(name).casefold()


def _unique(name: str, taken: set[str]) -> str:
    stem, ext = Path(name).stem, Path(name).suffix
    candidate, n = name, 2
    while candidate in taken:
        candidate = f"{stem} ({n}){ext}"
        n += 1
    return candidate


def _legacy_target(name: str) -> str | None:
    """Kind folder for a root folder named `שיעור N` or `מטלה N`; None for any other folder."""
    name = " ".join(unquote(name).split())
    match = LEGACY_LESSON_DIR_RE.match(name)
    if match:
        return _lesson_folder(int(match.group(1)))
    match = LEGACY_TASK_DIR_RE.match(name)
    if match:
        return _task_folder(int(match.group(1)))
    return None


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


def _step(item: dict[str, Any], old: str, new: str, sha256: str) -> dict[str, Any]:
    return {"id": str(item.get("ID", "")), "old": old, "new": new, "sha256": sha256}


def plan_reorg(course: dict[str, Any], listing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Moves that put the course's Drive files into the kind folders under their names.

    `listing` is `rclone lsjson -R` output (files and folders). Steps, in the order they must run:
    1. a root folder `שיעור N` / `מטלה N` moves as a whole into שיעורים/ / מטלות/ (merged file by file when the
       kind folder already exists);
    2. each registry source to its folder and name (a source whose file is not listed is skipped, a file already
       at its target is not moved);
    3. each unregistered root file to the folder its name gives, or, when its stem matches a registry source's
       stem, to that source's folder and display name with its own extension.
    Nothing inside a kind folder is moved except registry sources. A step is {id, old, new, sha256}; sha256 is
    empty for a file that is not a registry source and for a folder.
    """
    entries = {_listed_path(item): item for item in listing}
    dirs = {path for path, item in entries.items() if item.get("IsDir")}
    files = {path: item for path, item in entries.items() if not item.get("IsDir")}
    moved_dirs: dict[str, str] = {}
    merged_dirs: dict[str, str] = {}
    for folder in sorted(path for path in dirs if "/" not in path):
        target = _legacy_target(folder)
        if target is None or target == folder:
            continue
        if target in dirs:
            merged_dirs[folder] = target
        else:
            moved_dirs[folder] = target

    def remap(path: str) -> str:
        for old, new in moved_dirs.items():
            if path.startswith(old + "/"):
                return new + path[len(old):]
        return path

    here = {remap(path): item for path, item in files.items()}
    taken: dict[str, set[str]] = {}
    for path in here:
        folder, _, name = path.rpartition("/")
        taken.setdefault(folder, set()).add(name)
    plan: list[dict[str, Any]] = [_step(entries[old], old, new, "") for old, new in moved_dirs.items()]
    matched: list[tuple[dict[str, Any], str]] = []
    for source in course.get("sources", []):
        old = _current_path(source, set(here))
        if old is None:
            continue
        matched.append((source, old))
        folder, _, name = old.rpartition("/")
        taken.get(folder, set()).discard(name)  # a source does not collide with its own file
    for source, old in matched:
        new = drive_path_for(course, source, taken)
        if new != old:
            plan.append(_step(here[old], old, new, source.get("sha256", "")))
    claimed = {old for _, old in matched}
    by_key: dict[str, dict[str, Any]] = {}
    for source in course.get("sources", []):
        if _file_name(source):
            by_key.setdefault(_match_key(_file_name(source)), source)
    for path in sorted(here):
        if "/" in path or path in claimed:
            continue
        source = by_key.get(_match_key(path)) or {"file": path}
        plan.append(_step(here[path], path, drive_path_for(course, source, taken, name=path), ""))
    for folder, target in merged_dirs.items():
        names = taken.setdefault(target, set())
        for path in sorted(p for p in here if p.startswith(folder + "/") and "/" not in p[len(folder) + 1:]):
            if path in claimed:
                continue
            new_name = _unique(path.rsplit("/", 1)[1], names)
            names.add(new_name)
            plan.append(_step(here[path], path, f"{target}/{new_name}", ""))
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
