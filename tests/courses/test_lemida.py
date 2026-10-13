import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).parents[2] / "src/scripts/courses"))
import courses
import lemida


def registry(tmp_path, **overrides):
    directory = tmp_path / "term"
    directory.mkdir()
    (directory / "term.json").write_text(json.dumps({
        "term": "2026-2027", "timezone": "Asia/Jerusalem",
        "semesters": {"A": {"start": "2026-10-11", "end": "2027-01-29"}},
        "lemida": {"base_url": "https://moodle.example", "keychain_service": "academic-writer-lemida"},
        "local_root": str(tmp_path / "files"), "voice_memos_dir": str(tmp_path / "memos"),
        "drive_remote": "gdrive",
    }), encoding="utf-8")
    course = {"slug": "sample", "name": "Sample", "lemida_course_id": 42,
              "lemida_seen": {}, "drive_folder_id": "drive-1", "notebook_id": "nb-1",
              "slots": [{"day": "Mon", "start": "12:00", "end": "14:00", "semester": "A"}]}
    course.update(overrides)
    (directory / "sample.json").write_text(json.dumps(course), encoding="utf-8")
    return courses.Registry(directory)


def no_forums(base_url, token, function, params):
    return [] if function == "mod_forum_get_forums_by_courses" else {}


def test_module_classification_and_diff_fixture():
    fixture = [
        {"id": 1, "name": "Week 1", "modules": [
            {"id": 1, "modname": "resource", "name": "Slides", "contents": [{"mimetype": "application/pdf", "timemodified": 10}]},
            {"id": 2, "modname": "folder", "name": "Readings", "contents": [{"mimetype": "application/pdf", "timemodified": 12}]},
        ]},
        {"id": 2, "name": "Week 2", "modules": [
            {"id": 3, "modname": "zoom", "name": "Meeting", "contents": []},
            {"id": 4, "modname": "resource", "name": "Lecture video", "contents": [{"mimetype": "video/mp4", "timemodified": 13}]},
        ]},
    ]
    flat = lemida._flatten_modules(fixture)
    assert [lemida.classify_module(m) for m in flat] == ["resource", "resource", "report-only", "recording"]
    assert [m["id"] for m in lemida.changed_modules(flat, {"1": 10})] == [2, 3, 4]
    assert lemida.changed_modules([flat[0]], {"1": 9}) == [flat[0]]
    assert lemida._flatten_modules(flat) == flat


def test_download_adds_token_and_redacts_error(tmp_path, monkeypatch):
    seen = {}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def __init__(self): self.chunks = iter([b"fi", b"le", b""])
        def read(self, size): return next(self.chunks)
    def open_url(request, timeout=0):
        seen["url"] = request if isinstance(request, str) else request.full_url
        return Response()
    monkeypatch.setattr(lemida.urllib.request, "urlopen", open_url)
    target = lemida.download_file("https://moodle.example/pluginfile.php/1/a.pdf?forcedownload=1", "secret", tmp_path / "a.pdf", opener=open_url)
    assert target.read_bytes() == b"file"
    assert "token=secret" in seen["url"]
    try:
        lemida.download_file("https://x/file", "secret", tmp_path / "b", opener=lambda *a, **k: (_ for _ in ()).throw(URLError("https://x/?token=secret")))
    except lemida.LemidaError as exc:
        assert "secret" not in str(exc)
        assert "token=[REDACTED]" in str(exc)
    else:
        raise AssertionError("expected safe download error")


def test_moodle_error_json_is_failure():
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return json.dumps({"exception": "moodle_exception", "errorcode": "invalidtoken", "message": "bad"}).encode()
    try:
        lemida.moodle_course_contents("https://moodle.example", "abc", 42, opener=lambda *a, **k: Response())
    except lemida.LemidaError as exc:
        assert "invalidtoken" in str(exc)
    else:
        raise AssertionError("expected Moodle error")


