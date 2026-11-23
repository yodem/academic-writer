"""Per-task sources for the course registry (additive layer; every existing field keeps its meaning).

Canonical task id
    A task is anything the student hands in or posts. `<slug>.json` carries `tasks: [...]`, each
    {id, title, due_at, chore_ids[], status open|submitted, submitted_at, kind, spec_key?, room?, material?}
    (`room` and `material` appear only on an `exam` task).
    `id` is the id of the chore the task was derived from (10 hex chars, chores.json) when there is one;
    a task that exists only in the Trove spec (`tools/specs/<slug>.json`) gets `s-<spec key>`.
    Commands accept the id, a unique id prefix, or the spec key.

Linkage
    A ref (`refs/<slug>.json`) or a source (`<slug>.json` sources[]) may carry `tasks: [<task id>, ...]`.

Stdlib only; callers pass the term directory.
"""
from __future__ import annotations

import fcntl
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import chores as chores_mod
import courses

TASK_KINDS = ("assignment", "forum-post", "exam", "reading")  # perusall-capture chores are readings to capture, not hand-ins
DEFAULT_SPECS = Path("~/dev/jewish-studies/bar-ilan/courses-tashpaz/tools/specs")


class TaskError(Exception):
    """A failure the user can fix: printed as one line, exit 2."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _norm(text: Any) -> str:
    text = re.sub(r"[֑-ׇ]", "", str(text or ""))
    text = re.sub(r"[\"'“”„׳״,:;()\[\]{}.\-–—_/\\]", " ", text)
    return " ".join(text.lower().split())


def _lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    handle = (directory / ".lock").open("a+")  # the lock courses._locked_course takes for the course JSON
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def _unlock(handle) -> None:
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()


def course_path(directory: Path, slug: str) -> Path:
    return directory / f"{slug}.json"


def refs_file(directory: Path, slug: str) -> Path:
    return directory / "refs" / f"{slug}.json"


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_course(directory: Path, slug: str) -> dict[str, Any]:
    path = course_path(directory, slug)
    if not path.is_file():
        raise TaskError(f"unknown course {slug!r}: no {path}")
    return _read(path)


def load_refs_data(directory: Path, slug: str) -> dict[str, Any] | None:
    path = refs_file(directory, slug)
    return _read(path) if path.is_file() else None


def _chores(directory: Path, slug: str) -> list[dict[str, Any]]:
    path = directory / "chores.json"
    if not path.is_file():
        return []
    return [c for c in _read(path) if isinstance(c, dict) and c.get("course") == slug]



def _due_at(chore: dict[str, Any], timezone_name: str) -> str | None:
    """The chore's due_at, else its Lemida due text read as a date in the term's zone (chores saved before add_chore
    parsed it)."""
    return chore.get("due_at") or chores_mod.due_at_from_text(chore.get("due_text"), timezone_name)


def term_timezone(directory: Path) -> str:
    """The term's zone name from term.json (Asia/Jerusalem when unset or unreadable)."""
    try:
        term = _read(directory / "term.json")
    except (OSError, ValueError):
        return "Asia/Jerusalem"
    return str(term.get("timezone") or "Asia/Jerusalem") if isinstance(term, dict) else "Asia/Jerusalem"

def derive_tasks(existing: list[dict[str, Any]], chores: list[dict[str, Any]],
                 timezone_name: str = "Asia/Jerusalem") -> tuple[list[dict[str, Any]], bool]:
    """Existing tasks plus one new task per task-like chore not yet covered. Returns (tasks, changed). Never removes."""
    tasks = [dict(t) for t in existing]
    covered = {cid for t in tasks for cid in t.get("chore_ids", [])}
    changed = False
    by_id = {c["id"]: c for c in chores}
    for task in tasks:
        # a task made from one chore follows it: a rescan that moves the deadline or renames it updates the task
        chore = by_id.get(task["id"])
        if chore is None or task.get("chore_ids") != [chore["id"]]:
            continue
        for key, value in (("title", chore.get("title") or chore.get("ref", "")), ("due_at", _due_at(chore, timezone_name))):
            if value and task.get(key) != value:
                task[key] = value
                changed = True
    for chore in chores:
        if chore.get("kind") not in TASK_KINDS or chore["id"] in covered:
            continue
        done = chore.get("status") == "done"
        task = {"id": chore["id"], "title": chore.get("title") or chore.get("ref", ""), "due_at": _due_at(chore, timezone_name),
                "chore_ids": [chore["id"]], "status": "submitted" if done else "open",
                "submitted_at": chore.get("updated") if done else None, "kind": chore["kind"]}
        for optional in ("room", "material"):
            if chore.get(optional):
                task[optional] = chore[optional]
        tasks.append(task)
        changed = True
    return tasks, changed


