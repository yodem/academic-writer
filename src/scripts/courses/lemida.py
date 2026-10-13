"""Offline-testable Moodle/Lemida synchronization and daily scan helpers."""
from __future__ import annotations

import html
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


POSTS_FORMAT = 2


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


def moodle_call(base_url: str, token: str, function: str, params: dict[str, Any] | None = None, *,
                opener: Callable[..., Any] = urllib.request.urlopen) -> Any:
    """Call one Moodle web-service function and return its decoded JSON."""
    url = base_url.rstrip("/") + "/webservice/rest/server.php"
    fields = {"wstoken": token, "wsfunction": function, "moodlewsrestformat": "json"}
    fields.update({key: str(value) for key, value in (params or {}).items()})
    body = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with opener(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise LemidaError(f"Moodle request failed: {_redact(exc)}") from exc
    if isinstance(payload, dict) and payload.get("exception"):
        raise LemidaError(f"Moodle error {payload.get('errorcode', '')}: {_redact(payload.get('message', 'request failed'))}")
    return payload


def moodle_course_contents(base_url: str, token: str, course_id: Any, *, opener: Callable[..., Any] = urllib.request.urlopen) -> list[dict[str, Any]]:
    payload = moodle_call(base_url, token, "core_course_get_contents", {"courseid": course_id}, opener=opener)
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


def _plain_excerpt(message: Any, limit: int = 300) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", str(message or ""))
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[\\/\x00-\x1f]", "_", str(name)).strip().lstrip(".")
    return cleaned or "file"


def _iso(stamp: Any) -> str:
    try:
        return datetime.fromtimestamp(int(stamp), timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _author(post: dict[str, Any]) -> str:
    author = post.get("author")
    if isinstance(author, dict) and author.get("fullname"):
        return str(author["fullname"])
    return str(post.get("userfullname") or post.get("authorfullname") or "")


def _default_api(base_url: str, token: str, function: str, params: dict[str, Any]) -> Any:
    return moodle_call(base_url, token, function, params)


def _sync_forums(registry: courses.Registry, slug: str, course: dict[str, Any], *, base_url: str, token: str, api: Callable[..., Any],
                 download: Callable[..., Any], add_source: Callable[..., Any], runner: Callable[..., Any], root: Path,
                 dry_run: bool, announcements: list[dict[str, Any]], errors: list[str]) -> None:
    try:
        forums = api(base_url, token, "mod_forum_get_forums_by_courses", {"courseids[0]": course["lemida_course_id"]})
        if not isinstance(forums, list):
            raise LemidaError("unexpected forums response")
    except Exception as exc:
        errors.append(f"{slug} forums failed: {_redact(exc)}")
        return
    modern = course.get("lemida_posts_format") == POSTS_FORMAT
    seen_posts = {str(k): int(v or 0) for k, v in dict(course.get("lemida_seen_posts", {})).items()}
    seen_discussions = {str(k): int(v or 0) for k, v in dict(course.get("lemida_seen_discussions", {})).items()}
    for forum in forums:
        forum_name = str(forum.get("name", forum.get("id", "")))
        try:
            listing = api(base_url, token, "mod_forum_get_forum_discussions",
                          {"forumid": forum["id"], "sortorder": -1, "page": 0, "perpage": 50})
            discussions = listing.get("discussions", []) if isinstance(listing, dict) else []
        except Exception as exc:
            errors.append(f"{slug} forum {forum_name} failed: {_redact(exc)}")
            continue
        if not modern:
            # the pre-per-post format keyed this map by discussion id: those keys are not post ids
            for discussion in discussions:
                seen_posts.pop(str(discussion.get("discussion", discussion.get("id", ""))), None)
        for discussion in discussions:
            did = str(discussion.get("discussion", discussion.get("id", "")))
            stamp = int(discussion.get("timemodified", 0) or 0)
            newest = seen_discussions.get(did, seen_posts.get(str(discussion.get("id", "")), None))
            if not did or (newest is not None and stamp <= newest):
                continue
            try:
                payload = api(base_url, token, "mod_forum_get_discussion_posts", {"discussionid": did})
                posts = payload.get("posts", []) if isinstance(payload, dict) else []
            except Exception as exc:
                errors.append(f"{slug} forum discussion {did} failed: {_redact(exc)}")
                continue
            discussion_failed = False
            newest_post = 0
            for post in posts:
                pid = str(post.get("id", ""))
                post_time = int(post.get("timemodified", 0) or post.get("timecreated", 0) or 0)
                newest_post = max(newest_post, post_time)
                if not pid or (pid in seen_posts and post_time <= seen_posts[pid]):
                    continue
                failed = False
                attachments = []
                for item in post.get("attachments", []) or []:
                    name = _safe_name(item.get("filename", ""))
                    record = {"filename": name, "mimetype": item.get("mimetype", "")}
                    try:
                        if dry_run:
                            record["result"] = "dry-run"
                        else:
                            with tempfile.TemporaryDirectory(prefix="lemida-") as scratch:
                                target = Path(scratch) / f"lemida-forum-{did} - {name}"
                                download(str(item.get("fileurl", "")), token, target)
                                result = add_source(registry, target, slug, title=None, origin="lemida", origin_ref=f"forum:{did}", runner=runner)
                            record["result"] = result.get("status", "added") if isinstance(result, dict) else "added"
                            if isinstance(result, dict) and result.get("file"):
                                record["file"] = str(result["file"])
                    except Exception as exc:
                        failed = True
                        record["result"] = "error"
                        record["error"] = _redact(exc)
                        errors.append(f"{slug} forum {did} attachment {name} failed: {_redact(exc)}")
                    attachments.append(record)
                announcements.append({
                    "course": slug, "forum": forum_name, "discussion_id": did, "post_id": pid,
                    "subject": str(post.get("subject") or discussion.get("name") or ""),
                    "author": _author(post) or str(discussion.get("userfullname", "")),
                    "created": _iso(post.get("timecreated")), "timecreated": int(post.get("timecreated", 0) or 0),
                    "excerpt": _plain_excerpt(post.get("message")), "attachments": attachments,
                })
                if failed:
                    discussion_failed = True
                elif not dry_run:
                    with courses._locked_course(registry.directory, slug) as locked:
                        _mark_modern(locked.payload, discussions)
                        locked.payload.setdefault("lemida_seen_posts", {})[pid] = post_time
                        courses._atomic_json(locked.path, locked.payload)
                    seen_posts[pid] = post_time
                    modern = True
            if not discussion_failed and not dry_run and posts:
                with courses._locked_course(registry.directory, slug) as locked:
                    _mark_modern(locked.payload, discussions)
                    locked.payload.setdefault("lemida_seen_discussions", {})[did] = newest_post
                    courses._atomic_json(locked.path, locked.payload)
                seen_discussions[did] = newest_post
                modern = True


def _mark_modern(payload: dict[str, Any], discussions: list[dict[str, Any]]) -> None:
    """Switch a course to the per-post format, dropping legacy discussion-keyed entries."""
    if payload.get("lemida_posts_format") == POSTS_FORMAT:
        return
    legacy = {str(d.get("discussion", d.get("id", ""))) for d in discussions}
    payload["lemida_seen_posts"] = {k: v for k, v in dict(payload.get("lemida_seen_posts", {})).items() if str(k) not in legacy}
    payload["lemida_posts_format"] = POSTS_FORMAT


def sync_course(registry: courses.Registry, slug: str, *, runner: Callable[..., Any] = subprocess.run,
                fetch_contents: Callable[..., Any] | None = None, download: Callable[..., Any] = download_file,
                ingest: Callable[..., Any] | None = None, dry_run: bool = False, report_date: str | None = None,
                api: Callable[..., Any] | None = None, add_source: Callable[..., Any] | None = None) -> dict[str, Any]:
    course = registry.courses[slug]
    if not course.get("lemida_course_id"):
        return {"slug": slug, "status": "skipped", "reason": "missing lemida_course_id", "processed": [], "announcements": [], "errors": []}
    config = registry.term.get("lemida", {})
    base_url = config.get("base_url", "")
    token = _token(registry.term, runner)
    api = api or _default_api
    add_source = add_source or courses.add_source
    if fetch_contents is None:
        fetch_contents = lambda url, auth, cid: moodle_course_contents(url, auth, cid)
    errors: list[str] = []
    announcements: list[dict[str, Any]] = []
    processed: list[dict[str, Any]] = []
    root = Path(registry.term.get("local_root", registry.directory / "files")).expanduser()
    if ingest is None:
        ingest = courses.ingest_recording
    try:
        modules = _flatten_modules(fetch_contents(base_url, token, course["lemida_course_id"]))
    except Exception as exc:
        errors.append(f"{slug} contents failed: {_redact(exc)}")
        modules = []
    changed = changed_modules(modules, dict(course.get("lemida_seen", {})))
    for module in changed:
        kind = classify_module(module)
        title = str(module.get("name", module.get("id", "(unnamed)")))
        cmid = str(module.get("id", module.get("cmid", "")))
        stamp = _module_time(module)
        try:
            outcomes = []
            if kind in {"resource", "recording"}:
                for content in module.get("contents", []) or []:
                    fileurl = content.get("fileurl")
                    if not fileurl:
                        continue
                    filename = _safe_name(Path(urllib.parse.urlsplit(str(fileurl)).path).name or title)
                    if dry_run:
                        continue
                    if kind == "recording":
                        target = root / slug / "lemida" / filename
                        download(str(fileurl), token, target)
                        local_day = datetime.fromtimestamp(stamp, timezone.utc).astimezone().date().isoformat()
                        ingest(registry, target, course_slug=slug, lesson_date=local_day, runner=runner)
                        outcomes.append({"filename": filename, "result": "ingested"})
                    else:
                        with tempfile.TemporaryDirectory(prefix="lemida-") as scratch:
                            target = Path(scratch) / f"lemida-cm{cmid} - {filename}"
                            download(str(fileurl), token, target)
                            result = add_source(registry, target, slug, title=None, origin="lemida", origin_ref=f"cm:{cmid}", runner=runner)
                        outcomes.append({"filename": filename, "result": result.get("status", "added") if isinstance(result, dict) else "added"})
            entry = {"cmid": cmid, "name": title, "type": kind, "timemodified": stamp}
            if outcomes:
                entry["files"] = outcomes
            processed.append(entry)
        except Exception as exc:
            errors.append(f"{slug} module {cmid} ({title}) failed: {_redact(exc)}")
            continue
        if not dry_run:
            with courses._locked_course(registry.directory, slug) as locked:
                locked.payload.setdefault("lemida_seen", {})[cmid] = stamp
                courses._atomic_json(locked.path, locked.payload)
    # forums read the freshly written course JSON so seen-state merges correctly
    fresh = dict(course)
    try:
        fresh.update(json.loads((registry.directory / f"{slug}.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    _sync_forums(registry, slug, fresh, base_url=base_url, token=token, api=api, download=download, add_source=add_source,
                 runner=runner, root=root, dry_run=dry_run, announcements=announcements, errors=errors)
    return {"slug": slug, "status": "dry-run" if dry_run else "synced", "processed": processed, "announcements": announcements, "errors": errors}


def sync_notifications(registry: courses.Registry, *, runner: Callable[..., Any] = subprocess.run, api: Callable[..., Any] | None = None,
                       dry_run: bool = False) -> list[dict[str, Any]]:
    """Return the user's Lemida notifications newer than term.json state.last_notification_time."""
    config = registry.term.get("lemida", {})
    base_url = config.get("base_url", "")
    token = _token(registry.term, runner)
    api = api or _default_api
    info = api(base_url, token, "core_webservice_get_site_info", {})
    user_id = info.get("userid") if isinstance(info, dict) else None
    if user_id is None:
        raise LemidaError("could not determine the Lemida user id")
    term_path = registry.directory / "term.json"
    term = json.loads(term_path.read_text(encoding="utf-8"))
    last = int(term.get("state", {}).get("last_notification_time", 0) or 0)
    payload = api(base_url, token, "message_popup_get_popup_notifications", {"useridto": user_id, "newestfirst": 1, "limit": 50, "offset": 0})
    items = payload.get("notifications", []) if isinstance(payload, dict) else []
    fresh = []
    for item in items:
        created = int(item.get("timecreated", 0) or 0)
        if created <= last:
            continue
        fresh.append({
            "subject": str(item.get("subject") or item.get("shortenedsubject") or ""),
            "contexturl": str(item.get("contexturl") or ""), "timecreated": created,
            "created": _iso(created), "read": bool(item.get("read")),
        })
    if fresh and not dry_run:
        latest = json.loads(term_path.read_text(encoding="utf-8"))
        latest.setdefault("state", {})["last_notification_time"] = max(n["timecreated"] for n in fresh)
        courses._atomic_json(term_path, latest)
    return fresh


def _write_report(registry: courses.Registry, day: str, report: dict[str, Any]) -> None:
    courses._atomic_json(registry.directory / "logs" / f"lemida-{day}.json", report)


def report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# דוח למידה {report.get('date', '')}", ""]
    lines += ["## הודעות חדשות בקורסים", ""]
    announcements = report.get("announcements", []) or []
    if not announcements:
        lines += ["אין הודעות חדשות.", ""]
    for slug in sorted({a.get("course", "") for a in announcements}):
        lines += [f"### {slug}", ""]
        for item in (a for a in announcements if a.get("course") == slug):
            lines.append(f"- **{item.get('subject', '')}** ({item.get('author', '')}, {item.get('created', '')[:10]})")
            if item.get("excerpt"):
                lines.append(f"  - {item['excerpt']}")
            for att in item.get("attachments", []):
                where = att.get("file") or att.get("error") or att.get("result", "")
                lines.append(f"  - קובץ: {att.get('filename', '')} -> {att.get('result', '')} ({where})")
        lines.append("")
    lines += ["## התראות חדשות", ""]
    notes = report.get("notifications", []) or []
    if not notes:
        lines += ["אין התראות חדשות.", ""]
    for note in notes:
        flag = "נקרא" if note.get("read") else "לא נקרא"
        lines.append(f"- {note.get('subject', '')} ({note.get('created', '')[:10]}, {flag}) {note.get('contexturl', '')}".rstrip())
    lines.append("")
    lines += ["## תוכן חדש", ""]
    any_content = False
    for entry in report.get("courses", []) or []:
        for module in entry.get("processed", []):
            any_content = True
            files = ", ".join(f"{f['filename']} ({f['result']})" for f in module.get("files", []))
            lines.append(f"- {entry.get('slug', '')}: {module.get('name', '')} [{module.get('type', '')}]" + (f" - {files}" if files else ""))
    if not any_content:
        lines.append("אין תוכן חדש.")
    lines += ["", "## שגיאות", ""]
    errors = report.get("errors", []) or []
    if not errors:
        lines.append("אין שגיאות.")
    for err in errors:
        lines.append(f"- {err.get('slug', '') + ': ' if isinstance(err, dict) and err.get('slug') else ''}{err.get('error', err) if isinstance(err, dict) else err}")
    return "\n".join(lines) + "\n"


def _write_markdown(registry: courses.Registry, day: str, report: dict[str, Any]) -> Path:
    path = registry.directory / "logs" / f"lemida-{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report_markdown(report), encoding="utf-8")
    return path


def lemida_sync(registry: courses.Registry, *, slug: str | None = None, dry_run: bool = False,
                runner: Callable[..., Any] = subprocess.run, fetch_contents: Callable[..., Any] | None = None,
                download: Callable[..., Any] = download_file, ingest: Callable[..., Any] | None = None,
                report_date: str | None = None, api: Callable[..., Any] | None = None,
                add_source: Callable[..., Any] | None = None) -> dict[str, Any]:
    day = report_date or date.today().isoformat()
    targets = [slug] if slug else [key for key, value in registry.courses.items() if value.get("lemida_course_id")]
    report: dict[str, Any] = {"date": day, "courses": [], "announcements": [], "notifications": [], "errors": []}
    for target in targets:
        try:
            result = sync_course(registry, target, runner=runner, fetch_contents=fetch_contents, download=download, ingest=ingest,
                                 dry_run=dry_run, report_date=day, api=api, add_source=add_source)
            report["courses"].append(result)
            report["announcements"].extend(result.get("announcements", []))
            report["errors"].extend({"slug": target, "error": message} for message in result.get("errors", []))
        except LemidaError as exc:
            report["errors"].append({"slug": target, "error": str(exc)})
    if targets:
        try:
            report["notifications"] = sync_notifications(registry, runner=runner, api=api, dry_run=dry_run)
        except Exception as exc:
            report["errors"].append({"slug": "(notifications)", "error": _redact(exc)})
    _write_report(registry, day, report)
    report["report_md"] = str(_write_markdown(registry, day, report))
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
    inner = report["lemida"] if isinstance(report["lemida"], dict) else {}
    report["announcements"] = inner.get("announcements", [])
    report["notifications"] = inner.get("notifications", [])
    _write_report(registry, day, report)
    markdown = dict(inner)
    markdown.update({"date": day, "errors": report["errors"]})
    report["report_md"] = str(_write_markdown(registry, day, markdown))
    return report
