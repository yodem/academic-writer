"""Drive folder layout for course sources: kind folders, Chicago file names, and the reorg plan.

Every course's Drive root holds these folders, and nothing outside them is left at the root:
    00 כללי/                 the syllabus and the opening
    שיעורים/שיעור NN/        recordings, transcripts and lesson handouts, numbered by lesson order
    קריאות/<citation>/       readings, one folder per source named `Author, Short Title (Year)`
    מטלות/מטלה N/            assignments, numbered by the course's task order
    לא ממוין/                everything else, until the student sorts it

The folder comes from the registry (lesson key, task links, origin, title) and, for unregistered files, from the
file name. Names come from naming.py. Root folders named `שיעור N` / `מטלה N` move under their kind folder.
Moves are planned from one full listing and applied by Drive file id (`rclone backend moveid`), never by path,
so duplicate names cannot be mixed up. Nothing is replaced: every occupied path is reserved, a clash gets a
" (2)" suffix, and a cycle of moves is broken through a temporary name. The whole plan is journaled (fsynced)
before the first move; each move, registry update and NotebookLM rename then gets an intent line before it runs and
a done line after it, so a crash can be resumed from the journal by checking each file id. Standard library only.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
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


TRANSCRIPT_EXTS = {".txt", ".md", ".vtt", ".srt"}
TRANSCRIPT_RE = re.compile(r"^(wispr|zoom)[-_ ]|__zoom|transcript|תמלול", re.IGNORECASE)
NAME_DATE_RE = re.compile(r"(20\d{2})-?(\d{2})-?(\d{2})")


GENERIC_TITLE_RE = re.compile(r"^(שיעור\s*\d+|סילבוס|syllabus|מבוא|פתיחה|lesson\s*\d+)$", re.IGNORECASE)
MACHINE_NAME_RE = re.compile(r"^[\d\W_]+$")


def _lesson_title(course: dict[str, Any] | None, source: dict[str, Any]) -> str:
    """`תמלול שיעור NN · DD.MM.YYYY` for a lesson transcript, `הקלטת שיעור NN · …` for a recording, when its own name is
    machine-made (wispr-…, zoom-…, a bare date and time). A recording or transcript with a real title keeps it."""
    file_name = _file_name(source)
    ext = Path(file_name).suffix.lower()
    label = _label(source)
    media = source.get("kind") == "media" or ext in MEDIA_EXTS
    machine = bool(TRANSCRIPT_RE.search(_stem(file_name) + " " + label)) or bool(MACHINE_NAME_RE.match(label))
    if not machine or not (media or ext in TRANSCRIPT_EXTS):
        return ""
    key = str(source.get("lesson_key") or "")
    number = None
    if course is not None:
        if key:
            number = lesson_number(course, key)
        else:
            folder = _lesson_by_date(course, file_name) or ""
            found = re.search(r"שיעור (\d+)$", folder)
            number = int(found.group(1)) if found else None
    date = NAME_DATE_RE.search(key) or NAME_DATE_RE.search(file_name)
    word = "תמלול" if ext in TRANSCRIPT_EXTS else "הקלטת"  # a transcript stays a transcript even when registered as media
    title = f"{word} שיעור {number:02d}" if number else f"{word} שיעור"
    return f"{title} · {date.group(3)}.{date.group(2)}.{date.group(1)}" if date else title


def drive_name(source: dict[str, Any], course: dict[str, Any] | None = None) -> str:
    """The file and folder name: `Author, Short Title (Year)` for a structured citation; for a lesson transcript or
    recording, its lesson and date; else the display title, or the fuller original file name when the title is only a
    generic part of it (a lecturer's "שיעור 1" in "תפיסות יסוד בספרות הנבואה שיעור 1")."""
    meta = _meta(source)
    short = _short_name(meta)
    if short or meta.get("raw"):
        return short or naming.display_name(meta)
    lesson = _lesson_title(course, source)
    if lesson:
        return lesson
    label, stem = _label(source), _stem(_file_name(source))
    if GENERIC_TITLE_RE.match(label) and len(stem) > len(label) and label.casefold() in stem.casefold():
        return stem
    return naming.display_name(meta)


def lesson_keys(course: dict[str, Any]) -> set[str]:
    keys = {str(item.get("lesson_key", item.get("key", ""))) for item in course.get("lessons", [])}
    keys.discard("")
    return keys


LESSON_PATH_RE = re.compile(r"^" + re.escape(LESSONS_DIR) + r"/שיעור (\d+)/")


def assigned_lesson_numbers(course: dict[str, Any]) -> dict[str, int]:
    """Lesson numbers already given on Drive: a recording's recorded drive_path names its lesson folder."""
    out: dict[str, int] = {}
    for source in course.get("sources", []):
        match = LESSON_PATH_RE.match(str(source.get("drive_path") or ""))
        if source.get("lesson_key") and match:
            out.setdefault(str(source["lesson_key"]), int(match.group(1)))
    return out


def lesson_number(course: dict[str, Any], lesson_key: str) -> int:
    """1-based lesson folder number. A lesson that already has a folder keeps it, so numbers never shift; before any
    folder exists the lessons are numbered by key (the key starts with the date); a later lesson takes the next number."""
    assigned = assigned_lesson_numbers(course)
    if lesson_key in assigned:
        return assigned[lesson_key]
    unassigned = sorted((lesson_keys(course) | {lesson_key}) - set(assigned))
    return max(assigned.values(), default=0) + unassigned.index(lesson_key) + 1


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
    if ext in TRANSCRIPT_EXTS and _lesson_title(None, source):
        # a machine-named lesson transcript (wispr-…, zoom-…): its lesson by date, else the transcripts folder
        return _lesson_by_date(course, _file_name(source)) or f"{LESSONS_DIR}/תמלולים"
    for task_id in source.get("tasks") or []:
        number = task_number(course, str(task_id))
        if number is not None:
            return _task_folder(number)
    if source.get("origin") == "library" or source.get("ref") or source.get("kind") == "reading":
        return f"{READINGS_DIR}/{_segment(drive_name(source, course))}"
    match = LESSON_RE.search(label)
    if match:
        return _lesson_folder(int(match.group(1) or match.group(2)))
    match = TASK_RE.search(label)
    if match:
        return _task_folder(int(match.group(1)))
    if SYLLABUS_RE.search(label):
        return GENERAL_DIR
    if ext in DOC_EXTS:
        return f"{READINGS_DIR}/{_segment(drive_name(source, course))}"
    return UNSORTED_DIR


def drive_path_for(course: dict[str, Any], source: dict[str, Any], taken: dict[str, set[str]], name: str | None = None) -> str:
    """Folder plus file name for a source. `name` (a file name) sets the extension; default is the source's own file.

    `taken` maps each folder to the names already in it; the new name is added to it.
    """
    folder = folder_for(course, source)
    names = taken.setdefault(folder, set())
    ext = Path(name or _file_name(source)).suffix
    file_name = naming.drive_filename({"stem": drive_name(source, course)}, ext, names)
    names.add(file_name)
    return f"{folder}/{file_name}"


class ReorgError(ValueError):
    """A plan or journal that cannot be applied safely. Raised before anything is moved, or with the journal kept."""


NIGHTLY_PATTERN = r"^(/bin/)?bash .*courses-daily.sh"


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


def _entries(listing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for index, item in enumerate(listing):
        path = _listed_path(item)
        if not path:
            raise ReorgError("a Drive listing entry has no path")
        out.append({"n": index, "path": path, "id": str(item.get("ID") or ""), "dir": bool(item.get("IsDir")),
                    "sha256": str((item.get("Hashes") or {}).get("sha256") or "").lower()})
    return out


def _source_path(source: dict[str, Any], by_path: dict[str, list[dict[str, Any]]]) -> str | None:
    """Where a registry source's file is listed: its recorded drive_path, else its legacy name at the Drive root."""
    recorded = str(source.get("drive_path") or "")
    if recorded and recorded in by_path:
        return recorded
    legacy = Path(str(source.get("file") or "")).name
    if legacy and legacy in by_path and "/" not in legacy:
        return legacy
    return None


def _ancestors(path: str) -> list[str]:
    parts = path.split("/")[:-1]
    return ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]


def _temp_path(path: str, occupied: dict[str, list[int]], targets: set[str], serial: int) -> tuple[str, int]:
    folder, _, _ = path.rpartition("/")
    ext = Path(path).suffix
    while True:
        serial += 1
        name = f".reorg-tmp-{serial}{ext}"
        candidate = f"{folder}/{name}" if folder else name
        if not occupied.get(candidate) and candidate not in targets:
            return candidate, serial


def _move_step(item: dict[str, Any], old: str, new: str, final: bool) -> dict[str, Any]:
    return {"op": "move", "id": item["id"], "old": old, "new": new, "sha256": item["sha"], "final": final}


def plan_reorg(course: dict[str, Any], listing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Moves that put the course's Drive files into the kind folders under their names.

    `listing` is `rclone lsjson -R` output (files and folders, duplicate names allowed). Steps, in run order:
    1. a file that must move: one move per step, `op` "move", by Drive id (a cycle of moves first moves one file to a
       temporary name, `final` False, then on to its target);
    2. a registry source already at its target but without the recorded drive_path: `op` "record" (no Drive move);
    3. no deletions: folders emptied by merging a legacy root folder (`שיעור N` / `מטלה N`) are kept.
    A legacy root folder is never moved as a whole: its files go one by one into its kind folder, merged with
    collision-safe names, and each registry source inside it is planned like any other source.
    Nothing outside a legacy folder is moved except registry sources and unregistered root files. A registry
    source is kept in place when its name already has the Chicago form; otherwise it takes its name. Every
    occupied path is reserved, so a planned destination is never a path that is taken when its move runs.
    Raises ReorgError when a registry source matches more than one file, or a destination's parent folder name is
    duplicated in the listing (both could send a move to the wrong file or folder).
    """
    entries = _entries(listing)
    by_path: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        by_path.setdefault(entry["path"], []).append(entry)
    legacy: dict[str, str] = {}
    for entry in entries:
        path = entry["path"]
        if entry["dir"] and "/" not in path:
            target = _legacy_target(path)
            if target is not None and target != path:
                if len(by_path[path]) > 1:
                    raise ReorgError(f"{path}: the legacy folder name is duplicated in Drive; resolve it first")
                legacy[path] = target

    def legacy_root(path: str) -> str | None:
        return next((root for root in legacy if path.startswith(root + "/")), None)

    items: list[dict[str, Any]] = []
    claimed: set[int] = set()
    for source in course.get("sources", []):
        raw = _source_path(source, by_path)
        if raw is None:
            continue
        if len(by_path[raw]) > 1:
            raise ReorgError(f"{raw}: more than one Drive file has this name, so the registry source cannot be matched")
        entry = by_path[raw][0]
        if entry["dir"]:
            continue
        if entry["n"] in claimed:
            raise ReorgError(f"{raw}: two registry sources point at the same Drive file")
        claimed.add(entry["n"])
        items.append({"n": entry["n"], "id": entry["id"], "path": entry["path"], "sha": str(source.get("sha256", "")),
                      "source": source, "folder": None, "name": None})
    # A registry source whose recorded path is gone is still matched exactly when Drive's SHA-256 equals its own,
    # wherever it sits (a legacy folder included); a hash shared by two files or two sources is not used.
    claimed_sha = {it["sha"] for it in items if it["sha"]}
    by_sha: dict[str, list[dict[str, Any]]] = {}
    for source in course.get("sources", []):
        sha = str(source.get("sha256") or "").lower()
        if sha and sha not in claimed_sha:
            by_sha.setdefault(sha, []).append(source)
    files_by_sha: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if not entry["dir"] and entry["n"] not in claimed and entry["sha256"]:
            files_by_sha.setdefault(entry["sha256"], []).append(entry)
    for sha, found in files_by_sha.items():
        if len(found) == 1 and len(by_sha.get(sha, [])) == 1:
            entry, source = found[0], by_sha[sha][0]
            claimed.add(entry["n"])
            items.append({"n": entry["n"], "id": entry["id"], "path": entry["path"], "sha": str(source.get("sha256", "")),
                          "source": source, "folder": None, "name": None})
    by_key: dict[str, dict[str, Any]] = {}
    for source in course.get("sources", []):
        file_name = _file_name(source)
        if file_name:
            by_key.setdefault(_match_key(file_name), source)
    for entry in entries:
        if entry["dir"] or entry["n"] in claimed:
            continue
        path = entry["path"]
        root = legacy_root(path)
        if root is not None:
            rel_dir, _, name = path[len(root) + 1:].rpartition("/")
            folder = legacy[root] + (f"/{rel_dir}" if rel_dir else "")
            items.append({"n": entry["n"], "id": entry["id"], "path": path, "sha": "", "source": None,
                          "folder": folder, "name": name})
        elif "/" not in path:
            source = by_key.get(_match_key(path)) or {"file": path}
            items.append({"n": entry["n"], "id": entry["id"], "path": path, "sha": "", "source": source,
                          "folder": None, "name": None})
    # Pass 1: a registry source already in its kind folder with its Chicago name stays where it is.
    kept: set[int] = set()
    for item in items:
        if item["source"] is None:
            continue
        folder, _, current = item["path"].rpartition("/")
        ext = Path(current).suffix
        ideal = naming.drive_filename({"stem": drive_name(item["source"], course)}, ext, set())
        base = ideal[: len(ideal) - len(ext)] if ext else ideal
        item["folder"] = folder_for(course, item["source"])
        item["ext"] = ext
        if folder == item["folder"] and (current == ideal or re.fullmatch(re.escape(base) + r" \(\d+\)" + re.escape(ext), current)):
            kept.add(item["n"])
            item["target"] = item["path"]
    # Reserve every name that is not free to take: entries that stay, and kept sources.
    reserved: dict[str, set[str]] = {}
    movable = {item["n"] for item in items}
    for entry in entries:
        if entry["n"] in movable and entry["n"] not in kept:
            continue
        folder, _, name = entry["path"].rpartition("/")
        reserved.setdefault(folder, set()).add(name)
    # Pass 2: every other item takes the first free name of its folder, in source order.
    for item in items:
        if item["n"] in kept:
            continue
        names = reserved.setdefault(item["folder"], set())
        if item["source"] is not None:
            name = naming.drive_filename({"stem": drive_name(item["source"], course)}, item["ext"], names)
        else:
            name = _unique(item["name"], names)
        names.add(name)
        item["target"] = f"{item['folder']}/{name}" if item["folder"] else name
    # Ordering: a move waits until its target is free; a cycle is broken by moving one file to a temporary name.
    occupied: dict[str, list[int]] = {}
    for entry in entries:
        occupied.setdefault(entry["path"], []).append(entry["n"])
    targets = {item["target"] for item in items}
    pending = [item for item in items if item["target"] != item["path"]]
    moved = {item["n"] for item in pending}
    moves: list[dict[str, Any]] = []
    serial = 0
    while pending:
        ready = next((item for item in pending if not occupied.get(item["target"])), None)
        if ready is not None:
            new, final, item = ready["target"], True, ready
        else:
            item = pending[0]
            new, serial = _temp_path(item["path"], occupied, targets, serial)
            final = False
        moves.append(_move_step(item, item["path"], new, final))
        occupied[item["path"]].remove(item["n"])
        occupied.setdefault(new, []).append(item["n"])
        item["path"] = new
        if final:
            pending.remove(item)
    plan: list[dict[str, Any]] = moves
    file_paths = {entry["path"] for entry in entries if not entry["dir"]}
    dir_count: dict[str, int] = {}
    for entry in entries:
        if entry["dir"]:
            dir_count[entry["path"]] = dir_count.get(entry["path"], 0) + 1
    for step in moves:
        if not step["final"]:
            continue
        for ancestor in _ancestors(step["new"]):
            if ancestor in file_paths:
                raise ReorgError(f"{step['new']}: {ancestor} is a file, not a folder")
            if dir_count.get(ancestor, 0) > 1:
                raise ReorgError(f"{step['new']}: the folder {ancestor} is duplicated in Drive; resolve it first")
    for item in items:
        if item["n"] in moved or not item["sha"]:
            continue
        recorded = str(item["source"].get("drive_path") or "")
        if recorded != item["target"]:
            plan.append({"op": "record", "id": "", "old": item["target"], "new": item["target"], "sha256": item["sha"], "final": True})
    # Emptied legacy folders are kept: deleting a Drive folder can race with another client adding a file to it,
    # and a folder delete takes its children with it. The student removes empty folders by hand.
    simulate(plan, entries)
    return plan


def simulate(plan: list[dict[str, Any]], entries: list[dict[str, Any]]) -> None:
    """Replay the moves on the listing: each one must start at its file's place and end on a free path."""
    at = {entry["id"]: entry["path"] for entry in entries if entry["id"]}
    occupied: dict[str, int] = {}
    for entry in entries:
        occupied[entry["path"]] = occupied.get(entry["path"], 0) + 1
    for step in plan:
        if step["op"] != "move":
            continue
        if at.get(step["id"]) != step["old"]:
            raise ReorgError(f"simulation: {step['id']} is not at {step['old']!r}")
        if occupied.get(step["new"]):
            raise ReorgError(f"simulation: {step['new']!r} is occupied when {step['old']!r} moves there")
        occupied[step["old"]] -= 1
        occupied[step["new"]] = occupied.get(step["new"], 0) + 1
        at[step["id"]] = step["new"]


def validate_plan(plan: list[dict[str, Any]]) -> None:
    """Refuse a plan that cannot be run by file id, before any move. Raises ReorgError."""
    chains: dict[str, str] = {}
    finals: set[str] = set()
    for step in plan:
        op = step.get("op")
        if op not in ("move", "rmdir", "record"):
            raise ReorgError(f"unknown step {op!r}")
        if op in ("move", "rmdir") and not str(step.get("id") or "").strip():
            raise ReorgError(f"{step.get('old')}: no Drive file id, so it cannot be moved by id")
        if op == "move":
            new = str(step.get("new") or "")
            if not new or new.startswith("/") or ".." in new.split("/") or new == step["old"]:
                raise ReorgError(f"{step['old']}: bad destination {new!r}")
            if step["id"] in chains and chains[step["id"]] != step["old"]:
                raise ReorgError(f"{step['id']}: its moves do not form a chain")
            chains[step["id"]] = new
        if step.get("final") and op in ("move", "record"):
            if step["new"] in finals:
                raise ReorgError(f"two files would end at {step['new']!r}")
            finals.add(step["new"])


def _fields(step: dict[str, Any]) -> dict[str, Any]:
    return {"file_id": str(step.get("id") or ""), "old": step["old"], "new": step["new"],
            "sha256": str(step.get("sha256") or ""), "final": bool(step.get("final"))}


def _destination_taken(remote: str, root_id: str, new: str, runner: Callable[..., Any]) -> bool:
    """True when anything is already at `new`. Never overwrite: an unknown answer from rclone refuses the move."""
    result = runner(["rclone", "lsjson", f"{remote}:{new}", "--stat", "--drive-root-folder-id", str(root_id)],
                    check=False, text=True, capture_output=True)
    if result.returncode == 0:
        return True
    if result.returncode == 3:  # rclone: object or directory not found
        return False
    raise ReorgError(f"{new!r}: cannot check Drive for an existing file, not moving ({str(result.stderr or '').strip()})")


def move_file(remote: str, root_id: str, file_id: str, new: str, runner: Callable[..., Any] = subprocess.run) -> None:
    """Move one Drive file by id to `new` (a path under the course root), creating its parent folders first.

    Refuses (ReorgError, nothing moved) when anything is already at `new`. The check runs right before the move, but
    moveid delegates to moveto, which would replace a file created in between; `--ignore-existing` makes it skip
    instead. The object at `new` is then checked to carry this file's id, so a skip is raised as a failure.
    """
    parent = new.rpartition("/")[0]
    if parent:
        runner(["rclone", "mkdir", f"{remote}:{parent}", "--drive-root-folder-id", str(root_id)], check=True, text=True, capture_output=True)
    if _destination_taken(remote, root_id, new, runner):
        raise ReorgError(f"{new!r} is occupied in Drive, so {file_id} was not moved there")
    # The destination must carry the remote prefix: a bare path is a LOCAL rclone path, and moveid would pull the file off Drive.
    # --drive-server-side-across-configs: without it rclone sees the --drive-root-folder-id destination as another remote and
    # copies then deletes (a new file id, the original in the trash); with it the move is server-side and the id is kept.
    runner(["rclone", "backend", "moveid", f"{remote}:", str(file_id), f"{remote}:{new}", "--ignore-existing", "--drive-server-side-across-configs", "--drive-root-folder-id", str(root_id)],
           check=True, text=True, capture_output=True)
    result = runner(["rclone", "lsjson", f"{remote}:{new}", "--stat", "--drive-root-folder-id", str(root_id)], check=False, text=True, capture_output=True)
    if result.returncode != 0:
        raise ReorgError(f"{new!r}: cannot confirm {file_id} arrived there ({str(result.stderr or '').strip()}); not moving on")
    try:
        found = str(json.loads(str(result.stdout or "")).get("ID", ""))
    except (ValueError, AttributeError):
        found = ""
    if found != str(file_id):
        raise ReorgError(f"{new!r} holds {found or 'an unknown object'}, not {file_id}: the move was skipped, so {file_id} was not moved there")


JOURNAL_KIND = {"move": "drive_move", "rmdir": "drive_rmdir"}


def _key(line: dict[str, Any]) -> tuple[Any, ...]:
    """What an action is, independent of its op id: kind, file id, from, to and the source hash."""
    return (line.get("kind"), str(line.get("file_id") or ""), line.get("old"), line.get("new"), str(line.get("sha256") or ""))


class Journal:
    """Append-only JSON lines: a plan record, then an intent line (fsynced) before each action and a done or failed
    line after it. A torn last line (a crash mid-write) is cut before the next append, and the cut is logged."""

    def __init__(self, path: Path, *, remote: str, root: str, slug: str):
        self.path = path
        self.base = {"remote": remote, "root": str(root), "slug": slug}
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = read_journal(path)
        self.seq = max((int(line.get("seq", 0)) for line in lines), default=0)
        self.done_keys: set[tuple[Any, ...]] = set()
        self.open_intents: dict[tuple[Any, ...], dict[str, Any]] = {}
        for line in lines:
            if line.get("phase") == "intent":
                self.open_intents[_key(line)] = line
            elif line.get("phase") == "done":
                self.done_keys.add(_key(line))
                self.open_intents.pop(_key(line), None)

    def _append(self, line: dict[str, Any]) -> dict[str, Any]:
        self.seq += 1
        record = {**self.base, "seq": self.seq, "at": datetime.now(timezone.utc).isoformat(), **line}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return record

    def _repair_tail(self) -> None:
        """A file that does not end with a newline has a torn last line: keep it if it is whole JSON, else cut it off."""
        if not self.path.exists() or self.path.stat().st_size == 0:
            return
        with self.path.open("rb") as handle:
            handle.seek(-1, os.SEEK_END)
            if handle.read(1) == b"\n":
                return
        data = self.path.read_bytes()
        cut = data.rfind(b"\n") + 1  # byte-wise: the fragment may end inside a multi-byte character
        fragment = data[cut:].decode("utf-8", errors="replace")
        try:
            json.loads(data[cut:].decode("utf-8"))
            whole = True
        except (UnicodeDecodeError, ValueError):
            whole = False
        with self.path.open("r+b") as handle:
            if whole:
                handle.seek(0, os.SEEK_END)
                handle.write(b"\n")
            else:
                handle.truncate(cut)
            handle.flush()
            os.fsync(handle.fileno())
        self._append({"phase": "repair", "action": "completed" if whole else "truncated", "bytes": len(data) - cut,
                      "fragment": fragment[:200]})

    def _write(self, line: dict[str, Any]) -> dict[str, Any]:
        self._repair_tail()
        return self._append(line)

    def write_plan(self, plan: list[dict[str, Any]]) -> list[str]:
        """The complete ordered plan, fsynced before the first mutation. Returns one op id per step, in order."""
        if any(line.get("phase") == "plan" for line in read_journal(self.path)):
            raise ReorgError(f"{self.path}: the journal already has a plan")
        steps = []
        for index, step in enumerate(plan, start=1):
            steps.append({"seq": index, "op_id": uuid.uuid4().hex, "op": step["op"],
                          "kind": JOURNAL_KIND.get(step["op"], ""), **_fields(step)})
        self._write({"phase": "plan", "op_id": uuid.uuid4().hex, "steps": steps})
        return [step["op_id"] for step in steps]

    def is_done(self, kind: str, fields: dict[str, Any]) -> bool:
        return _key({"kind": kind, **fields}) in self.done_keys

    def run(self, kind: str, fields: dict[str, Any], action: Callable[[], Any], op_id: str | None = None) -> Any:
        """Write the intent, run the action, write the done line. An action already done is not run again; an intent
        left open by an earlier run is completed rather than duplicated. Returns the action's result (None if skipped)."""
        key = _key({"kind": kind, **fields})
        if key in self.done_keys:
            return None
        intent = self.open_intents.get(key)
        if intent is None:
            intent = self._write({"phase": "intent", "op_id": op_id or uuid.uuid4().hex, "kind": kind, **fields})
            self.open_intents[key] = intent
        return self.complete(intent, action)

    def complete(self, intent: dict[str, Any], action: Callable[[], Any]) -> Any:
        """Run the action of an intent already in the journal (a resume), then write its done line. A failure writes a
        failed line and raises, leaving the intent open."""
        body = {k: v for k, v in intent.items() if k not in ("seq", "at", "phase", "remote", "root", "slug")}
        try:
            result = action()
        except Exception as exc:
            self._write({**body, "phase": "failed", "error": str(exc)[:500]})
            raise
        self._write({**body, "phase": "done"})
        self.done_keys.add(_key(intent))
        self.open_intents.pop(_key(intent), None)
        return result


def read_journal(path: Path) -> list[dict[str, Any]]:
    """Every line of a journal. A torn last line (a crash mid-write) is ignored: its action had not started.

    Split on the newline byte first and decode each line alone: a crash can cut a multi-byte UTF-8 character (Hebrew),
    and decoding the whole file would then fail before the torn tail is found.
    """
    if not path.exists():
        return []
    pieces = path.read_bytes().split(b"\n")
    out: list[dict[str, Any]] = []
    for index, raw in enumerate(pieces):
        if not raw.strip():
            continue
        try:
            out.append(json.loads(raw.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            if index == len(pieces) - 1:
                break  # the torn fragment; _repair_tail cuts it before the next append
            raise ReorgError(f"{path}: line {index + 1} is not JSON")
    return out


def pending_ops(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Intent lines with no done line for the same op id, in journal order."""
    done = {line.get("op_id") for line in lines if line.get("phase") == "done"}
    intents = [line for line in lines if line.get("phase") == "intent" and line.get("op_id") not in done]
    return sorted(intents, key=lambda line: int(line.get("seq", 0)))


def plan_steps(lines: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """The journal's plan as (op id, step) pairs in run order, in the shape `apply_reorg` takes. Raises without a plan."""
    plans = [line for line in lines if line.get("phase") == "plan"]
    if len(plans) != 1:
        raise ReorgError("the journal has no single plan record, so its remaining steps cannot be known; not resuming")
    return [(str(item["op_id"]), {"op": item["op"], "id": str(item.get("file_id") or ""), "old": item["old"], "new": item["new"],
                                  "sha256": str(item.get("sha256") or ""), "final": bool(item.get("final"))})
            for item in plans[0].get("steps", [])]


def apply_reorg(plan: list[dict[str, Any]], remote: str, root_id: str, log: Path,
                runner: Callable[..., Any] = subprocess.run, *, slug: str = "",
                after_step: Callable[[dict[str, Any], Journal], None] | None = None) -> None:
    """Run a validated plan by file id, journaling every action to `log`.

    The whole plan is written and fsynced first, so `--resume` can run every remaining step, not only the one in flight.
    `after_step(step, journal)` runs after each final move (and for each record step), so the caller can journal its
    own registry update and NotebookLM rename with `journal.run`. A failure raises and leaves its intent unfinished.
    """
    validate_plan(plan)
    if not plan:
        return  # nothing to move: no journal either
    journal = Journal(log, remote=remote, root=root_id, slug=slug)
    op_ids = journal.write_plan(plan)
    for step, op_id in zip(plan, op_ids):
        if step["op"] == "move":
            journal.run("drive_move", _fields(step), lambda step=step: move_file(remote, root_id, step["id"], step["new"], runner), op_id)
        if after_step is not None and step.get("final") and step.get("sha256"):
            after_step(step, journal)