def sync_tasks(directory: Path, slug: str, *, write: bool = True) -> list[dict[str, Any]]:
    """Make `tasks[]` in the course file cover every task chore. Writes only when something was added."""
    handle = _lock(directory)
    try:
        course = load_course(directory, slug)
        tasks, changed = derive_tasks(course.get("tasks", []), _chores(directory, slug), term_timezone(directory))
        if changed and write:
            course["tasks"] = tasks
            courses._atomic_json(course_path(directory, slug), course)
        return tasks
    finally:
        _unlock(handle)


def resolve_task(tasks: list[dict[str, Any]], ident: str) -> dict[str, Any]:
    exact = [t for t in tasks if t["id"] == ident or t.get("spec_key") == ident]
    matches = exact or [t for t in tasks if t["id"].startswith(ident)]
    if len(matches) != 1:
        raise TaskError(f"task {ident!r}: {'no match' if not matches else 'ambiguous'}")
    return matches[0]


# --- per-source status ------------------------------------------------------------------------------

def _matching_source(ref: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    for src in sources:
        if (ref.get("sha8") and src.get("sha8") == ref["sha8"]) or (src.get("origin_ref") and src["origin_ref"] == ref.get("key")):
            return src
    return None


def _trove_of(value: Any) -> str:
    if isinstance(value, dict):
        return f"{value.get('book_id', '')}:{value.get('page', '')}" if value.get("book_id") else ""
    return str(value or "")


def ref_status(ref: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    src = _matching_source(ref, sources) or {}
    trove = ref.get("trove_url") or _trove_of(ref.get("trove")) or _trove_of(src.get("trove"))
    notebook = src.get("notebook_source_id") or ref.get("notebook_source_id") or ""
    return {"type": "ref", "key": ref.get("key"), "title": ref.get("citation", ""), "ref_status": ref.get("status", ""),
            "downloaded": ref.get("status") in ("downloaded", "ingested") or bool(ref.get("download_path") or ref.get("drive_pdf")),
            "in_trove": bool(trove), "trove": trove,
            "in_notebooklm": bool(notebook), "notebook_source_id": notebook,
            "annas": ref.get("annas", "not-checked")}


def source_status(src: dict[str, Any]) -> dict[str, Any]:
    file = src.get("file")
    trove = _trove_of(src.get("trove"))
    notebook = src.get("notebook_source_id") or ""
    return {"type": "source", "key": src.get("sha8") or (src.get("sha256") or "")[:8], "title": src.get("title", ""),
            "ref_status": src.get("status", ""), "downloaded": bool(file and Path(file).exists()) or bool(src.get("drive")),
            "in_trove": bool(trove), "trove": trove, "in_notebooklm": bool(notebook), "notebook_source_id": notebook,
            "annas": "n/a"}


def task_show(directory: Path, slug: str, ident: str) -> dict[str, Any]:
    tasks = sync_tasks(directory, slug, write=False)
    task = resolve_task(tasks, ident)
    course = load_course(directory, slug)
    sources = course.get("sources", [])
    refs_data = load_refs_data(directory, slug) or {"refs": []}
    items = [ref_status(r, sources) for r in refs_data["refs"] if task["id"] in r.get("tasks", [])]
    items += [source_status(s) for s in sources if task["id"] in s.get("tasks", [])]
    return {"course": slug, "task": task, "sources": items}


def task_list(directory: Path, slug: str) -> list[dict[str, Any]]:
    tasks = sync_tasks(directory, slug, write=False)
    refs_data = load_refs_data(directory, slug) or {"refs": []}
    sources = load_course(directory, slug).get("sources", [])
    out = []
    for task in tasks:
        n = sum(task["id"] in r.get("tasks", []) for r in refs_data["refs"]) + sum(task["id"] in s.get("tasks", []) for s in sources)
        out.append({**task, "source_count": n})
    return out


# --- writes -----------------------------------------------------------------------------------------

def task_link(directory: Path, slug: str, ident: str, *, ref: str | None = None, source: str | None = None) -> dict[str, Any]:
    if bool(ref) == bool(source):
        raise TaskError("link needs exactly one of --ref KEY or --source SHA8")
    handle = _lock(directory)
    try:
        course = load_course(directory, slug)
        tasks, changed = derive_tasks(course.get("tasks", []), _chores(directory, slug), term_timezone(directory))
        task = resolve_task(tasks, ident)
        if ref:
            data = load_refs_data(directory, slug)
            target = next((r for r in (data or {"refs": []})["refs"] if r.get("key") == ref), None)
            if target is None:
                raise TaskError(f"no ref {ref!r} in {refs_file(directory, slug)}")
        else:
            data = None
            target = next((s for s in course.get("sources", []) if s.get("sha8", "").startswith(source) or s.get("sha256", "").startswith(source)), None)
            if target is None:
                raise TaskError(f"no source {source!r} in {slug}")
        linked = task["id"] not in target.setdefault("tasks", [])
        if linked:
            target["tasks"].append(task["id"])
        if ref and linked:
            courses._atomic_json(refs_file(directory, slug), data)
        if changed or (not ref and linked):
            course["tasks"] = tasks
            courses._atomic_json(course_path(directory, slug), course)
        return {"task": task["id"], "linked": linked, "target": ref or source}
    finally:
        _unlock(handle)


def task_submit(directory: Path, slug: str, ident: str) -> dict[str, Any]:
    """Mark a task submitted and close its linked chores. Idempotent."""
    handle = _lock(directory)
    try:
        course = load_course(directory, slug)
        tasks, _ = derive_tasks(course.get("tasks", []), _chores(directory, slug), term_timezone(directory))
        task = resolve_task(tasks, ident)
        closed = []
        registry = courses.Registry(directory)
        for cid in task.get("chore_ids", []):
            chore = next((c for c in chores_mod.load(registry) if c["id"] == cid), None)
            if chore and chore.get("status") != "done":
                chores_mod.mark_done(registry, cid)
                closed.append(cid)
        if task.get("status") != "submitted":
            task["status"] = "submitted"
            task["submitted_at"] = _now()
            task["closed_chores"] = closed  # what unsubmit reopens; a repeat submit keeps the first list
        course["tasks"] = tasks
        courses._atomic_json(course_path(directory, slug), course)
        return {"task": task["id"], "status": task["status"], "submitted_at": task["submitted_at"], "closed_chores": closed}
    finally:
        _unlock(handle)


def task_unsubmit(directory: Path, slug: str, ident: str) -> dict[str, Any]:
    """Undo task_submit: reopen the task and the chores that submit closed. Idempotent.

    A task submitted before `closed_chores` was recorded reopens all of its chore_ids."""
    handle = _lock(directory)
    try:
        course = load_course(directory, slug)
        tasks, _ = derive_tasks(course.get("tasks", []), _chores(directory, slug), term_timezone(directory))
        task = resolve_task(tasks, ident)
        reopened = []
        if task.get("status") == "submitted":
            registry = courses.Registry(directory)
            wanted = task.get("closed_chores", task.get("chore_ids", []))
            for cid in wanted:
                chore = next((c for c in chores_mod.load(registry) if c["id"] == cid), None)
                if chore and chore.get("status") == "done":
                    chores_mod.reopen(registry, cid)
                    reopened.append(cid)
            task["status"] = "open"
            task["submitted_at"] = None
            task.pop("closed_chores", None)
            course["tasks"] = tasks
            courses._atomic_json(course_path(directory, slug), course)
        return {"task": task["id"], "status": task["status"], "reopened_chores": reopened}
    finally:
        _unlock(handle)


# --- migration --------------------------------------------------------------------------------------

def _backup(path: Path, stamp: str) -> Path:
    dest = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, dest)
    return dest


def _spec_items(spec_task: dict[str, Any]) -> list[dict[str, Any]]:
    return [i for i in (spec_task.get("primary") or []) + (spec_task.get("secondary") or []) if isinstance(i, dict) and i.get("title")]


def _contains(small: list[str], big: list[str]) -> bool:
    return bool(small) and any(big[i:i + len(small)] == small for i in range(len(big) - len(small) + 1))


def _matches(title: str, text: str) -> bool:
    """Whole-token containment either way, so 'מטלה 1' never matches 'מטלה 10'."""
    a, b = _norm(title).split(), _norm(text).split()
    return len(_norm(title)) >= 4 and (_contains(a, b) or (len(_norm(text)) >= 4 and _contains(b, a)))


_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def _spec_kind(key: str, title: str) -> str | None:
    for head in (key.strip(), title.strip()):
        if head.startswith("פורום"):
            return "forum-post"
        if head.startswith("מטלה"):
            return "assignment"
    return None


def _fold_target(tasks: list[dict[str, Any]], key: str, title: str) -> tuple[dict[str, Any], str] | None:
    """The one chore-backed task a spec task duplicates: same kind, and the due date named in the spec title; with no date in the title, the only open one."""
    kind = _spec_kind(key, title)
    if kind is None:
        return None
    pool = [t for t in tasks if t.get("chore_ids") and t.get("kind") == kind and not t.get("spec_key")]
    found = _DATE_RE.search(title)
    if found:
        day, month, year = (int(x) for x in found.groups())
        dated = [t for t in pool if str(t.get("due_at") or "")[:10] == f"{year:04d}-{month:02d}-{day:02d}"]
        if len(dated) == 1:
            return dated[0], "due date"
        # an explicit date never falls back onto a chore that has a different due date; an undated chore cannot contradict it
        pool = [t for t in pool if not t.get("due_at")] if not dated else []
    open_ones = [t for t in pool if t.get("status") == "open"]
    return (open_ones[0], "only open chore of its kind") if len(open_ones) == 1 else None


def migrate(directory: Path, specs_dir: Path | None = None, *, dry_run: bool = False) -> dict[str, Any]:
    """Add tasks[] and task links from chores, specs/<slug>.json and refs `found_in`. Ambiguity is reported, never guessed."""
    specs_dir = (specs_dir or DEFAULT_SPECS).expanduser()
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    report: dict[str, Any] = {"dry_run": dry_run, "courses": {}, "backups": [], "ambiguous": [], "unmatched": [], "possible_duplicates": [], "merged": []}
    registry = courses.Registry(directory)
    for slug in sorted(registry.courses):
        course = load_course(directory, slug)
        tasks, changed = derive_tasks(course.get("tasks", []), _chores(directory, slug), term_timezone(directory))
        refs_data = load_refs_data(directory, slug)
        refs_list = refs_data["refs"] if refs_data else []
        sources = course.get("sources", [])
        spec_path = specs_dir / f"{slug}.json"
        spec = _read(spec_path) if spec_path.is_file() else {"tasks": []}
        links: list[dict[str, str]] = []
        refs_changed = course_sources_changed = False
        for st in spec.get("tasks", []):
            key, title = str(st.get("key", "")), st.get("title", "")
            same = [t for t in tasks if _norm(t["title"]) == _norm(title) and title]
            tagged = [t for t in tasks if t.get("spec_key") == key]
            if tagged:
                task = tagged[0]
            elif len(same) == 1:
                task = same[0]
                task["spec_key"] = key
                changed = True
            elif len(same) <= 1 and (fold := _fold_target(tasks, key, title)) is not None:
                task = fold[0]
                task["spec_key"] = key
                changed = True
                report["merged"].append({"course": slug, "spec_task": key, "into": task["id"], "why": fold[1]})
            else:
                if len(same) > 1:
                    report["ambiguous"].append({"course": slug, "task": key, "why": "several tasks share the title", "candidates": [t["id"] for t in same]})
                task = {"id": f"s-{key}", "title": title, "due_at": None, "chore_ids": [], "status": "open", "submitted_at": None,
                        "kind": "spec", "spec_key": key}
                tasks.append(task)
                changed = True
            for item in _spec_items(st):
                for pool, label in ((refs_list, "ref"), (sources, "source")):
                    field = "citation" if label == "ref" else "title"
                    hits = [e for e in pool if _matches(item["title"], e.get(field, ""))]
                    if len(hits) == 1:
                        if task["id"] not in hits[0].setdefault("tasks", []):
                            hits[0]["tasks"].append(task["id"])
                            links.append({"task": task["id"], label: hits[0].get("key") or hits[0].get("sha8", ""), "via": "spec"})
                            refs_changed |= label == "ref"
                            course_sources_changed |= label == "source"
                    elif len(hits) > 1:
                        report["ambiguous"].append({"course": slug, "task": key, "item": item["title"], "type": label,
                                                    "candidates": [h.get("key") or h.get("sha8") for h in hits]})
                if not any(_matches(item["title"], e.get("citation", "")) for e in refs_list) and \
                        not any(_matches(item["title"], e.get("title", "")) for e in sources):
                    report["unmatched"].append({"course": slug, "task": key, "item": item["title"]})
        # found_in is a heuristic: link only when exactly one task title is named
        for r in refs_list:
            claimed = [t for t in tasks if t.get("title") and _matches(t["title"], str(r.get("found_in", "")))]
            if len(claimed) == 1 and claimed[0]["id"] not in r.setdefault("tasks", []):
                r["tasks"].append(claimed[0]["id"])
                links.append({"task": claimed[0]["id"], "ref": r.get("key"), "via": "found_in"})
                refs_changed = True
            elif len(claimed) > 1:
                report["ambiguous"].append({"course": slug, "ref": r.get("key"), "why": "found_in names several tasks",
                                            "candidates": [t["id"] for t in claimed]})
        for r in refs_list:
            if r.get("tasks") == []:
                del r["tasks"]
        for s in sources:
            if s.get("tasks") == []:
                del s["tasks"]
        chore_tasks = [t for t in tasks if t.get("chore_ids")]
        for t in tasks:
            if t.get("kind") == "spec" and chore_tasks:
                report["possible_duplicates"].append({"course": slug, "spec_task": t["id"], "title": t["title"],
                                                      "chore_tasks": [{"id": c["id"], "title": c["title"]} for c in chore_tasks]})
        report["courses"][slug] = {"tasks": len(tasks), "links": links}
        if dry_run:
            continue
        if changed or course_sources_changed:
            report["backups"].append(str(_backup(course_path(directory, slug), stamp)))
            course["tasks"] = tasks
            courses._atomic_json(course_path(directory, slug), course)
        if refs_changed and refs_data is not None:
            report["backups"].append(str(_backup(refs_file(directory, slug), stamp)))
            courses._atomic_json(refs_file(directory, slug), refs_data)
    return report


# --- Lemida submission check ------------------------------------------------------------------------

HANDIN_KINDS = ("assignment", "forum-post", "exam")


def _split_courses(text: str | None) -> list[str] | None:
    """`--courses a,b c` as a slug list; None when the flag was not given."""
    return None if text is None else text.replace(",", " ").split()


def open_handins(directory: Path, only: Any = None) -> dict[str, list[dict[str, Any]]]:
    """The open tasks the nightly watch must look at in Lemida, and the open ones it cannot.

    A hand-in is an open assignment or forum-post task, or an exam task whose module is a quiz in the course's
    `watch_seen`; its chore ref must be a numeric cmid and its course active with a `lemida_course_id`. A forum-post
    ref counts only when `watch_seen` knows it as a forum cmid (it may be a discussion id); an assignment ref whose
    known module type is neither assign nor quiz is skipped. A task whose linked chores name several refs is skipped
    (closing it would close them all on one module's evidence), so it is never closed and never a coverage gap.
    Reads the registry only (derive is not written back) and never contacts Lemida. `only` limits the courses."""
    registry = courses.Registry(directory)
    base = str(registry.term.get("lemida", {}).get("base_url", "")).rstrip("/")
    active = registry.active_courses()
    wanted = sorted(active) if only is None else sorted(s for s in set(only) if s in active)
    out: dict[str, list[dict[str, Any]]] = {"handins": [], "skipped": []}
    for slug in wanted:
        course = registry.courses[slug]
        tasks = sync_tasks(directory, slug, write=False)
        by_id = {c["id"]: c for c in _chores(directory, slug)}
        for task in tasks:
            kind = task.get("kind")
            if task.get("status") != "open" or kind not in HANDIN_KINDS:
                continue
            skip = {"task": task["id"], "course": slug}
            refs = sorted({chores_mod.canonical_ref(str(by_id[cid].get("ref", ""))) for cid in task.get("chore_ids", []) if cid in by_id})
            if len(refs) > 1:  # task_submit closes every linked chore, so one module's evidence cannot stand for several
                out["skipped"].append({**skip, "reason": f"links several Lemida modules ({', '.join(r or '(none)' for r in refs)})"})
                continue
            ref = refs[0] if refs else ""
            absent = course.get("lemida_absent")
            if not course.get("lemida_course_id"):
                reason = "lemida_absent" if isinstance(absent, str) and absent.strip() else "no lemida_course_id"
                out["skipped"].append({**skip, "reason": reason})
                continue
            if not ref.isdigit():
                out["skipped"].append({**skip, "reason": f"ref {ref or '(none)'!r} is not a numeric cmid"})
                continue
            seen = ((course.get("watch_seen") or {}).get("modules") or {}).get(ref) or {}
            mod = str(seen.get("type") or courses.CHORE_MODULE_TYPE.get(kind, ""))
            if kind == "exam" and mod != "quiz":
                continue  # an exam that is not a Lemida quiz is not handed in there
            if kind == "forum-post" and seen.get("type") != "forum":
                out["skipped"].append({**skip, "reason": "ref is not a known forum cmid (may be a discussion id)"})
                continue
            if kind == "assignment" and mod not in ("assign", "quiz"):
                out["skipped"].append({**skip, "reason": f"module {ref} is a {mod or 'unknown'!r}, not an assign or quiz"})
                continue
            out["handins"].append({"task": task["id"], "course": slug, "kind": kind, "title": task.get("title", ""),
                                   "due_at": task.get("due_at"), "cmid": ref, "type": mod,
                                   "url": courses.lemida_module_url(base, course, ref, kind)})
    return out


ROW_TYPES = ("assign", "quiz", "forum")


def _is_pos_id(value: Any) -> bool:
    """A positive integer, or a string of ASCII digits that is one."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value > 0
    return isinstance(value, str) and value.isascii() and value.isdigit() and int(value) > 0


def row_problem(row: Any) -> str | None:
    """Why this `submissions.checked` row is malformed, or None when it is well formed (types only, no registry)."""
    if not isinstance(row, dict):
        return "row is not an object"
    if not isinstance(row.get("task"), str) or not row["task"]:
        return "task is not a non-empty string"
    if not isinstance(row.get("course"), str):
        return "course is not a string"
    if not _is_pos_id(row.get("cmid")):
        return "cmid is not a positive integer or a string of digits"
    if row.get("type") not in ROW_TYPES:
        return f"type {row.get('type')!r} is not one of {', '.join(ROW_TYPES)}"
    for key in ("status", "team_status"):
        if key in row and not isinstance(row[key], str):
            return f"{key} is not a string"
    if "quiz_review_links" in row and (not isinstance(row["quiz_review_links"], int) or isinstance(row["quiz_review_links"], bool)
                                        or row["quiz_review_links"] < 0):
        return "quiz_review_links is not an integer >= 0"
    if "my_user_id" in row and not _is_pos_id(row["my_user_id"]):
        return "my_user_id is not a positive integer or a string of digits"
    if "author_ids" in row and (not isinstance(row["author_ids"], list) or not all(_is_pos_id(a) for a in row["author_ids"])):
        return "author_ids is not a list of positive integers or strings of digits"
    if "error" in row and (not isinstance(row["error"], str) or not row["error"]):
        return "error is not a non-empty string"
    return None


def row_matches(row: dict[str, Any], handin: dict[str, Any]) -> bool:
    """Does a well-formed row name exactly this hand-in (task id, course, cmid and module type)?"""
    return (row.get("task") == handin["task"] and row.get("course") == handin["course"]
            and str(row.get("cmid")) == str(handin["cmid"]) and row.get("type") == handin["type"])


def row_evidence(row: dict[str, Any]) -> bool:
    """Does the row carry what its type needs to count as checked: an `error`, or the type's evidence field(s)?"""
    if "error" in row:
        return True
    need = {"assign": ("status",), "quiz": ("quiz_review_links",), "forum": ("my_user_id", "author_ids")}[row["type"]]
    return all(key in row for key in need)


def confirmed(row: Any) -> bool:
    """Does this `submissions.checked` row show Lemida holding the student's hand-in? Python decides, not the watch."""
    if not isinstance(row, dict) or "error" in row:
        return False
    kind = row.get("type")
    if kind == "assign":
        return row.get("status") == "submitted" or row.get("team_status") == "submitted"
    if kind == "quiz":
        links = row.get("quiz_review_links")
        return isinstance(links, int) and not isinstance(links, bool) and links >= 1
    if kind == "forum":
        me = row.get("my_user_id")
        authors = row.get("author_ids")
        if isinstance(me, bool) or not isinstance(me, (str, int)) or not str(me) or not isinstance(authors, list):
            return False
        return str(me) in {str(a) for a in authors}
    return False


def sync_submissions(directory: Path, day: str, run_id: str) -> dict[str, Any]:
    """Close every open hand-in the coverage file's `submissions.checked` rows prove submitted. Idempotent.

    Raises TaskError (nothing closed) when the file is missing, belongs to another run, is dated another day or its
    `submissions` section or any row is malformed or evidence-free (the gate's `row_evidence` rule: an `error`, or the type's
    evidence fields; for assign that is `status`, which may be ""; `team_status` alone is not evidence), or two rows name the same task.
    A row is trusted only when it equals an open hand-in (`open_handins`) in task id, course, cmid and type; a row naming a task
    already submitted is skipped. Identity errors (a well-formed row naming an unknown or non-hand-in task, or a mismatched
    course, cmid or type) do not block valid rows: valid confirmed rows still close, the errors are reported and the CLI exits 1."""
    import lemida_coverage
    registry = courses.Registry(directory)
    path, day = lemida_coverage.resolve_coverage_path(registry, day, run_id)
    if not path.is_file():
        raise TaskError(f"coverage file missing: {path}")
    try:
        data = _read(path)
    except (OSError, ValueError) as exc:
        raise TaskError(f"coverage file unreadable: {path}: {exc}")
    if not isinstance(data, dict):
        raise TaskError(f"coverage file is not a JSON object: {path}")
    if data.get("run_id") != run_id:
        raise TaskError(f"stale report: run_id {data.get('run_id')!r} is not this run ({run_id})")
    if data.get("date") != day:
        raise TaskError(f"coverage file dated {data.get('date')!r}, expected {day} (stale report)")
    section = data.get("submissions")
    if not isinstance(section, dict) or section.get("complete") is not True or not isinstance(section.get("checked"), list):
        raise TaskError("submissions must be an object with complete true and checked a list")
    rows = section["checked"]
    for index, row in enumerate(rows):
        problem = row_problem(row)
        if problem:
            raise TaskError(f"submissions.checked[{index}]: {problem}")
        if not row_evidence(row):
            raise TaskError(f"submissions.checked[{index}] (task {row['task']}): row has neither an error nor the {row['type']} evidence fields")
    names = [row["task"] for row in rows]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise TaskError(f"submissions.checked has more than one row for task {', '.join(dupes)}")
    handins = {h["task"]: h for h in open_handins(directory)["handins"]}
    report: dict[str, Any] = {"date": day, "closed": [], "kept_open": [], "errors": []}
    for row in rows:
        ident, slug = row["task"], row["course"]
        handin = handins.get(ident)
        if handin is None:
            known = registry.courses.get(slug)
            already = known is not None and any(
                t["id"] == ident and t.get("status") != "open" for t in sync_tasks(directory, slug, write=False))
            if not already:
                report["errors"].append({"task": ident, "course": slug, "reason": "not an open hand-in"})
            continue  # already closed: a rerun does nothing
        if not row_matches(row, handin):
            report["errors"].append({"task": ident, "course": slug, "reason": (
                f"row does not match the hand-in (course {handin['course']}, cmid {handin['cmid']}, type {handin['type']})")})
            continue
        if confirmed({**row, "type": handin["type"]}):
            task_submit(directory, handin["course"], ident)
            report["closed"].append({"task": ident, "course": slug, "title": handin.get("title", "")})
        else:
            raw = row.get("error") and f"error: {row['error']}" or row.get("status") or row.get("team_status") or ""
            report["kept_open"].append({"task": ident, "course": slug, "status": raw})
    return report


# --- CLI glue ---------------------------------------------------------------------------------------

def add_task_parser(sub) -> None:
    """Register `task list|show|link|submit|unsubmit` on a subparsers object."""
    task_p = sub.add_parser("task", help="per-task sources: list, show, link, submit, unsubmit")
    tsub = task_p.add_subparsers(dest="task_command", required=True)
    tl = tsub.add_parser("list", help="list a course's tasks")
    tl.add_argument("--course", required=True)
    ts = tsub.add_parser("show", help="a task with its refs/sources and unified status")
    ts.add_argument("--course", required=True)
    ts.add_argument("--task", required=True)
    ts.add_argument("--json", action="store_true")
    tk = tsub.add_parser("link", help="link a ref (or source) to a task")
    tk.add_argument("--course", required=True)
    tk.add_argument("--task", required=True)
    tk.add_argument("--ref")
    tk.add_argument("--source", help="sha8 of a registered source")
    tb = tsub.add_parser("submit", help="mark a task submitted and close its chores")
    tb.add_argument("--course", required=True)
    tb.add_argument("--task", required=True)
    tu = tsub.add_parser("unsubmit", help="undo submit: reopen the task and the chores submit closed")
    tu.add_argument("--course", required=True)
    tu.add_argument("--task", required=True)
    toh = tsub.add_parser("open-handins", help="open hand-in tasks the nightly watch must check in Lemida (reads the registry only)")
    toh.add_argument("--courses", help="space or comma separated slugs (default: every active course)")
    toh.add_argument("--json", action="store_true")
    tss = tsub.add_parser("sync-submissions", help="close the tasks the coverage file's submissions.checked rows prove submitted")
    tss.add_argument("--date", help="YYYY-MM-DD of the coverage file (default: today in the term's timezone)")
    tss.add_argument("--run-id", required=True)
    tss.add_argument("--json", action="store_true")


def run_task_command(directory: Path, args) -> int:
    try:
        if args.task_command == "open-handins":
            result = open_handins(directory, _split_courses(args.courses))
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                for r in result["handins"]:
                    print(f"{r['task']}  {r['course']}  {r['kind']}  {r['type']}  cmid {r['cmid']}  due {r.get('due_at') or '-'}  {r['title']}  {r['url'] or '-'}")
                for r in result["skipped"]:
                    print(f"skipped {r['task']}  {r['course']}: {r['reason']}")
            return 0
        if args.task_command == "sync-submissions":
            import lemida_coverage
            day = args.date or lemida_coverage.today(courses.Registry(directory))
            try:
                report = sync_submissions(directory, day, args.run_id)
            except TaskError as exc:
                print(f"sync-submissions: {exc}")
                return 1
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                for r in report["closed"]:
                    print(f"closed {r['task']}  {r['course']}  {r['title']}")
                for r in report["kept_open"]:
                    print(f"kept open {r['task']}  {r['course']}  status {r['status'] or '-'}")
                for r in report["errors"]:
                    print(f"error {r['task']}: {r['reason']}")
                print(f"submissions {report['date']}: {len(report['closed'])} closed, {len(report['kept_open'])} kept open, {len(report['errors'])} errors")
            return 1 if report["errors"] else 0
        if args.task_command == "list":
            print(json.dumps(task_list(directory, args.course), ensure_ascii=False, indent=2))
        elif args.task_command == "show":
            result = task_show(directory, args.course, args.task)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                t = result["task"]
                print(f"{t['id']}  {t['status']}  {t['title']}  due {t.get('due_at') or '-'}")
                for s in result["sources"]:
                    mark = lambda ok: "yes" if ok else "no"  # noqa: E731
                    print(f"  {s['type']} {s['key']}: downloaded {mark(s['downloaded'])}, trove {mark(s['in_trove'])}, "
                          f"notebooklm {mark(s['in_notebooklm'])}, annas {s['annas']}  {s['title'][:60]}")
        elif args.task_command == "link":
            print(json.dumps(task_link(directory, args.course, args.task, ref=args.ref, source=args.source), ensure_ascii=False))
        elif args.task_command == "unsubmit":
            print(json.dumps(task_unsubmit(directory, args.course, args.task), ensure_ascii=False))
        else:
            print(json.dumps(task_submit(directory, args.course, args.task), ensure_ascii=False))
        return 0
    except (TaskError, ValueError) as exc:
        import sys
        print(f"task: {exc}", file=sys.stderr)
        return 2
