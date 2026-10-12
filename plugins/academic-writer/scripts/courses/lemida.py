"""Offline-testable Moodle/Lemida synchronization and daily scan helpers."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import courses


class LemidaError(RuntimeError):
    pass


def _redact(value: Any) -> str:
    text = str(value)
    return re.sub(r"([?&](?:wstoken|token)=)[^&\s]+", r"\1[REDACTED]", text, flags=re.I)


def classify_module(module: dict[str, Any]) -> str:
    name = str(module.get("modname", "")).lower()
    if name in {"videostream", "kalvidres", "recording"}:
        return "recording"
    contents = module.get("contents", []) or []
    if any(str(item.get("mimetype", "")).lower().startswith(("audio/", "video/")) for item in contents):
        return "recording"
    if name in {"resource", "folder"}:
        return "resource"
    if name in {"url", "zoom", "forum", "lti", "page", "assign", "quiz"}:
        return "report-only"
    return "report-only"


def changed_modules(modules: list[dict[str, Any]], seen: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for module in modules:
        cmid = str(module.get("id", module.get("cmid", "")))
        if not cmid:
            continue
        previous = seen.get(cmid)
        current = max((int(c.get("timemodified", 0) or 0) for c in module.get("contents", []) or []), default=0)
        if previous is None or current > int(previous or 0):
            result.append(module)
    return result


def _flatten_modules(contents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Accept Moodle's section list and the older flat module-list shape."""
    flattened: list[dict[str, Any]] = []
    for item in contents:
        if isinstance(item.get("modules"), list):
            flattened.extend(module for module in item["modules"] if isinstance(module, dict))
        elif "id" in item or "cmid" in item:
            flattened.append(item)
    return flattened


def moodle_course_contents(base_url: str, token: str, course_id: Any, *, opener: Callable[..., Any] = urllib.request.urlopen) -> list[dict[str, Any]]:
    url = base_url.rstrip("/") + "/webservice/rest/server.php"
    body = urllib.parse.urlencode({"wstoken": token, "wsfunction": "core_course_get_contents", "courseid": str(course_id), "moodlewsrestformat": "json"}).encode()
    request = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with opener(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise LemidaError(f"Moodle request failed: {_redact(exc)}") from exc
    if isinstance(payload, dict) and payload.get("exception"):
        raise LemidaError(f"Moodle error {payload.get('errorcode', '')}: {_redact(payload.get('message', 'request failed'))}")
    if not isinstance(payload, list):
        raise LemidaError("Moodle returned an unexpected course contents response")
    return payload


def download_file(url: str, token: str, destination: Path, *, opener: Callable[..., Any] = urllib.request.urlopen) -> Path:
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if k.lower() != "token"]
    query.append(("token", token))
    authorized = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with opener(authorized, timeout=60) as response:
            with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False) as output:
                temporary = Path(output.name)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        os.replace(temporary, destination)
    except Exception as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise LemidaError(f"download failed: {_redact(exc)}") from exc
    return destination


