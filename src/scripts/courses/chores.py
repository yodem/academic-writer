"""Chores store for the course pipeline: things Yotam (not a script) must do.

`REG/chores.json` is the store. `REG/digest/` holds only the read-only digest that NanoClaw mounts
(`chores.md` in Hebrew, `chores.json`, and `wispr-unmatched.json`: the Wispr meetings no course claimed, as id/time/reason and a course-slug guess only); nothing else may live there. No ids or tokens reach the digest.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import courses

KINDS = ("assignment", "forum-post", "perusall-capture", "kotar-source", "missing-text", "manual", "exam", "reading")
STATUSES = ("open", "done")
KIND_HE = {
    "assignment": "מטלה",
    "forum-post": "הודעה בפורום",
    "perusall-capture": "צילום מפרוסל",
    "kotar-source": "מקור בכותר",
    "missing-text": "טקסט חסר",
    "manual": "משימה",
    "exam": "בחינה",
    "reading": "קריאה",
}
FIELDS = ("title", "text", "core_texts", "time_left_text", "due_text", "due_at", "room", "material")
DIGEST_FILES = ("chores.md", "chores.json", "wispr-unmatched.json")
_TOKEN_RE = re.compile(r"((?:wstoken|token|key|sesskey)=)[^&\s]+", re.I)


GENERAL = "general"  # pseudo-course for system chores (open Chrome, ToC audit failed)
SIGNIN_REF = "lemida-signin"  # the one "Chrome is signed out of Lemida" chore, whatever the watcher calls it
_SIGNIN_RE = re.compile(r"^(?:lemida[-_ ]?)?(?:log[-_ ]?in|sign[-_ ]?in)(?:[-_ ]\d{4}-\d{2}-\d{2})?$")
_CMID_RE = re.compile(r"^(?:cm|cmid)[:\-_ ]?(\d+)$")
_URL_ID_RE = re.compile(r"^https?://\S*[?&]id=(\d+)")


def canonical_ref(ref: str) -> str:
    """One spelling per Lemida item, so a reworded re-scan updates the chore instead of duplicating it.

    `cm:123`, `cmid-123` and a Moodle `...view.php?id=123` URL become `123`; any sign-in/login ref becomes
    SIGNIN_REF. Other refs are trimmed and lowercased."""
    ref = " ".join(ref.split()).lower()
    if _SIGNIN_RE.match(ref):
        return SIGNIN_REF
    match = _CMID_RE.match(ref) or _URL_ID_RE.match(ref)
    return match.group(1) if match else ref


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


MONTHS = {"ינואר": 1, "פברואר": 2, "מרץ": 3, "מרס": 3, "אפריל": 4, "מאי": 5, "יוני": 6, "יולי": 7, "אוגוסט": 8,
          "ספטמבר": 9, "אוקטובר": 10, "נובמבר": 11, "דצמבר": 12,
          "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
          "september": 9, "october": 10, "november": 11, "december": 12}
DUE_RE = re.compile(r"(\d{1,2})\s+(?:ב)?([^\W\d_]+),?\s+(\d{4})(?:,?\s+(\d{1,2}):(\d{2}))?")


def due_at_from_text(text: str | None, timezone_name: str = "Asia/Jerusalem") -> str | None:
    """Lemida's due text ("יום שני, 2 נובמבר 2026, 00:00" or "Monday, 2 November 2026, 12:00 AM") as an ISO time in
    the term's zone; None when it does not read as a date. The watcher passes due_at itself when it can; this is
    the fallback, so a dated assignment never becomes undated because the date was left as text."""
    m = DUE_RE.search(str(text or ""))
    if not m:
        return None
    month = MONTHS.get(m.group(2).casefold())
    if not month:
        return None
    hour, minute = int(m.group(4) or 0), int(m.group(5) or 0)
    tail = str(text)[m.end():].strip().upper()
    if tail.startswith("PM") and hour < 12:
        hour += 12
    elif tail.startswith("AM") and hour == 12:
        hour = 0
    try:
        when = datetime(int(m.group(3)), month, int(m.group(1)), hour, minute, tzinfo=ZoneInfo(timezone_name))
    except ValueError:
        return None
    return when.isoformat()


def add_chore(registry: courses.Registry, *, course: str, kind: str, ref: str, title: str = "", text: str = "",
              core_texts: list[str] | None = None, time_left_text: str = "", due_text: str = "",
              due_at: str | None = None, room: str = "", material: str = "") -> dict[str, Any]:
    """Create a chore, or update the existing one with the same (course, kind, canonical ref); never duplicates.

    An updated chore keeps its id, `created` and status (a done chore stays done). A sign-in chore is always
    one `general` chore, whichever course the watcher was scanning."""
    if kind not in KINDS:
        raise ValueError(f"unknown chore kind {kind!r}; expected one of {', '.join(KINDS)}")
    if not course or not ref:
        raise ValueError("a chore needs a course and a ref")
    ref = canonical_ref(ref)
    if ref == SIGNIN_REF:
        course = GENERAL
    if course != GENERAL and course not in registry.courses:
        raise ValueError(f"unknown course {course!r} (use {GENERAL!r} for a chore not tied to a course)")
    if not due_at and due_text:
        due_at = due_at_from_text(due_text, registry.term.get("timezone", "Asia/Jerusalem"))
    values = {"title": title, "text": text, "core_texts": list(core_texts or []), "time_left_text": time_left_text,
              "due_text": due_text, "due_at": due_at, "room": room, "material": material}
    handle = _lock(registry)
    try:
        chores = load(registry)
        for chore in chores:
            if (chore["course"], chore["kind"], canonical_ref(chore["ref"])) == (course, kind, ref):
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


def reopen(registry: courses.Registry, chore_id_: str) -> dict[str, Any]:
    """Undo mark_done: set a done chore back to open (the dashboard's undo). Idempotent."""
    handle = _lock(registry)
    try:
        chores = load(registry)
        matches = [c for c in chores if c["id"].startswith(chore_id_)]
        if len(matches) != 1:
            raise ValueError(f"chore {chore_id_!r}: {'no match' if not matches else 'ambiguous'}")
        chore = matches[0]
        if chore["status"] != "open":
            chore["status"] = "open"
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
        if chore.get("room"):
            lines.append(f"  - חדר: {_clean(chore['room'])}")
        if chore.get("material"):
            lines.append(f"  - חומר לבחינה: {_clean(chore['material'])}")
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
