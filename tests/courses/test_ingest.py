import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "src/scripts/courses"))
import courses


def make_registry(tmp_path, **course_overrides):
    directory = tmp_path / "term"
    directory.mkdir()
    (directory / "term.json").write_text(json.dumps({
        "timezone": "Asia/Jerusalem", "notebook_source_limit": 45,
        "semesters": {"A": {"start": "2026-10-11", "end": "2027-01-29"}},
    }), encoding="utf-8")
    course = {
        "slug": "sample", "name": "Sample Course", "lecturer": "Dr Example",
        "slots": [{"day": "Mon", "start": "12:00", "end": "14:00", "semester": "A"}],
        "notebook_id": "notebook-1", "manuscript_id": "manuscript-1", "book_id": "book-1",
        "lessons": [],
    }
    course.update(course_overrides)
    (directory / "sample.json").write_text(json.dumps(course), encoding="utf-8")
    return courses.Registry(directory)


def runner_for(tmp_path, source_list=None, add_result=None, transcript="A lesson transcript."):
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        if command[0] == "nlm" and command[1:3] == ["source", "list"]:
            output = json.dumps(source_list if source_list is not None else [])
        elif command[0] == "nlm" and command[1:3] == ["source", "add"]:
            output = json.dumps(add_result if add_result is not None else {"id": "source-1"})
        elif command[0] == "nlm" and command[1:3] == ["content", "source"]:
            output = json.dumps({"content": transcript})
        elif command[0] == "ffmpeg":
            Path(command[-1]).write_bytes(b"converted audio")
            output = ""
        else:
            raise AssertionError(f"unexpected command: {command}")
        return subprocess.CompletedProcess(command, 0, output, "")
    return runner, calls


def test_ingest_uploads_transcript_metadata_and_digest_job(tmp_path):
    registry = make_registry(tmp_path)
    audio = tmp_path / "lesson.m4a"
    audio.write_bytes(b"audio bytes")
    runner, calls = runner_for(tmp_path)

    result = courses.ingest_recording(registry, audio, course_slug="sample", lesson_date="2026-10-12", runner=runner)

    assert result["source_id"] == "source-1"
    lesson_dir = registry.directory / "lessons/sample/2026-10-12"
    assert (lesson_dir / "transcript.txt").read_text() == "A lesson transcript."
    meta = json.loads((lesson_dir / "meta.json").read_text())
    assert meta["audio_sha256"] == hashlib.sha256(b"audio bytes").hexdigest()
    assert meta["transcript_words"] == 3
    assert meta["weekday"] == "Mon"
    assert json.loads((registry.directory / "queue/sample-2026-10-12.json").read_text()) == {
        "slug": "sample", "date": "2026-10-12", "transcript_path": str(lesson_dir / "transcript.txt"),
        "meta_path": str(lesson_dir / "meta.json"), "manuscript_id": "manuscript-1",
        "book_id": "book-1", "course_name": "Sample Course", "lecturer": "Dr Example",
    }
    updated = json.loads((registry.directory / "sample.json").read_text())
    assert updated["lessons"] == [{"date": "2026-10-12", "audio_sha256": meta["audio_sha256"], "source_id": "source-1", "trove_page": None}]
    assert calls[0] == ["nlm", "source", "list", "notebook-1"]
    assert calls[1][0:3] == ["nlm", "source", "add"]
    assert ["nlm", "content", "source", "source-1"] in calls


def test_ingest_deduplicates_before_notebook_calls(tmp_path):
    audio = tmp_path / "dup.m4a"
    audio.write_bytes(b"same")
    digest = hashlib.sha256(b"same").hexdigest()
    registry = make_registry(tmp_path, lessons=[{"date": "2026-10-12", "audio_sha256": digest, "source_id": "old", "trove_page": None}])
    runner, calls = runner_for(tmp_path)
    assert courses.ingest_recording(registry, audio, course_slug="sample", lesson_date="2026-10-12", runner=runner)["status"] == "already ingested"
    assert calls == []


def test_ingest_stops_at_configured_notebook_limit(tmp_path):
    registry = make_registry(tmp_path)
    audio = tmp_path / "lesson.m4a"
    audio.write_bytes(b"audio")
    runner, calls = runner_for(tmp_path, source_list=[{"id": str(i)} for i in range(45)])
    try:
        courses.ingest_recording(registry, audio, course_slug="sample", lesson_date="2026-10-12", runner=runner)
    except courses.IngestError as exc:
        assert exc.exit_code == 4
        assert "45" in str(exc)
    else:
        raise AssertionError("expected source limit error")
    assert len(calls) == 1


def test_ingest_reuses_source_id_without_upload(tmp_path):
    registry = make_registry(tmp_path)
    audio = tmp_path / "lesson.m4a"
    audio.write_bytes(b"audio")
    runner, calls = runner_for(tmp_path)
    result = courses.ingest_recording(registry, audio, course_slug="sample", source_id="existing", lesson_date="2026-10-12", runner=runner)
    assert result["source_id"] == "existing"
    assert not any(command[1:3] == ["source", "add"] for command in calls)


def test_ingest_accepts_nested_upload_id_and_converts_video(tmp_path):
    registry = make_registry(tmp_path)
    video = tmp_path / "lesson.mp4"
    video.write_bytes(b"video bytes")
    runner, calls = runner_for(tmp_path, add_result={"source": {"id": "nested-source"}})
    result = courses.ingest_recording(registry, video, course_slug="sample", lesson_date="2026-10-12", runner=runner)
    assert result["source_id"] == "nested-source"
    assert calls[0][0] == "ffmpeg"
    assert "-vn" in calls[0] and "-ac" in calls[0] and "-c:a" in calls[0]


def test_ingest_unmatched_recording_exits_three_without_upload(tmp_path):
    registry = make_registry(tmp_path)
    audio = tmp_path / "20261012 190000.m4a"
    audio.write_bytes(b"audio")
    runner, calls = runner_for(tmp_path)
    try:
        courses.ingest_recording(registry, audio, runner=runner)
    except courses.IngestError as exc:
        assert exc.exit_code == 3
        assert "unmatched" in str(exc)
    else:
        raise AssertionError("expected unmatched mapping error")
    assert calls == []


def test_ingest_cli_accepts_explicit_date_and_course(tmp_path, monkeypatch, capsys):
    registry = make_registry(tmp_path)
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(registry.directory))
    # CLI subprocesses are exercised through the real runner only in explicit dry-run mode.
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"audio")
    assert courses.main(["ingest", str(audio), "--course", "sample", "--date", "2026-10-12", "--dry-run"]) == 0
    assert "sample" in capsys.readouterr().out