def _token(term: dict[str, Any], runner: Callable[..., Any]) -> str:
    config = term.get("lemida", {})
    command = ["security", "find-generic-password", "-s", str(config.get("keychain_service", "academic-writer-lemida")), "-w"]
    if config.get("keychain_account"):
        command += ["-a", str(config["keychain_account"])]
    try:
        result = runner(command, check=True, text=True, capture_output=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise LemidaError("Lemida token missing; create it with: security add-generic-password -s academic-writer-lemida -a <user> -w") from exc
    token = result.stdout.strip()
    if not token:
        raise LemidaError("Lemida token missing; create it with: security add-generic-password -s academic-writer-lemida -a <user> -w")
    return token


def _module_time(module: dict[str, Any]) -> int:
    return max((int(x.get("timemodified", 0) or 0) for x in module.get("contents", []) or []), default=0)


def sync_course(registry: courses.Registry, slug: str, *, runner: Callable[..., Any] = subprocess.run,
                fetch_contents: Callable[..., Any] | None = None, download: Callable[..., Any] = download_file,
                ingest: Callable[..., Any] | None = None, dry_run: bool = False, report_date: str | None = None) -> dict[str, Any]:
    course = registry.courses[slug]
    if not course.get("lemida_course_id"):
        return {"slug": slug, "status": "skipped", "reason": "missing lemida_course_id", "processed": []}
    config = registry.term.get("lemida", {})
    token = _token(registry.term, runner)
    if fetch_contents is None:
        fetch_contents = lambda base_url, auth, cid: moodle_course_contents(base_url, auth, cid)
    modules = _flatten_modules(fetch_contents(config.get("base_url", ""), token, course["lemida_course_id"]))
    seen = dict(course.get("lemida_seen", {}))
    changed = changed_modules(modules, seen)
    root = Path(registry.term.get("local_root", registry.directory / "files")).expanduser()
    drive_remote = registry.term.get("drive_remote", "gdrive")
    processed = []
    if ingest is None:
        ingest = courses.ingest_recording
    for module in changed:
        kind = classify_module(module)
        title = str(module.get("name", module.get("id", "(unnamed)")))
        cmid = str(module.get("id", module.get("cmid", "")))
        stamp = _module_time(module)
        try:
            if kind in {"resource", "recording"}:
                for content in module.get("contents", []) or []:
                    fileurl = content.get("fileurl")
                    if not fileurl:
                        continue
                    filename = Path(urllib.parse.urlsplit(str(fileurl)).path).name or title
                    target = root / slug / "lemida" / filename
                    if not dry_run:
                        download(str(fileurl), token, target)
                        if kind == "recording":
                            local_day = datetime.fromtimestamp(stamp, timezone.utc).astimezone().date().isoformat()
                            ingest(registry, target, course_slug=slug, lesson_date=local_day, runner=runner)
                        else:
                            runner(["rclone", "copy", str(target), f"{drive_remote}:", "--drive-root-folder-id", str(course.get("drive_folder_id", ""))], check=True, text=True, capture_output=True)
            processed.append({"cmid": cmid, "name": title, "type": kind, "timemodified": stamp})
        except Exception as exc:
            raise LemidaError(f"{slug} module {cmid} ({title}) failed: {_redact(exc)}") from exc
        if not dry_run:
            with courses._locked_course(registry.directory, slug) as locked:
                locked.payload.setdefault("lemida_seen", {})[cmid] = stamp
                courses._atomic_json(locked.path, locked.payload)
            seen[cmid] = stamp
    return {"slug": slug, "status": "dry-run" if dry_run else "synced", "processed": processed}


def _write_report(registry: courses.Registry, day: str, report: dict[str, Any]) -> None:
    courses._atomic_json(registry.directory / "logs" / f"lemida-{day}.json", report)


def lemida_sync(registry: courses.Registry, *, slug: str | None = None, dry_run: bool = False,
                runner: Callable[..., Any] = subprocess.run, fetch_contents: Callable[..., Any] | None = None,
                download: Callable[..., Any] = download_file, ingest: Callable[..., Any] | None = None,
                report_date: str | None = None) -> dict[str, Any]:
    day = report_date or date.today().isoformat()
    targets = [slug] if slug else [key for key, value in registry.courses.items() if value.get("lemida_course_id")]
    report: dict[str, Any] = {"date": day, "courses": [], "errors": []}
    for target in targets:
        try:
            report["courses"].append(sync_course(registry, target, runner=runner, fetch_contents=fetch_contents, download=download, ingest=ingest, dry_run=dry_run, report_date=day))
        except LemidaError as exc:
            report["errors"].append({"slug": target, "error": str(exc)})
    _write_report(registry, day, report)
    return report


def _queue(registry: courses.Registry) -> list[str]:
    path = registry.directory / "queue"
    return sorted(str(p) for p in path.glob("*.json")) if path.exists() else []


def daily(registry: courses.Registry, *, dry_run: bool = False, runner: Callable[..., Any] = subprocess.run,
          ingest: Callable[..., Any] | None = None, report_date: str | None = None,
          sync: Callable[..., Any] | None = None) -> dict[str, Any]:
    day = report_date or date.today().isoformat()
    term_path = registry.directory / "term.json"
    term = json.loads(term_path.read_text(encoding="utf-8"))
    state = term.setdefault("state", {})
    last = state.get("last_voice_memo_scan") or term.get("semesters", {}).get("A", {}).get("start") or "1970-01-01"
    term_tz = ZoneInfo(term.get("timezone", "Asia/Jerusalem"))
    boundary = datetime.fromisoformat(str(last))
    if boundary.tzinfo is None:
        boundary = boundary.replace(tzinfo=term_tz)
    else:
        boundary = boundary.astimezone(term_tz)
    memo_dir = Path(term.get("voice_memos_dir", "~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings")).expanduser()
    scan = {"processed": [], "unmatched": [], "errors": []}
    completed = True
    if memo_dir.exists():
        for audio in sorted(memo_dir.glob("*.m4a")):
            try:
                when = courses.recording_time(audio, timezone_name=term.get("timezone", "Asia/Jerusalem"))
                if when.astimezone(term_tz) <= boundary:
                    continue
                slug, reason = courses.map_recording(registry, when)
                if not slug:
                    scan["unmatched"].append({"file": audio.name, "reason": reason})
                    continue
                if not dry_run:
                    result = (ingest or courses.ingest_recording)(registry, audio, course_slug=slug, lesson_date=when.date().isoformat(), runner=runner)
                    scan["processed"].append({"file": audio.name, "result": result})
            except Exception as exc:
                completed = False
                scan["errors"].append({"file": audio.name, "error": _redact(exc)})
    else:
        scan["errors"].append({"error": f"Voice Memos directory not found: {memo_dir}"})
        completed = False
    if completed and not dry_run:
        state["last_voice_memo_scan"] = datetime.now().astimezone().isoformat()
        courses._atomic_json(term_path, term)
    report: dict[str, Any] = {"date": day, "voice_memos": scan, "lemida": None, "queue": _queue(registry), "errors": []}
    if sync is None:
        sync = lemida_sync
    try:
        report["lemida"] = sync(registry, dry_run=dry_run, runner=runner, ingest=ingest, report_date=day)
        sync_errors = report["lemida"].get("errors", []) if isinstance(report["lemida"], dict) else []
        if sync_errors:
            report["errors"].extend(item.get("error", str(item)) if isinstance(item, dict) else str(item) for item in sync_errors)
            report["exit_code"] = 5 if any("token missing" in str(item).lower() for item in sync_errors) else 2
    except LemidaError as exc:
        report["errors"].append(str(exc))
        report["exit_code"] = 5 if "token missing" in str(exc).lower() else 2
    if not completed:
        report["exit_code"] = 1
    _write_report(registry, day, report)
    return report
