#!/usr/bin/env python3
"""Per-user academic course registry and resource validator.

The registry is deliberately external to this plugin. Its files are JSON so
they can be reviewed and edited without installing a package.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, time, timedelta, timezone
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import drive_layout
import naming
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CODE_RE = re.compile(r"(?<!\d)(?:\d{6}(?:-\d{2})?|\d{5}(?:-\d{2})?|\d{2}-\d{3}-\d{2})(?!\d)")


def normalise_name(value: str) -> str:
    """Collapse whitespace and treat Hebrew quote variants consistently."""
    value = unicodedata.normalize("NFC", value)
    value = value.replace("״", '"').replace("׳", "'")
    return " ".join(value.split())


def entry_label(title: object) -> str:
    """The label part of a hinted ToC title ("<label> - <hint>")."""
    return normalise_name(str(title).split(" - ", 1)[0])


def _is_finished(record: dict[str, Any]) -> bool:
    """A term or course marked finished in its own JSON (status "finished"): its loops are skipped."""
    return str(record.get("status", "")) == "finished"


def _term_finished(term_dir: Path) -> bool:
    try:
        return _is_finished(json.loads((term_dir / "term.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return False


def _term_dir(root: Path, term: str | None = None) -> Path:
    """The term directory: the named one (finished or not), else the single term that is not finished."""
    if term is None:
        term = os.environ.get("ACADEMIC_TERM")
    if term:
        return root / term
    dirs = sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []
    live = [p for p in dirs if not _term_finished(p)]
    if len(live) == 1:
        return live[0]
    if (root / "term.json").is_file():
        return root
    raise ValueError(f"term is required; use --term or ACADEMIC_TERM under {root}")


class Registry:
    def __init__(self, directory: Path):
        self.directory = directory
        self.term = json.loads((directory / "term.json").read_text(encoding="utf-8"))
        self.courses: dict[str, dict[str, Any]] = {}
        for path in sorted(directory.glob("*.json")):
            if path.name == "term.json":
                continue
            course = json.loads(path.read_text(encoding="utf-8"))
            # links.json and any other non-course JSON carry no "slug": they are not courses
            if not isinstance(course, dict) or not course.get("slug"):
                continue
            self.courses[course["slug"]] = course

    def active_courses(self, include: str | None = None) -> dict[str, dict[str, Any]]:
        """Courses the loops work on: those not finished (their own status or their term's). `include` keeps one named finished course."""
        term_done = _is_finished(self.term)
        return {slug: course for slug, course in self.courses.items()
                if slug == include or not (term_done or _is_finished(course))}


# Moodle has no generic module page: the module type is part of the path (mod/assign/view.php?id=N)
CHORE_MODULE_TYPE = {"assignment": "assign", "forum-post": "forum"}
READING_POST_RE = re.compile(r"d(\d+)-p(\d+)")


def lemida_module_url(base: str, course: dict[str, Any], ref: Any, chore_kind: str = "") -> str | None:
    """Lemida page of module `ref`. The type comes from the course's watch_seen, else from the chore kind; None when unknown."""
    ref = str(ref or "")
    post = READING_POST_RE.fullmatch(ref)
    if base and post:
        # a reading announced in a forum post: ref d<discussion>-p<post>, one chore per post
        return f"{base.rstrip('/')}/mod/forum/discuss.php?d={post.group(1)}#p{post.group(2)}"
    seen = ((course.get("watch_seen") or {}).get("modules") or {}).get(ref) or {}
    mod = str(seen.get("type") or CHORE_MODULE_TYPE.get(chore_kind, ""))
    if not (base and ref.isdigit() and re.fullmatch(r"[a-z]+", mod)):
        return None
    return f"{base.rstrip('/')}/mod/{mod}/view.php?id={ref}"


def courses_root() -> Path:
    """Root that holds one directory per term.

    Order: ACADEMIC_COURSES_DIR; <home>/.academic-helper/terms when it exists; the legacy
    ~/.academic-writer/courses when it exists (a pre-migration user keeps working); then the home terms
    folder even if missing (a new home); then the legacy path.
    """
    override = os.environ.get("ACADEMIC_COURSES_DIR")
    if override:
        return Path(override).expanduser()
    legacy = Path("~/.academic-writer/courses").expanduser()
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        import home as home_mod
        acad = home_mod.home_dir()
    except Exception:
        acad = None
    finally:
        sys.path.pop(0)
    if acad is None:
        return legacy
    terms = acad / ".academic-helper" / "terms"
    if terms.is_dir():
        return terms
    return legacy if legacy.exists() else terms


def registry_dir(term: str | None = None) -> Path:
    """The term directory every course tool reads: the root plus --term / ACADEMIC_TERM / the sole term."""
    return _term_dir(courses_root(), term)


def registry_from_args(args: argparse.Namespace) -> Registry:
    return Registry(registry_dir(args.term))


WEEKDAYS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
VOICE_MEMO_RE = re.compile(r"^(\d{8}) (\d{6})(?:-[A-Za-z0-9]+)?(?:\.[^.]+)?$")


def recording_time(path: Path, birth_time: float | None = None, timezone_name: str = "Asia/Jerusalem") -> datetime:
    """Return recording creation time in the configured local timezone.

    Voice Memo timestamps are local wall times. Other files use their birth
    time when available, falling back to mtime, both interpreted as instants.
    ``birth_time`` is injectable to keep the platform-dependent path testable.
    """
    tz = ZoneInfo(timezone_name)
    match = VOICE_MEMO_RE.fullmatch(path.name)
    if match:
        parsed = datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
        return parsed.replace(tzinfo=tz)
    if birth_time is None:
        stat = path.stat()
        birth_time = getattr(stat, "st_birthtime", stat.st_mtime)
    return datetime.fromtimestamp(birth_time, tz=timezone.utc).astimezone(tz)


def _semester_dates(term: dict[str, Any], semester: str) -> tuple[date, date] | None:
    semesters = term.get("semesters", {})
    config = semesters.get(semester) if isinstance(semesters, dict) else None
    if not isinstance(config, dict):
        return None
    start = config.get("start", config.get("start_date"))
    end = config.get("end", config.get("end_date"))
    if not start or not end:
        return None
    return date.fromisoformat(str(start)), date.fromisoformat(str(end))


def _in_semester(term: dict[str, Any], semester: str, day: date) -> bool:
    labels = ("A", "B") if semester.lower() == "yearly" else (semester,)
    for label in labels:
        dates = _semester_dates(term, label)
        if dates and dates[0] <= day <= dates[1]:
            return True
    return False


def map_recording(registry: Registry, when: datetime) -> tuple[str | None, str | None]:
    """Map a recording start time to a course slug, or explain why it cannot."""
    tz = ZoneInfo(registry.term.get("timezone", "Asia/Jerusalem"))
    local_when = when.replace(tzinfo=tz) if when.tzinfo is None else when.astimezone(tz)
    weekday = local_when.weekday()
    matches: list[str] = []
    had_day = False
    had_semester = False
    for slug, course in registry.active_courses().items():
        for slot in course.get("slots", []):
            slot_day = slot.get("day")
            if WEEKDAYS.get(str(slot_day)) != weekday:
                continue
            had_day = True
            semester = str(slot.get("semester", ""))
            if not _in_semester(registry.term, semester, local_when.date()):
                continue
            had_semester = True
            start = datetime.combine(local_when.date(), time.fromisoformat(slot["start"]), tz)
            end = datetime.combine(local_when.date(), time.fromisoformat(slot["end"]), tz)
            if start - timedelta(minutes=15) <= local_when <= end + timedelta(minutes=30):
                matches.append(slug)
    matches = sorted(set(matches))
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        return None, f"ambiguous: {', '.join(matches)}"
    if had_day and not had_semester:
        return None, "outside configured semester dates"
    if had_semester:
        return None, "outside course slot window"
    return None, "no course slot matches this weekday and semester"


def _json_from_command(command: list[str], runner: Callable[..., Any]) -> Any:
    result = runner(command, check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


class IngestError(Exception):
    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


def _source_id(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("id", "source_id"):
            if payload.get(key):
                return str(payload[key])
        nested = payload.get("source")
        if isinstance(nested, dict) and nested.get("id"):
            return str(nested["id"])
    raise ValueError("NotebookLM source add response did not contain a source id")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _atomic_json(path: Path, payload: Any) -> None:
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _locked_course(directory: Path, slug: str):
    """Lock the registry before reading/modifying one course record."""
    class LockedCourse:
        def __enter__(self):
            self.lock = (directory / ".lock").open("a+")
            fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX)
            self.path = directory / f"{slug}.json"
            self.payload = json.loads(self.path.read_text(encoding="utf-8"))
            return self
        def __exit__(self, *exc):
            fcntl.flock(self.lock.fileno(), fcntl.LOCK_UN)
            self.lock.close()
    return LockedCourse()


def _registration_lock(directory: Path, slug: str):
    """Exclusive per-course lock held for a whole add_source call (separate from the short JSON-write lock)."""
    class RegistrationLock:
        def __enter__(self):
            directory.mkdir(parents=True, exist_ok=True)
            self.lock = (directory / f".{slug}.register.lock").open("a+")
            fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX)
            return self
        def __exit__(self, *exc):
            fcntl.flock(self.lock.fileno(), fcntl.LOCK_UN)
            self.lock.close()
    return RegistrationLock()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mark_lesson_done(registry: Registry, slug: str, lesson_key: str, page: int, status: str = "done") -> dict[str, Any]:
    """Record a lesson's Trove page under the course lock.

    ``status="appended"`` records the page right after it is written, before the ToC is
    rebuilt and verified, so an interrupted run resumes instead of appending it again.
    """
    if status not in {"appended", "done"}:
        raise ValueError(f"invalid lesson status: {status}")
    if slug not in registry.courses:
        raise ValueError(f"unknown course: {slug}")
    with _locked_course(registry.directory, slug) as locked:
        lesson = next((item for item in locked.payload.get("lessons", []) if item.get("lesson_key", item.get("key")) == lesson_key), None)
        if lesson is None:
            raise ValueError(f"unknown lesson key for {slug}: {lesson_key}")
        lesson["trove_page"] = page
        lesson["status"] = status
        _atomic_json(locked.path, locked.payload)
        return dict(lesson)


def ingest_recording(
    registry: Registry,
    audio: Path,
    *,
    course_slug: str | None = None,
    source_id: str | None = None,
    lesson_date: str | None = None,
    dry_run: bool = False,
    runner: Callable[..., Any] = subprocess.run,
    birth_time: float | None = None,
    transcript_file: bool = False,
    lesson_time: str | None = None,
    lesson_owner: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Upload audio to NotebookLM and persist a resumable lesson record.

    With ``transcript_file=True`` the file is a text transcript: it needs an explicit
    course and date, is uploaded as a text source, and is its own transcript.
    ``lesson_owner`` (e.g. ``{"wispr_meeting_id": ...}``) is stored on the lesson record in the
    same write that creates it; a stored lesson with the same bytes but another or no owner is
    refused rather than resumed.
    """
    audio = Path(audio).expanduser()
    if not audio.is_file():
        raise IngestError(f"{'transcript' if transcript_file else 'audio'} file not found: {audio}")
    timezone_name = registry.term.get("timezone", "Asia/Jerusalem")
    if lesson_time is not None and not re.fullmatch(r"([01]\d|2[0-3])[0-5]\d", lesson_time):
        raise IngestError(f"invalid lesson time (expected HHMM): {lesson_time}")
    if transcript_file:
        if not course_slug or not lesson_date:
            raise IngestError("--transcript requires --course and --date")
        when = None
    else:
        when = recording_time(audio, birth_time=birth_time, timezone_name=timezone_name)
    if course_slug:
        if course_slug not in registry.courses:
            raise IngestError(f"unknown course: {course_slug}")
        slug = course_slug
    else:
        slug, reason = map_recording(registry, when)
        if not slug:
            raise IngestError(f"unmatched: {reason}", 3)
    course = registry.courses[slug]
    day = lesson_date or when.date().isoformat()
    try:
        date.fromisoformat(day)
    except ValueError as exc:
        raise IngestError(f"invalid lesson date: {day}") from exc
    digest = _file_sha256(audio)
    notebook_id = course.get("notebook_id")
    if not notebook_id:
        raise IngestError(f"{slug}: missing notebook_id")
    if dry_run:
        return {"status": "dry run", "slug": slug, "date": day, "audio_sha256": digest, "notebook_id": notebook_id}

    # Explicit date-only input carries no time, so use 0000. Otherwise derive
    # the stable lesson key from the recording's local start time.
    if transcript_file or lesson_date:
        hm = lesson_time or "0000"
    else:
        hm = when.strftime("%H%M")
    lesson_base = f"{day}-{hm}"
    lessons_root = registry.directory / "lessons" / slug
    lessons_root.mkdir(parents=True, exist_ok=True)
    with _locked_course(registry.directory, slug) as locked:
        stored_course = locked.payload
        matching = next((x for x in stored_course.get("lessons", []) if x.get("audio_sha256") == digest), None)
        if matching and lesson_owner and any(matching.get(k) != v for k, v in lesson_owner.items()):
            held = {k: matching.get(k) for k in lesson_owner}
            raise IngestError(f"lesson {matching.get('lesson_key')} has the same bytes but is owned by {held}; refusing to reuse it")
        if matching and matching.get("status", "done") in {"queued", "appended", "done"}:
            return {"status": "already ingested", "slug": slug, "date": matching.get("date", day), "lesson_key": matching.get("lesson_key"), "audio_sha256": digest}
        found = matching if matching and matching.get("status") == "pending_transcript" else None
        if found:
            lesson_key = found.get("lesson_key") or found.get("key")
            selected_source = str(found.get("source_id"))
            lesson_dir = lessons_root / lesson_key
            reuse_pending = True
        else:
            lesson_dir = lessons_root / lesson_base
            suffix = 2
            while lesson_dir.exists():
                lesson_dir = lessons_root / f"{lesson_base}-{suffix}"
                suffix += 1
            lesson_dir.mkdir()
            lesson_key = lesson_dir.name
            reuse_pending = False
            selected_source = str(source_id) if source_id else ""
    if reuse_pending:
        pass
    else:
        upload_path = audio
        temporary_audio: Path | None = None
        if transcript_file:
            if not source_id:
                listed = _json_from_command(["nlm", "source", "list", str(notebook_id)], runner)
                sources = _as_list(listed, "sources", "items")
                limit = int(registry.term.get("notebook_source_limit", 45))
                if len(sources) >= limit:
                    raise IngestError(f"NotebookLM notebook has {len(sources)} sources; configured limit is {limit}", 4)
            if not selected_source:
                added = _json_from_command(["nlm", "source", "add", str(notebook_id), "--file", str(audio), "--title", f"{lesson_key} תמלול שיעור", "--wait", "--json"], runner)
                selected_source = _source_id(added)
        elif audio.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
            fd, temporary_name = tempfile.mkstemp(suffix=".m4a", prefix="academic-course-")
            os.close(fd)
            temporary_audio = Path(temporary_name)
            try:
                try:
                    runner(["ffmpeg", "-y", "-i", str(audio), "-vn", "-ac", "1", "-c:a", "aac", "-b:a", "64k", str(temporary_audio)], check=True, text=True, capture_output=True)
                except FileNotFoundError as exc:
                    raise IngestError("ffmpeg is required to extract audio from video; install ffmpeg and retry") from exc
                except subprocess.SubprocessError as exc:
                    raise IngestError(f"ffmpeg audio extraction failed: {exc}") from exc
                upload_path = temporary_audio
                listed = _json_from_command(["nlm", "source", "list", str(notebook_id)], runner) if not source_id else []
                sources = _as_list(listed, "sources", "items") if not source_id else []
                limit = int(registry.term.get("notebook_source_limit", 45))
                if not source_id and len(sources) >= limit:
                    raise IngestError(f"NotebookLM notebook has {len(sources)} sources; configured limit is {limit}", 4)
                if not selected_source:
                    added = _json_from_command(["nlm", "source", "add", str(notebook_id), "--file", str(upload_path), "--title", f"{lesson_key} שיעור", "--wait", "--wait-timeout", "3600", "--json"], runner)
                    selected_source = _source_id(added)
            finally:
                temporary_audio.unlink(missing_ok=True)
        else:
            if not source_id:
                listed = _json_from_command(["nlm", "source", "list", str(notebook_id)], runner)
                sources = _as_list(listed, "sources", "items")
                limit = int(registry.term.get("notebook_source_limit", 45))
                if len(sources) >= limit:
                    raise IngestError(f"NotebookLM notebook has {len(sources)} sources; configured limit is {limit}", 4)
            if not selected_source:
                added = _json_from_command(["nlm", "source", "add", str(notebook_id), "--file", str(upload_path), "--title", f"{lesson_key} שיעור", "--wait", "--wait-timeout", "3600", "--json"], runner)
                selected_source = _source_id(added)
        # Persist upload completion immediately, before asking NotebookLM for
        # transcript content, and reread under the exclusive registry lock.
        meta_path = lesson_dir / "meta.json"
        meta = {"slug": slug, "date": day, "lesson_key": lesson_key, "audio_path": str(audio.resolve()), "audio_sha256": digest, "source_id": selected_source, "notebook_id": str(notebook_id), "status": "upload_done"}
        _atomic_json(meta_path, meta)
        with _locked_course(registry.directory, slug) as locked:
            stored_course = locked.payload
            lessons = list(stored_course.get("lessons", []))
            if not any(x.get("audio_sha256") == digest and x.get("status") == "pending_transcript" for x in lessons):
                lessons.append({"date": day, "lesson_key": lesson_key, "audio_sha256": digest, "source_id": selected_source, "trove_page": None,
                                "status": "pending_transcript", **(lesson_owner or {})})
                stored_course["lessons"] = lessons
                _atomic_json(locked.path, stored_course)
    if transcript_file:
        transcript = audio.read_text(encoding="utf-8")
    else:
        try:
            content_result = _json_from_command(["nlm", "content", "source", selected_source], runner)
            transcript = content_result.get("content") if isinstance(content_result, dict) else None
            if not isinstance(transcript, str):
                raise IngestError("NotebookLM transcript response has no string content")
        except (IngestError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            raise IngestError(f"NotebookLM transcript failed for source_id {selected_source}: {exc}") from exc

    transcript_path = lesson_dir / "transcript.txt"
    _atomic_write(transcript_path, transcript)
    local_day = datetime.fromisoformat(day).date()
    weekday = next((name for name, number in WEEKDAYS.items() if number == local_day.weekday()), local_day.strftime("%a"))
    meta_path = lesson_dir / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    else:
        meta = {"slug": slug, "date": day, "lesson_key": lesson_key, "audio_path": str(audio.resolve()), "audio_sha256": digest, "source_id": selected_source, "notebook_id": str(notebook_id), "status": "upload_done"}
    meta.update({"weekday": weekday, "transcript_words": len(transcript.split()), "transcript_source": "file" if transcript_file else "notebooklm", "created_at": datetime.now(ZoneInfo(timezone_name)).isoformat(), "status": "queued"})
    _atomic_json(meta_path, meta)
    queue_path = registry.directory / "queue" / f"{slug}-{lesson_key}.json"
    _atomic_json(queue_path, {"slug": slug, "date": day, "lesson_key": lesson_key, "transcript_path": str(transcript_path), "meta_path": str(meta_path), "book_id": course.get("book_id"), "course_name": course.get("name"), "lecturer": course.get("lecturer")})
    with _locked_course(registry.directory, slug) as locked:
        stored_course = locked.payload
        for entry in stored_course.get("lessons", []):
            if entry.get("lesson_key") == lesson_key:
                entry["status"] = "queued"
                break
        _atomic_json(locked.path, stored_course)
    return {"status": "ingested", "slug": slug, "date": day, "lesson_key": lesson_key, "source_id": selected_source, "transcript_path": str(transcript_path), "queue_path": str(queue_path)}


def _as_list(value: Any, *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        if isinstance(value, dict) and isinstance(value.get(key), list):
            return value[key]
    if isinstance(value, list):
        return value
    raise ValueError("expected a JSON list")


def validate_registry(registry: Registry, runner: Callable[..., Any] = subprocess.run) -> list[str]:
    """Return one actionable mismatch per absent resource or name mismatch."""
    problems: list[str] = []
    try:
        notebooks = _as_list(_json_from_command(["nlm", "notebook", "list"], runner), "notebooks", "items")
    except Exception as exc:
        return [f"NotebookLM lookup failed: {exc}"]
    try:
        books = _as_list(_json_from_command(["trove", "items", "list", "--json", "--no-session"], runner), "items", "books")
    except Exception as exc:
        return [f"Trove lookup failed: {exc}"]
    notebook_by_id = {str(x.get("id")): x for x in notebooks}
    book_by_id = {str(x.get("id")): x for x in books}

    drive_cache: dict[str, list[dict[str, Any]] | Exception] = {}
    remote = registry.term.get("drive_remote", "gdrive")
    subject_map = registry.term.get("drive_subject_folders", {})
    naming = registry.term.get("naming", {})
    for slug, course in registry.active_courses().items():
        context = {**course, "term": registry.term.get("term", "")}
        try:
            expected = {
                key: naming.get(key, "{name}").format_map(context)
                for key in ("drive", "notebook")
            }
            # course books keep the title the manuscript template gave them; a `book` template wins when set
            expected["book"] = naming.get("book", naming.get("manuscript", "{name}")).format_map(context)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            problems.append(f"{slug}: naming template error: {exc}")
            continue
        for key in ("drive_folder_id", "notebook_id", "book_id"):
            if not course.get(key):
                problems.append(f"{slug}: missing {key}")
        notebook_id = course.get("notebook_id")
        if notebook_id:
            obj = notebook_by_id.get(str(notebook_id))
            if obj is None:
                problems.append(f"{slug}: NotebookLM notebook {notebook_id} not found")
            elif normalise_name(str(obj.get("title", ""))) != normalise_name(expected["notebook"]):
                problems.append(f"{slug}: NotebookLM name mismatch (expected {expected['notebook']!r}, got {obj.get('title')!r})")
        book_id = course.get("book_id")
        if book_id:
            obj = book_by_id.get(str(book_id))
            if obj is None:
                problems.append(f"{slug}: Trove book {book_id} not found")
            elif normalise_name(str(obj.get("title", ""))) != normalise_name(expected["book"]):
                problems.append(f"{slug}: Trove name mismatch (expected {expected['book']!r}, got {obj.get('title')!r})")
        drive_id = course.get("drive_folder_id")
        if drive_id:
            label = course.get("drive_subject_folder") or course.get("drive_subject")
            subject_id = subject_map.get(label, label)
            if not subject_id:
                problems.append(f"{slug}: no Drive subject folder configured")
                continue
            if subject_id not in drive_cache:
                try:
                    result = runner(["rclone", "lsjson", f"{remote}:", "--drive-root-folder-id", str(subject_id), "--dirs-only"], check=True, text=True, capture_output=True)
                    drive_cache[subject_id] = json.loads(result.stdout)
                except Exception as exc:
                    drive_cache[subject_id] = exc
            listing = drive_cache[subject_id]
            if isinstance(listing, Exception):
                problems.append(f"{slug}: Drive lookup failed: {listing}")
                continue
            obj = next((x for x in listing if str(x.get("ID", x.get("id", ""))) == str(drive_id)), None)
            if obj is None:
                problems.append(f"{slug}: Drive folder {drive_id} not found under subject folder {label or subject_id}")
            elif normalise_name(str(obj.get("Name", obj.get("name", "")))) != normalise_name(expected["drive"]):
                problems.append(f"{slug}: Drive name mismatch (expected {expected['drive']!r}, got {obj.get('Name', obj.get('name'))!r})")
    return problems


def _cell_paragraphs(cell: ET.Element) -> list[str]:
    """Keep paragraph/line-break boundaries, including multiple runs."""
    out: list[str] = []
    for paragraph in cell.findall(".//" + W + "p"):
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == W + "t":
                parts.append(node.text or "")
            elif node.tag == W + "br":
                parts.append("\n")
        out.extend(line.strip() for line in "".join(parts).splitlines() if line.strip())
        joined = "".join(parts).strip()
        if joined and "\n" not in joined and joined.strip() not in out[-1:]:
            # A paragraph containing only regular text was already emitted.
            pass
    return out


def _cell_text(cell: ET.Element) -> str:
    return "\n".join(_cell_paragraphs(cell))


def parse_docx(path: Path) -> list[dict[str, Any]]:
    """Parse a BIU-like timetable table into reviewable course stubs."""
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    tables = root.findall(".//" + W + "tbl")
    if not tables:
        raise ValueError("DOCX contains no tables")
    table = max(tables, key=lambda t: len(t.findall("./" + W + "tr")))
    rows: list[list[dict[str, Any]]] = []
    for tr in table.findall("./" + W + "tr"):
        cells = []
        for tc in tr.findall("./" + W + "tc"):
            text = _cell_text(tc)
            span_el = tc.find("./" + W + "tcPr/" + W + "gridSpan")
            span = int(span_el.get(W + "val", "1")) if span_el is not None else 1
            merge_el = tc.find("./" + W + "tcPr/" + W + "vMerge")
            cells.append({"text": text, "span": span, "merge": merge_el is not None, "continuation": merge_el is not None and merge_el.get(W + "val") is None})
        rows.append(cells)
    if not rows:
        return []

    # Expand physical cells onto the table grid; row 0 provides the weekday headers.
    expanded: list[list[dict[str, Any] | None]] = []
    for row in rows:
        grid: list[dict[str, Any] | None] = []
        for cell in row:
            grid.extend([cell] * cell["span"])
        expanded.append(grid)
    width = max(map(len, expanded))
    expanded = [r + [None] * (width - len(r)) for r in expanded]
    headers: list[tuple[int, int, str]] = []
    head = expanded[0]
    col = 0
    while col < width:
        cell = head[col]
        if cell and cell["text"]:
            span = 1
            while col + span < width and head[col + span] is cell:
                span += 1
            label = cell["text"].splitlines()[0].strip()
            if re.search(r"ראשון|שני|שלישי|רביעי|חמישי|שישי|שבת|יום א|יום ב|יום ג|יום ד|יום ה|יום ו", label):
                headers.append((col, col + span, label))
            col += span
        else:
            col += 1
    stubs: list[dict[str, Any]] = []
    carry: dict[int, str] = {}
    last_stub_by_subcolumn: dict[int, int] = {}
    for row in expanded[1:]:
        row_text = " ".join(c["text"] for c in row if c and c["text"])
        time_match = re.search(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", row_text)
        if not time_match:
            continue
        start, end = time_match.groups()
        for first, last, day_label in headers:
            for subcol in range(first, last):
                cell = row[subcol]
                if cell and cell["merge"] and cell["continuation"]:
                    text = carry.get(subcol, "")
                elif cell and cell["text"]:
                    text = cell["text"]
                    carry[subcol] = text
                else:
                    continue
                if subcol > first and row[subcol - 1] is cell:
                    continue
                if cell and cell["merge"] and cell["continuation"]:
                    previous = last_stub_by_subcolumn.get(subcol)
                    if previous is not None:
                        stubs[previous]["slots"][0]["end"] = end
                    continue
                same_cell_span = 1
                while subcol + same_cell_span < last and row[subcol + same_cell_span] is cell:
                    same_cell_span += 1
                if same_cell_span > 1 and subcol % 2 == first % 2:
                    semester = "yearly"
                elif same_cell_span > 1:
                    continue
                else:
                    semester = "A" if (subcol - first) % 2 == 0 else "B"
                if not text or re.fullmatch(r"\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}", text):
                    continue
                code_match = CODE_RE.search(text)
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                name = next((line for line in lines if not CODE_RE.search(line) and not re.search(r"נ[״׳']?ז|נ" + '"' + r"?ז", line)), lines[0])
                lecturer = next((line for line in lines if re.search(r"פרופ|ד״ר|ד׳ר|ד'ר|דוקטור", line)), "")
                day = next((d for d, pattern in [("Sun", "ראשון|א׳|א'"), ("Mon", "שני|ב׳|ב'"), ("Tue", "שלישי|ג׳|ג'"), ("Wed", "רביעי|ד׳|ד'"), ("Thu", "חמישי|ה׳|ה'"), ("Fri", "שישי|ו׳|ו'")] if re.search(pattern, day_label)), day_label)
                stubs.append({"code": code_match.group(0) if code_match else None, "name": name, "lecturer": lecturer or None, "credits": next((re.search(r"\d+(?:\.\d+)?\s*נ[״׳']?ז", line).group(0) for line in lines if re.search(r"\d+(?:\.\d+)?\s*נ[״׳']?ז", line)), None), "slots": [{"day": day, "start": start, "end": end, "semester": semester}]})
                stub_index = len(stubs) - 1
                for offset in range(same_cell_span):
                    last_stub_by_subcolumn[subcol + offset] = stub_index
    return stubs



LESSON_KEY_PREFIX = "- מפתח שיעור: "


def find_lesson_page(registry: Registry, slug: str, lesson_key: str, runner: Callable[..., Any] = subprocess.run) -> int | None:
    """Return the Trove page whose header carries exactly this lesson key, or None."""
    course = registry.courses.get(slug)
    if course is None:
        raise ValueError(f"unknown course: {slug}")
    if not course.get("book_id"):
        raise ValueError(f"{slug}: missing book_id")
    result = runner(["trove", "items", "get", str(course["book_id"]), "--no-session"], check=True, text=True, capture_output=True)
    page = 0
    found = None
    for line in result.stdout.splitlines():
        if line.startswith("# "):
            page += 1
        elif line.strip() == LESSON_KEY_PREFIX + lesson_key:
            if found is not None and found != page:
                raise ValueError(f"{slug}: lesson key {lesson_key} appears on pages {found} and {page}")
            found = page
    return found


LESSONS_ENTRY = "תמלולי שיעורים"


def check_lesson(registry: Registry, slug: str, date: str, runner: Callable[..., Any] = subprocess.run) -> list[str]:
    """Return problems for a lesson that should be done and nested under the lessons entry.

    ``date`` is either an exact lesson key (``YYYY-MM-DD-HHMM[-n]``), which checks that one
    lesson, or a bare date, which checks every lesson recorded on that day.
    """
    course = registry.courses.get(slug)
    if course is None:
        return [f"unknown course: {slug}"]
    def key_of(item: dict[str, Any]) -> str:
        return str(item.get("lesson_key", item.get("key", "")))

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}-\d{4}(?:-\d+)?", date):
        lessons = [item for item in course.get("lessons", []) if key_of(item) == date]
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        lessons = [item for item in course.get("lessons", []) if str(item.get("date", "")) == date or key_of(item).startswith(date + "-")]
    else:
        return [f"invalid lesson selector {date!r}: use YYYY-MM-DD or YYYY-MM-DD-HHMM"]
    if not lessons:
        return [f"{slug}: no lesson recorded for {date}"]
    problems: list[str] = []
    pages = []
    for lesson in lessons:
        if lesson.get("status") not in {"appended", "done"} or not lesson.get("trove_page"):
            problems.append(f"{slug}: lesson {key_of(lesson) or date} is not done (status={lesson.get('status')!r}, trove_page={lesson.get('trove_page')!r})")
        else:
            pages.append(int(lesson["trove_page"]))
    if problems:
        return problems
    book_id = course.get("book_id")
    if not book_id:
        return [f"{slug}: missing book_id"]
    try:
        data = _json_from_command(["trove", "items", "toc", str(book_id), "--json", "--no-session"], runner)
    except Exception as exc:
        return [f"{slug}: Trove ToC lookup failed: {exc}"]
    items = data.get("items", []) if isinstance(data, dict) else data
    toc = items[0].get("toc", []) if items else []
    parent_index = next((i for i, entry in enumerate(toc) if entry_label(entry.get("title", "")) == LESSONS_ENTRY and entry.get("level") == 1), None)
    if parent_index is None:
        return [f"{slug}: ToC has no level-1 entry {LESSONS_ENTRY!r}"]
    children = []
    for entry in toc[parent_index + 1:]:
        if entry.get("level", 1) <= 1:
            break
        children.append(entry)
    child_pages = {entry.get("page") for entry in children if entry.get("level") == 2}
    for page in pages:
        if page not in child_pages:
            problems.append(f"{slug}: lesson page {page} is not a level-2 entry under {LESSONS_ENTRY!r}")
    if problems or len(date) <= 10:
        return problems
    try:
        actual = find_lesson_page(registry, slug, date, runner=runner)
    except Exception as exc:
        return [f"{slug}: could not confirm page identity: {exc}"]
    if actual not in pages:
        problems.append(f"{slug}: recorded page {pages} does not carry lesson key {date} (found on {actual})")
    return problems


MEDIA_EXTENSIONS = {".m4a", ".mp3", ".wav", ".mp4", ".mov", ".mkv", ".webm"}
READINGS_ENTRY = "חומרי קריאה"
TITLE_PREFIX_RE = re.compile(r"^(?:\d+|email-\d{4}-\d{2}-\d{2})\s*-\s*")
ORIGINS = ("lemida", "email", "recording", "library", "other")


def _default_title(path: Path) -> str:
    stem = TITLE_PREFIX_RE.sub("", path.stem).strip()
    return stem or path.stem


def _snapshot_source(registry: Registry, slug: str, file: Path, sha8: str) -> Path:
    """Copy a source into a content-addressed, never-overwritten snapshot and return its path."""
    safe = re.sub(r"[\\/\x00-\x1f]", "_", file.name).strip().lstrip(".") or "file"
    snapshot = registry.directory / "sources" / slug / f"{sha8}-{safe}"
    if not snapshot.exists():
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=snapshot.parent, prefix=f".{sha8}.", suffix=".tmp")
        os.close(handle)
        try:
            shutil.copyfile(file, temporary)
            os.replace(temporary, snapshot)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
    return snapshot


def _source_kind(path: Path) -> str:
    return {".pdf": "pdf", ".docx": "docx", ".pptx": "pptx"}.get(path.suffix.lower(), "other")


def _pdf_pages(path: Path, runner: Callable[..., Any]) -> int | None:
    if path.suffix.lower() != ".pdf":
        return None
    try:
        result = runner(["pdfinfo", str(path)], check=True, text=True, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"^Pages:\s*(\d+)", str(result.stdout), re.MULTILINE)
    return int(match.group(1)) if match else None


def _update_source(registry: Registry, slug: str, sha: str, **fields: Any) -> dict[str, Any]:
    """Merge fields into one recorded source under the course lock (fresh re-read)."""
    with _locked_course(registry.directory, slug) as locked:
        sources = locked.payload.setdefault("sources", [])
        entry = next((s for s in sources if s.get("sha256") == sha), None)
        if entry is None:
            entry = {"sha256": sha}
            sources.append(entry)
        entry.update(fields)
        _atomic_json(locked.path, locked.payload)
        return dict(entry)


def _folder_listing(runner: Callable[..., Any], remote: str, root_id: str, subdir: str) -> list[dict[str, Any]]:
    """Files already in a Drive folder under the course root, with their hashes; an absent folder holds none."""
    try:
        listing = _json_from_command(["rclone", "lsjson", f"{remote}:{subdir}", "--drive-root-folder-id", str(root_id),
                                      "--files-only", "--hash"], runner)
    except subprocess.CalledProcessError as exc:
        if exc.returncode == 3:  # rclone: directory not found
            return []
        raise IngestError(f"Drive listing failed: {exc}") from exc
    return [item for item in _as_list(listing, "files", "items") if isinstance(item, dict)]


def _folder_names(runner: Callable[..., Any], remote: str, root_id: str, subdir: str) -> set[str]:
    """File names already in a Drive folder under the course root; an absent folder holds none."""
    return {str(item.get("Name", "")) for item in _folder_listing(runner, remote, root_id, subdir)}


def _upload_to_drive(registry: Registry, course: dict[str, Any], file: Path, preview: dict[str, Any], runner: Callable[..., Any]) -> str:
    """Copy a file into its kind folder under its Chicago name, never over another file. Returns its Drive path."""
    folder = course.get("drive_folder_id")
    if not folder:
        raise IngestError(f"{course.get('slug')}: missing drive_folder_id")
    remote = registry.term.get("drive_remote", "gdrive")
    subdir = drive_layout.folder_for(course, preview)
    listing = _folder_listing(runner, remote, folder, subdir)
    local_md5 = hashlib.md5(file.read_bytes()).hexdigest()
    for item in listing:
        # A retry after an upload that landed but was never recorded: reuse that copy instead of making a second one.
        if str(((item.get("Hashes") or {}).get("md5") or "")).lower() == local_md5:
            return f"{subdir}/{item.get('Name')}" if subdir else str(item.get("Name"))
    names = {str(item.get("Name", "")) for item in listing}
    rel = drive_layout.drive_path_for(course, preview, {subdir: names})
    try:
        # --ignore-existing: a file another Drive client put at this path after the listing is skipped, never replaced.
        runner(["rclone", "copyto", str(file), f"{remote}:{rel}", "--ignore-existing", "--drive-root-folder-id", str(folder)],
               check=True, text=True, capture_output=True)
        stat = _json_from_command(["rclone", "lsjson", f"{remote}:{rel}", "--stat", "--hash", "--drive-root-folder-id", str(folder)], runner)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise IngestError(f"Drive copy failed: {exc}") from exc
    remote_md5 = ((stat.get("Hashes") or {}).get("md5") or (stat.get("Hashes") or {}).get("MD5")) if isinstance(stat, dict) else None
    if not remote_md5 or remote_md5.lower() != local_md5:
        raise IngestError(f"Drive copy not confirmed: the file at {rel} on Drive has MD5 {remote_md5}, the local file {local_md5}; "
                          "another file may hold that path")
    return rel


def add_source(
    registry: Registry,
    file: Path,
    course_slug: str,
    title: str | None = None,
    origin: str = "other",
    origin_ref: str | None = None,
    runner: Callable[..., Any] = subprocess.run,
    transcript: bool = False,
    lesson_date: str | None = None,
    lesson_time: str | None = None,
    kind: str | None = None,
    lesson_owner: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Copy a course file to Drive and NotebookLM and queue its Trove job (resumable).

    Recordings and transcripts are sources too: they are snapshotted, copied to Drive and
    recorded with ``kind="media"``, then handed to ``ingest_recording``; their Trove home
    is the lesson page. ``kind`` is "media" or "document"; None picks by extension. An explicit
    "media" accepts any filename (ffmpeg probes the content, not the name). ``lesson_owner`` is
    passed to ``ingest_recording`` for a recording or transcript.
    """
    if kind not in (None, "media", "document"):
        raise IngestError(f"invalid kind: {kind}")
    file = Path(file).expanduser()
    if not file.is_file():
        raise IngestError(f"file not found: {file}")
    if course_slug not in registry.courses:
        raise IngestError(f"unknown course: {course_slug}")
    if origin not in ORIGINS:
        raise IngestError(f"invalid origin: {origin}")
    # one registration at a time per course: dedupe check through queue job are one critical section
    with _registration_lock(registry.directory, course_slug):
        return _add_source_locked(registry, file, course_slug, title=title, origin=origin, origin_ref=origin_ref, runner=runner,
                                  transcript=transcript, lesson_date=lesson_date, lesson_time=lesson_time, kind=kind,
                                  lesson_owner=lesson_owner)


def _add_source_locked(registry: Registry, file: Path, course_slug: str, *, title: str | None, origin: str, origin_ref: str | None,
                       runner: Callable[..., Any], transcript: bool, lesson_date: str | None, lesson_time: str | None,
                       kind: str | None = None, lesson_owner: dict[str, str] | None = None) -> dict[str, Any]:
    if kind is None:
        kind = "media" if file.suffix.lower() in MEDIA_EXTENSIONS else "document"
    if transcript or kind == "media":
        return _add_media_source(registry, file, course_slug, title=title, origin=origin, origin_ref=origin_ref, runner=runner,
                                 transcript=transcript, lesson_date=lesson_date, lesson_time=lesson_time, lesson_owner=lesson_owner)
    sha = _file_sha256(file)
    sha8 = sha[:8]
    with _locked_course(registry.directory, course_slug) as locked:
        course = locked.payload
        existing = next((s for s in course.get("sources", []) if s.get("sha256") == sha), None)
    if existing and existing.get("status") in {"queued", "done"}:
        return {"status": "already added", "slug": course_slug, "sha8": sha8, "title": existing.get("title"), "source_status": existing.get("status"), "file": existing.get("file")}
    title = title or (existing or {}).get("title") or _default_title(file)
    recorded = Path(str((existing or {}).get("file") or ""))
    if existing and existing.get("file") and recorded.is_file():
        file = recorded  # an earlier attempt already recorded its bytes; keep that path
    else:
        file = _snapshot_source(registry, course_slug, file, sha8)
    need_drive = not (existing and existing.get("drive"))
    need_nlm = not (existing and existing.get("notebook_source_id"))
    notebook_id = course.get("notebook_id")
    if need_nlm:
        if not notebook_id:
            raise IngestError(f"{course_slug}: missing notebook_id")
        listed = _json_from_command(["nlm", "source", "list", str(notebook_id)], runner)
        limit = int(registry.term.get("notebook_source_limit", 45))
        count = len(_as_list(listed, "sources", "items"))
        if count >= limit:
            raise IngestError(f"NotebookLM notebook has {count} sources; configured limit is {limit}", 4)
    preview = {"name": file.name, "file": str(file), "title": title, "origin": origin, "origin_ref": origin_ref, "kind": kind}
    if need_drive:
        # The upload holds the registry lock that drive-reorg holds while it plans and moves, so an upload cannot land
        # on a planned destination mid-reorg. (_upload_to_drive takes no lock itself: no nested locking here.)
        with _locked_course(registry.directory, course_slug) as locked:
            rel = _upload_to_drive(registry, locked.payload, file, preview, runner)
        _update_source(registry, course_slug, sha, sha8=sha8, title=title, file=str(file.resolve()), origin=origin, origin_ref=origin_ref,
                       drive=True, drive_path=rel, notebook_source_id=None, trove=None, status="drive_done",
                       added_at=datetime.now(timezone.utc).isoformat())
    if need_nlm:
        added = _json_from_command(["nlm", "source", "add", str(notebook_id), "--file", str(file), "--title", drive_layout.display_title(preview), "--wait", "--json"], runner)
        if isinstance(added, dict) and added.get("source_id"):
            source_id = str(added["source_id"])
        else:
            source_id = _source_id(added)
        _update_source(registry, course_slug, sha, notebook_source_id=source_id, status="uploaded")
    job_path = registry.directory / "queue" / "sources" / f"{course_slug}-{sha8}.json"
    _atomic_json(job_path, {
        "slug": course_slug, "sha8": sha8, "title": title, "file": str(file.resolve()),
        "pages": _pdf_pages(file, runner), "kind": _source_kind(file),
        "book_id": course.get("book_id"), "course_name": course.get("name"),
    })
    entry = _update_source(registry, course_slug, sha, status="queued")
    return {"status": "added", "slug": course_slug, "sha8": sha8, "title": title, "notebook_source_id": entry.get("notebook_source_id"), "queue_path": str(job_path), "file": str(file.resolve())}


def _add_media_source(registry: Registry, file: Path, course_slug: str, *, title: str | None, origin: str, origin_ref: str | None,
                      runner: Callable[..., Any], transcript: bool, lesson_date: str | None, lesson_time: str | None,
                      lesson_owner: dict[str, str] | None = None) -> dict[str, Any]:
    if transcript and not lesson_date:
        raise IngestError("--transcript requires --date")
    sha = _file_sha256(file)
    sha8 = sha[:8]
    if not transcript and not lesson_date:
        # the original's own start time, read before snapshotting (the snapshot has neither name nor birth time)
        when = recording_time(file, timezone_name=registry.term.get("timezone", "Asia/Jerusalem"))
        lesson_date, lesson_time = when.date().isoformat(), when.strftime("%H%M")
    with _locked_course(registry.directory, course_slug) as locked:
        course = locked.payload
        existing = next((s for s in course.get("sources", []) if s.get("sha256") == sha), None)
    if existing and existing.get("status") in {"queued", "done"} and existing.get("lesson_key"):
        return {"status": "already added", "slug": course_slug, "sha8": sha8, "title": existing.get("title"),
                "lesson_key": existing.get("lesson_key"), "source_status": existing.get("status"), "file": existing.get("file")}
    title = title or (existing or {}).get("title") or _default_title(file)
    recorded = Path(str((existing or {}).get("file") or ""))
    snapshot = recorded if existing and existing.get("file") and recorded.is_file() else _snapshot_source(registry, course_slug, file, sha8)
    # ingest the immutable snapshot; date and time were fixed above from the caller or the original
    result = ingest_recording(registry, snapshot, course_slug=course_slug, lesson_date=lesson_date, lesson_time=lesson_time,
                              runner=runner, transcript_file=transcript, **({"lesson_owner": lesson_owner} if lesson_owner else {}))
    lesson_key = result.get("lesson_key")
    source_id = result.get("source_id")
    if not (lesson_key and source_id):
        with _locked_course(registry.directory, course_slug) as locked:
            lesson = next((x for x in locked.payload.get("lessons", []) if x.get("audio_sha256") == sha), {})
        lesson_key = lesson_key or lesson.get("lesson_key")
        source_id = source_id or lesson.get("source_id")
    if not (existing and existing.get("drive")):
        # Uploaded only now, with the key ingest actually gave this lesson (a same-minute clash gets a suffix there),
        # so the Drive lesson folder always matches the lesson.
        preview = {"name": snapshot.name, "file": str(snapshot), "title": title, "origin": origin, "origin_ref": origin_ref,
                   "kind": "media", "lesson_key": lesson_key or f"{lesson_date}-{lesson_time or '0000'}"}
        # the listing, the name choice and the copy hold the registry lock, as the document upload does (no nested locking)
        with _locked_course(registry.directory, course_slug) as locked:
            rel = _upload_to_drive(registry, locked.payload, snapshot, preview, runner)
        _update_source(registry, course_slug, sha, sha8=sha8, title=title, file=str(snapshot.resolve()), origin=origin, origin_ref=origin_ref,
                       kind="media", drive=True, drive_path=rel, trove=None, added_at=datetime.now(timezone.utc).isoformat())
    _update_source(registry, course_slug, sha, kind="media", lesson_key=lesson_key, notebook_source_id=str(source_id) if source_id else None, status="queued")
    merged = dict(result)
    merged.update({"sha8": sha8, "title": title, "file": str(snapshot.resolve())})
    return merged


def _select_source(course: dict[str, Any], slug: str, sha8: str) -> dict[str, Any]:
    matches = [s for s in course.get("sources", []) if str(s.get("sha256", "")).startswith(sha8)]
    if not matches:
        raise ValueError(f"{slug}: no source with sha {sha8}")
    if len(matches) > 1:
        raise ValueError(f"{slug}: sha prefix {sha8} is ambiguous")
    return matches[0]


def source_done(registry: Registry, slug: str, sha8: str, trove: str) -> dict[str, Any]:
    """Record the Trove location (``book_id:page``) of a source and retire its job."""
    if slug not in registry.courses:
        raise ValueError(f"unknown course: {slug}")
    book_id, separator, page_text = trove.rpartition(":")
    if not separator or not book_id or not page_text.isdigit():
        raise ValueError(f"invalid --trove {trove!r}: use <book_id>:<page>")
    with _locked_course(registry.directory, slug) as locked:
        entry = _select_source(locked.payload, slug, sha8)
        entry["trove"] = {"book_id": book_id, "page": int(page_text)}
        entry["status"] = "done"
        _atomic_json(locked.path, locked.payload)
        result = dict(entry)
    job = registry.directory / "queue" / "sources" / f"{slug}-{result['sha256'][:8]}.json"
    if job.is_file():
        done_dir = job.parent / "done"
        done_dir.mkdir(parents=True, exist_ok=True)
        os.replace(job, done_dir / job.name)
    return result


def _toc_of(book_id: str, runner: Callable[..., Any]) -> list[dict[str, Any]]:
    data = _json_from_command(["trove", "items", "toc", str(book_id), "--json", "--no-session"], runner)
    items = data.get("items", []) if isinstance(data, dict) else data
    return items[0].get("toc", []) if items else []


def check_source(registry: Registry, slug: str, sha8: str | None = None, runner: Callable[..., Any] = subprocess.run) -> list[str]:
    """Return one problem per missing home (Drive, NotebookLM, Trove) of each selected source."""
    course = registry.courses.get(slug)
    if course is None:
        return [f"unknown course: {slug}"]
    sources = course.get("sources", [])
    if sha8:
        try:
            sources = [_select_source(course, slug, sha8)]
        except ValueError as exc:
            return [str(exc)]
    if not sources:
        return []
    problems: list[str] = []
    drive_names: set[str] | None = None
    notebook_ids: set[str] | None = None
    course_toc: list[dict[str, Any]] | None = None
    folder = course.get("drive_folder_id")
    remote = registry.term.get("drive_remote", "gdrive")
    if not folder:
        problems.append(f"{slug}: missing drive_folder_id")
    else:
        try:
            listing = _json_from_command(["rclone", "lsjson", f"{remote}:", "--drive-root-folder-id", str(folder), "--files-only", "-R"], runner)
            drive_names = {str(item.get("Path") or item.get("Name", "")) for item in _as_list(listing, "files", "items")}
        except Exception as exc:
            problems.append(f"{slug}: Drive listing failed: {exc}")
    if course.get("notebook_id"):
        try:
            listing = _json_from_command(["nlm", "source", "list", str(course["notebook_id"])], runner)
            notebook_ids = {str(item.get("id", item.get("source_id", ""))) for item in _as_list(listing, "sources", "items")}
        except Exception as exc:
            problems.append(f"{slug}: NotebookLM listing failed: {exc}")
    else:
        problems.append(f"{slug}: missing notebook_id")
    for source in sources:
        label = f"{slug} {str(source.get('sha256', ''))[:8]} ({source.get('title')})"
        name = Path(str(source.get("file", ""))).name
        recorded = source.get("drive_path")
        # a source moved by drive-reorg is found at its recorded path; an older one at the root under its own name
        expected = str(recorded) if recorded else name
        if drive_names is not None and expected not in drive_names:
            problems.append(f"{label}: {expected!r} is not in the Drive folder")
        source_id = source.get("notebook_source_id")
        if not source_id:
            problems.append(f"{label}: no NotebookLM source recorded")
        elif notebook_ids is not None and str(source_id) not in notebook_ids:
            problems.append(f"{label}: NotebookLM source {source_id} is not in the notebook")
        if source.get("kind") == "media":
            # its Trove home is the lesson page, verified by check_lesson
            lesson_key = source.get("lesson_key")
            lesson = next((x for x in course.get("lessons", []) if x.get("lesson_key", x.get("key")) == lesson_key), None) if lesson_key else None
            if lesson is None:
                problems.append(f"{label}: no lesson recorded (lesson_key={lesson_key!r})")
            elif lesson.get("status") not in {"appended", "done"}:
                problems.append(f"{label}: lesson pending (lesson {lesson_key} status={lesson.get('status')!r}, not verified)")
            else:
                problems.extend(f"{label}: {problem}" for problem in check_lesson(registry, slug, str(lesson_key), runner=runner))
            continue
        trove = source.get("trove")
        if source.get("status") != "done" or not isinstance(trove, dict) or not trove.get("book_id"):
            problems.append(f"{label}: Trove not done (status={source.get('status')!r}, trove={trove!r})")
            continue
        if not course.get("book_id"):
            problems.append(f"{label}: course has no book_id")
            continue
        try:
            if course_toc is None:
                course_toc = _toc_of(str(course["book_id"]), runner)
        except Exception as exc:
            problems.append(f"{label}: Trove ToC lookup failed: {exc}")
            continue
        parent = next((i for i, e in enumerate(course_toc) if e.get("level") == 1 and entry_label(e.get("title", "")) == READINGS_ENTRY), None)
        if parent is None:
            problems.append(f"{label}: course ToC has no level-1 entry {READINGS_ENTRY!r}")
            continue
        children = []
        for entry in course_toc[parent + 1:]:
            if entry.get("level", 1) <= 1:
                break
            if entry.get("level") == 2:
                children.append(entry)
        if str(trove["book_id"]) == str(course["book_id"]):
            if trove.get("page") not in {e.get("page") for e in children}:
                problems.append(f"{label}: page {trove.get('page')} is not a level-2 entry under {READINGS_ENTRY!r}")
            else:
                wanted = normalise_name(str(source.get("title", "")))
                at_page = [normalise_name(str(e.get("title", ""))) for e in children if e.get("page") == trove.get("page")]
                if not any(t == wanted or t.startswith(wanted + " - ") for t in at_page):
                    problems.append(f"{label}: level-2 entry at page {trove.get('page')} is {at_page[0]!r}, not titled {wanted!r}")
        else:
            wanted = normalise_name(str(source.get("title", "")))
            if not any(normalise_name(str(e.get("title", ""))) == wanted or normalise_name(str(e.get("title", ""))).startswith(wanted + " - ") for e in children):
                problems.append(f"{label}: no level-2 pointer titled {wanted!r} under {READINGS_ENTRY!r}")
            try:
                if not _toc_of(str(trove["book_id"]), runner):
                    problems.append(f"{label}: Trove book {trove['book_id']} has an empty ToC")
            except Exception as exc:
                problems.append(f"{label}: Trove book {trove['book_id']} ToC lookup failed: {exc}")
    return problems


def _nightly_running(runner: Callable[..., Any]) -> bool:
    """True while the nightly courses job runs (pgrep matches its bash command line)."""
    result = runner(["pgrep", "-f", drive_layout.NIGHTLY_PATTERN], check=False, text=True, capture_output=True)
    return result.returncode == 0 and bool(str(result.stdout or "").strip())


def _listing(runner: Callable[..., Any], remote: str, folder: str) -> list[dict[str, Any]]:
    return _as_list(_json_from_command(["rclone", "lsjson", f"{remote}:", "--drive-root-folder-id", str(folder), "-R"], runner), "files", "items")


def _source_by_sha(course: dict[str, Any], sha: str) -> dict[str, Any] | None:
    return next((s for s in course.get("sources", []) if sha and s.get("sha256") == sha), None)


def _nlm_title(source: dict[str, Any] | None) -> str | None:
    """The NotebookLM title a source gets after a move; media keep their lesson titles."""
    if source is None or source.get("kind") == "media":
        return None
    return drive_layout.display_title(source)


def _set_drive_path(locked: Any, sha: str, new: str) -> None:
    """Record a source's Drive path under the course lock the caller holds (no re-lock: that would deadlock)."""
    entry = _source_by_sha(locked.payload, sha)
    if entry is None:
        raise drive_layout.ReorgError(f"registry has no source {sha[:8]} to record {new!r} for")
    entry["drive_path"] = new
    _atomic_json(locked.path, locked.payload)


def _manifest(slug: str, folder: str, course: dict[str, Any], plan: list[dict[str, Any]]) -> dict[str, Any]:
    moves = []
    for step in plan:
        source = _source_by_sha(course, str(step.get("sha256") or ""))
        moves.append({**step, "notebook_source_id": (source or {}).get("notebook_source_id"), "nlm_title": _nlm_title(source)})
    return {"slug": slug, "drive_folder_id": str(folder), "moves": moves}


def _checkpoint(locked: Any, runner: Callable[..., Any], course_id: str | None):
    """After each final move: rename the NotebookLM source, then record drive_path (the commit point), each journaled."""
    def after_step(step: dict[str, Any], journal: drive_layout.Journal) -> None:
        sha = str(step.get("sha256") or "")
        source = _source_by_sha(locked.payload, sha)
        if source is None or source.get("drive_path") == step["new"]:
            return
        fields = {"file_id": str(step.get("id") or ""), "old": step["old"], "new": step["new"], "sha256": sha, "final": True}
        title = _nlm_title(source)
        if title and source.get("notebook_source_id") and course_id:
            journal.run("nlm_rename", {**fields, "notebook_id": course_id, "notebook_source_id": str(source["notebook_source_id"]),
                                       "nlm_title": title},
                        lambda: runner(["nlm", "source", "rename", str(source["notebook_source_id"]), title, "--notebook", str(course_id)],
                                       check=True, text=True, capture_output=True))
        journal.run("registry", fields, lambda: _set_drive_path(locked, sha, step["new"]))
    return after_step


def drive_reorg(registry: Registry, slugs: list[str], *, apply: bool = False, force: bool = False,
                runner: Callable[..., Any] | None = None) -> list[dict[str, Any]]:
    """Manifest of Drive moves and NotebookLM renames per course; with apply, makes them, journaled by file id.

    Without apply it only lists (one read-only rclone listing per course). With apply, each course is planned and
    moved under its registry lock: the listing is taken twice and must plan the same moves, else nothing moves.
    Refuses while the nightly job runs unless `force`. Journal: REG/logs/drive-reorg-<stamp>-<slug>.jsonl.
    """
    runner = runner or subprocess.run
    if apply and not force and _nightly_running(runner):
        raise drive_layout.ReorgError("the nightly courses job is running; wait for it, or pass --force")
    remote = registry.term.get("drive_remote", "gdrive")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    manifests: list[dict[str, Any]] = []
    for slug in slugs:
        course = registry.courses.get(slug)
        if course is None:
            raise ValueError(f"unknown course: {slug}")
        folder = course.get("drive_folder_id")
        if not folder:
            manifests.append({"slug": slug, "error": "missing drive_folder_id", "moves": []})
            continue
        if not apply:
            manifests.append(_manifest(slug, str(folder), course, drive_layout.plan_reorg(course, _listing(runner, remote, folder))))
            continue
        with _locked_course(registry.directory, slug) as locked:
            plan = drive_layout.plan_reorg(locked.payload, _listing(runner, remote, folder))
            if drive_layout.plan_reorg(locked.payload, _listing(runner, remote, folder)) != plan:
                raise drive_layout.ReorgError(f"{slug}: Drive changed while planning; nothing was moved, rerun")
            manifests.append(_manifest(slug, str(folder), locked.payload, plan))
            log = registry.directory / "logs" / f"drive-reorg-{stamp}-{slug}.jsonl"
            try:
                drive_layout.apply_reorg(plan, remote, str(folder), log, runner=runner, slug=slug,
                                         after_step=_checkpoint(locked, runner, locked.payload.get("notebook_id")))
            finally:
                registry.courses[slug] = locked.payload
    return manifests


def drive_reorg_resume(registry: Registry, journal_path: Path, *, force: bool = False,
                       runner: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Finish a journal's remaining steps, in plan order (not only the one in flight).

    Each Drive step already done is skipped. Each other move is checked by file id: at its new path it is only marked
    done, at its old path it is moved, anywhere else it is reported and left alone. After every final move the
    NotebookLM rename and the registry checkpoint run again unless their done lines exist, so a crash or a failed
    rename past the move still ends with both.
    """
    runner = runner or subprocess.run
    if not force and _nightly_running(runner):
        raise drive_layout.ReorgError("the nightly courses job is running; wait for it, or pass --force")
    lines = drive_layout.read_journal(journal_path)
    if not lines:
        raise drive_layout.ReorgError(f"{journal_path}: empty or missing journal")
    slug, remote, root = str(lines[0]["slug"]), str(lines[0]["remote"]), str(lines[0]["root"])
    steps = drive_layout.plan_steps(lines)
    journal = drive_layout.Journal(journal_path, remote=remote, root=root, slug=slug)
    remaining = [step for _, step in steps if step["op"] in ("move", "rmdir")
                 and not journal.is_done(drive_layout.JOURNAL_KIND[step["op"]], drive_layout._fields(step))]
    done: list[str] = []
    with _locked_course(registry.directory, slug) as locked:
        # The journal must belong to this registry's course: the selected term's course, the same remote and Drive root.
        expected = (str(registry.term.get("drive_remote", "gdrive")), str(locked.payload.get("drive_folder_id") or ""))
        if not locked.payload.get("slug") or (remote, root) != expected:
            raise drive_layout.ReorgError(f"{journal_path}: journal is for {slug} on {remote}:{root}, but the selected "
                                          f"registry has {expected[0]}:{expected[1] or '(no folder)'}; select the right term")
        after_step = _checkpoint(locked, runner, locked.payload.get("notebook_id"))
        try:
            at = {str(item.get("ID")): drive_layout._listed_path(item) for item in _listing(runner, remote, root)}
            for op_id, step in steps:
                if step["op"] not in ("move", "rmdir"):
                    if step.get("final") and step.get("sha256"):
                        after_step(step, journal)
                    continue
                kind, fields = drive_layout.JOURNAL_KIND[step["op"]], drive_layout._fields(step)
                file_id = str(step.get("id") or "")
                if not journal.is_done(kind, fields):
                    if step["op"] == "move":
                        current = at.get(file_id)
                        if current == step["new"]:
                            journal.run(kind, fields, lambda: None, op_id)
                        elif current == step["old"]:
                            if step["new"] in at.values():
                                raise drive_layout.ReorgError(f"{file_id}: {step['new']!r} is occupied, not moving")
                            journal.run(kind, fields, lambda step=step: drive_layout.move_file(remote, root, file_id, step["new"], runner), op_id)
                            at[file_id] = step["new"]
                        else:
                            raise drive_layout.ReorgError(f"{file_id} is at {current!r}, neither {step['old']!r} nor {step['new']!r}; not touching it")
                    elif file_id in at and at[file_id] == step["old"]:
                        journal.run(kind, fields, lambda step=step: drive_layout.rmdir_folder(remote, root, step["old"], runner), op_id)
                    else:
                        journal.run(kind, fields, lambda: None, op_id)
                    done.append(f"{kind} {step['old']} -> {step['new']}")
                if step["op"] == "move" and step.get("final") and step.get("sha256"):
                    after_step(step, journal)
        finally:
            registry.courses[slug] = locked.payload
    return {"slug": slug, "pending": len(remaining), "done": done}


CHORE_KINDS = ("assignment", "forum-post", "perusall-capture", "kotar-source", "missing-text", "manual", "exam", "reading")
BLOCKED_MESSAGE = "lemida: blocked, use chrome watcher"
_BLOCKED_RE = re.compile(r"radware|captcha|bot manager|text/html|<html|expecting value", re.I)


def lemida_blocked(errors: list[Any]) -> bool:
    """True when Lemida errors look like the Radware captcha page (HTML where Moodle JSON was expected)."""
    return any(_BLOCKED_RE.search(json.dumps(e, ensure_ascii=False) if not isinstance(e, str) else e) for e in errors)


def watch_baseline(registry: Registry, slug: str, pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Replace the course's watch_seen with everything on `pages` marked seen (clears a `suspect` course)."""
    import watch_diff as wd
    if slug not in registry.courses:
        raise ValueError(f"unknown course {slug!r}")
    seen = wd.baseline(pages)
    with _locked_course(registry.directory, slug) as locked:
        locked.payload["watch_seen"] = seen
        _atomic_json(locked.path, locked.payload)
        registry.courses[slug] = locked.payload
    return seen


def watch_diff(registry: Registry, slug: str, pages: list[dict[str, Any]], *, apply: bool = False,
               ok_ids: list[str] | None = None) -> tuple[dict[str, Any], list[str]]:
    """Diff Chrome-extracted pages against the course's `watch_seen` (+ legacy `lemida_seen`, sources).

    Seen state advances only with apply=True and only for ok_ids. Returns (diff as dict, ids advanced)."""
    import dataclasses
    import watch_diff as wd
    if slug not in registry.courses:
        raise ValueError(f"unknown course {slug!r}")
    empty = {"modules": {}, "discussions": {}, "assigns": {}, "sections": {}}

    def compute(course: dict[str, Any]):
        seen = course.get("watch_seen") or empty
        diff = wd.diff_course(pages, seen, legacy_seen=dict(course.get("lemida_seen", {})), sources=course.get("sources", []))
        return seen, diff

    if not apply:
        return dataclasses.asdict(compute(registry.courses[slug])[1]), []
    with _locked_course(registry.directory, slug) as locked:
        seen, diff = compute(locked.payload)
        advanced = sorted(set(ok_ids or []))
        locked.payload["watch_seen"] = wd.advance(seen, diff, set(advanced))
        _atomic_json(locked.path, locked.payload)
        registry.courses[slug] = locked.payload
    return dataclasses.asdict(diff), advanced


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--term", help="term directory name (defaults to ACADEMIC_TERM or the sole configured term)")
    parser.add_argument("--data-dir", help="the plugin data folder, where the home pointer lives (defaults to CLAUDE_PLUGIN_DATA)")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="validate all configured live course resources")
    validate.add_argument("--json", action="store_true", help="emit mismatch list as JSON")
    imp = sub.add_parser("import-docx", help="extract schedule rows into course stubs for review")
    imp.add_argument("docx", type=Path)
    imp.add_argument("--out", type=Path, help="directory to write one JSON stub per course")
    imp.add_argument("--dry-run", action="store_true", help="print stubs without writing")
    mapping = sub.add_parser("map", help="map an audio recording to a configured course")
    mapping.add_argument("audio", type=Path)
    mapping.add_argument("--json", action="store_true", help="emit a JSON result")
    lemida_sync_parser = sub.add_parser("lemida-sync", help="sync course resources from Lemida")
    lemida_sync_parser.add_argument("--course", help="limit sync to one course slug")
    lemida_sync_parser.add_argument("--dry-run", action="store_true")
    lemida_sync_parser.add_argument("--json", action="store_true")
    daily_parser = sub.add_parser("daily", help="scan Voice Memos, sync Lemida, and show pending lesson jobs")
    daily_parser.add_argument("--dry-run", action="store_true")
    daily_parser.add_argument("--json", action="store_true", help="emit the run result as JSON")
    ingest = sub.add_parser("ingest", help="upload a lesson recording (or, with --transcript, a text transcript) and save its transcript")
    ingest.add_argument("audio", type=Path)
    ingest.add_argument("--course", help="course slug (otherwise map from recording time)")
    ingest.add_argument("--source-id", help="reuse an existing NotebookLM source")
    ingest.add_argument("--date", help="lesson date (YYYY-MM-DD)")
    ingest.add_argument("--transcript", action="store_true", help="the file is a text transcript (needs --course and --date), not a recording")
    ingest.add_argument("--time", help="lesson start time HHMM (with --transcript; default 0000)")
    ingest.add_argument("--dry-run", action="store_true", help="show the selected course without uploading")
    ingest.add_argument("--json", action="store_true", help="emit a JSON result")
    done = sub.add_parser("lesson-done", help="record the Trove page for a completed lesson")
    done.add_argument("slug")
    done.add_argument("lesson_key")
    done.add_argument("--page", type=int, required=True)
    done.add_argument("--status", choices=["appended", "done"], default="done", help="appended = page written, not yet verified")
    find = sub.add_parser("find-lesson-page", help="print the Trove page whose header carries exactly this lesson key")
    find.add_argument("slug")
    find.add_argument("lesson_key")
    check = sub.add_parser("check-lesson", help="verify a lesson is done and nested under the lessons entry in Trove")
    check.add_argument("slug")
    check.add_argument("date", help="lesson key (YYYY-MM-DD-HHMM) for one lesson, or YYYY-MM-DD for every lesson that day")
    add = sub.add_parser("add-source", help="copy a course file to Drive and NotebookLM and queue its Trove job")
    add.add_argument("file", type=Path)
    add.add_argument("--course", required=True)
    add.add_argument("--title")
    add.add_argument("--origin", choices=ORIGINS, default="other")
    add.add_argument("--origin-ref")
    add.add_argument("--transcript", action="store_true", help="the file is a text lesson transcript (needs --date)")
    add.add_argument("--date", help="lesson date (YYYY-MM-DD) for a recording or transcript")
    add.add_argument("--time", help="lesson start time HHMM (default 0000 when --date is given)")
    add.add_argument("--json", action="store_true")
    sdone = sub.add_parser("source-done", help="record the Trove location of a source")
    sdone.add_argument("slug")
    sdone.add_argument("sha8")
    sdone.add_argument("--trove", required=True, help="<book_id>:<page>")
    csrc = sub.add_parser("check-source", help="verify sources are in Drive, NotebookLM and nested in Trove")
    csrc.add_argument("slug")
    csrc.add_argument("--sha", help="check only the source with this sha prefix")
    reorg = sub.add_parser("drive-reorg", help="move course sources into their kind folders under Chicago names (prints the manifest; moves only with --apply)")
    reorg_scope = reorg.add_mutually_exclusive_group()
    reorg_scope.add_argument("--course", metavar="SLUG")
    reorg_scope.add_argument("--all", action="store_true")
    reorg_scope.add_argument("--resume", type=Path, metavar="JOURNAL", help="finish the unfinished ops of a drive-reorg journal (needs --apply)")
    reorg.add_argument("--apply", action="store_true", help="make the moves and NotebookLM renames (default: manifest only)")
    reorg.add_argument("--force", action="store_true", help="apply even while the nightly courses job is running")
    wdiff = sub.add_parser("watch-diff", help="diff Chrome-extracted Lemida pages against the course's watch state")
    wdiff.add_argument("slug")
    wdiff.add_argument("--pages", type=Path, required=True, help="JSON file: a list of page objects")
    wdiff.add_argument("--baseline", action="store_true", help="mark everything on --pages as seen (clears a suspect course)")
    wdiff.add_argument("--apply", action="store_true", help="advance the seen state (needs --ok)")
    wdiff.add_argument("--ok", nargs="*", default=None, help="ids (cmid / discussion / section) handled successfully")
    lcov = sub.add_parser("lemida-coverage-check", help="exit 1 and print each gap when the nightly Lemida watch did not cover everything")
    lcov.add_argument("--date", help="YYYY-MM-DD of the coverage file (default: today in the term's timezone)")
    lcov.add_argument("--run-id", required=True, help="the run id the nightly job passed to the watch; a report with another run_id is a stale gap")
    lcov.add_argument("--courses", help="space or comma separated slugs to check (default: every active course)")
    lcov.add_argument("--json", action="store_true")
    chores_p = sub.add_parser("chores", help="things Yotam must do by hand (chores.json and its digest)")
    chores_sub = chores_p.add_subparsers(dest="chores_command", required=True)
    reg_parent = argparse.ArgumentParser(add_help=False)
    reg_parent.add_argument("--registry", type=Path, help="registry directory (default: the term directory)")
    cadd = chores_sub.add_parser("add", parents=[reg_parent], help="add a chore, or update the one with the same course/kind/ref")
    cadd.add_argument("--course", required=True)
    cadd.add_argument("--kind", required=True, choices=CHORE_KINDS)
    cadd.add_argument("--ref", required=True, help="stable reference (e.g. cmid or URL) used to dedupe")
    cadd.add_argument("--title", default="")
    cadd.add_argument("--text", default="")
    cadd.add_argument("--core-text", action="append", default=[], dest="core_texts")
    cadd.add_argument("--time-left-text", default="")
    cadd.add_argument("--due-text", default="")
    cadd.add_argument("--due-at", help="ISO 8601 deadline")
    cadd.add_argument("--room", default="", help="exam room")
    cadd.add_argument("--material", default="", help="exam material")
    clist = chores_sub.add_parser("list", parents=[reg_parent], help="list chores as JSON")
    clist.add_argument("--status", choices=["open", "done"])
    clist.add_argument("--course")
    cdone = chores_sub.add_parser("done", parents=[reg_parent], help="mark a chore done")
    cdone.add_argument("id")
    chores_sub.add_parser("digest", parents=[reg_parent], help="write REG/digest/chores.md and chores.json")
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I leaves the script dir off sys.path
    import tasks as tasks_mod
    tasks_mod.add_task_parser(sub)
    mig = sub.add_parser("migrate-tasks", help="add tasks[] and task links from chores, specs and refs (backs up every touched JSON)")
    mig.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    mig.add_argument("--specs-dir", type=Path, help="tools/specs directory (default: courses-tashpaz/tools/specs)")
    wispr_p = sub.add_parser("wispr-scan", help="import lecture recordings from Wispr Flow into the lesson pipeline")
    wispr_p.add_argument("--since", help="only meetings on/after this local date (YYYY-MM-DD)")
    wispr_p.add_argument("--dry-run", action="store_true", help="match only; write and upload nothing")
    wispr_p.add_argument("--json", action="store_true")
    bookmarks_p = sub.add_parser("bookmarks", help="rebuild each course's Chrome bookmark folder (AppleScript; Chrome must be open)")
    bookmarks_p.add_argument("slug", nargs="?", help="one course slug (or use --all)")
    bookmarks_p.add_argument("--all", action="store_true", help="every course in the registry")
    bookmarks_p.add_argument("--print-script", action="store_true", help="print the AppleScript and exit without touching Chrome")
    bookmarks_p.add_argument("--check", action="store_true", help="read-only: exit 1 when applying would change Chrome")
    import dashboard
    dashboard.add_parser(sub)
    import nightly
    nightly.add_parser(sub)
    args = parser.parse_args(argv)
    if args.data_dir:  # skills run this through the Bash tool, which gets no CLAUDE_PLUGIN_DATA
        os.environ["CLAUDE_PLUGIN_DATA"] = args.data_dir
    if args.command == "dashboard":  # before the registry is read: a fresh install shows the empty state
        return dashboard.run(args)
    if args.command == "nightly":  # no registry needed: it manages the schedule
        return nightly.run(args)
    try:
        if args.command == "import-docx":
            stubs = parse_docx(args.docx)
            if args.out and not args.dry_run:
                args.out.mkdir(parents=True, exist_ok=True)
                for i, stub in enumerate(stubs, 1):
                    (args.out / f"course-{i:02d}.json").write_text(json.dumps(stub, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(stubs, ensure_ascii=False, indent=2))
            return 0
        if args.command == "chores" and args.registry:
            registry = Registry(args.registry)
        else:
            registry = registry_from_args(args)
        if args.command == "watch-diff":
            if args.apply and args.ok is None:
                print("error: --apply needs --ok <ids> (seen advances only for ids you name)", file=sys.stderr)
                return 2
            pages = json.loads(args.pages.read_text(encoding="utf-8"))
            if not isinstance(pages, list):
                raise ValueError("--pages must hold a JSON list of pages")
            if args.baseline:
                seen = watch_baseline(registry, args.slug, pages)
                print(json.dumps({"baseline": True, "modules": len(seen["modules"]), "discussions": len(seen["discussions"]),
                                  "assigns": len(seen["assigns"]), "sections": len(seen["sections"])}))
                return 0
            diff, advanced = watch_diff(registry, args.slug, pages, apply=args.apply, ok_ids=args.ok)
            print(json.dumps(diff, ensure_ascii=False, indent=2))
            if args.apply:
                print(f"advanced {len(advanced)} id(s)", file=sys.stderr)
            return 0
        if args.command == "lemida-coverage-check":
            import lemida_coverage
            day = args.date or lemida_coverage.today(registry)
            only = [s for s in (args.courses or "").replace(",", " ").split()] if args.courses is not None else None
            gaps = lemida_coverage.check(registry, day, args.run_id, only=only)
            if args.json:
                print(json.dumps({"date": day, "ok": not gaps, "gaps": gaps}, ensure_ascii=False))
            else:
                for gap in gaps:
                    print(gap)
                if not gaps:
                    print(f"lemida coverage {day}: complete")
            return 1 if gaps else 0
        if args.command == "chores":
            import chores
            if args.chores_command == "add":
                chore = chores.add_chore(registry, course=args.course, kind=args.kind, ref=args.ref, title=args.title, text=args.text,
                                         core_texts=args.core_texts, time_left_text=args.time_left_text, due_text=args.due_text,
                                         due_at=args.due_at, room=args.room, material=args.material)
                print(json.dumps(chore, ensure_ascii=False))
            elif args.chores_command == "list":
                print(json.dumps(chores.list_chores(registry, status=args.status, course=args.course), ensure_ascii=False, indent=2))
            elif args.chores_command == "done":
                print(json.dumps(chores.mark_done(registry, args.id), ensure_ascii=False))
            else:
                print(f"digest: {chores.write_digest(registry)}")
            return 0
        if args.command == "task":
            return tasks_mod.run_task_command(registry.directory, args)
        if args.command == "migrate-tasks":
            print(json.dumps(tasks_mod.migrate(registry.directory, args.specs_dir, dry_run=args.dry_run), ensure_ascii=False, indent=2))
            return 0
        if args.command == "wispr-scan":
            import wispr
            report = wispr.scan(registry, since=args.since, dry_run=args.dry_run)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print(f"wispr-scan: {len(report['matched'])} matched, {len(report['unmatched'])} unmatched, "
                      f"{len(report['skipped'])} already imported, {len(report['errors'])} errors" + (f" ({report['note']})" if report.get("note") else ""))
            return 1 if report["errors"] else 0
        if args.command == "bookmarks":
            import bookmarks
            return bookmarks.run(registry, slug=args.slug, all_courses=args.all, print_script=args.print_script, check_only=args.check)
        if args.command == "find-lesson-page":
            found = find_lesson_page(registry, args.slug, args.lesson_key)
            if found is None:
                print(f"{args.slug}: no page carries lesson key {args.lesson_key}")
                return 3
            print(found)
            return 0
        if args.command == "check-lesson":
            problems = check_lesson(registry, args.slug, args.date)
            for problem in problems:
                print(problem)
            if not problems:
                print(f"{args.slug} {args.date}: lesson done and nested under {LESSONS_ENTRY}")
            return 1 if problems else 0
        if args.command == "add-source":
            result = add_source(registry, args.file, args.course, title=args.title, origin=args.origin, origin_ref=args.origin_ref,
                                transcript=args.transcript, lesson_date=args.date, lesson_time=args.time)
            print(json.dumps(result, ensure_ascii=False) if args.json else f"{result['status']}: {result.get('title', result.get('slug'))}")
            return 0
        if args.command == "source-done":
            print(json.dumps(source_done(registry, args.slug, args.sha8, args.trove), ensure_ascii=False))
            return 0
        if args.command == "drive-reorg":
            if args.resume:
                if not args.apply:
                    parser.error("--resume makes the pending moves; add --apply")
                print(json.dumps(drive_reorg_resume(registry, args.resume, force=args.force), ensure_ascii=False, indent=2))
                return 0
            if not (args.course or args.all):
                parser.error("drive-reorg needs --course, --all or --resume")
            slugs = sorted(registry.active_courses()) if args.all else [args.course]
            print(json.dumps(drive_reorg(registry, slugs, apply=args.apply, force=args.force), ensure_ascii=False, indent=2))
            return 0
        if args.command == "check-source":
            problems = check_source(registry, args.slug, args.sha)
            for problem in problems:
                print(problem)
            if not problems:
                print(f"{args.slug}: all sources verified" if registry.courses.get(args.slug, {}).get("sources") else f"{args.slug}: no sources")
            return 1 if problems else 0
        if args.command == "lesson-done":
            lesson = mark_lesson_done(registry, args.slug, args.lesson_key, args.page, status=args.status)
            print(json.dumps(lesson, ensure_ascii=False))
            return 0
        if args.command in {"lemida-sync", "daily"}:
            import lemida
            with lemida.run_lock(registry):
                if args.command == "lemida-sync":
                    result = lemida.lemida_sync(registry, slug=args.course, dry_run=args.dry_run)
                    if args.json:
                        print(json.dumps(result, ensure_ascii=False))
                    else:
                        for error in result.get("errors", []):
                            print(f"{error['slug']}: {error['error']}", file=sys.stderr)
                    return 2 if result.get("errors") else 0
                def guarded_sync(*a: Any, **k: Any) -> Any:
                    # Voice Memos are already processed by the time daily calls this: a blocked Lemida must not lose them
                    try:
                        return lemida.lemida_sync(*a, **k)
                    except Exception as exc:
                        raise lemida.LemidaError(str(exc)) from exc

                result = lemida.daily(registry, dry_run=args.dry_run, sync=guarded_sync)
                if lemida_blocked(result.get("errors", [])):
                    result["lemida_blocked"] = True
                    result["exit_code"] = 5
                    print(BLOCKED_MESSAGE, file=sys.stderr if args.json else sys.stdout)
                if args.json:
                    print(json.dumps(result, ensure_ascii=False))
                else:
                    print(f"Report: {result['report_md']}" if result.get("report_md") else "Report: (none)")
                    print("Pending queue jobs:")
                    for item in result.get("queue", []):
                        print(item)
                return int(result.get("exit_code", 0))
        if args.command == "map":
            when = recording_time(args.audio, timezone_name=registry.term.get("timezone", "Asia/Jerusalem"))
            slug, reason = map_recording(registry, when)
            if args.json:
                print(json.dumps({"slug": slug, "reason": reason, "when": when.isoformat()}, ensure_ascii=False))
            elif slug:
                print(slug)
            elif reason and reason.startswith("ambiguous:"):
                print(reason)
            else:
                print(f"unmatched: {reason}")
            return 0 if slug else 3
        if args.command == "ingest":
            result = ingest_recording(registry, args.audio, course_slug=args.course, source_id=args.source_id, lesson_date=args.date, dry_run=args.dry_run, transcript_file=args.transcript, lesson_time=args.time)
            if args.json:
                print(json.dumps(result, ensure_ascii=False))
            elif result["status"] == "already ingested":
                print(f"already ingested: {result['slug']} {result['date']}")
            else:
                print(json.dumps(result, ensure_ascii=False))
            return 0
        problems = validate_registry(registry)
        if args.json:
            print(json.dumps({"valid": not problems, "mismatches": problems}, ensure_ascii=False))
        else:
            for problem in problems:
                print(problem)
            if not problems:
                print(f"Validated {len(registry.courses)} courses")
        return 1 if problems else 0
    except IngestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError, zipfile.BadZipFile, ET.ParseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
