"""Nightly import of lecture recordings from Wispr Flow into the lesson-notes pipeline.

Wispr Flow keeps meetings in a local SQLite database (live, WAL) plus one folder per meeting.
``scan`` matches each finished meeting to a course slot by its recording time. A matched meeting becomes
a text transcript handed to ``courses.add_source(..., transcript=True)`` (Drive, NotebookLM, queue job), or
an alternate on a lesson that already exists. An unmatched or ambiguous meeting may be a private work
meeting: only its id, times and reason are read and kept, never its title, summary or transcript.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import courses

DEFAULT_DATA_DIR = "~/Library/Application Support/Wispr Flow"
UNMATCHED_FILE = "wispr-unmatched.json"
EARLY_START = timedelta(minutes=20)
MIN_OVERLAP = timedelta(minutes=30)
MIN_FRACTION = 0.5


def data_dir(term: dict[str, Any]) -> Path:
    return Path(term.get("wispr_dir", DEFAULT_DATA_DIR)).expanduser()


def _connect(db: Path) -> tuple[sqlite3.Connection, Path | None]:
    """Open the live database read-only; fall back to a copy of db+wal+shm in a temp dir."""
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.execute("select count(*) from Meetings").fetchone()
        return conn, None
    except sqlite3.Error:
        tmp = Path(tempfile.mkdtemp(prefix="wispr-scan-"))
        for suffix in ("", "-wal", "-shm"):
            src = Path(str(db) + suffix)
            if src.exists():
                shutil.copyfile(src, tmp / (db.name + suffix))
        return sqlite3.connect(f"file:{tmp / db.name}?mode=ro", uri=True), tmp


def _parse_created(text: str) -> datetime:
    # '2026-10-13 13:04:49.396 +00:00'
    return datetime.fromisoformat(text.strip().replace(" +", "+").replace(" -", "-").replace(" ", "T", 1)).astimezone(timezone.utc)


def list_meetings(db: Path) -> list[dict[str, Any]]:
    """Finished, non-deleted meetings: metadata only (id and times). Titles, summaries and transcripts are not selected."""
    conn, tmp = _connect(db)
    try:
        rows = conn.execute(
            "select id, createdAt, endedAt, recordedMs from Meetings "
            "where finalized = 1 and transcriptReady = 1 and isDeleted = 0 order by createdAt"
        ).fetchall()
    finally:
        conn.close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    meetings = []
    for mid, created, ended, recorded in rows:
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
    """Return (slug, None) for exactly one matching course, else (None, reason)."""
    tz = ZoneInfo(registry.term.get("timezone", "Asia/Jerusalem"))
    lstart, lend = start.astimezone(tz), end.astimezone(tz)
    duration = lend - lstart
    day = lstart.date()
    matches: set[str] = set()
    for slug, course in registry.courses.items():
        for slot in course.get("slots", []):
            if courses.WEEKDAYS.get(str(slot.get("day"))) != lstart.weekday():
                continue
            if not courses._in_semester(registry.term, str(slot.get("semester", "")), day):
                continue
            s = datetime.combine(day, datetime.strptime(slot["start"], "%H:%M").time(), tz)
            e = datetime.combine(day, datetime.strptime(slot["end"], "%H:%M").time(), tz)
            if lstart < s - EARLY_START:
                continue
            overlap = min(lend, e) - max(lstart, s)
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
    """The Wispr summary of one MATCHED meeting."""
    conn, tmp = _connect(db)
    try:
        row = conn.execute("select summary from Meetings where id = ?", (meeting_id,)).fetchone()
    finally:
        conn.close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    return (row[0] or "").strip() if row else ""


def _seen_ids(registry: courses.Registry, term: dict[str, Any]) -> set[str]:
    seen = {str(x) for x in (term.get("state") or {}).get("wispr_seen", [])}
    for course in registry.courses.values():
        for lesson in course.get("lessons", []):
            if lesson.get("wispr_meeting_id"):
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
    seen = _seen_ids(registry, term)
    new_seen: list[str] = []
    for meeting in list_meetings(db):
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
        existing = next((x for x in registry.courses[slug].get("lessons", []) if x.get("date") == day), None)
        mdir = base / "meetings" / meeting["id"]
        try:
            if existing:
                entry["action"] = "alternate"
                entry["lesson_key"] = existing.get("lesson_key", existing.get("key"))
                if not dry_run:
                    _record_alternate(registry, slug, existing, meeting["id"], mdir, db)
            else:
                entry["action"] = "import"
                if not dry_run:
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


def _import(registry, slug, meeting_id, day, hm, mdir, db, runner, add_source) -> dict[str, Any]:
    staging = registry.directory / "wispr" / slug
    staging.mkdir(parents=True, exist_ok=True)
    path = staging / f"wispr-{day}-{hm}-{meeting_id[:8]}.txt"
    courses._atomic_write(path, _compose(mdir, db, meeting_id))
    kwargs = {"runner": runner} if runner else {}
    result = (add_source or courses.add_source)(registry, path, slug, origin="recording", transcript=True,
                                                lesson_date=day, lesson_time=hm, **kwargs)
    lesson_key = result.get("lesson_key")
    if lesson_key:
        with courses._locked_course(registry.directory, slug) as locked:
            for lesson in locked.payload.get("lessons", []):
                if lesson.get("lesson_key") == lesson_key:
                    lesson["wispr_meeting_id"] = meeting_id
            courses._atomic_json(locked.path, locked.payload)
    return {"lesson_key": lesson_key, "result_status": result.get("status")}


def _record_alternate(registry, slug, existing, meeting_id, mdir, db) -> None:
    """Keep the Wispr transcript beside an existing lesson. No Trove page is touched or replaced."""
    key = existing.get("lesson_key", existing.get("key"))
    folder = registry.directory / "lessons" / slug / str(key)
    path = folder / f"wispr-{meeting_id[:8]}.txt"
    courses._atomic_write(path, _compose(mdir, db, meeting_id))
    with courses._locked_course(registry.directory, slug) as locked:
        for lesson in locked.payload.get("lessons", []):
            if lesson.get("lesson_key", lesson.get("key")) == key:
                alts = lesson.setdefault("alternates", [])
                if not any(a.get("meeting_id") == meeting_id for a in alts):
                    alts.append({"source": "wispr", "meeting_id": meeting_id, "path": str(path)})
        courses._atomic_json(locked.path, locked.payload)