def test_seen_updates_only_after_module_actions_succeed(tmp_path):
    reg = registry(tmp_path)
    data = [{"id": 1, "name": "Section", "modules": [{"id": 9, "modname": "page", "name": "Info", "contents": []}]}]
    def request(*args, **kwargs): return data
    def runner(command, **kwargs):
        if command[0] == "security": return subprocess.CompletedProcess(command, 0, "token-value\n", "")
        raise AssertionError(command)
    report = lemida.sync_course(reg, "sample", runner=runner, fetch_contents=request, api=no_forums, report_date="2026-10-12")
    stored = json.loads((reg.directory / "sample.json").read_text())
    assert stored["lemida_seen"] == {"9": 0}
    assert report["processed"][0]["name"] == "Info"

    # A concurrent registry update must survive the locked seen write.
    (reg.directory / "sample.json").write_text(json.dumps({"slug": "sample", "lemida_course_id": 42, "lemida_seen": {"other": 7}, "drive_folder_id": "drive-1"}))
    concurrent_update = {"done": False}
    def racing_runner(command, **kwargs):
        if command[0] == "security" and not concurrent_update["done"]:
            concurrent_update["done"] = True
            path = reg.directory / "sample.json"
            latest = json.loads(path.read_text())
            latest["concurrent_update"] = "kept"
            path.write_text(json.dumps(latest))
            return subprocess.CompletedProcess(command, 0, "token-value\n", "")
        return runner(command, **kwargs)
    lemida.sync_course(reg, "sample", runner=racing_runner, fetch_contents=lambda *a: [{"id": 11, "modname": "page", "name": "Info 2", "contents": []}], api=no_forums, report_date="2026-10-12")
    stored = json.loads((reg.directory / "sample.json").read_text())
    assert stored["lemida_seen"] == {"other": 7, "11": 0}
    assert stored["concurrent_update"] == "kept"

    (reg.directory / "sample.json").write_text(json.dumps({"slug": "sample", "lemida_course_id": 42, "lemida_seen": {}, "drive_folder_id": "drive-1"}))
    def fail_action(*args, **kwargs): raise RuntimeError("failed")
    failed = lemida.sync_course(reg, "sample", runner=runner, fetch_contents=lambda *a: [{"id": 10, "modname": "resource", "name": "PDF", "contents": [{"mimetype": "application/pdf", "timemodified": 2, "fileurl": "https://x/f"}]}], download=fail_action, api=no_forums, report_date="2026-10-12")
    assert failed["errors"] and "module 10" in failed["errors"][0]
    assert json.loads((reg.directory / "sample.json").read_text())["lemida_seen"] == {}


def test_daily_scans_memos_then_handles_missing_token(tmp_path):
    memo_dir = tmp_path / "memos"
    memo_dir.mkdir()
    memo = memo_dir / "20261012 120422.m4a"
    memo.write_bytes(b"memo")
    reg = registry(tmp_path)
    calls = []
    def fake_ingest(registry, audio, **kwargs):
        calls.append((audio, kwargs["course_slug"], kwargs["lesson_date"]))
        return {"status": "ingested", "slug": "sample"}
    def runner(command, **kwargs):
        if command[0] == "security": raise subprocess.CalledProcessError(1, command, stderr="not found")
        return subprocess.CompletedProcess(command, 0, "", "")
    result = lemida.daily(reg, runner=runner, ingest=fake_ingest, report_date="2026-10-12")
    assert result["exit_code"] == 5
    assert calls == [(memo, "sample", "2026-10-12")]
    term = json.loads((reg.directory / "term.json").read_text())
    assert term["state"]["last_voice_memo_scan"]
    assert (reg.directory / "logs/lemida-2026-10-12.json").exists()


