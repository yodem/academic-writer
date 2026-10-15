"""Chores store for the course pipeline: things Yotam (not a script) must do.

`REG/chores.json` is the store. `REG/digest/` holds only the read-only digest that NanoClaw mounts
(`chores.md` in Hebrew, `chores.json`); nothing else may live there. No ids or tokens reach the digest.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import courses

KINDS = ("assignment", "forum-post", "perusall-capture", "kotar-source", "missing-text", "manual")
STATUSES = ("open", "done")
KIND_HE = {
    "assignment": "מטלה",
    "forum-post": "הודעה בפורום",
    "perusall-capture": "צילום מפרוסל",
    "kotar-source": "מקור בכותר",
    "missing-text": "טקסט חסר",
    "manual": "משימה",
}
FIELDS = ("title", "text", "core_texts", "time_left_text", "due_text", "due_at")
DIGEST_FILES = ("chores.md", "chores.json")
_TOKEN_RE = re.compile(r"((?:wstoken|token|key|sesskey)=)[^&\s]+", re.I)


GENERAL = "general"  # pseudo-course for system chores (open Chrome, ToC audit failed)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _path(registry: courses.Registry) -> Path:
    return registry.directory / "chores.json"


def chore_id(course: str, kind: str, ref: str) -> str:
    return hashlib.sha256(f"{course}\0{kind}\0{ref}".encode()).hexdigest()[:10]


def _lock(registry: courses.Registry):
    registry.directory.mkdir(parents=True, exist_ok=True)
    handle = (registry.directory / ".chores.lock").open("a+")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def load(registry: courses.Registry) -> list[dict[str, Any]]:
    path = _path(registry)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: chores.json must be a list")
    return data


def add_chore(registry: courses.Registry, *, course: str, kind: str, ref: str, title: str = "", text: str = "",
              core_texts: list[str] | None = None, time_left_text: str = "", due_text: str = "",
              due_at: str | None = None) -> dict[str, Any]:
    """Create a chore, or update the existing one with the same (course, kind, ref); never duplicates.

    An updated chore keeps its id, `created` and status (a done chore stays done)."""
    if kind not in KINDS:
        raise ValueError(f"unknown chore kind {kind!r}; expected one of {', '.join(KINDS)}")
    if not course or not ref:
        raise ValueError("a chore needs a course and a ref")
    if course != GENERAL and course not in registry.courses:
        raise ValueError(f"unknown course {course!r} (use {GENERAL!r} for a chore not tied to a course)")
    values = {"title": title, "text": text, "core_texts": list(core_texts or []), "time_left_text": time_left_text,
              "due_text": due_text, "due_at": due_at}
    handle = _lock(registry)
    try:
        chores = load(registry)
        for chore in chores:
            if (chore["course"], chore["kind"], chore["ref"]) == (course, kind, ref):
                # a re-scan may know less than an earlier one: only non-empty values overwrite
                changed = {k: v for k, v in values.items() if v not in ("", None, []) and chore.get(k) != v}
                if changed:
                    chore.update(changed)
                    chore["updated"] = _now()
                    courses._atomic_json(_path(registry), chores)
                return chore
        now = _now()
        chore = {"id": chore_id(course, kind, ref), "kind": kind, "course": course, "ref": ref, **values,
                 "status": "open", "created": now, "updated": now}
        chores.append(chore)
        courses._atomic_json(_path(registry), chores)
        return chore
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def list_chores(registry: courses.Registry, *, status: str | None = None, course: str | None = None) -> list[dict[str, Any]]:
    return [c for c in load(registry) if (status is None or c["status"] == status) and (course is None or c["course"] == course)]


def mark_done(registry: courses.Registry, chore_id_: str) -> dict[str, Any]:
    handle = _lock(registry)
    try:
        chores = load(registry)
        matches = [c for c in chores if c["id"].startswith(chore_id_)]
        if len(matches) != 1:
            raise ValueError(f"chore {chore_id_!r}: {'no match' if not matches else 'ambiguous'}")
        chore = matches[0]
        if chore["status"] != "done":
            chore["status"] = "done"
            chore["updated"] = _now()
            courses._atomic_json(_path(registry), chores)
        return chore
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return _TOKEN_RE.sub(r"\1[REDACTED]", value)
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _due_key(chore: dict[str, Any]) -> tuple[int, str, str]:
    due = chore.get("due_at")
    if not due:
        return (1, "", chore.get("created", ""))
    try:
        parsed = datetime.fromisoformat(str(due))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (0, parsed.astimezone(timezone.utc).isoformat(), chore.get("created", ""))
    except ValueError:
        return (1, "", chore.get("created", ""))


def render_digest(registry: courses.Registry, open_chores: list[dict[str, Any]]) -> str:
    lines = ["# מטלות פתוחות", ""]
    if not open_chores:
        lines.append("אין מטלות פתוחות.")
    for chore in open_chores:
        name = registry.courses.get(chore["course"], {}).get("name", chore["course"])
        title = chore.get("title") or chore["ref"]
        lines.append(f"- **{_clean(name)}** · {KIND_HE[chore['kind']]}: {_clean(title)}")
        if chore.get("time_left_text"):
            lines.append(f"  - זמן שנותר: {_clean(chore['time_left_text'])}")
        if chore.get("due_text"):
            lines.append(f"  - מועד הגשה: {_clean(chore['due_text'])}")
        if chore.get("core_texts"):
            lines.append(f"  - טקסטי ליבה: {'; '.join(_clean(chore['core_texts']))}")
        if chore.get("text"):
            lines.append(f"  - המטלה: {' '.join(str(_clean(chore['text'])).split())}")
    return "\n".join(lines) + "\n"


def write_digest(registry: courses.Registry) -> Path:
    """Write REG/digest/{chores.md,chores.json} (open chores, by due date) and remove anything else there."""
    open_chores = sorted(list_chores(registry, status="open"), key=_due_key)
    folder = registry.directory / "digest"
    folder.mkdir(parents=True, exist_ok=True)
    public = [{k: _clean(v) for k, v in c.items() if k != "id"} for c in open_chores]
    courses._atomic_write(folder / "chores.md", render_digest(registry, open_chores))
    courses._atomic_json(folder / "chores.json", public)
    for extra in folder.iterdir():
        if extra.name not in DIGEST_FILES:
            if extra.is_dir():
                import shutil
                shutil.rmtree(extra)
            else:
                extra.unlink()
    return folder
