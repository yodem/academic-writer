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

Writes go only through existing functions: `POST /api/task/submit` and `/api/task/unsubmit` call tasks.py;
`POST /api/fetch` writes a job to queue/fetch/<ts>-<course>.json for Claude or the nightly run to execute with
`refs.py fetch` (the server never fetches anything). `GET /api/events` is a Server-Sent Events stream: a server
thread scans the registry's mtimes about once a second and sends `state-changed`; the browser never polls.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import hmac
import http.server
import json
import os
import re
import secrets
import socketserver
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I leaves the script dir off sys.path
import courses  # noqa: E402
import tasks as tasks_mod  # noqa: E402

HERE = Path(__file__).resolve().parent
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


def ref_item(ref: Dict[str, Any], sources: List[Dict[str, Any]], queued: bool) -> Dict[str, Any]:
    st = tasks_mod.ref_status(ref, sources)
    has_text = st["downloaded"] or st["in_trove"]
    status = ref.get("status", "")
    missing = status in MISSING_STATUSES and not has_text and not queued
    ocr = _ocr_waiting(ref)
    return {"type": "ref", "key": ref.get("key", ""), "title": ref.get("citation", ""), "status": status,
            "role": ref.get("role", ""), "downloaded": st["downloaded"], "in_trove": st["in_trove"],
            "in_notebooklm": st["in_notebooklm"], "trove": st["trove"], "missing": missing, "queued": queued,
            "ocr": ocr, "waiting": queued or bool(ocr), "fetchable": not has_text and status != "ingested" and not queued,
            "tasks": list(ref.get("tasks") or [])}


def source_item(src: Dict[str, Any]) -> Dict[str, Any]:
    st = tasks_mod.source_status(src)
    return {"type": "source", "key": st["key"], "title": src.get("title", ""), "status": src.get("status", ""),
            "role": "", "downloaded": st["downloaded"], "in_trove": st["in_trove"], "in_notebooklm": st["in_notebooklm"],
            "trove": st["trove"], "missing": False, "queued": False, "ocr": None, "waiting": False, "fetchable": False,
            "tasks": list(src.get("tasks") or [])}


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
    return "קריאה" if kind in READING_KINDS else "הגשה"


# --- state ---------------------------------------------------------------------------------------

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
            "lede": [{"t": "עוד אין קורסים."}], "agenda": _agenda_frame(start), "wispr_unmatched": [], "warnings": []}


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


