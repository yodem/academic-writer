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
" (2)" suffix, and a cycle of moves is broken through a temporary name. Each move, registry update and NotebookLM
rename is journaled as an intent line before it runs and a done line after it (fsynced), so a crash can be
resumed from the journal by checking each file id. Standard library only.
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
        out.append({"n": index, "path": path, "id": str(item.get("ID") or ""), "dir": bool(item.get("IsDir"))})
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
    3. the folders emptied by merging a legacy root folder (`שיעור N` / `מטלה N`): `op` "rmdir", deepest first.
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
        ideal = naming.drive_filename({"stem": drive_name(item["source"])}, ext, set())
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
            name = naming.drive_filename({"stem": drive_name(item["source"])}, item["ext"], names)
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
    emptied = [entry for entry in entries if entry["dir"] and (entry["path"] in legacy or legacy_root(entry["path"]) is not None)]
    for entry in sorted(emptied, key=lambda e: e["path"].count("/"), reverse=True):
        plan.append({"op": "rmdir", "id": entry["id"], "old": entry["path"], "new": "", "sha256": "", "final": False})
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


def move_file(remote: str, root_id: str, file_id: str, new: str, runner: Callable[..., Any] = subprocess.run) -> None:
    """Move one Drive file by id to `new` (a path under the course root), creating its parent folders first."""
    parent = new.rpartition("/")[0]
    if parent:
        runner(["rclone", "mkdir", f"{remote}:{parent}", "--drive-root-folder-id", str(root_id)], check=True, text=True, capture_output=True)
    runner(["rclone", "backend", "moveid", f"{remote}:", str(file_id), new, "--drive-root-folder-id", str(root_id)],
           check=True, text=True, capture_output=True)


def rmdir_folder(remote: str, root_id: str, path: str, runner: Callable[..., Any] = subprocess.run) -> None:
    """Remove an emptied folder. rclone refuses a non-empty folder, so nothing in it is lost."""
    runner(["rclone", "rmdir", f"{remote}:{path}", "--drive-root-folder-id", str(root_id)], check=True, text=True, capture_output=True)


class Journal:
    """Append-only JSON lines. An intent line is written and fsynced before an action; a done line after it."""

    def __init__(self, path: Path, *, remote: str, root: str, slug: str):
        self.path = path
        self.base = {"remote": remote, "root": str(root), "slug": slug}
        path.parent.mkdir(parents=True, exist_ok=True)
        self.seq = max((int(line.get("seq", 0)) for line in read_journal(path)), default=0)

    def _write(self, line: dict[str, Any]) -> dict[str, Any]:
        self.seq += 1
        record = {**self.base, "seq": self.seq, "at": datetime.now(timezone.utc).isoformat(), **line}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return record

    def run(self, kind: str, fields: dict[str, Any], action: Callable[[], Any]) -> Any:
        """Write the intent, run the action, write the done line. Returns the action's result."""
        intent = self._write({"phase": "intent", "op_id": uuid.uuid4().hex, "kind": kind, **fields})
        return self.complete(intent, action)

    def complete(self, intent: dict[str, Any], action: Callable[[], Any]) -> Any:
        """Run the action of an intent already in the journal (a resume), then write its done line."""
        result = action()
        body = {k: v for k, v in intent.items() if k not in ("seq", "at", "phase", "remote", "root", "slug")}
        self._write({**body, "phase": "done"})
        return result


def read_journal(path: Path) -> list[dict[str, Any]]:
    """Every line of a journal. A torn last line (a crash mid-write) is ignored: its action had not started."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for index, text in enumerate(lines):
        if not text.strip():
            continue
        try:
            out.append(json.loads(text))
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                break
            raise ReorgError(f"{path}: line {index + 1} is not JSON")
    return out


def pending_ops(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Intent lines with no done line for the same op id, in journal order."""
    done = {line.get("op_id") for line in lines if line.get("phase") == "done"}
    intents = [line for line in lines if line.get("phase") == "intent" and line.get("op_id") not in done]
    return sorted(intents, key=lambda line: int(line.get("seq", 0)))


def apply_reorg(plan: list[dict[str, Any]], remote: str, root_id: str, log: Path,
                runner: Callable[..., Any] = subprocess.run, *, slug: str = "",
                after_step: Callable[[dict[str, Any], Journal], None] | None = None) -> None:
    """Run a validated plan by file id, journaling every action to `log`.

    `after_step(step, journal)` runs after each final move (and for each record step), so the caller can journal its
    own registry update and NotebookLM rename with `journal.run`. A failure raises and leaves its intent unfinished:
    `pending_ops` on the journal shows what to reconcile.
    """
    validate_plan(plan)
    journal = Journal(log, remote=remote, root=root_id, slug=slug)
    for step in plan:
        if step["op"] == "move":
            journal.run("drive_move", _fields(step), lambda step=step: move_file(remote, root_id, step["id"], step["new"], runner))
        elif step["op"] == "rmdir":
            journal.run("drive_rmdir", _fields(step), lambda step=step: rmdir_folder(remote, root_id, step["old"], runner))
        if after_step is not None and step.get("final") and step.get("sha256"):
            after_step(step, journal)
