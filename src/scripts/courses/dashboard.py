"""Local course dashboard: one page that shows how every course stands (`courses.py dashboard`).

Stdlib only (Python 3.9+). The server binds 127.0.0.1 and nothing else. Each run makes a random key that is
part of the printed URL; the first load turns it into an HttpOnly, SameSite=Strict cookie. Every request needs
the key or the cookie and an exact `Host: 127.0.0.1:<port>`; a POST also needs `Origin: http://127.0.0.1:<port>`.

Reads (never writes) the term directory: term.json, <slug>.json, links.json, refs/<slug>.json, chores.json
(digest/chores.json when the store is absent), digest/wispr-unmatched.json (id and time only), logs/daily-*.log
and queue/fetch/*.json. `GET /api/state` joins them and computes, deterministically:

- each course's next open task (nearest `due_at`; undated tasks after dated ones);
- a task's state: `missing` when a linked source is not-found or print-only and has no text, or an open
  `missing-text` chore names the task (its ref starts with the task's Lemida ref and a dash); `waiting` when a
  fetch job for a linked ref is queued or its OCR is queued/flagged/blocked; `ready` when every linked source is
  downloaded and in Trove; `unlinked` when no source is linked (never shown as ready); otherwise `pending`;
- the one-sentence lede ("what needs you") and the week agenda (class slots, semester-aware, in the term time zone).

Home-aware (read-only): the state also carries who the user is (`home.md` in the home folder), the role's nav, the
setup checks (`setup_checks.run_checks`, at most once a minute), every registered workspace and its agent-activity
runs (`activity.list_runs`), course colours, exams, a semester timeline and the week mode. A lecturer or researcher
gets no term fields: their overview is built from writing runs, workspaces and recently added sources.

Writes go only through existing functions: `POST /api/task/submit` and `/api/task/unsubmit` call tasks.py;
`POST /api/fetch` writes a job to queue/fetch/<ts>-<course>.json for Claude or the nightly run to execute with
`refs.py fetch` (the server never fetches anything). `POST /api/extract` writes a job to queue/extract/<ts>-<course>.json
({course, items: [{kind: source|ref, key, method}], created_at}) for the nightly run's `refs.py extract-queue` (the server
never extracts, OCRs or calls a model). Nothing is extracted unless the student asked for it here. `GET /api/events` is a Server-Sent Events stream: a server
thread scans the registry's mtimes about once a second and sends `state-changed`; the browser never polls.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import hmac
import http.server
import importlib.util
import json
import os
import re
import secrets
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I leaves the script dir off sys.path
import courses  # noqa: E402
import tasks as tasks_mod  # noqa: E402
import extract as extract_mod  # noqa: E402
import nightly as nightly_mod  # noqa: E402

HERE = Path(__file__).resolve().parent


def _load_script(name: str, filename: str):
    """Load a sibling script of src/scripts by path, so its generic module name never lands on sys.path."""
    spec = importlib.util.spec_from_file_location(name, HERE.parent / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


home_mod = _load_script("aw_home", "home.py")
activity_mod = _load_script("aw_activity", "activity.py")
setup_mod = _load_script("aw_setup_checks", "setup_checks.py")
ASSETS = HERE / "dashboard"
DEFAULT_PORT = 8787
SOON_HOURS = 72
NEW_LESSON_DAYS = 1  # a lesson dated today or yesterday is "new"
RECENT_SUBMIT_HOURS = 12  # a task submitted this recently stays on the overview, struck through
READING_KINDS = ("reading",)
LESSON_DONE = ("done", "appended")
MISSING_STATUSES = ("not-found", "print-only")
OCR_WAITING = ("queued", "flagged", "blocked")
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
IDENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
ASSET_RE = re.compile(r"^/img/([a-z0-9-]+\.webp)$")
VIEW_RE = re.compile(r"^/views/([a-z-]+\.js)$")
STATIC_FILES = {"/app.css": "text/css; charset=utf-8", "/margin.css": "text/css; charset=utf-8",
                "/about.json": "application/json; charset=utf-8"}
COURSE_COLORS = ("teal", "coral", "violet", "blue", "ochre", "rose", "olive", "slate")  # brand file order
NON_TERM_ROLES = ("lecturer", "researcher")
NAV_STUDENT = ["overview", "timeline", "courses", "writing", "about"]
NAV_OTHER = ["overview", "writing", "about"]
SETUP_CACHE_SECONDS = 60
LIBRARY_DAYS = 7
LIBRARY_DATE_KEYS = ("addedAt", "added_at", "added", "createdAt", "created_at", "created", "ingestedAt")
MAX_TIMELINE_WEEKS = 80
MAX_BODY = 64 * 1024
DN = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
SEM_HE = {"A": "סמסטר א׳", "B": "סמסטר ב׳", "yearly": "שנתי"}


# --- reading the registry ------------------------------------------------------------------------

def _read_json(path: Path, warnings: List[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        warnings.append(f"{path.name}: {exc}")
        return None


def _parse_dt(value: Any, tz: ZoneInfo) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(text[:10]), datetime.min.time())
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def _semester_range(term: Dict[str, Any], label: str) -> Optional[Tuple[date, date]]:
    try:
        return courses._semester_dates(term, label)
    except (TypeError, ValueError):
        return None


def slot_active(term: Dict[str, Any], semester: Any, day: date) -> bool:
    """A slot meets on `day` when its semester covers it. With no semester dates configured, slots always meet."""
    sems = term.get("semesters")
    if not isinstance(sems, dict) or not any(_semester_range(term, k) for k in sems):
        return True
    label = str(semester or "yearly")
    if label.lower() == "yearly":
        return any(_semester_range(term, k) and _semester_range(term, k)[0] <= day <= _semester_range(term, k)[1] for k in sems)
    rng = _semester_range(term, label)
    return bool(rng and rng[0] <= day <= rng[1])


def course_season(term: Dict[str, Any], course: Dict[str, Any], today: date) -> str:
    """`current`, `later` (every slot is in a semester that has not started) or `past`."""
    slots = [s for s in course.get("slots") or [] if isinstance(s, dict)]
    sems = term.get("semesters")
    if not slots or not isinstance(sems, dict):
        return "current"
    states = set()
    for slot in slots:
        label = str(slot.get("semester") or "yearly")
        if label.lower() == "yearly" or not _semester_range(term, label):
            states.add("current")
            continue
        start, end = _semester_range(term, label)
        states.add("later" if today < start else "past" if today > end else "current")
    if "current" in states:
        return "current"
    return "later" if "later" in states else "past"


def _nightly(directory: Path) -> Optional[str]:
    logs = sorted((directory / "logs").glob("daily-*.log")) if (directory / "logs").is_dir() else []
    if not logs:
        return None
    newest = logs[-1]
    try:
        lines = newest.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        match = re.match(r"^== done (\S+)", line)
        if match:
            stamp = match.group(1)
            stamp = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", stamp)  # 2026-10-16T10:52:47+0300
            try:
                return datetime.fromisoformat(stamp).isoformat()
            except ValueError:
                break
    return datetime.fromtimestamp(newest.stat().st_mtime, tz=timezone.utc).isoformat()


def queued_fetches(directory: Path) -> List[Dict[str, Any]]:
    """Pending fetch jobs: top-level queue/fetch/*.json (a consumer moves finished jobs to queue/fetch/done/)."""
    folder = directory / "queue" / "fetch"
    jobs = []
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            data = _read_json(path, [])
            if isinstance(data, dict) and data.get("course"):
                jobs.append({**data, "file": path.name})
    return jobs


def queued_extracts(directory: Path) -> set:
    """(course, kind, key) of every item waiting for extraction: pending queue/extract/*.json jobs, and handoff files
    (queue/extract/handoff/*.json) whose text Claude has not written yet. Read-only."""
    waiting = set()
    folder = directory / "queue" / "extract"
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        job = _read_json(path, [])
        if isinstance(job, dict) and job.get("course"):
            for it in job.get("items") or []:
                if isinstance(it, dict):
                    waiting.add((str(job["course"]), str(it.get("kind")), str(it.get("key"))))
    handoff = folder / "handoff"
    for path in sorted(handoff.glob("*.json")) if handoff.is_dir() else []:
        h = _read_json(path, [])
        if isinstance(h, dict) and h.get("course") and not (h.get("out") and Path(str(h["out"])).is_file()):
            waiting.add((str(h["course"]), str(h.get("kind")), str(h.get("key"))))
    return waiting


def pending_source_jobs(directory: Path) -> Dict[Tuple[str, str], float]:
    """(course, sha8) -> the job file's mtime, for every `courses.py add-source` Trove job still in queue/sources
    (nothing drains them by itself; the mtime is when the file was downloaded and registered)."""
    folder = directory / "queue" / "sources"
    out: Dict[Tuple[str, str], float] = {}
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        job = _read_json(path, [])
        if isinstance(job, dict) and job.get("slug") and job.get("sha8"):
            try:
                out[(str(job["slug"]), str(job["sha8"]))] = path.stat().st_mtime
            except OSError:
                continue
    return out


def extract_watch_on(agents: Optional[Path] = None) -> bool:
    """True when `courses.py nightly watch on` installed the LaunchAgent that extracts and ingests a dashboard pick at once."""
    folder = agents or Path.home() / "Library" / "LaunchAgents"
    return (folder / (nightly_mod.WATCH_LABEL + ".plist")).is_file()


def _untroved_days(src: Dict[str, Any], st: Dict[str, Any], since: Optional[float], now: Optional[datetime]) -> Optional[int]:
    """Whole days a downloaded source has waited outside Trove (its add-source job's age, else its file's), or None
    when it is in Trove or was never downloaded."""
    if not st["downloaded"] or st["in_trove"]:
        return None
    if since is None:
        try:
            since = Path(str(src.get("file"))).expanduser().stat().st_mtime if src.get("file") else None
        except OSError:
            since = None
    if since is None or now is None:
        return 0
    return max(0, (now - datetime.fromtimestamp(since, now.tzinfo)).days)


# --- per-source and per-task status --------------------------------------------------------------

def _ocr_waiting(ref: Dict[str, Any]) -> Optional[str]:
    ocr_next = ref.get("ocr_next")
    if isinstance(ocr_next, dict) and str(ocr_next.get("state", "")).lower() in OCR_WAITING:
        return str(ocr_next.get("state")).lower()
    ocr = ref.get("ocr")
    if isinstance(ocr, str) and ocr.strip().upper().startswith("BLOCKED"):
        return "blocked"
    if isinstance(ocr, dict) and str(ocr.get("state", "")).lower() in ("flagged", "blocked"):
        return str(ocr.get("state")).lower()
    return None


def _extract_flags(directory: Optional[Path], slug: str, kind: str, key: str, file: Any, downloaded: bool,
                   in_trove: bool, pending_job: bool, waiting: set) -> Dict[str, Any]:
    """`extracted` (text file exists), `extract_queued`, and `extractable`: a downloaded file with no extracted text that
    is not in Trove yet (a source with a pending add-source job counts as not extracted even if its file is the only copy)."""
    extracted = bool(directory and key and extract_mod.has_extracted_text(directory, slug, kind, key))
    queued = (slug, kind, key) in waiting
    on_disk = bool(file) and Path(str(file)).expanduser().is_file()
    return {"extracted": extracted, "extract_queued": queued,
            "extractable": bool(downloaded and on_disk and not extracted and not queued and (pending_job or not in_trove))}


def ref_item(ref: Dict[str, Any], sources: List[Dict[str, Any]], queued: bool, *, directory: Optional[Path] = None,
             slug: str = "", waiting: Optional[set] = None) -> Dict[str, Any]:
    st = tasks_mod.ref_status(ref, sources)
    has_text = st["downloaded"] or st["in_trove"]
    status = ref.get("status", "")
    missing = status in MISSING_STATUSES and not has_text and not queued
    ocr = _ocr_waiting(ref)
    return {"type": "ref", "key": ref.get("key", ""), "title": ref.get("citation", ""), "status": status,
            "role": ref.get("role", ""), "downloaded": st["downloaded"], "in_trove": st["in_trove"],
            "in_notebooklm": st["in_notebooklm"], "trove": st["trove"], "missing": missing, "queued": queued,
            "ocr": ocr, "waiting": queued or bool(ocr), "fetchable": not has_text and status != "ingested" and not queued,
            "tasks": list(ref.get("tasks") or []),
            **_extract_flags(directory, slug, "ref", str(ref.get("key", "")), ref.get("download_path"), st["downloaded"],
                             st["in_trove"], False, waiting or set())}


def source_item(src: Dict[str, Any], *, directory: Optional[Path] = None, slug: str = "", waiting: Optional[set] = None,
                pending_jobs: Optional[Dict[Tuple[str, str], float]] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    st = tasks_mod.source_status(src)
    jobs = pending_jobs or {}
    return {"type": "source", "key": st["key"], "title": src.get("title", ""), "status": src.get("status", ""),
            "role": "", "downloaded": st["downloaded"], "in_trove": st["in_trove"], "in_notebooklm": st["in_notebooklm"],
            "trove": st["trove"], "missing": False, "queued": False, "ocr": None, "waiting": False, "fetchable": False,
            "tasks": list(src.get("tasks") or []),
            "untroved_days": _untroved_days(src, st, jobs.get((slug, st["key"])), now),
            **_extract_flags(directory, slug, "source", st["key"], src.get("file"), st["downloaded"], st["in_trove"],
                             (slug, st["key"]) in jobs, waiting or set())}


def chore_item(chore: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "chore", "key": chore.get("id", ""), "title": chore.get("title") or chore.get("ref", ""), "status": "missing-text",
            "role": "", "downloaded": False, "in_trove": False, "in_notebooklm": False, "trove": "", "missing": True,
            "queued": False, "ocr": None, "waiting": False, "fetchable": False, "tasks": []}


def task_state(task: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
    if task.get("status") == "submitted":
        return "submitted"
    if any(i["missing"] for i in items):
        return "missing"
    if any(i["waiting"] for i in items):
        return "waiting"
    if not items:
        return "unlinked"
    if all(i["downloaded"] and i["in_trove"] for i in items):
        return "ready"
    return "pending"


def kind_word(kind: Any) -> str:
    return "קריאה" if kind in READING_KINDS else "בחינה" if kind == "exam" else "הגשה"


# --- state ---------------------------------------------------------------------------------------

# --- time windows: one definition, used by build_state and next_boundary alike --------------------
# Aware datetimes that share a ZoneInfo subtract as wall-clock times, so across a DST switch "72 hours" would
# drift by an hour. Every window is computed on UTC instants instead.

def _utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc)


def soon_from(due: datetime) -> datetime:
    """The instant a deadline enters the SOON_HOURS window (72 real hours before it)."""
    return _utc(due) - timedelta(hours=SOON_HOURS)


def undo_until(submitted_at: datetime) -> datetime:
    """The instant a dashboard submit leaves the RECENT_SUBMIT_HOURS undo window."""
    return _utc(submitted_at) + timedelta(hours=RECENT_SUBMIT_HOURS)


def is_soon(due: datetime, now: datetime) -> bool:
    return soon_from(due) <= _utc(now) <= _utc(due)


def is_overdue(due: datetime, now: datetime) -> bool:
    return _utc(due) < _utc(now)


def in_undo_window(submitted_at: datetime, now: datetime) -> bool:
    return _utc(now) < undo_until(submitted_at)


def _due_sort(task: Dict[str, Any]) -> Tuple[int, str, str]:
    return (0, task["due_utc"], task["id"]) if task.get("due_utc") else (1, "", task["id"])


def week_start(day: date) -> date:
    """Weeks start on Sunday."""
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _empty_state(reason: str, now: datetime) -> Dict[str, Any]:
    today = now.date()
    start = week_start(today)
    return {"empty": True, "reason": reason, "term": None, "timezone": None, "now": now.isoformat(), "today": today.isoformat(),
            "nightly": None, "courses": [], "overview": {"rows": [], "quiet": [], "later": [], "counts": {"submit": 0, "read": 0}},
            "lede": [{"t": "עוד אין קורסים."}], "agenda": _agenda_frame(start), "wispr_unmatched": [], "warnings": [],
            "exams": [], "timeline": {"weeks": []}}


def _agenda_frame(start: date) -> Dict[str, Any]:
    return {"start": start.isoformat(), "prev": (start - timedelta(days=7)).isoformat(), "next": (start + timedelta(days=7)).isoformat(),
            "days": [{"date": (start + timedelta(days=k)).isoformat(), "dow": k, "items": []} for k in range(7)], "has_work": False}


def resolve_directory(term: Optional[str] = None) -> Optional[Path]:
    """The term directory, or None for a fresh install (no registry yet) or an ambiguous term. Never raises."""
    try:
        return courses.registry_dir(term)
    except (ValueError, OSError):
        return None


def missing_reason(term: Optional[str] = None) -> str:
    """Why resolve_directory found nothing: `ambiguous-term` (several terms, none chosen) or `no-registry`."""
    root = courses.courses_root()
    try:
        terms = [p for p in root.iterdir() if p.is_dir()] if root.is_dir() else []
    except OSError:
        terms = []
    return "ambiguous-term" if len(terms) > 1 and not (term or os.environ.get("ACADEMIC_TERM")) else "no-registry"


def _https(url: Any) -> Optional[str]:
    """Only https links reach the page (a registry value can never become a javascript: link)."""
    return url if isinstance(url, str) and url.startswith("https://") else None


def assign_colors(raw_courses: Dict[str, Dict[str, Any]], links: Any = None) -> Dict[str, str]:
    """A brand course hue per course. An explicit `color` in the course file wins and is reserved; the others
    take the eight hues in brand order over courses sorted by slug, skipping hues taken explicitly (`links` is
    accepted for the caller's signature and unused). Past eight courses the hues repeat in order."""
    out: Dict[str, str] = {}
    for slug, course in raw_courses.items():
        candidate = course.get("color")
        if isinstance(candidate, str) and candidate in COURSE_COLORS:
            out[slug] = candidate
    free = [c for c in COURSE_COLORS if c not in out.values()] or list(COURSE_COLORS)
    n = 0
    for slug in sorted(raw_courses):
        if slug not in out:
            out[slug] = free[n % len(free)]
            n += 1
    return out


def week_mode(now: datetime) -> str:
    """`week-ahead` from Saturday 18:00 local through Sunday, otherwise `today` (weekday(): Saturday 5, Sunday 6)."""
    return "week-ahead" if now.weekday() == 6 or (now.weekday() == 5 and now.hour >= 18) else "today"


def exam_rows(course_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [{"course": c["slug"], "task": t["id"], "title": t["title"], "due_at": t["due_at"], "due_date": t["due_date"],
             "due_time": t["due_time"], "room": t["room"], "material": t["material"], "soon": t["soon"],
             "overdue": t["overdue"]}
            for c in course_list for t in c["tasks"] if t["exam"] and t["status"] != "submitted"]
    rows.sort(key=lambda r: (0, r["due_at"], r["task"]) if r["due_at"] else (1, "", r["task"]))
    return rows


def build_timeline(term: Dict[str, Any], course_list: List[Dict[str, Any]], today: date) -> Dict[str, Any]:
    """Weeks (Sunday start) covering every semester plus any week that holds a dated task, each with its items."""
    items: Dict[date, List[Dict[str, Any]]] = {}
    for c in course_list:
        for t in c["tasks"]:
            if not t["due_date"]:
                continue
            day = date.fromisoformat(t["due_date"])
            items.setdefault(week_start(day), []).append({
                "date": t["due_date"], "time": t["due_time"] if t["due_time"] != "00:00" else "", "course": c["slug"],
                "task": t["id"], "title": t["title"], "state": t["state"], "status": t["status"],
                "kind": "exam" if t["exam"] else "reading" if t["reading"] else "submit"})
    starts = set(items)
    sems = term.get("semesters")
    for label in (sems if isinstance(sems, dict) else {}):
        rng = _semester_range(term, label)
        if rng:
            cursor = week_start(rng[0])
            while cursor <= rng[1]:
                starts.add(cursor)
                cursor += timedelta(days=7)
    weeks = []
    for start in sorted(starts)[:MAX_TIMELINE_WEEKS]:
        rows = sorted(items.get(start, []), key=lambda i: (i["date"], i["time"], i["task"]))
        weeks.append({"start": start.isoformat(), "current": start == week_start(today), "items": rows})
    return {"weeks": weeks}


def build_state(directory: Optional[Path], now: Optional[datetime] = None, week: Optional[str] = None,
                reason: str = "no-registry", ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Join the registry files into the page's one JSON. Pure read: nothing is written or locked.

    `ctx` (from `gather_context`) adds home, nav, setup, workspaces and writing; without it those carry
    "not configured" values, which keeps the term-only callers working."""
    warnings: List[str] = []
    has_registry = directory is not None and (directory / "term.json").is_file()
    if ctx and ctx.get("role") in NON_TERM_ROLES:  # a lecturer or researcher takes no courses: the registry is ignored
        return _finish(_writer_state(now or datetime.now().astimezone(), ctx), ctx, has_registry)
    if directory is None or not has_registry:
        state = _empty_state(reason if directory is None else "no-registry", (now or datetime.now().astimezone()))
        return _finish(state, ctx, has_registry)
    term = _read_json(directory / "term.json", warnings) or {}
    try:
        tz = ZoneInfo(str(term.get("timezone") or "Asia/Jerusalem"))
    except Exception:  # unknown zone name: fall back rather than fail the page
        tz = ZoneInfo("Asia/Jerusalem")
    now = (now or datetime.now(tz)).astimezone(tz)
    today = now.date()

    raw_courses: Dict[str, Dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        if path.name == "term.json":
            continue
        data = _read_json(path, warnings)
        if isinstance(data, dict) and data.get("slug") and SLUG_RE.match(str(data["slug"])):
            raw_courses[str(data["slug"])] = data
    if not raw_courses:
        state = _empty_state("no-courses", now)
        state.update({"term": term.get("term"), "timezone": str(tz), "nightly": _nightly(directory), "warnings": warnings})
        return _finish(state, ctx, has_registry)

    links = _read_json(directory / "links.json", warnings) or {}
    colors = assign_colors(raw_courses, links)
    unmatched_raw = _read_json(directory / "digest" / "wispr-unmatched.json", warnings) or {}
    meetings = unmatched_raw.get("meetings") if isinstance(unmatched_raw, dict) else unmatched_raw
    unmatched = []
    for m in meetings or []:
        if isinstance(m, dict) and m.get("start"):
            when = _parse_dt(m.get("start"), tz)
            if when:
                guess = m.get("course_guess")
                unmatched.append({"id": str(m.get("id", "")), "start": when.isoformat(),
                                  "course_guess": guess if isinstance(guess, str) and SLUG_RE.match(guess) else None})
    store = _read_json(directory / "chores.json", warnings)
    if store is None:  # a mirror that only has the digest: chores without ids (no task can be derived from them)
        store = [dict(c, id="") for c in (_read_json(directory / "digest" / "chores.json", warnings) or [])]
    chores = [c for c in store if isinstance(c, dict)] if isinstance(store, list) else []
    jobs = queued_fetches(directory)
    extract_waiting = queued_extracts(directory)
    source_jobs = pending_source_jobs(directory)
    queued_keys = {(j["course"], str(k)) for j in jobs for k in (j.get("refs") or [])}
    lemida_base = str((term.get("lemida") or {}).get("base_url", "")).rstrip("/")

    out_courses = []
    for slug, course in raw_courses.items():
        course_chores = [c for c in chores if c.get("course") == slug]
        derived, _ = tasks_mod.derive_tasks(course.get("tasks") or [], [c for c in course_chores if c.get("id")], str(tz))
        refs_data = _read_json(directory / "refs" / f"{slug}.json", warnings) or {}
        refs_list = [r for r in refs_data.get("refs") or [] if isinstance(r, dict)]
        sources = [s for s in course.get("sources") or [] if isinstance(s, dict)]
        ref_items = [ref_item(r, sources, (slug, str(r.get("key"))) in queued_keys, directory=directory, slug=slug,
                              waiting=extract_waiting) for r in refs_list]
        src_items = [source_item(s, directory=directory, slug=slug, waiting=extract_waiting, pending_jobs=source_jobs, now=now) for s in sources if s.get("kind") != "media" and not s.get("lesson_key")]
        chore_by_id = {c.get("id"): c for c in course_chores}
        untroved = [i["untroved_days"] for i in src_items if i["untroved_days"] is not None]

        task_rows = []
        linked_keys = set()
        claimed_chores = set()
        for task in derived:
            tid = task["id"]
            items = [i for i in ref_items + src_items if tid in i["tasks"]]
            linked_keys.update((i["type"], i["key"]) for i in items)
            lemida_refs = [str(chore_by_id.get(cid, {}).get("ref", "")) for cid in task.get("chore_ids") or []]
            for chore in course_chores:
                if chore.get("kind") == "missing-text" and chore.get("status") == "open" and any(
                        r and str(chore.get("ref", "")).startswith(r + "-") for r in lemida_refs):
                    items.append(chore_item(chore))
                    claimed_chores.add(chore.get("id"))
            due = _parse_dt(task.get("due_at"), tz)
            submitted_at = _parse_dt(task.get("submitted_at"), tz)
            # the first chore whose module type is known gives the link
            lemida_url = next((url for url in (courses.lemida_module_url(lemida_base, course, chore_by_id.get(cid, {}).get("ref"),
                                                                         chore_by_id.get(cid, {}).get("kind", ""))
                                               for cid in task.get("chore_ids") or []) if url), None)
            first_chore = chore_by_id.get((task.get("chore_ids") or [None])[0]) or {}
            task_rows.append({
                "id": tid, "course": slug, "title": task.get("title") or "", "kind": task.get("kind") or "",
                "kind_word": kind_word(task.get("kind")), "reading": task.get("kind") in READING_KINDS,
                "exam": task.get("kind") == "exam", "room": str(task.get("room") or ""),
                "material": str(task.get("material") or ""),
                "status": task.get("status") or "open", "due_at": due.isoformat() if due else None,
                "due_date": due.date().isoformat() if due else None, "due_time": due.strftime("%H:%M") if due else None,
                "due_utc": due.astimezone(timezone.utc).isoformat() if due else None,
                "soon": bool(due and is_soon(due, now)),
                "overdue": bool(due and is_overdue(due, now)),
                "submitted_at": submitted_at.isoformat() if submitted_at else None,
                # only a submit made through task_submit (it records closed_chores) can be undone or called "you marked it";
                # a task whose chore the watcher closed is just a past task
                "recently_submitted": bool(submitted_at and "closed_chores" in task
                                           and in_undo_window(submitted_at, now)),
                "desc": first_chore.get("text") or "", "core_texts": list(first_chore.get("core_texts") or []),
                "lemida_url": _https(lemida_url),
                "state": task_state(task, items), "items": items,
                "missing_count": sum(1 for i in items if i["missing"]),
            })
        open_tasks = sorted((t for t in task_rows if t["status"] != "submitted"), key=_due_sort)
        more = [i for i in ref_items + src_items if (i["type"], i["key"]) not in linked_keys]
        lessons = []
        for lesson in course.get("lessons") or []:
            if not isinstance(lesson, dict):
                continue
            try:
                ldate = date.fromisoformat(str(lesson.get("date", ""))[:10])
            except ValueError:
                ldate = None
            done = lesson.get("status") in LESSON_DONE
            lessons.append({"date": ldate.isoformat() if ldate else None, "status": lesson.get("status") or "",
                            "new": bool(done and ldate and 0 <= (today - ldate).days <= NEW_LESSON_DAYS)})
        lessons.sort(key=lambda x: x["date"] or "")
        notices = [{"kind": c.get("kind"), "title": c.get("title") or c.get("ref", ""),
                    "due_at": (_parse_dt(c.get("due_at"), tz).isoformat() if _parse_dt(c.get("due_at"), tz) else None)}
                   for c in course_chores if c.get("status") == "open" and c.get("kind") not in tasks_mod.TASK_KINDS
                   and c.get("id") not in claimed_chores]
        link = links.get(slug) if isinstance(links, dict) else None
        link = link if isinstance(link, dict) else {}
        lemida_course = link.get("lemida_url") or (f"{lemida_base}/course/view.php?id={course['lemida_course_id']}"
                                                   if lemida_base and course.get("lemida_course_id") else None)
        notebook = link.get("notebook_url") or (f"https://notebooklm.google.com/notebook/{course['notebook_id']}" if course.get("notebook_id") else None)
        drive = link.get("drive_url") or (f"https://drive.google.com/drive/folders/{course['drive_folder_id']}" if course.get("drive_folder_id") else None)
        book_id = link.get("trove_book_id") or course.get("book_id")
        trove_url = None
        try:
            import bookmarks  # TROVE_URL_FORM is None until a verified form is recorded there
            trove_url = bookmarks.trove_url(str(book_id)) if book_id else None
        except Exception:
            trove_url = None
        out_courses.append({
            "slug": slug, "name": course.get("name") or slug, "lecturer": course.get("lecturer") or "",
            "color": colors[slug], "unmatched_recordings": sum(1 for u in unmatched if u["course_guess"] == slug),
            "mode": course.get("mode"), "slots": [s for s in course.get("slots") or [] if isinstance(s, dict)],
            "season": course_season(term, course, today),
            "links": {"lemida": _https(lemida_course), "notebook": _https(notebook), "drive": _https(drive),
                      "trove_book_id": book_id, "trove_url": _https(trove_url), "wispr": _https(link.get("wispr_url"))},
            "tasks": sorted(task_rows, key=_due_sort), "next_task": open_tasks[0]["id"] if open_tasks else None,
            "state": open_tasks[0]["state"] if open_tasks else None, "open_count": len(open_tasks), "more": more,
            "lessons": lessons, "new_lesson": any(l["new"] for l in lessons), "notices": notices,
            "perusall_open": sum(1 for c in course_chores if c.get("kind") == "perusall-capture" and c.get("status") == "open"),
            "storage": {"trove_book_id": book_id, "notebook_sources": sum(1 for s in sources if s.get("notebook_source_id")),
                        "drive": bool(drive), "sources": len(src_items), "refs": len(ref_items)},
            "queued_jobs": sum(1 for j in jobs if j["course"] == slug),
            "untroved": {"count": len(untroved), "oldest_days": max(untroved, default=0)},
        })

    by_slug = {c["slug"]: c for c in out_courses}
    rows = []
    for c in out_courses:
        for t in c["tasks"]:
            if t["id"] == c["next_task"]:
                rows.append({"course": c["slug"], "task": t["id"], "submitted": False})
    rows.sort(key=lambda r: _due_sort(next(t for t in by_slug[r["course"]]["tasks"] if t["id"] == r["task"])))
    for c in out_courses:
        for t in c["tasks"]:
            if t["status"] == "submitted" and t["recently_submitted"]:
                rows.append({"course": c["slug"], "task": t["id"], "submitted": True})
    busy = {r["course"] for r in rows if not r["submitted"]}
    quiet = [c["slug"] for c in out_courses if c["slug"] not in busy and c["season"] != "later"]
    later = [c["slug"] for c in out_courses if c["slug"] not in busy and c["season"] == "later"]
    open_all = [t for c in out_courses for t in c["tasks"] if t["status"] != "submitted"]
    counts = {"submit": sum(1 for t in open_all if not t["reading"] and not t["exam"]),
              "read": sum(1 for t in open_all if t["reading"])}

    try:
        start = week_start(date.fromisoformat(week)) if week else week_start(today)
    except ValueError:
        start = week_start(today)

    state = {
        "empty": False, "reason": None, "term": term.get("term"), "timezone": str(tz), "now": now.isoformat(),
        "today": today.isoformat(), "nightly": _nightly(directory), "extract_watch": extract_watch_on(), "courses": out_courses,
        "overview": {"rows": rows, "quiet": quiet, "later": later, "counts": counts},
        "lede": lede(out_courses, now), "agenda": agenda(term, out_courses, start, today),
        "wispr_unmatched": unmatched, "queued_jobs": len(jobs), "warnings": warnings,
        "exams": exam_rows(out_courses), "timeline": build_timeline(term, out_courses, today),
    }
    return _finish(state, ctx, has_registry)


# --- home, roles, setup, writing -----------------------------------------------------------------

def _clean_str(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def registry_rows(home: Optional[Path]) -> List[Dict[str, Any]]:
    """The registered workspaces of `home`, each `{path, type, course, exists}` with plain strings only.
    A row that is not an object, or whose path is not a non-empty string, is skipped; a type or course that is not
    a string reads as None. Never raises on a malformed `workspaces.json`."""
    if home is None:
        return []
    rows = []
    for row in home_mod._load_rows(home):
        path = row.get("path") if isinstance(row, dict) else None
        if not isinstance(path, str) or not path or "\0" in path:
            continue
        try:
            exists = Path(path).is_dir()
        except (OSError, ValueError):
            exists = False
        rows.append({"path": path, "type": _clean_str(row.get("type")), "course": _clean_str(row.get("course")),
                     "exists": exists})
    return rows


def workspace_rows(home: Optional[Path]) -> List[Dict[str, Any]]:
    """The registered workspaces of `home` plus the folders found under it that never reached the registry
    (`home_mod.discover_workspaces`), deduplicated by resolved path so a registered row keeps its own fields."""
    rows = registry_rows(home)
    if home is None:
        return rows
    known = set()
    for row in rows:
        known.add(_resolved(row["path"]))
    for found in home_mod.discover_workspaces(home):
        key = _resolved(found["path"])
        if key in known:
            continue
        known.add(key)
        rows.append({"path": found["path"], "type": None, "course": None, "exists": True})
    return rows


def _resolved(path: str) -> str:
    try:
        return str(Path(path).resolve())
    except (OSError, RuntimeError, ValueError):
        return path


def _library_added(sources: Any, now: datetime) -> List[Tuple[str, str, str]]:
    """(id, title, added iso) of `sources.json` entries added within LIBRARY_DAYS; undated entries never count."""
    rows = sources.get("sources") if isinstance(sources, dict) else sources
    found = []
    for entry in rows if isinstance(rows, list) else []:
        if not isinstance(entry, dict):
            continue
        stamp = next((entry[k] for k in LIBRARY_DATE_KEYS if entry.get(k)), None)
        when = _parse_dt(stamp, now.tzinfo or timezone.utc)
        if when and timedelta(0) <= _utc(now) - _utc(when) <= timedelta(days=LIBRARY_DAYS):
            ident = str(entry.get("sourceId") or entry.get("id") or "")
            found.append((ident, str(entry.get("title") or entry.get("name") or ident), when.isoformat()))
    return found


def gather_context(home: Optional[Path], checks: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    """Everything the page needs beyond the term registry. Read-only; a missing or moved home is reported, never made."""
    values: Dict[str, Any] = {}
    rows: List[Dict[str, Any]] = []
    missing = False
    if home is not None:
        try:
            if home.is_dir():
                values, _ = home_mod._read_md(home / home_mod.DIR_NAME / home_mod.HOME_FILE)
                rows = workspace_rows(home)
            else:
                missing = True
        except OSError:
            missing = True
    role = values.get("role") if values.get("role") in home_mod.ROLES else None
    runs = activity_mod.list_runs(rows, limit=200, now=now.timestamp())
    per_ws: Dict[str, List[Dict[str, Any]]] = {}
    for view in runs["active"] + runs["history"]:
        per_ws.setdefault(str(view["workspace"]), []).append(view)
    workspaces = []
    for row in rows:
        mine = per_ws.get(row["path"], [])  # newest first, as list_runs sorts
        workspaces.append({"path": row["path"], "name": Path(row["path"]).name, "type": row.get("type"),
                           "course": row.get("course"), "exists": bool(row.get("exists")), "runs": len(mine),
                           "last_run": mine[0]["started"] if mine else None,
                           "last_status": mine[0]["status"] if mine else None})
    library: List[Dict[str, Any]] = []
    if role in NON_TERM_ROLES:
        for row in rows:
            if not row.get("exists"):
                continue
            data = _read_json(Path(row["path"]) / home_mod.DIR_NAME / "sources.json", [])
            for ident, title, added in _library_added(data, now):
                library.append({"workspace": Path(row["path"]).name, "id": ident, "title": title, "added": added})
        library.sort(key=lambda x: (x["added"], x["id"]), reverse=True)
    return {
        "home": {"name": _clean_str(values.get("name")), "role": role, "institution": _clean_str(values.get("institution")),
                 "degree": _clean_str(values.get("degree")), "missing": missing, "configured": home is not None},
        "role": role, "setup": checks, "workspaces": workspaces, "library": library,
        "writing": {"active": runs["active"], "history": runs["history"]},
    }


def _no_context() -> Dict[str, Any]:
    return {"home": {"name": None, "role": None, "institution": None, "degree": None, "missing": False, "configured": False},
            "role": None, "setup": {"complete": None, "checks": []}, "workspaces": [], "library": [],
            "writing": {"active": [], "history": []}}


def setup_block(runner: Callable[[], List[Dict[str, Any]]]) -> Dict[str, Any]:
    """`{complete, checks}`; complete means no required (non-optional) check failed. A crashing runner reads as incomplete."""
    try:
        checks = [c for c in runner() if isinstance(c, dict)]
    except Exception as exc:
        return {"complete": False, "checks": [], "error": str(exc)}
    return {"complete": not any(c.get("ok") is False and not c.get("optional") for c in checks), "checks": checks}


def _nav(ctx: Dict[str, Any], has_registry: bool) -> List[str]:
    role = ctx.get("role")
    nav = list(NAV_STUDENT if role == "student" or (role is None and has_registry) else NAV_OTHER)
    if ctx["setup"].get("complete") is False:
        nav.insert(0, "setup")
    return nav


def _writer_state(now: datetime, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """A lecturer's or researcher's state: no term fields; the overview comes from writing runs, projects and library."""
    today = now.date()
    active, history = ctx["writing"]["active"], ctx["writing"]["history"]
    projects = sorted(ctx["workspaces"], key=lambda w: (w["last_run"] or "", w["path"]), reverse=True)
    results = [{k: r.get(k) for k in ("run", "flow", "workspace", "course", "status", "docx", "last_verdict", "redrafted", "ended")}
               for r in history[:5]]
    week_ago = _utc(now) - timedelta(days=7)
    recent = sum(1 for r in active + history if (_parse_dt(r.get("started"), timezone.utc) or week_ago) >= week_ago)
    if active:
        lede = [{"t": f"כתיבה בעיצומה ב{Path(str(active[0]['workspace'])).name}."}]
    elif recent:
        lede = [{"t": f"בשבוע האחרון היו {recent} ריצות כתיבה."}]
    else:
        lede = [{"t": "אין ריצות כתיבה בשבוע האחרון."}]
    return {"empty": False, "reason": None, "term": None, "timezone": None, "now": now.isoformat(), "today": today.isoformat(),
            "nightly": None, "courses": [], "exams": [], "timeline": {"weeks": []},
            "overview": {"primary": active[0] if active else None, "projects": projects, "results": results,
                         "library": ctx["library"]},
            "lede": lede, "agenda": _agenda_frame(week_start(today)), "wispr_unmatched": [], "queued_jobs": 0, "warnings": []}


def _finish(state: Dict[str, Any], ctx: Optional[Dict[str, Any]] = None, has_registry: bool = False) -> Dict[str, Any]:
    ctx = ctx or _no_context()
    state.update({"home": ctx["home"], "nav": _nav(ctx, has_registry), "setup": ctx["setup"],
                  "writing": ctx["writing"], "workspaces": ctx["workspaces"],
                  "week_mode": week_mode(datetime.fromisoformat(state["now"]))})
    body = json.dumps({k: v for k, v in state.items() if k != "now"}, sort_keys=True, ensure_ascii=False)
    state["version"] = hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]
    return state


def _when_phrase(due: datetime, now: datetime) -> str:
    days = (due.date() - now.date()).days
    if days == 0:
        day = "היום"
    elif days == 1:
        day = "מחר"
    elif 1 < days <= 6:
        day = f"ביום {DN[(due.weekday() + 1) % 7]}"
    else:
        day = f"ב־{due.day}.{due.month}"
    hm = due.strftime("%H:%M")
    if hm in ("00:00",):
        return day
    return f"{day} עד {hm}" if hm == "23:59" else f"{day} ב־{hm}"


def lede(course_list: List[Dict[str, Any]], now: datetime) -> List[Dict[str, str]]:
    """The 'what needs you' sentence as text segments; `mark: circ` segments get the red ink circle."""
    names = {c["slug"]: c["name"] for c in course_list}
    open_tasks = sorted((t for c in course_list for t in c["tasks"] if t["status"] != "submitted"), key=_due_sort)
    subs = [t for t in open_tasks if not t["reading"] and not t["exam"]]  # exams have their own column
    parts: List[Dict[str, str]] = []
    first = subs[0] if subs else None
    if first is None:
        parts.append({"t": "אין הגשות פתוחות."})
    else:
        course = names.get(first["course"], first["course"])
        if first["due_at"]:
            due = datetime.fromisoformat(first["due_at"])
            verb = "היה צריך להגיש" if is_overdue(due, now) else "מגישים"
            head = f"{_when_phrase(due, now)} {verb} את {first['title']} ב{course}"
        else:
            head = f"ההגשה הפתוחה הבאה, בלי תאריך, היא {first['title']} ב{course}"
        state = first["state"]
        if state == "missing":
            n = first["missing_count"]
            parts += [{"t": head + ", וחסר לה "}, {"t": "מקור אחד" if n == 1 else f"{n} מקורות", "mark": "circ"}, {"t": "."}]
        elif state == "waiting":
            parts.append({"t": head + ", ו־Claude יביא את מה שחסר לה בריצה הלילית."})
        elif state == "ready":
            parts.append({"t": head + ", וכל המקורות שלה כבר אצלך."})
        else:
            parts.append({"t": head + "."})
    horizon = now + timedelta(days=8)
    for t in open_tasks:
        if t["reading"] and t["due_at"] and datetime.fromisoformat(t["due_at"]) <= horizon:
            due = datetime.fromisoformat(t["due_at"])
            course = names.get(t["course"], t["course"])
            parts.append({"t": f" עד יום {DN[(due.weekday() + 1) % 7]} צריך לקרוא ל{course}: {t['title']}."})
    for c in course_list:
        if c["new_lesson"]:
            parts.append({"t": f" שיעור חדש תומלל ב{c['name']}."})
    week_end = now + timedelta(days=7)
    others = [t for t in subs[1:] if t["due_at"] and datetime.fromisoformat(t["due_at"]) <= week_end]
    if first is not None and not others:
        parts.append({"t": " שאר השבוע הקרוב פנוי."})
    return parts


def agenda(term: Dict[str, Any], course_list: List[Dict[str, Any]], start: date, today: date) -> Dict[str, Any]:
    frame = _agenda_frame(start)
    for day in frame["days"]:
        d = date.fromisoformat(day["date"])
        items = []
        for c in course_list:
            for slot in c["slots"]:
                if courses.WEEKDAYS.get(str(slot.get("day"))) == d.weekday() and slot_active(term, slot.get("semester"), d):
                    items.append({"type": "class", "course": c["slug"], "time": f"{slot.get('start', '')}–{slot.get('end', '')}",
                                  "sort": str(slot.get("start", "99"))})
            for t in c["tasks"]:
                if t["due_date"] == day["date"]:
                    hm = t["due_time"] if t["due_time"] not in (None, "00:00") else ""
                    items.append({"type": "task", "course": c["slug"], "task": t["id"], "time": hm, "sort": hm or "00"})
        items.sort(key=lambda i: (i["sort"], i["type"]))
        day["items"] = items
        day["past"] = d < today
        day["today"] = d == today
    frame["has_work"] = any(i["type"] == "task" for day in frame["days"] for i in day["items"])
    return frame


def next_boundary(state: Dict[str, Any], now: datetime) -> Optional[datetime]:
    """The next instant the state changes with no file changing: local midnight (today, relative dates), a due time
    passing (overdue), a due time coming within SOON_HOURS (the red date), or a submit ageing out of the undo window."""
    if state.get("timezone"):
        tz = ZoneInfo(state["timezone"])
    else:
        tz = now.tzinfo or timezone.utc
    local = now.astimezone(tz)
    candidates = [datetime.combine(local.date() + timedelta(days=1), datetime.min.time()).replace(tzinfo=tz)]
    for c in state.get("courses", []):
        for t in c.get("tasks", []):
            if t.get("status") != "submitted" and t.get("due_at"):
                due = datetime.fromisoformat(t["due_at"])
                candidates += [_utc(due), soon_from(due)]
            if t.get("recently_submitted") and t.get("submitted_at"):
                candidates.append(undo_until(datetime.fromisoformat(t["submitted_at"])))
    future = [c for c in candidates if _utc(c) > _utc(now)]
    return min(future, key=_utc).astimezone(tz) if future else None


# --- writes --------------------------------------------------------------------------------------

class RequestError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _known_course(directory: Optional[Path], slug: Any) -> str:
    if directory is None or not isinstance(slug, str) or not SLUG_RE.match(slug) or not (directory / f"{slug}.json").is_file():
        raise RequestError(400, "unknown course")
    return slug


def queue_fetch(directory: Path, slug: str, ref_keys: List[str], task: Optional[str] = None) -> Dict[str, Any]:
    """Write one fetch job for Claude/the nightly run. Never fetches. Unknown refs are refused."""
    data = tasks_mod.load_refs_data(directory, slug) or {"refs": []}
    known = {str(r.get("key")) for r in data.get("refs", []) if isinstance(r, dict)}
    keys = []
    for key in ref_keys:
        if not isinstance(key, str) or key not in known:
            raise RequestError(400, f"unknown ref {key!r}")
        if key not in keys:
            keys.append(key)
    if not keys:
        raise RequestError(400, "no refs")
    if task is not None:
        tasks_mod.resolve_task(tasks_mod.derive_tasks(tasks_mod.load_course(directory, slug).get("tasks") or [],
                                                      tasks_mod._chores(directory, slug),
                                                      tasks_mod.term_timezone(directory))[0], task)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / "queue" / "fetch" / f"{stamp}-{slug}.json"
    job = {"course": slug, "refs": keys, "task": task, "created": datetime.now().astimezone().isoformat(timespec="seconds"),
           "requested_by": "dashboard",
           "run": [f"refs.py fetch --course {slug} --ref {k}" + (f" --task {task}" if task else "") for k in keys]}
    courses._atomic_json(path, job)
    return {"queued": keys, "job": path.name}


def queue_extract(directory: Path, slug: str, items: Any, method: Any = None) -> Dict[str, Any]:
    """Write one extract job for the nightly run. Never extracts. Unknown items and unknown methods are refused."""
    default = "auto" if method in (None, "") else method
    if default not in extract_mod.METHODS:
        raise RequestError(400, f"unknown method {default!r}")
    if not isinstance(items, list) or not items or len(items) > 200:
        raise RequestError(400, "items must be a non-empty list")
    course = _read_json(directory / f"{slug}.json", [])
    course = course if isinstance(course, dict) else {}
    source_keys = set()
    for src in course.get("sources") or []:
        if isinstance(src, dict) and (src.get("sha8") or src.get("sha256")):
            source_keys.add(str(src.get("sha8") or str(src.get("sha256"))[:8]))
    ref_keys = {str(r.get("key")) for r in (_read_json(directory / "refs" / f"{slug}.json", {}) or {}).get("refs", [])
                if isinstance(r, dict)}
    clean: List[Dict[str, str]] = []
    for it in items:
        if not isinstance(it, dict):
            raise RequestError(400, "bad item")
        kind, key = it.get("kind"), it.get("key")
        use = default if it.get("method") in (None, "") else it.get("method")
        if kind not in extract_mod.KINDS or not isinstance(key, str) or key not in (source_keys if kind == "source" else ref_keys):
            raise RequestError(400, f"unknown item {kind!r}:{key!r}")
        if use not in extract_mod.METHODS:
            raise RequestError(400, f"unknown method {use!r}")
        if not any(c["kind"] == kind and c["key"] == key for c in clean):
            clean.append({"kind": kind, "key": key, "method": use})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / "queue" / "extract" / f"{stamp}-{slug}.json"
    courses._atomic_json(path, {"course": slug, "items": clean, "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                                "requested_by": "dashboard"})
    return {"queued": [f"{c['kind']}:{c['key']}" for c in clean], "job": path.name}


# --- server --------------------------------------------------------------------------------------

def _home_entries(home: Optional[Path]) -> List[Tuple[str, int, int]]:
    """mtime/size of home.md, workspaces.json and every registered workspace's `runs/*/activity.jsonl`
    (a stat per file; nothing is read), plus whether each workspace folder is there."""
    entries: List[Tuple[str, int, int]] = []
    if home is None:
        return entries
    meta = home / home_mod.DIR_NAME
    entries.append(("home/exists", int(home.is_dir()), 0))
    for name in (home_mod.HOME_FILE, home_mod.WORKSPACES_FILE):
        try:
            st = (meta / name).stat()
            entries.append((f"home/{name}", st.st_mtime_ns, st.st_size))
        except OSError:
            continue
    try:
        rows = workspace_rows(home) if home.is_dir() else []
    except OSError:
        rows = []
    for row in rows:
        entries.append((f"ws/{row['path']}", int(bool(row.get("exists"))), 0))
        try:
            for file in sorted((Path(row["path"]) / home_mod.DIR_NAME / "runs").glob("*/activity.jsonl")):
                st = file.stat()
                entries.append((f"run/{file}", st.st_mtime_ns, st.st_size))
        except OSError:
            continue
    return entries


def _signature(directory: Optional[Path], root: Path, home: Optional[Path] = None) -> Tuple[Any, ...]:
    entries: List[Tuple[str, int, int]] = _home_entries(home)
    folders = [root] if directory is None else [directory, directory / "refs", directory / "digest", directory / "queue" / "fetch", directory / "queue" / "extract", directory / "queue" / "extract" / "handoff", directory / "queue" / "sources", directory / "logs"]
    for folder in folders:
        try:
            with os.scandir(folder) as it:
                for entry in it:
                    if entry.name.startswith(".") or not entry.is_file(follow_symlinks=False):
                        if directory is None and entry.is_dir():
                            entries.append((entry.name, 0, 0))
                        continue
                    st = entry.stat(follow_symlinks=False)
                    entries.append((f"{folder.name}/{entry.name}", st.st_mtime_ns, st.st_size))
        except OSError:
            continue
    return tuple(sorted(entries))


def opener_command(path: Path, platform: Optional[str] = None) -> List[str]:
    """The argument list that opens `path` in its default app: `open` on macOS, `xdg-open` elsewhere."""
    return ["open" if (platform or sys.platform) == "darwin" else "xdg-open", str(path)]


def default_opener(argv: List[str]) -> None:
    """Launch `argv` detached, no shell."""
    subprocess.Popen(argv, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def resolve_run_docx(home: Optional[Path], run: Any, workspace: Any) -> Path:
    """The Word file recorded by `run` of a registered `workspace`, checked for opening; raises RequestError.
    The caller names the run and the workspace only: the path always comes from the run's own activity file."""
    if not isinstance(run, str) or not IDENT_RE.match(run) or ".." in run or not isinstance(workspace, str) or not workspace:
        raise RequestError(400, "bad run")
    rows = workspace_rows(home)
    roots = []
    for row in rows:
        try:
            roots.append((row["path"], Path(row["path"]).resolve()))
        except (OSError, ValueError, RuntimeError):
            continue
    match = next((r for given, r in roots if given == workspace), None)
    if match is None:
        raise RequestError(404, "unknown workspace")
    activity = match / home_mod.DIR_NAME / "runs" / run / "activity.jsonl"
    if not activity.is_file():
        raise RequestError(404, "unknown run")
    recorded = activity_mod.read_run(activity, workspace=workspace)["docx"]
    if not recorded or not recorded.lower().endswith(".docx"):
        raise RequestError(404, "no Word file recorded")
    try:
        candidate = Path(recorded)
        target = (candidate if candidate.is_absolute() else match / candidate).resolve()
    except (OSError, ValueError, RuntimeError):
        raise RequestError(400, "bad path")
    if target.suffix.lower() != ".docx":
        raise RequestError(400, "not a Word file")
    if not any(target == root or root in target.parents for _, root in roots):
        raise RequestError(400, "outside the workspaces")
    if not target.is_file():
        raise RequestError(404, "file not found")
    return target


class _HTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class DashboardServer:
    COOKIE = "aw_dashboard"

    def __init__(self, resolve: Callable[[], Optional[Path]], *, host: str = "127.0.0.1", port: int = DEFAULT_PORT,
                 key: Optional[str] = None, interval: float = 1.0, now: Optional[Callable[[], datetime]] = None,
                 reason: Optional[Callable[[], str]] = None,
                 home: Optional[Callable[[], Optional[Path]]] = None,
                 setup: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                 monotonic: Optional[Callable[[], float]] = None,
                 opener: Optional[Callable[[List[str]], None]] = None):
        if host not in ("127.0.0.1", "localhost"):
            raise ValueError("the dashboard binds 127.0.0.1 only")
        self.resolve = resolve
        self.home = home or home_mod.home_dir  # the home folder (None when none is chosen)
        self.setup = setup or (lambda: setup_mod.run_checks(os.environ))
        self.monotonic = monotonic or time.monotonic
        self.opener = opener or default_opener  # injectable so tests never launch an app
        self._setup_cache: Optional[Tuple[float, Dict[str, Any]]] = None
        self._setup_lock = threading.Lock()
        self.host, self.requested_port = "127.0.0.1", port
        self.key = key or secrets.token_urlsafe(24)
        self.interval = interval
        self.now = now
        self.reason = reason or (lambda: "no-registry")
        self.httpd: Optional[_HTTPServer] = None
        self.version = 0
        self._cond = threading.Condition()
        self._closed = False
        self._threads: List[threading.Thread] = []

    @property
    def port(self) -> int:
        return self.httpd.server_address[1] if self.httpd else self.requested_port

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?key={self.key}"

    def start(self) -> "DashboardServer":
        handler = self._handler()
        try:
            self.httpd = _HTTPServer((self.host, self.requested_port), handler)
        except OSError as exc:
            if exc.errno not in (errno.EADDRINUSE, errno.EACCES) or self.requested_port == 0:
                raise
            self.httpd = _HTTPServer((self.host, 0), handler)  # the default port is busy: take a free one
        for name, target in (("aw-dashboard-http", self.httpd.serve_forever), ("aw-dashboard-watch", self._watch)):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)
        return self

    def _clock(self) -> datetime:
        return self.now() if self.now else datetime.now(timezone.utc)

    def _watch(self) -> None:
        """Push `state-changed` when a registry file changes, and when the clock crosses a time boundary
        (local midnight, a due time, the 72-hour mark, the undo window) even though no file changed."""
        root = courses.courses_root()
        last = None
        boundary: Optional[datetime] = None
        while not self._closed:
            try:
                sig = _signature(self.resolve(), root, self._home())
                now = self._clock()
                changed = last is not None and sig != last
                crossed = boundary is not None and now >= boundary
                if changed or crossed:
                    with self._cond:
                        self.version += 1
                        self._cond.notify_all()
                if changed or crossed or last is None:
                    try:
                        boundary = next_boundary(self.state(), now)
                    except Exception:  # a malformed registry must not stop the watcher; retry at the next change
                        boundary = None
                last = sig
            except Exception as exc:  # whatever one pass hits, the next pass runs: SSE must outlive any bad file
                print(f"dashboard watcher: {type(exc).__name__}: {exc}", file=sys.stderr)
            with self._cond:
                self._cond.wait(timeout=self.interval)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with self._cond:
            self._cond.notify_all()
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        for thread in self._threads:
            thread.join(timeout=2)

    def _home(self) -> Optional[Path]:
        try:
            return self.home()
        except Exception:
            return None

    def _setup_block(self) -> Dict[str, Any]:
        """The setup checks, run at most once per SETUP_CACHE_SECONDS (they start processes)."""
        with self._setup_lock:
            stamp = self.monotonic()
            if self._setup_cache is None or stamp - self._setup_cache[0] >= SETUP_CACHE_SECONDS:
                self._setup_cache = (stamp, setup_block(self.setup))
            return self._setup_cache[1]

    def state(self, week: Optional[str] = None) -> Dict[str, Any]:
        directory = self.resolve()
        now = self.now() if self.now else None
        ctx = gather_context(self._home(), self._setup_block(), now or datetime.now().astimezone())
        return build_state(directory, now=now, week=week, ctx=ctx,
                           reason=self.reason() if directory is None else "no-registry")

    def _handler(self):
        board = self

        class Handler(http.server.BaseHTTPRequestHandler):
            server_version = "aw-dashboard"
            sys_version = ""

            def log_message(self, *_args: Any) -> None:
                return

            # -- checks
            def _host_ok(self) -> bool:
                return self.headers.get("Host", "") == f"127.0.0.1:{board.port}"

            def _cookie_key(self) -> str:
                for part in self.headers.get("Cookie", "").split(";"):
                    name, _, value = part.strip().partition("=")
                    if name == board.COOKIE:
                        return value
                return ""

            def _authed(self, query_key: str = "") -> bool:
                supplied = query_key or self.headers.get("X-Dashboard-Key", "") or self._cookie_key()
                return bool(supplied) and hmac.compare_digest(supplied.encode(), board.key.encode())

            def _headers(self, status: int, content_type: str, extra: Optional[Dict[str, str]] = None) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Security-Policy",
                                 "default-src 'none'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
                                 "font-src https://fonts.gstatic.com; img-src 'self'; connect-src 'self'; base-uri 'none'; "
                                 "form-action 'none'; frame-ancestors 'none'")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)

            def _json(self, status: int, payload: Any) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self._headers(status, "application/json; charset=utf-8", {"Content-Length": str(len(body))})
                self.end_headers()
                self.wfile.write(body)

            def _deny(self) -> None:
                self._json(403, {"error": "forbidden"})

            # -- GET
            def do_GET(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlsplit(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                query_key = (query.get("key") or [""])[0]
                if not self._host_ok() or not self._authed(query_key):
                    self._deny()
                    return
                if parsed.path == "/favicon.ico":
                    self._headers(204, "image/x-icon", {"Content-Length": "0"})
                    self.end_headers()
                    return
                if parsed.path in ("/", "/index.html"):
                    try:
                        body = (ASSETS / "index.html").read_bytes()
                    except OSError:
                        self._json(500, {"error": "page missing"})
                        return
                    cookie = f"{board.COOKIE}={board.key}; HttpOnly; SameSite=Strict; Path=/"
                    self._headers(200, "text/html; charset=utf-8", {"Content-Length": str(len(body)), "Set-Cookie": cookie})
                    self.end_headers()
                    self.wfile.write(body)
                    return
                static = STATIC_FILES.get(parsed.path)
                view = VIEW_RE.match(parsed.path)
                if static or view:
                    path = ASSETS / "views" / view.group(1) if view else ASSETS / parsed.path.lstrip("/")
                    ctype = "text/javascript; charset=utf-8" if view else static
                    try:
                        body = path.read_bytes() if path.is_file() else None
                    except OSError:
                        body = None
                    if body is None:
                        self._json(404, {"error": "not found"})
                        return
                    self._headers(200, ctype, {"Content-Length": str(len(body))})
                    self.end_headers()
                    self.wfile.write(body)
                    return
                match = ASSET_RE.match(parsed.path)
                if match:
                    path = ASSETS / "img" / match.group(1)
                    if not path.is_file():
                        self._json(404, {"error": "not found"})
                        return
                    body = path.read_bytes()
                    self._headers(200, "image/webp", {"Content-Length": str(len(body))})
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if parsed.path == "/api/state":
                    try:
                        payload = board.state((query.get("week") or [None])[0])
                    except Exception as exc:  # a malformed registry must not kill the page
                        self._json(500, {"error": f"state: {exc}"})
                        return
                    self._json(200, payload)
                    return
                if parsed.path == "/api/events":
                    self._events()
                    return
                self._json(404, {"error": "not found"})

            def _events(self) -> None:
                self._headers(200, "text/event-stream; charset=utf-8", {"Connection": "keep-alive"})
                self.end_headers()
                try:
                    with board._cond:
                        seen = board.version
                    self.wfile.write(b"retry: 3000\nevent: hello\ndata: {}\n\n")
                    self.wfile.flush()
                    while not board._closed:
                        with board._cond:
                            board._cond.wait(timeout=15)
                            current = board.version
                        if board._closed:
                            break
                        if current != seen:
                            seen = current
                            self.wfile.write(f"event: state-changed\ndata: {json.dumps({'v': current})}\n\n".encode())
                        else:
                            self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return

            # -- POST
            def do_POST(self) -> None:  # noqa: N802
                origin = self.headers.get("Origin", "")
                if not self._host_ok() or not self._authed() or origin != f"http://127.0.0.1:{board.port}":
                    self._deny()
                    return
                if not self.headers.get("Content-Type", "").startswith("application/json"):
                    self._json(415, {"error": "json only"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = -1
                if length < 0 or length > MAX_BODY:
                    self._json(413, {"error": "body too large"})
                    return
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                    if not isinstance(body, dict):
                        raise ValueError("object expected")
                except ValueError:
                    self._json(400, {"error": "bad json"})
                    return
                directory = board.resolve()
                path = urllib.parse.urlsplit(self.path).path
                try:
                    if path in ("/api/task/submit", "/api/task/unsubmit"):
                        slug = _known_course(directory, body.get("course"))
                        task = body.get("task")
                        if not isinstance(task, str) or not IDENT_RE.match(task):
                            raise RequestError(400, "bad task")
                        fn = tasks_mod.task_submit if path.endswith("/submit") else tasks_mod.task_unsubmit
                        result = fn(directory, slug, task)
                    elif path == "/api/fetch":
                        slug = _known_course(directory, body.get("course"))
                        refs = body.get("refs")
                        task = body.get("task")
                        if not isinstance(refs, list) or len(refs) > 200:
                            raise RequestError(400, "refs must be a list")
                        if task is not None and (not isinstance(task, str) or not IDENT_RE.match(task)):
                            raise RequestError(400, "bad task")
                        result = queue_fetch(directory, slug, refs, task)
                    elif path == "/api/extract":
                        slug = _known_course(directory, body.get("course"))
                        result = queue_extract(directory, slug, body.get("items"), body.get("method"))
                    elif path == "/api/open":
                        target = resolve_run_docx(board._home(), body.get("run"), body.get("workspace"))
                        try:
                            board.opener(opener_command(target))
                        except OSError:
                            raise RequestError(500, "could not open the file")
                        result = {"ok": True, "name": target.name}
                    else:
                        self._json(404, {"error": "not found"})
                        return
                except RequestError as exc:
                    self._json(exc.status, {"error": str(exc)})
                    return
                except (tasks_mod.TaskError, ValueError, KeyError, OSError) as exc:
                    self._json(400, {"error": str(exc)})
                    return
                with board._cond:  # wake the watcher so the change reaches every open page now
                    board._cond.notify_all()
                self._json(200, result)

            def do_PUT(self) -> None:  # noqa: N802
                self._json(405, {"error": "method not allowed"})

            do_DELETE = do_PUT
            do_PATCH = do_PUT

        return Handler


def run(args: argparse.Namespace) -> int:
    if args.host not in ("127.0.0.1", "localhost"):
        print(f"error: the dashboard listens on 127.0.0.1 only (got --host {args.host})", file=sys.stderr)
        return 2
    term = getattr(args, "term", None)
    server = DashboardServer(lambda: resolve_directory(term), host=args.host, port=args.port,
                             reason=lambda: missing_reason(term)).start()
    directory = resolve_directory(term)
    print(f"Dashboard: {server.url}", flush=True)
    print("Local only: listening on 127.0.0.1; the key in the URL is the password for this run. Ctrl-C stops it.", flush=True)
    if directory is None and missing_reason(term) == "ambiguous-term":
        print("Several terms are registered: restart with --term <name> (or set ACADEMIC_TERM) to choose one.", flush=True)
    elif directory is None:
        print("No course registry yet: the page shows the empty state until /academic-writer:courses creates one.", flush=True)
    if not args.no_open:
        try:
            webbrowser.open(server.url)
        except Exception:
            pass
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
    return 0


def add_parser(sub) -> None:
    dash = sub.add_parser("dashboard", help="serve the local course dashboard on 127.0.0.1 and print its URL")
    dash.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port to try first (default {DEFAULT_PORT}; a free one if busy)")
    dash.add_argument("--host", default="127.0.0.1", help="must be 127.0.0.1; any other host is refused")
    dash.add_argument("--no-open", action="store_true", help="print the URL without opening a browser")
