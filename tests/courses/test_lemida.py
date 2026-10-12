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


def test_module_classification_and_diff_fixture():
    fixture = [
        {"id": 1, "modname": "resource", "name": "Slides", "contents": [{"mimetype": "application/pdf", "timemodified": 10}]},
        {"id": 2, "modname": "resource", "name": "Lecture", "contents": [{"mimetype": "audio/mpeg", "timemodified": 11}]},
        {"id": 3, "modname": "zoom", "name": "Meeting", "contents": []},
        {"id": 4, "modname": "videostream", "name": "Class", "contents": []},
    ]
    assert lemida.classify_module(fixture[0]) == "resource"
    assert lemida.classify_module(fixture[1]) == "recording"
    assert lemida.classify_module(fixture[2]) == "report-only"
    assert lemida.classify_module(fixture[3]) == "recording"
    assert [m["id"] for m in lemida.changed_modules(fixture, {"1": 10})] == [2, 3, 4]
    assert lemida.changed_modules([fixture[0]], {"1": 9}) == [fixture[0]]


def test_download_adds_token_and_redacts_error(tmp_path, monkeypatch):
    seen = {}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b"file"
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
    data = [{"id": 9, "modname": "page", "name": "Info", "contents": []}]
    def request(*args, **kwargs): return data
    def runner(command, **kwargs):
        if command[0] == "security": return subprocess.CompletedProcess(command, 0, "token-value\n", "")
        raise AssertionError(command)
    report = lemida.sync_course(reg, "sample", runner=runner, fetch_contents=request, report_date="2026-10-12")
    stored = json.loads((reg.directory / "sample.json").read_text())
    assert stored["lemida_seen"] == {"9": 0}
    assert report["processed"][0]["name"] == "Info"

    (reg.directory / "sample.json").write_text(json.dumps({"slug": "sample", "lemida_course_id": 42, "lemida_seen": {}, "drive_folder_id": "drive-1"}))
    def fail_action(*args, **kwargs): raise RuntimeError("failed")
    try:
        lemida.sync_course(reg, "sample", runner=runner, fetch_contents=lambda *a: [{"id": 10, "modname": "resource", "name": "PDF", "contents": [{"mimetype": "application/pdf", "timemodified": 2, "fileurl": "https://x/f"}]}], download=fail_action, report_date="2026-10-12")
    except lemida.LemidaError:
        pass
    else:
        raise AssertionError("expected action error")
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
