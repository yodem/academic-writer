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
import subprocess
import sys
import tempfile
from datetime import date, datetime, time, timedelta, timezone
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CODE_RE = re.compile(r"(?<!\d)(?:\d{6}(?:-\d{2})?|\d{5}(?:-\d{2})?|\d{2}-\d{3}-\d{2})(?!\d)")


def normalise_name(value: str) -> str:
    """Collapse whitespace and treat Hebrew quote variants consistently."""
    value = unicodedata.normalize("NFC", value)
    value = value.replace("״", '"').replace("׳", "'")
    return " ".join(value.split())


def _term_dir(root: Path, term: str | None = None) -> Path:
    if term is None:
        term = os.environ.get("ACADEMIC_TERM")
    if term:
        return root / term
    dirs = sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []
    if len(dirs) == 1:
        return dirs[0]
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
            slug = course.get("slug", path.stem)
            self.courses[slug] = course


def registry_from_args(args: argparse.Namespace) -> Registry:
    root = Path(os.environ.get("ACADEMIC_COURSES_DIR", "~/.academic-writer/courses")).expanduser()
    return Registry(_term_dir(root, args.term))


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
    for slug, course in registry.courses.items():
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
) -> dict[str, Any]:
    """Upload audio to NotebookLM and persist a resumable lesson record."""
    audio = Path(audio).expanduser()
    if not audio.is_file():
        raise IngestError(f"audio file not found: {audio}")
    timezone_name = registry.term.get("timezone", "Asia/Jerusalem")
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
    hm = "0000" if lesson_date else when.strftime("%H%M")
    lesson_base = f"{day}-{hm}"
    lessons_root = registry.directory / "lessons" / slug
    lessons_root.mkdir(parents=True, exist_ok=True)
    with _locked_course(registry.directory, slug) as locked:
        stored_course = locked.payload
        matching = next((x for x in stored_course.get("lessons", []) if x.get("audio_sha256") == digest), None)
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
        if audio.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
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
                lessons.append({"date": day, "lesson_key": lesson_key, "audio_sha256": digest, "source_id": selected_source, "trove_page": None, "status": "pending_transcript"})
                stored_course["lessons"] = lessons
                _atomic_json(locked.path, stored_course)
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
    meta.update({"weekday": weekday, "transcript_words": len(transcript.split()), "created_at": datetime.now(ZoneInfo(timezone_name)).isoformat(), "status": "queued"})
    _atomic_json(meta_path, meta)
    queue_path = registry.directory / "queue" / f"{slug}-{lesson_key}.json"
    _atomic_json(queue_path, {"slug": slug, "date": day, "lesson_key": lesson_key, "transcript_path": str(transcript_path), "meta_path": str(meta_path), "manuscript_id": course.get("manuscript_id"), "book_id": course.get("book_id"), "course_name": course.get("name"), "lecturer": course.get("lecturer")})
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
        manuscripts = _as_list(_json_from_command(["trove", "ms", "list", "--json", "--no-session"], runner), "manuscripts", "items")
    except Exception as exc:
        return [f"Trove lookup failed: {exc}"]
    notebook_by_id = {str(x.get("id")): x for x in notebooks}
    manuscript_by_id = {str(x.get("id")): x for x in manuscripts}

    drive_cache: dict[str, list[dict[str, Any]] | Exception] = {}
    remote = registry.term.get("drive_remote", "gdrive")
    subject_map = registry.term.get("drive_subject_folders", {})
    naming = registry.term.get("naming", {})
    for slug, course in registry.courses.items():
        context = {**course, "term": registry.term.get("term", "")}
        try:
            expected = {
                key: naming.get(key, "{name}").format_map(context)
                for key in ("drive", "notebook", "manuscript")
            }
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            problems.append(f"{slug}: naming template error: {exc}")
            continue
        for key in ("drive_folder_id", "notebook_id", "manuscript_id"):
            if not course.get(key):
                problems.append(f"{slug}: missing {key}")
        notebook_id = course.get("notebook_id")
        if notebook_id:
            obj = notebook_by_id.get(str(notebook_id))
            if obj is None:
                problems.append(f"{slug}: NotebookLM notebook {notebook_id} not found")
            elif normalise_name(str(obj.get("title", ""))) != normalise_name(expected["notebook"]):
                problems.append(f"{slug}: NotebookLM name mismatch (expected {expected['notebook']!r}, got {obj.get('title')!r})")
        manuscript_id = course.get("manuscript_id")
        if manuscript_id:
            obj = manuscript_by_id.get(str(manuscript_id))
            if obj is None:
                problems.append(f"{slug}: Trove manuscript {manuscript_id} not found")
            elif normalise_name(str(obj.get("title", ""))) != normalise_name(expected["manuscript"]):
                problems.append(f"{slug}: Trove name mismatch (expected {expected['manuscript']!r}, got {obj.get('title')!r})")
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
    parent_index = next((i for i, entry in enumerate(toc) if normalise_name(str(entry.get("title", ""))) == LESSONS_ENTRY and entry.get("level") == 1), None)
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
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--term", help="term directory name (defaults to ACADEMIC_TERM or the sole configured term)")
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
    ingest = sub.add_parser("ingest", help="upload a lesson recording and save its NotebookLM transcript")
    ingest.add_argument("audio", type=Path)
    ingest.add_argument("--course", help="course slug (otherwise map from recording time)")
    ingest.add_argument("--source-id", help="reuse an existing NotebookLM source")
    ingest.add_argument("--date", help="lesson date (YYYY-MM-DD)")
    ingest.add_argument("--dry-run", action="store_true", help="show the selected course without uploading")
    ingest.add_argument("--json", action="store_true", help="emit a JSON result")
    done = sub.add_parser("lesson-done", help="record the Trove page for a completed lesson")
    done.add_argument("slug")
    done.add_argument("lesson_key")
    done.add_argument("--page", type=int, required=True)
    done.add_argument("--status", choices=["appended", "done"], default="done", help="appended = page written, not yet verified")
    check = sub.add_parser("check-lesson", help="verify a lesson is done and nested under the lessons entry in Trove")
    check.add_argument("slug")
    check.add_argument("date", help="lesson key (YYYY-MM-DD-HHMM) for one lesson, or YYYY-MM-DD for every lesson that day")
    args = parser.parse_args(argv)
    try:
        if args.command == "import-docx":
            stubs = parse_docx(args.docx)
            if args.out and not args.dry_run:
                args.out.mkdir(parents=True, exist_ok=True)
                for i, stub in enumerate(stubs, 1):
                    (args.out / f"course-{i:02d}.json").write_text(json.dumps(stub, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(stubs, ensure_ascii=False, indent=2))
            return 0
        registry = registry_from_args(args)
        if args.command == "check-lesson":
            problems = check_lesson(registry, args.slug, args.date)
            for problem in problems:
                print(problem)
            if not problems:
                print(f"{args.slug} {args.date}: lesson done and nested under {LESSONS_ENTRY}")
            return 1 if problems else 0
        if args.command == "lesson-done":
            lesson = mark_lesson_done(registry, args.slug, args.lesson_key, args.page, status=args.status)
            print(json.dumps(lesson, ensure_ascii=False))
            return 0
        if args.command in {"lemida-sync", "daily"}:
            import lemida
            if args.command == "lemida-sync":
                result = lemida.lemida_sync(registry, slug=args.course, dry_run=args.dry_run)
                if args.json:
                    print(json.dumps(result, ensure_ascii=False))
                else:
                    for error in result.get("errors", []):
                        print(f"{error['slug']}: {error['error']}", file=sys.stderr)
                return 2 if result.get("errors") else 0
            result = lemida.daily(registry, dry_run=args.dry_run)
            if args.json:
                print(json.dumps(result, ensure_ascii=False))
            else:
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
            result = ingest_recording(registry, args.audio, course_slug=args.course, source_id=args.source_id, lesson_date=args.date, dry_run=args.dry_run)
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