def test_daily_scan_failure_still_runs_lms_and_exits_one(tmp_path, monkeypatch):
    memo_dir = tmp_path / "memos"
    memo_dir.mkdir()
    (memo_dir / "20261012 120422.m4a").write_bytes(b"memo")
    reg = registry(tmp_path)
    sync_calls = []
    def fail_time(*args, **kwargs): raise OSError("scan stat failed")
    monkeypatch.setattr(courses, "recording_time", fail_time)
    def run_sync(*args, **kwargs):
        sync_calls.append(True)
        return {"errors": []}
    result = lemida.daily(reg, sync=run_sync, report_date="2026-10-12")
    assert sync_calls == [True]
    assert result["exit_code"] == 1
    assert "scan stat failed" in result["voice_memos"]["errors"][0]["error"]


def test_daily_scan_boundary_compares_instants_with_term_timezone(tmp_path):
    memo_dir = tmp_path / "memos"
    memo_dir.mkdir()
    (memo_dir / "20261012 120000.m4a").write_bytes(b"memo")
    reg = registry(tmp_path)
    term_path = reg.directory / "term.json"
    term = json.loads(term_path.read_text())
    term["state"] = {"last_voice_memo_scan": "2026-10-12T12:00:00+03:00"}
    term_path.write_text(json.dumps(term))
    calls = []
    result = lemida.daily(reg, sync=lambda *a, **k: {"errors": []}, ingest=lambda *a, **k: calls.append(a), report_date="2026-10-12")
    assert calls == []
    assert result["voice_memos"]["processed"] == []



def test_daily_cli_json_is_valid_json(monkeypatch, tmp_path, capsys):
    """The real daily routine with --json must print exactly one JSON document."""
    import json as _json
    import courses as courses_mod
    import lemida as lemida_mod
    memos = tmp_path / "memos"
    memos.mkdir()
    (tmp_path / "term.json").write_text(_json.dumps({"term": "T", "voice_memos_dir": str(memos), "state": {"last_voice_memo_scan": "2026-01-01T00:00:00+02:00"}}), encoding="utf-8")
    (tmp_path / "queue").mkdir()
    (tmp_path / "queue" / "c1-2026-01-05-1204.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(tmp_path))
    monkeypatch.setattr(lemida_mod, "lemida_sync", lambda registry, **kw: {"courses": [], "errors": []})
    assert courses_mod.main(["--term", ".", "daily", "--dry-run", "--json"]) == 0
    out = capsys.readouterr().out
    data = _json.loads(out)
    assert data["queue"]


# ---- forums, notifications and the report -------------------------------------------------

SECRET_RUNNER = lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "token-value\n", "")
NOW = 1_760_000_000


def moodle_api(calls=None, posts_by_discussion=None, notifications=None, fail_course=None):
    posts_by_discussion = posts_by_discussion or {}

    def api(base_url, token, function, params):
        if calls is not None:
            calls.append((function, dict(params)))
        if function == "mod_forum_get_forums_by_courses":
            if params["courseids[0]"] == fail_course:
                raise lemida.LemidaError("Moodle error boom")
            return [{"id": 7, "course": params["courseids[0]"], "name": "Announcements", "type": "news"}]
        if function == "mod_forum_get_forum_discussions":
            return {"discussions": [
                {"id": 901, "discussion": 11, "name": "Exam date", "timemodified": NOW, "userfullname": "Dr. Example"},
                {"id": 902, "discussion": 12, "name": "Old news", "timemodified": NOW - 5000, "userfullname": "Dr. Example"},
            ], "warnings": []}
        if function == "mod_forum_get_discussion_posts":
            return posts_by_discussion[int(params["discussionid"])]
        if function == "core_webservice_get_site_info":
            return {"userid": 55, "username": "student"}
        if function == "message_popup_get_popup_notifications":
            return {"notifications": notifications or [], "unreadcount": 1}
        raise AssertionError(function)
    return api


