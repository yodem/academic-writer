import tempfile
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
    lesson_dir = registry.directory / "lessons/sample/2026-10-12-0000"
    assert (lesson_dir / "transcript.txt").read_text() == "A lesson transcript."
    meta = json.loads((lesson_dir / "meta.json").read_text())
    assert meta["audio_sha256"] == hashlib.sha256(b"audio bytes").hexdigest()
    assert meta["transcript_words"] == 3
    assert meta["weekday"] == "Mon"
    assert json.loads((registry.directory / "queue/sample-2026-10-12-0000.json").read_text()) == {
        "slug": "sample", "date": "2026-10-12", "lesson_key": "2026-10-12-0000", "transcript_path": str(lesson_dir / "transcript.txt"),
        "meta_path": str(lesson_dir / "meta.json"), "manuscript_id": "manuscript-1",
        "book_id": "book-1", "course_name": "Sample Course", "lecturer": "Dr Example",
    }
    updated = json.loads((registry.directory / "sample.json").read_text())
    assert updated["lessons"] == [{"date": "2026-10-12", "lesson_key": "2026-10-12-0000", "audio_sha256": meta["audio_sha256"], "source_id": "source-1", "trove_page": None, "status": "queued"}]
    assert calls[0] == ["nlm", "source", "list", "notebook-1"]
    assert calls[1][0:3] == ["nlm", "source", "add"]
    assert ["nlm", "content", "source", "source-1"] in calls


def test_ingest_deduplicates_before_notebook_calls(tmp_path):
    audio = tmp_path / "dup.m4a"
    audio.write_bytes(b"same")
    digest = hashlib.sha256(b"same").hexdigest()
    registry = make_registry(tmp_path, lessons=[{"date": "2026-10-12", "lesson_key": "2026-10-12-0000", "audio_sha256": digest, "source_id": "old", "trove_page": None, "status": "queued"}])
    runner, calls = runner_for(tmp_path)
    assert courses.ingest_recording(registry, audio, course_slug="sample", lesson_date="2026-10-12", runner=runner)["status"] == "already ingested"
    assert calls == []


def test_ingest_treats_pre_status_lesson_as_already_ingested(tmp_path):
    audio = tmp_path / "legacy.m4a"
    audio.write_bytes(b"legacy bytes")
    digest = hashlib.sha256(b"legacy bytes").hexdigest()
    registry = make_registry(tmp_path, lessons=[{"date": "2026-10-12", "lesson_key": "2026-10-12-0000", "audio_sha256": digest, "source_id": "old-source", "trove_page": 12}])
    runner, calls = runner_for(tmp_path)
    result = courses.ingest_recording(registry, audio, course_slug="sample", lesson_date="2026-10-12", runner=runner)
    assert result["status"] == "already ingested"
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


def test_ingest_collision_uses_incremented_lesson_key(tmp_path):
    registry = make_registry(tmp_path)
    audio = tmp_path / "one.m4a"
    audio.write_bytes(b"one")
    runner, _ = runner_for(tmp_path)
    one = courses.ingest_recording(registry, audio, course_slug="sample", lesson_date="2026-10-12", runner=runner)
    audio.write_bytes(b"two")
    runner2, _ = runner_for(tmp_path, add_result={"id": "source-2"})
    two = courses.ingest_recording(registry, audio, course_slug="sample", lesson_date="2026-10-12", runner=runner2)
    assert one["lesson_key"] == "2026-10-12-0000"
    assert two["lesson_key"] == "2026-10-12-0000-2"
    assert (registry.directory / "lessons/sample/2026-10-12-0000/transcript.txt").exists()
    assert (registry.directory / "lessons/sample/2026-10-12-0000-2/transcript.txt").exists()


