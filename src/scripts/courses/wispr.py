"""Nightly import of lecture recordings from Wispr Flow into the lesson-notes pipeline.

Wispr Flow keeps meetings in a local SQLite database (live, WAL) plus one folder per meeting.
``scan`` matches each finished meeting to a course slot by its recording time. A matched meeting becomes
a text transcript handed to ``courses.add_source(..., transcript=True)`` (Drive, NotebookLM, queue job), or
an alternate on a lesson that already exists. An unmatched or ambiguous meeting may be a private work
meeting: only its id, times and reason are read and kept, never its title, summary or transcript.

The database is only ever read in place through a read-only connection. It is never copied: if it cannot
be opened read-only, the scan fails closed and imports nothing.
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote
from zoneinfo import ZoneInfo

import courses

DEFAULT_DATA_DIR = "~/Library/Application Support/Wispr Flow"
UNMATCHED_FILE = "wispr-unmatched.json"
PENDING = "pending_transcript"
EARLY_START = timedelta(minutes=20)
MIN_OVERLAP = timedelta(minutes=30)
MIN_FRACTION = 0.5
OPEN_ATTEMPTS = 4
OPEN_BACKOFF = 0.5  # seconds before the first retry, doubled after each
# the only Meetings columns read before a meeting is matched to a course
METADATA_SQL = ("select id, createdAt, endedAt, recordedMs from Meetings "
                "where finalized = 1 and transcriptReady = 1 and isDeleted = 0 order by createdAt")


def data_dir(term: dict[str, Any]) -> Path:
    return Path(term.get("wispr_dir", DEFAULT_DATA_DIR)).expanduser()


def _query(db: Path, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    """Run one query on the live database, in place and read-only, retrying briefly while it is busy.

    There is no fallback: the database (which also holds private work meetings) is never copied.
    """
    uri = f"file:{quote(str(db.resolve()))}?mode=ro"
    last: sqlite3.Error | None = None
    for attempt in range(OPEN_ATTEMPTS):
        if attempt:
            time.sleep(OPEN_BACKOFF * 2 ** (attempt - 1))
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=5)
            try:
                return conn.execute(sql, params).fetchall()
            finally:
                conn.close()
        except sqlite3.Error as exc:
            last = exc
    raise courses.IngestError(f"Wispr Flow database could not be opened read-only after {OPEN_ATTEMPTS} attempts "
                              f"({last}); nothing was imported: {db}")


def _parse_created(text: str) -> datetime:
    # '2026-10-13 13:04:49.396 +00:00'
    return datetime.fromisoformat(text.strip().replace(" +", "+").replace(" -", "-").replace(" ", "T", 1)).astimezone(timezone.utc)


def list_meetings(db: Path) -> list[dict[str, Any]]:
    """Finished, non-deleted meetings: metadata only (id and times). Titles, summaries and transcripts are not selected."""
    meetings = []
    for mid, created, ended, recorded in _query(db, METADATA_SQL):
        start = _parse_created(created)
        if ended:
            end = datetime.fromtimestamp(float(ended) / 1000, tz=timezone.utc)
        else:
            end = start + timedelta(milliseconds=float(recorded or 0))
        if end <= start:
            end = start + timedelta(milliseconds=float(recorded or 0))
        meetings.append({"id": str(mid), "start": start, "end": end})
    return meetings


def match_course(registry: courses.Registry, start: datetime, end: datetime) -> tuple[str | None, str | None]:
    """Return (slug, None) for exactly one matching course, else (None, reason).

    Durations and overlaps are computed on UTC instants (local wall-clock arithmetic breaks across a DST
    change); local time only picks the weekday, the date and the slot boundaries.
    """
    tz = ZoneInfo(registry.term.get("timezone", "Asia/Jerusalem"))
    ustart, uend = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    lstart = ustart.astimezone(tz)
    duration = uend - ustart
    day = lstart.date()
    matches: set[str] = set()
    for slug, course in registry.courses.items():
        for slot in course.get("slots", []):
            if courses.WEEKDAYS.get(str(slot.get("day"))) != lstart.weekday():
                continue
            if not courses._in_semester(registry.term, str(slot.get("semester", "")), day):
                continue
            s = datetime.combine(day, datetime.strptime(slot["start"], "%H:%M").time(), tz).astimezone(timezone.utc)
            e = datetime.combine(day, datetime.strptime(slot["end"], "%H:%M").time(), tz).astimezone(timezone.utc)
            if ustart < s - EARLY_START:
                continue
            overlap = min(uend, e) - max(ustart, s)
            if overlap <= timedelta(0):
                continue
            if overlap >= MIN_OVERLAP or (duration > timedelta(0) and overlap / duration >= MIN_FRACTION):
                matches.add(slug)
    if len(matches) == 1:
        return next(iter(matches)), None
    if matches:
        return None, f"ambiguous: {', '.join(sorted(matches))}"
    return None, "no course slot matches"


def render_transcript(meeting_dir: Path) -> str:
    """Speaker-labelled transcript from refined.ndjson (falls back to live.ndjson)."""
    path = meeting_dir / "refined.ndjson"
    if not path.is_file():
        path = meeting_dir / "live.ndjson"
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        item = json.loads(raw)
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        speaker = item.get("speaker") or {}
        label = speaker.get("name") or (f"דובר {speaker['id']}" if speaker.get("id") is not None else "דובר")
        lines.append(f"[{item.get('timestamp', '')}] {label}: {text}")
    if not lines:
        raise ValueError("empty transcript")
    return "\n".join(lines) + "\n"


def read_summary(db: Path, meeting_id: str) -> str:
    """The Wispr summary of one MATCHED meeting (never called for an unmatched or ambiguous one)."""
    rows = _query(db, "select summary from Meetings where id = ?", (meeting_id,))
    return (rows[0][0] or "").strip() if rows else ""


def _seen_ids(registry: courses.Registry, term: dict[str, Any]) -> set[str]:
    seen = {str(x) for x in (term.get("state") or {}).get("wispr_seen", [])}
    for course in registry.courses.values():
        for lesson in course.get("lessons", []):
            # a lesson still pending is an incomplete import of its meeting: resume it, do not skip it
            if lesson.get("wispr_meeting_id") and lesson.get("status") != PENDING:
                seen.add(str(lesson["wispr_meeting_id"]))
            for alt in lesson.get("alternates", []) or []:
                if alt.get("meeting_id"):
                    seen.add(str(alt["meeting_id"]))
    return seen


def _stamp(item: dict[str, Any], tz: ZoneInfo) -> dict[str, Any]:
    return {"id": item["id"], "start": item["start"].astimezone(tz).isoformat(), "end": item["end"].astimezone(tz).isoformat()}


def _write_unmatched(registry: courses.Registry, entries: list[dict[str, Any]]) -> Path:
    path = registry.directory / "digest" / UNMATCHED_FILE
    courses._atomic_json(path, {"updated": datetime.now(timezone.utc).isoformat(), "meetings": entries})
    return path


def scan(registry: courses.Registry, *, since: str | None = None, dry_run: bool = False,
         runner: Callable[..., Any] | None = None, add_source: Callable[..., Any] | None = None) -> dict[str, Any]:
    term_path = registry.directory / "term.json"
    term = json.loads(term_path.read_text(encoding="utf-8"))
    tz = ZoneInfo(term.get("timezone", "Asia/Jerusalem"))
    base = data_dir(term)
    db = base / "flow.sqlite"
    report: dict[str, Any] = {"dry_run": dry_run, "matched": [], "unmatched": [], "skipped": [], "errors": []}
    if not db.is_file():
        report["note"] = f"Wispr Flow database not found: {db}"
        return report
    floor = datetime.fromisoformat(since).replace(tzinfo=tz).astimezone(timezone.utc) if since else None
    meetings = list_meetings(db)  # fails closed (IngestError) before anything is written
    seen = _seen_ids(registry, term)
    new_seen: list[str] = []
    planned: dict[tuple[str, str], str] = {}  # dry run only: (course, day) -> key of an import it would make
    for meeting in meetings:
        if floor and meeting["start"] < floor:
            continue
        if meeting["id"] in seen:
            report["skipped"].append({"id": meeting["id"], "reason": "already imported"})
            continue
        slug, reason = match_course(registry, meeting["start"], meeting["end"])
        if not slug:
            report["unmatched"].append({**_stamp(meeting, tz), "reason": reason})
            continue
        local = meeting["start"].astimezone(tz)
        day, hm = local.date().isoformat(), local.strftime("%H%M")
        entry = {**_stamp(meeting, tz), "slug": slug, "date": day}
        mdir = base / "meetings" / meeting["id"]
        try:
            # the course file is re-read for every meeting: an earlier import in this run changed it
            lessons = _fresh_lessons(registry, slug)
            same_day = [x for x in lessons if x.get("date") == day]
            # resume only a lesson this very meeting owns; the marker is persisted when the lesson is created
            resume = next((x for x in same_day if x.get("wispr_meeting_id") == meeting["id"]), None)
            if not resume:
                _refuse_unowned(registry, slug, meeting["id"], day, hm, same_day)
            existing = None if resume else (same_day[0] if same_day else None)
            if not existing and not resume and dry_run and (slug, day) in planned:
                existing = {"lesson_key": planned[(slug, day)]}
            if existing:
                entry["action"] = "alternate"
                entry["lesson_key"] = existing.get("lesson_key", existing.get("key"))
                if not dry_run:
                    _record_alternate(registry, slug, existing, meeting["id"], mdir, db)
            else:
                entry["action"] = "resume" if resume else "import"
                if dry_run:
                    planned[(slug, day)] = f"{day}-{hm}"
                else:  # a real import is visible to later meetings through the re-read course file, once it exists
                    entry.update(_import(registry, slug, meeting["id"], day, hm, mdir, db, runner, add_source))
            if not dry_run:
                new_seen.append(meeting["id"])
            report["matched"].append(entry)
        except Exception as exc:  # one failing meeting never stops the rest; it is retried tomorrow
            entry["error"] = str(exc)[:200]
            report["errors"].append(entry)
    if not dry_run:
        if new_seen:
            term = json.loads(term_path.read_text(encoding="utf-8"))
            state = term.setdefault("state", {})
            state["wispr_seen"] = sorted({*map(str, state.get("wispr_seen", [])), *new_seen})
            courses._atomic_json(term_path, term)
        _write_unmatched(registry, report["unmatched"])
    return report


def _compose(mdir: Path, db: Path, meeting_id: str) -> str:
    text = render_transcript(mdir)
    summary = read_summary(db, meeting_id)
    if summary:
        text += f"\n---\nWispr summary (automatic, unverified; the transcript above is the source):\n\n{summary}\n"
    return text


def _fresh_lessons(registry, slug) -> list[dict[str, Any]]:
    path = registry.directory / f"{slug}.json"
    return list(json.loads(path.read_text(encoding="utf-8")).get("lessons", []))


def _staged_path(registry, slug, meeting_id, day, hm) -> Path:
    return registry.directory / "wispr" / slug / f"wispr-{day}-{hm}-{meeting_id[:8]}.txt"


def _refuse_unowned(registry, slug, meeting_id, day, hm, same_day) -> None:
    """A same-day lesson built from this meeting's staged transcript but owned by no or another meeting is a
    conflict: it is neither resumed (a hash is not ownership) nor shelved as an alternate. The meeting is left
    unseen and reported as an error."""
    staged = _staged_path(registry, slug, meeting_id, day, hm)
    if not staged.is_file():
        return
    digest = courses._file_sha256(staged)
    for lesson in same_day:
        if lesson.get("audio_sha256") == digest and lesson.get("wispr_meeting_id") != meeting_id:
            owner = lesson.get("wispr_meeting_id") or "none recorded"
            raise courses.IngestError(f"lesson {lesson.get('lesson_key', lesson.get('key'))} holds this meeting's transcript "
                                      f"but its owner is {owner}; not resumed")


def _import(registry, slug, meeting_id, day, hm, mdir, db, runner, add_source) -> dict[str, Any]:
    staging = registry.directory / "wispr" / slug
    staging.mkdir(parents=True, exist_ok=True)
    path = _staged_path(registry, slug, meeting_id, day, hm)
    if not path.is_file():  # a resumed import must hand over the same bytes, or it would look like a new recording
        courses._atomic_write(path, _compose(mdir, db, meeting_id))
    kwargs = {"runner": runner} if runner else {}
    # the pipeline stores the owner on the lesson record in the same write that creates it, so an import
    # that fails later leaves a lesson only this meeting may resume, and refuses a lesson another one owns
    result = (add_source or courses.add_source)(registry, path, slug, origin="recording", transcript=True,
                                                lesson_date=day, lesson_time=hm,
                                                lesson_owner={"wispr_meeting_id": meeting_id}, **kwargs)
    lesson_key = result.get("lesson_key")
    if not lesson_key:
        raise courses.IngestError(f"{slug}: the import of meeting {meeting_id} returned no lesson")
    with courses._locked_course(registry.directory, slug) as locked:
        lesson = next((x for x in locked.payload.get("lessons", []) if x.get("lesson_key") == lesson_key), None)
        if lesson is None:
            raise courses.IngestError(f"{slug}: no lesson {lesson_key} after importing meeting {meeting_id}")
        owner = lesson.get("wispr_meeting_id")
        if owner != meeting_id:  # never adopt a lesson after the fact: ownership is written when it is created
            raise courses.IngestError(f"{slug}: lesson {lesson_key} is owned by {owner or 'no meeting'}, not {meeting_id}")
    return {"lesson_key": lesson_key, "result_status": result.get("status")}


def _record_alternate(registry, slug, existing, meeting_id, mdir, db) -> None:
    """Keep the Wispr transcript beside an existing lesson. No Trove page is touched or replaced.

    Fails (and writes nothing) unless the lesson exists in the course file.
    """
    key = existing.get("lesson_key", existing.get("key"))
    with courses._locked_course(registry.directory, slug) as locked:
        lesson = next((x for x in locked.payload.get("lessons", []) if key and x.get("lesson_key", x.get("key")) == key), None)
        if lesson is None:
            raise courses.IngestError(f"{slug}: no lesson {key} to attach meeting {meeting_id} to")
        path = registry.directory / "lessons" / slug / str(key) / f"wispr-{meeting_id[:8]}.txt"
        courses._atomic_write(path, _compose(mdir, db, meeting_id))
        alts = lesson.setdefault("alternates", [])
        if not any(a.get("meeting_id") == meeting_id for a in alts):
            alts.append({"source": "wispr", "meeting_id": meeting_id, "path": str(path)})
        courses._atomic_json(locked.path, locked.payload)