POSTS = {
    11: {"posts": [{"id": 901, "subject": "Exam date", "author": {"id": 3, "fullname": "Dr. Example"},
                    "timecreated": NOW, "message": "<p>The exam is on <b>Monday</b>.</p><p>&amp; bring a pen</p>",
                    "attachments": [{"filename": "exam info.pdf", "fileurl": "https://moodle.example/webservice/pluginfile.php/9/mod_forum/attachment/1/exam%20info.pdf", "mimetype": "application/pdf"}]}]},
    12: {"posts": [{"id": 902, "subject": "Old news", "author": {"fullname": "Dr. Example"}, "timecreated": NOW - 5000, "message": "old", "attachments": []}]},
}


def fake_download(url, token, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"%PDF-1.4 fake")
    return destination


def test_forum_attachment_goes_through_add_source_and_seen_advances(tmp_path):
    reg = registry(tmp_path)
    added = []
    def fake_add(registry_, file, course_slug, title=None, origin="other", origin_ref=None, runner=None):
        added.append((Path(file).name, course_slug, origin, origin_ref, Path(file).read_bytes()))
        return {"status": "added"}
    api = moodle_api(posts_by_discussion=POSTS)
    result = lemida.sync_course(reg, "sample", runner=SECRET_RUNNER, fetch_contents=lambda *a: [], download=fake_download, api=api, add_source=fake_add, report_date="2026-10-13")
    assert added == [("lemida-forum-11 - exam info.pdf", "sample", "lemida", "forum:11", b"%PDF-1.4 fake")]
    assert (tmp_path / "files/sample/sources/lemida-forum-11 - exam info.pdf").exists()
    subjects = [a["subject"] for a in result["announcements"]]
    assert subjects == ["Exam date", "Old news"]
    first = result["announcements"][0]
    assert first["author"] == "Dr. Example" and "The exam is on Monday" in first["excerpt"] and "<" not in first["excerpt"]
    assert first["attachments"][0]["result"] == "added"
    stored = json.loads((reg.directory / "sample.json").read_text())
    assert stored["lemida_seen_posts"] == {"11": NOW, "12": NOW - 5000}