def test_ingest_persists_pending_source_and_reuses_without_count_guard(tmp_path):
    registry = make_registry(tmp_path)
    audio = tmp_path / "lesson.m4a"
    audio.write_bytes(b"audio")
    runner, _ = runner_for(tmp_path)
    def transcript_failure(command, **kwargs):
        if command[1:3] == ["source", "list"]:
            return subprocess.CompletedProcess(command, 0, json.dumps([{}]), "")
        if command[1:3] == ["source", "add"]:
            return subprocess.CompletedProcess(command, 0, json.dumps({"id": "uploaded-source"}), "")
        if command[1:3] == ["content", "source"]:
            raise subprocess.CalledProcessError(1, command, stderr="offline")
        return runner(command, **kwargs)
    try:
        courses.ingest_recording(registry, audio, course_slug="sample", lesson_date="2026-10-12", runner=transcript_failure)
    except courses.IngestError as exc:
        assert "uploaded-source" in str(exc)
    else:
        raise AssertionError("expected transcript failure")
    updated = json.loads((registry.directory / "sample.json").read_text())
    assert updated["lessons"][0]["status"] == "pending_transcript"
    assert updated["lessons"][0]["source_id"] == "uploaded-source"
    pending_key = updated["lessons"][0]["lesson_key"]
    pending_meta = json.loads((registry.directory / f"lessons/sample/{pending_key}/meta.json").read_text())
    assert pending_meta["status"] == "upload_done"
    assert pending_meta["source_id"] == "uploaded-source"
    commands = []
    def retry(command, **kwargs):
        commands.append(command)
        if command[1:3] == ["content", "source"]:
            return subprocess.CompletedProcess(command, 0, json.dumps({"content": "Recovered transcript"}), "")
        return runner(command, **kwargs)
    result = courses.ingest_recording(registry, audio, course_slug="sample", lesson_date="2026-10-12", runner=retry)
    assert result["source_id"] == "uploaded-source"
    assert not any(command[1:3] in (["source", "list"], ["source", "add"]) for command in commands)
    assert json.loads((registry.directory / "sample.json").read_text())["lessons"][0]["status"] == "queued"


def test_ingest_exclusive_lock_rereads_latest_course(tmp_path):
    registry = make_registry(tmp_path, unrelated="original")
    audio = tmp_path / "lesson.m4a"
    audio.write_bytes(b"audio")
    runner, _ = runner_for(tmp_path)
    orig_locked = courses._locked_course
    observed = []
    def locking(directory, slug):
        observed.append(directory / ".lock")
        return orig_locked(directory, slug)
    courses._locked_course = locking
    try:
        # Simulate another writer's update after registry startup snapshot.
        path = registry.directory / "sample.json"
        fresh = json.loads(path.read_text())
        fresh["unrelated"] = "latest"
        path.write_text(json.dumps(fresh))
        courses.ingest_recording(registry, audio, course_slug="sample", lesson_date="2026-10-12", runner=runner)
        assert json.loads(path.read_text())["unrelated"] == "latest"
        assert observed and all(path.name == ".lock" for path in observed)
    finally:
        courses._locked_course = orig_locked


def test_video_ffmpeg_missing_removes_temp_and_has_clear_error(tmp_path):
    registry = make_registry(tmp_path)
    video = tmp_path / "lesson.mp4"
    video.write_bytes(b"video")
    before = set(Path(tempfile.gettempdir()).glob("academic-course-*.m4a"))
    def missing(*args, **kwargs):
        raise FileNotFoundError("ffmpeg")
    try:
        courses.ingest_recording(registry, video, course_slug="sample", lesson_date="2026-10-12", runner=missing)
    except courses.IngestError as exc:
        assert "install ffmpeg" in str(exc)
    else:
        raise AssertionError("expected missing ffmpeg error")
    after = set(Path(tempfile.gettempdir()).glob("academic-course-*.m4a"))
    assert after <= before


def test_ingest_given_source_id_skips_source_count_guard(tmp_path):
    registry = make_registry(tmp_path)
    audio = tmp_path / "lesson.m4a"
    audio.write_bytes(b"audio")
    runner, calls = runner_for(tmp_path)
    result = courses.ingest_recording(registry, audio, course_slug="sample", source_id="existing-source", lesson_date="2026-10-12", runner=runner)
    assert result["source_id"] == "existing-source"
    assert not any(command[1:3] == ["source", "list"] for command in calls)
    assert not any(command[1:3] == ["source", "add"] for command in calls)


def test_ingest_treats_appended_lesson_as_already_ingested(tmp_path):
    audio = tmp_path / "appended.m4a"
    audio.write_bytes(b"appended bytes")
    digest = hashlib.sha256(b"appended bytes").hexdigest()
    registry = make_registry(tmp_path, lessons=[{"date": "2026-10-12", "lesson_key": "2026-10-12-1204", "audio_sha256": digest, "source_id": "src", "trove_page": 3, "status": "appended"}])
    runner, calls = runner_for(tmp_path)
    result = courses.ingest_recording(registry, audio, course_slug="sample", lesson_date="2026-10-12", runner=runner)
    assert result["status"] == "already ingested"
    assert calls == []
    assert len(json.loads((registry.directory / "sample.json").read_text(encoding="utf-8"))["lessons"]) == 1
