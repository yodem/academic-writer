"""Per-task sources for the course registry (additive layer; every existing field keeps its meaning).

Canonical task id
    A task is anything the student hands in or posts. `<slug>.json` carries `tasks: [...]`, each
    {id, title, due_at, chore_ids[], status open|submitted, submitted_at, kind, spec_key?}.
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

TASK_KINDS = ("assignment", "forum-post")  # perusall-capture chores are readings to capture, not hand-ins
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


def derive_tasks(existing: list[dict[str, Any]], chores: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Existing tasks plus one new task per task-like chore not yet covered. Returns (tasks, changed). Never removes."""
    tasks = [dict(t) for t in existing]
    covered = {cid for t in tasks for cid in t.get("chore_ids", [])}
    changed = False
    for chore in chores:
        if chore.get("kind") not in TASK_KINDS or chore["id"] in covered:
            continue
        done = chore.get("status") == "done"
        tasks.append({"id": chore["id"], "title": chore.get("title") or chore.get("ref", ""), "due_at": chore.get("due_at"),
                      "chore_ids": [chore["id"]], "status": "submitted" if done else "open",
                      "submitted_at": chore.get("updated") if done else None, "kind": chore["kind"]})
        changed = True
    return tasks, changed


def sync_tasks(directory: Path, slug: str, *, write: bool = True) -> list[dict[str, Any]]:
    """Make `tasks[]` in the course file cover every task chore. Writes only when something was added."""
    handle = _lock(directory)
    try:
        course = load_course(directory, slug)
        tasks, changed = derive_tasks(course.get("tasks", []), _chores(directory, slug))
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
        tasks, changed = derive_tasks(course.get("tasks", []), _chores(directory, slug))
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
        tasks, _ = derive_tasks(course.get("tasks", []), _chores(directory, slug))
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
        tasks, _ = derive_tasks(course.get("tasks", []), _chores(directory, slug))
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


def migrate(directory: Path, specs_dir: Path | None = None, *, dry_run: bool = False) -> dict[str, Any]:
    """Add tasks[] and task links from chores, specs/<slug>.json and refs `found_in`. Ambiguity is reported, never guessed."""
    specs_dir = (specs_dir or DEFAULT_SPECS).expanduser()
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    report: dict[str, Any] = {"dry_run": dry_run, "courses": {}, "backups": [], "ambiguous": [], "unmatched": [], "possible_duplicates": []}
    registry = courses.Registry(directory)
    for slug in sorted(registry.courses):
        course = load_course(directory, slug)
        tasks, changed = derive_tasks(course.get("tasks", []), _chores(directory, slug))
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


def run_task_command(directory: Path, args) -> int:
    try:
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