def test_seen_posts_are_skipped_and_failed_attachment_does_not_advance(tmp_path):
    reg = registry(tmp_path, lemida_seen_posts={"11": NOW, "12": NOW - 5000})
    calls = []
    result = lemida.sync_course(reg, "sample", runner=SECRET_RUNNER, fetch_contents=lambda *a: [], download=fake_download,
                                api=moodle_api(calls, POSTS), add_source=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no")), report_date="d")
    assert result["announcements"] == []
    assert not [c for c in calls if c[0] == "mod_forum_get_discussion_posts"]

    (tmp_path / "second").mkdir()
    reg = registry(tmp_path / "second", lemida_seen_posts={})
    def failing_add(*a, **k): raise courses.IngestError("notebook full")
    result = lemida.sync_course(reg, "sample", runner=SECRET_RUNNER, fetch_contents=lambda *a: [], download=fake_download,
                                api=moodle_api(posts_by_discussion=POSTS), add_source=failing_add, report_date="d")
    assert result["errors"] and "notebook full" in result["errors"][0]
    stored = json.loads((reg.directory / "sample.json").read_text())
    assert stored["lemida_seen_posts"] == {"12": NOW - 5000}
    assert result["announcements"][0]["attachments"][0]["result"] == "error"


def test_content_files_use_add_source_with_cm_ref(tmp_path):
    reg = registry(tmp_path)
    added = []
    data = [{"id": 1, "modules": [{"id": 5, "modname": "resource", "name": "Slides", "contents": [
        {"filename": "s.pdf", "fileurl": "https://moodle.example/pluginfile.php/1/s.pdf", "mimetype": "application/pdf", "timemodified": 20}]}]}]
    lemida.sync_course(reg, "sample", runner=SECRET_RUNNER, fetch_contents=lambda *a: data, download=fake_download, api=no_forums,
                       add_source=lambda r, f, s, **k: added.append((Path(f).name, k["origin"], k["origin_ref"])) or {"status": "added"})
    assert added == [("lemida-cm5 - s.pdf", "lemida", "cm:5")]
    assert json.loads((reg.directory / "sample.json").read_text())["lemida_seen"] == {"5": 20}


def test_notifications_filtered_by_time_and_state_advances(tmp_path):
    reg = registry(tmp_path)
    term_path = reg.directory / "term.json"
    term = json.loads(term_path.read_text())
    term["state"] = {"last_notification_time": NOW - 100}
    term_path.write_text(json.dumps(term))
    notes = [
        {"id": 1, "subject": "New grade", "contexturl": "https://moodle.example/mod/assign/view.php?id=3", "timecreated": NOW, "read": False},
        {"id": 2, "subject": "Older", "contexturl": "https://moodle.example/x", "timecreated": NOW - 100, "read": True},
    ]
    calls = []
    fresh = lemida.sync_notifications(reg, runner=SECRET_RUNNER, api=moodle_api(calls, notifications=notes))
    assert [n["subject"] for n in fresh] == ["New grade"] and fresh[0]["read"] is False
    popup = [p for f, p in calls if f == "message_popup_get_popup_notifications"][0]
    assert popup["useridto"] == 55 and popup["limit"] == 50 and popup["newestfirst"] == 1
    assert json.loads(term_path.read_text())["state"]["last_notification_time"] == NOW
    assert lemida.sync_notifications(reg, runner=SECRET_RUNNER, api=moodle_api(notifications=notes)) == []


def test_notification_state_not_advanced_on_failure_or_dry_run(tmp_path):
    reg = registry(tmp_path)
    notes = [{"subject": "n", "contexturl": "", "timecreated": NOW, "read": False}]
    lemida.sync_notifications(reg, runner=SECRET_RUNNER, api=moodle_api(notifications=notes), dry_run=True)
    assert "last_notification_time" not in json.loads((reg.directory / "term.json").read_text()).get("state", {})


def test_one_course_failing_does_not_block_another_and_md_written(tmp_path):
    reg = registry(tmp_path)
    other = {"slug": "other", "name": "Other", "lemida_course_id": 43, "lemida_seen": {}, "drive_folder_id": "d2", "notebook_id": "n2",
             "slots": [{"day": "Tue", "start": "10:00", "end": "12:00", "semester": "A"}]}
    (reg.directory / "other.json").write_text(json.dumps(other))
    reg = courses.Registry(reg.directory)
    notes = [{"subject": "Hello", "contexturl": "https://moodle.example/n", "timecreated": NOW, "read": True}]
    report = lemida.lemida_sync(reg, runner=SECRET_RUNNER, fetch_contents=lambda *a: [], download=fake_download,
                                api=moodle_api(posts_by_discussion=POSTS, notifications=notes, fail_course=42),
                                add_source=lambda *a, **k: {"status": "added"}, report_date="2026-10-13")
    assert [a["course"] for a in report["announcements"]] == ["other", "other"]
    assert any(e["slug"] == "sample" and "boom" in e["error"] for e in report["errors"])
    assert report["notifications"][0]["subject"] == "Hello"
    saved = json.loads((reg.directory / "logs/lemida-2026-10-13.json").read_text())
    assert saved["announcements"] and saved["notifications"]
    md = (reg.directory / "logs/lemida-2026-10-13.md").read_text(encoding="utf-8")
    assert "Exam date" in md and "exam info.pdf" in md and "Hello" in md and "boom" in md and "token-value" not in md


def test_daily_report_carries_announcements_and_md(tmp_path):
    reg = registry(tmp_path)
    (tmp_path / "memos").mkdir()
    stub = lambda *a, **k: {"errors": [], "announcements": [{"course": "sample", "subject": "S", "author": "A", "created": "2026-10-13T00:00:00", "excerpt": "e", "attachments": []}], "notifications": []}
    result = lemida.daily(reg, sync=stub, report_date="2026-10-13")
    assert result["announcements"][0]["subject"] == "S"
    assert Path(result["report_md"]).read_text(encoding="utf-8").count("S") >= 1
    assert json.loads((reg.directory / "logs/lemida-2026-10-13.json").read_text())["announcements"]