def build_state(directory: Optional[Path], now: Optional[datetime] = None, week: Optional[str] = None,
                reason: str = "no-registry") -> Dict[str, Any]:
    """Join the registry files into the page's one JSON. Pure read: nothing is written or locked."""
    warnings: List[str] = []
    if directory is None or not (directory / "term.json").is_file():
        state = _empty_state(reason if directory is None else "no-registry", (now or datetime.now().astimezone()))
        return _finish(state)
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
        return _finish(state)

    links = _read_json(directory / "links.json", warnings) or {}
    store = _read_json(directory / "chores.json", warnings)
    if store is None:  # a mirror that only has the digest: chores without ids (no task can be derived from them)
        store = [dict(c, id="") for c in (_read_json(directory / "digest" / "chores.json", warnings) or [])]
    chores = [c for c in store if isinstance(c, dict)] if isinstance(store, list) else []
    jobs = queued_fetches(directory)
    queued_keys = {(j["course"], str(k)) for j in jobs for k in (j.get("refs") or [])}
    lemida_base = str((term.get("lemida") or {}).get("base_url", "")).rstrip("/")

    out_courses = []
    for slug, course in raw_courses.items():
        course_chores = [c for c in chores if c.get("course") == slug]
        derived, _ = tasks_mod.derive_tasks(course.get("tasks") or [], [c for c in course_chores if c.get("id")])
        refs_data = _read_json(directory / "refs" / f"{slug}.json", warnings) or {}
        refs_list = [r for r in refs_data.get("refs") or [] if isinstance(r, dict)]
        sources = [s for s in course.get("sources") or [] if isinstance(s, dict)]
        ref_items = [ref_item(r, sources, (slug, str(r.get("key"))) in queued_keys) for r in refs_list]
        src_items = [source_item(s) for s in sources if s.get("kind") != "media" and not s.get("lesson_key")]
        chore_by_id = {c.get("id"): c for c in course_chores}

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
            lemida_ref = next((r for r in lemida_refs if r.isdigit()), "")
            first_chore = chore_by_id.get((task.get("chore_ids") or [None])[0]) or {}
            task_rows.append({
                "id": tid, "course": slug, "title": task.get("title") or "", "kind": task.get("kind") or "",
                "kind_word": kind_word(task.get("kind")), "reading": task.get("kind") in READING_KINDS,
                "status": task.get("status") or "open", "due_at": due.isoformat() if due else None,
                "due_date": due.date().isoformat() if due else None, "due_time": due.strftime("%H:%M") if due else None,
                "due_utc": due.astimezone(timezone.utc).isoformat() if due else None,
                "soon": bool(due and timedelta(0) <= due - now <= timedelta(hours=SOON_HOURS)),
                "overdue": bool(due and due < now),
                "submitted_at": submitted_at.isoformat() if submitted_at else None,
                # only a submit made through task_submit (it records closed_chores) can be undone or called "you marked it";
                # a task whose chore the watcher closed is just a past task
                "recently_submitted": bool(submitted_at and "closed_chores" in task
                                           and now - submitted_at <= timedelta(hours=RECENT_SUBMIT_HOURS)),
                "desc": first_chore.get("text") or "", "core_texts": list(first_chore.get("core_texts") or []),
                "lemida_url": _https(f"{lemida_base}/mod/view.php?id={lemida_ref}") if lemida_base and lemida_ref else None,
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
            "mode": course.get("mode"), "slots": [s for s in course.get("slots") or [] if isinstance(s, dict)],
            "season": course_season(term, course, today),
            "links": {"lemida": _https(lemida_course), "notebook": _https(notebook), "drive": _https(drive),
                      "trove_book_id": book_id, "trove_url": _https(trove_url)},
            "tasks": sorted(task_rows, key=_due_sort), "next_task": open_tasks[0]["id"] if open_tasks else None,
            "state": open_tasks[0]["state"] if open_tasks else None, "open_count": len(open_tasks), "more": more,
            "lessons": lessons, "new_lesson": any(l["new"] for l in lessons), "notices": notices,
            "perusall_open": sum(1 for c in course_chores if c.get("kind") == "perusall-capture" and c.get("status") == "open"),
            "storage": {"trove_book_id": book_id, "notebook_sources": sum(1 for s in sources if s.get("notebook_source_id")),
                        "drive": bool(drive), "sources": len(src_items), "refs": len(ref_items)},
            "queued_jobs": sum(1 for j in jobs if j["course"] == slug),
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
    counts = {"submit": sum(1 for t in open_all if not t["reading"]), "read": sum(1 for t in open_all if t["reading"])}

    try:
        start = week_start(date.fromisoformat(week)) if week else week_start(today)
    except ValueError:
        start = week_start(today)
    unmatched_raw = _read_json(directory / "digest" / "wispr-unmatched.json", warnings) or {}
    meetings = unmatched_raw.get("meetings") if isinstance(unmatched_raw, dict) else unmatched_raw
    unmatched = []
    for m in meetings or []:
        if isinstance(m, dict) and m.get("start"):
            when = _parse_dt(m.get("start"), tz)
            if when:
                unmatched.append({"id": str(m.get("id", "")), "start": when.isoformat()})

    state = {
        "empty": False, "reason": None, "term": term.get("term"), "timezone": str(tz), "now": now.isoformat(),
        "today": today.isoformat(), "nightly": _nightly(directory), "courses": out_courses,
        "overview": {"rows": rows, "quiet": quiet, "later": later, "counts": counts},
        "lede": lede(out_courses, now), "agenda": agenda(term, out_courses, start, today),
        "wispr_unmatched": unmatched, "queued_jobs": len(jobs), "warnings": warnings,
    }
    return _finish(state)


def _finish(state: Dict[str, Any]) -> Dict[str, Any]:
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
    subs = [t for t in open_tasks if not t["reading"]]
    parts: List[Dict[str, str]] = []
    first = subs[0] if subs else None
    if first is None:
        parts.append({"t": "אין הגשות פתוחות."})
    else:
        course = names.get(first["course"], first["course"])
        if first["due_at"]:
            due = datetime.fromisoformat(first["due_at"])
            verb = "היה צריך להגיש" if due < now else "מגישים"
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
            parts.append({"t": f" עד יום {DN[(due.weekday() + 1) % 7]} צריך לקרוא את {t['title']}."})
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
                                                      tasks_mod._chores(directory, slug))[0], task)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / "queue" / "fetch" / f"{stamp}-{slug}.json"
    job = {"course": slug, "refs": keys, "task": task, "created": datetime.now().astimezone().isoformat(timespec="seconds"),
           "requested_by": "dashboard",
           "run": [f"refs.py fetch --course {slug} --ref {k}" + (f" --task {task}" if task else "") for k in keys]}
    courses._atomic_json(path, job)
    return {"queued": keys, "job": path.name}


# --- server --------------------------------------------------------------------------------------

def _signature(directory: Optional[Path], root: Path) -> Tuple[Any, ...]:
    entries: List[Tuple[str, int, int]] = []
    folders = [root] if directory is None else [directory, directory / "refs", directory / "digest", directory / "queue" / "fetch", directory / "logs"]
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


class _HTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class DashboardServer:
    COOKIE = "aw_dashboard"

    def __init__(self, resolve: Callable[[], Optional[Path]], *, host: str = "127.0.0.1", port: int = DEFAULT_PORT,
                 key: Optional[str] = None, interval: float = 1.0, now: Optional[Callable[[], datetime]] = None,
                 reason: Optional[Callable[[], str]] = None):
        if host not in ("127.0.0.1", "localhost"):
            raise ValueError("the dashboard binds 127.0.0.1 only")
        self.resolve = resolve
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

    def _watch(self) -> None:
        root = courses.courses_root()
        last = None
        while not self._closed:
            sig = _signature(self.resolve(), root)
            if last is not None and sig != last:
                with self._cond:
                    self.version += 1
                    self._cond.notify_all()
            last = sig
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

    def state(self, week: Optional[str] = None) -> Dict[str, Any]:
        directory = self.resolve()
        return build_state(directory, now=self.now() if self.now else None, week=week,
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
                                 "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline' https://fonts.googleapis.com; "
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
