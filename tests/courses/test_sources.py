import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src/scripts/courses"))
import courses

TOC = [
    {"level": 1, "title": "חומרי קריאה", "page": 3},
    {"level": 2, "title": "Reading One", "page": 4},
    {"level": 3, "title": "Section", "page": 5},
    {"level": 1, "title": "תמלולי שיעורים", "page": 9},
]


def make_registry(tmp_path, term=None, **overrides):
    directory = tmp_path / "term"
    directory.mkdir()
    term_json = {"timezone": "Asia/Jerusalem", "notebook_source_limit": 45, "semesters": {"A": {"start": "2026-10-11", "end": "2027-01-29"}}}
    term_json.update(term or {})
    (directory / "term.json").write_text(json.dumps(term_json), encoding="utf-8")
    course = {"slug": "sample", "name": "Sample Course", "lecturer": "Dr X", "slots": [], "notebook_id": "nb-1",
              "book_id": "book-1", "drive_folder_id": "folder-1", "lessons": []}
    course.update(overrides)
    (directory / "sample.json").write_text(json.dumps(course), encoding="utf-8")
    return courses.Registry(directory)


def reload(registry):
    return json.loads((registry.directory / "sample.json").read_text(encoding="utf-8"))


class Fake:
    def __init__(self, nlm_list=None, drive=None, toc=None, other_toc=None, pages=7, fail_nlm_add=False):
        self.calls = []
        self.nlm_list = nlm_list if nlm_list is not None else []
        self.drive = drive if drive is not None else []
        self.toc = toc if toc is not None else TOC
        self.other_toc = other_toc if other_toc is not None else [{"level": 1, "title": "Ch", "page": 1}]
        self.pages = pages
        self.fail_nlm_add = fail_nlm_add

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if command[0] == "rclone" and command[1] == "copyto":
            self.copied = getattr(self, "copied", {})
            self.copied[command[3]] = hashlib.md5(Path(command[2]).read_bytes()).hexdigest()
            out = ""
        elif command[0] == "rclone" and command[1] == "lsjson" and "--stat" in command:
            out = json.dumps({"Path": command[2].split(":", 1)[1], "Hashes": {"md5": getattr(self, "copied", {}).get(command[2])}})
        elif command[0] == "rclone" and command[1] == "lsjson":
            out = json.dumps([d if isinstance(d, dict) else {"Name": d.rsplit("/", 1)[-1], "Path": d} for d in self.drive])
        elif command[:3] == ["nlm", "source", "list"]:
            out = json.dumps(self.nlm_list)
        elif command[:3] == ["nlm", "source", "add"]:
            if self.fail_nlm_add:
                raise subprocess.CalledProcessError(1, command)
            out = json.dumps({"source_id": "src-1"})
        elif command[0] == "pdfinfo":
            out = f"Title: x\nPages:          {self.pages}\n"
        elif command[:3] == ["trove", "items", "toc"]:
            toc = self.toc if command[3] == "book-1" else self.other_toc
            out = json.dumps({"items": [{"toc": toc}]})
        else:
            raise AssertionError(f"unexpected command: {command}")
        return subprocess.CompletedProcess(command, 0, out, "")

    def of(self, *prefix):
        return [c for c in self.calls if c[:len(prefix)] == list(prefix)]


def pdf(tmp_path, name="01 - Reading One.pdf", data=b"%PDF pdf bytes"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_add_source_argv_job_and_record(tmp_path):
    registry = make_registry(tmp_path, term={"drive_remote": "mydrive"})
    path = pdf(tmp_path)
    fake = Fake()
    result = courses.add_source(registry, path, "sample", origin="lemida", origin_ref="mod/42", runner=fake)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["status"] == "added"
    snap = registry.directory / "sources" / "sample" / f"{sha[:8]}-01 - Reading One.pdf"
    assert snap.read_bytes() == path.read_bytes()
    assert fake.of("rclone", "copyto") == [["rclone", "copyto", str(snap), "mydrive:קריאות/Reading One/Reading One.pdf", "--ignore-existing", "--drive-root-folder-id", "folder-1"]]
    assert fake.of("nlm", "source", "add") == [["nlm", "source", "add", "nb-1", "--file", str(snap), "--title", "Reading One", "--wait", "--json"]]
    record = reload(registry)["sources"][0]
    assert record["file"] == str(snap.resolve())
    assert record["sha256"] == sha and record["sha8"] == sha[:8]
    assert (record["title"], record["origin"], record["origin_ref"]) == ("Reading One", "lemida", "mod/42")
    assert record["drive"] is True and record["notebook_source_id"] == "src-1" and record["trove"] is None
    assert record["status"] == "queued" and record["added_at"]
    job = json.loads((registry.directory / "queue/sources" / f"sample-{sha[:8]}.json").read_text())
    assert job == {"slug": "sample", "sha8": sha[:8], "title": "Reading One", "file": str(snap.resolve()), "pages": 7,
                   "kind": "pdf", "book_id": "book-1", "course_name": "Sample Course"}


def test_same_name_different_bytes_make_two_snapshots_and_jobs(tmp_path):
    registry = make_registry(tmp_path)
    first = pdf(tmp_path, "reading.pdf", b"%PDF first")
    courses.add_source(registry, first, "sample", runner=Fake())
    first.write_bytes(b"%PDF second version")
    courses.add_source(registry, first, "sample", runner=Fake())
    jobs = [json.loads(p.read_text()) for p in sorted((registry.directory / "queue/sources").glob("*.json"))]
    assert len(jobs) == 2 and len({j["file"] for j in jobs}) == 2
    assert sorted(Path(j["file"]).read_bytes() for j in jobs) == [b"%PDF first", b"%PDF second version"]
    assert len(list((registry.directory / "sources" / "sample").iterdir())) == 2


def test_identical_bytes_readded_dedupe_without_new_snapshot(tmp_path):
    registry = make_registry(tmp_path)
    courses.add_source(registry, pdf(tmp_path, "a.pdf", b"%PDF same"), "sample", runner=Fake())
    fake = Fake()
    result = courses.add_source(registry, pdf(tmp_path, "b.pdf", b"%PDF same"), "sample", runner=fake)
    assert result["status"] == "already added" and fake.calls == []
    assert len(list((registry.directory / "sources" / "sample").iterdir())) == 1


def test_default_title_strips_prefixes_and_non_pdf_has_no_pages(tmp_path):
    registry = make_registry(tmp_path)
    path = pdf(tmp_path, "email-2026-10-12 - Syllabus.docx", b"docx")
    fake = Fake()
    courses.add_source(registry, path, "sample", runner=fake)
    job = next((registry.directory / "queue/sources").glob("*.json"))
    data = json.loads(job.read_text())
    assert data["title"] == "Syllabus" and data["pages"] is None and data["kind"] == "docx"
    assert not fake.of("pdfinfo")


def test_dedupe_makes_no_calls(tmp_path):
    registry = make_registry(tmp_path)
    path = pdf(tmp_path)
    courses.add_source(registry, path, "sample", runner=Fake())
    fake = Fake()
    result = courses.add_source(registry, path, "sample", runner=fake)
    assert result["status"] == "already added"
    assert fake.calls == []


def test_resume_after_drive_only(tmp_path):
    registry = make_registry(tmp_path)
    path = pdf(tmp_path)
    broken = Fake(fail_nlm_add=True)
    with pytest.raises(subprocess.CalledProcessError):
        courses.add_source(registry, path, "sample", runner=broken)
    assert reload(registry)["sources"][0]["status"] == "drive_done"
    fake = Fake()
    assert courses.add_source(registry, path, "sample", runner=fake)["status"] == "added"
    assert not fake.of("rclone", "copyto")
    assert len(fake.of("nlm", "source", "add")) == 1
    assert reload(registry)["sources"][0]["status"] == "queued"


def test_resume_after_uploaded_without_job(tmp_path):
    path = pdf(tmp_path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    registry = make_registry(tmp_path, sources=[{"sha256": sha, "sha8": sha[:8], "title": "Reading One", "file": str(path), "origin": "other",
                                                 "origin_ref": None, "drive": True, "notebook_source_id": "src-9", "trove": None, "status": "uploaded"}])
    fake = Fake()
    courses.add_source(registry, path, "sample", runner=fake)
    assert not fake.of("rclone") and not fake.of("nlm")
    assert (registry.directory / "queue/sources" / f"sample-{sha[:8]}.json").is_file()
    record = reload(registry)["sources"][0]
    assert record["status"] == "queued" and record["notebook_source_id"] == "src-9"


def test_count_guard_exit_4_before_any_upload(tmp_path):
    registry = make_registry(tmp_path)
    fake = Fake(nlm_list=[{"id": str(i)} for i in range(45)])
    with pytest.raises(courses.IngestError) as exc:
        courses.add_source(registry, pdf(tmp_path), "sample", runner=fake)
    assert exc.value.exit_code == 4
    assert not fake.of("rclone") and not fake.of("nlm", "source", "add")


def test_missing_drive_folder_is_error(tmp_path):
    registry = make_registry(tmp_path, drive_folder_id=None)
    with pytest.raises(courses.IngestError, match="drive_folder_id"):
        courses.add_source(registry, pdf(tmp_path), "sample", runner=Fake())


def media_registry(tmp_path, **overrides):
    return make_registry(tmp_path, **overrides)


def fake_ingest_factory(registry, calls=None, status="queued"):
    def fake_ingest(reg, audio, **kwargs):
        if calls is not None:
            calls.append((audio, kwargs))
        sha = courses._file_sha256(Path(audio))
        path = reg.directory / "sample.json"
        data = json.loads(path.read_text())
        data.setdefault("lessons", []).append({"lesson_key": "2026-10-12-1204", "date": "2026-10-12", "audio_sha256": sha,
                                               "source_id": "src-9", "trove_page": 6 if status in {"done", "appended"} else None, "status": status})
        path.write_text(json.dumps(data))
        return {"status": "ingested", "slug": "sample", "date": "2026-10-12", "lesson_key": "2026-10-12-1204", "source_id": "src-9"}
    return fake_ingest


def test_media_add_source_copies_to_drive_records_and_delegates(tmp_path, monkeypatch):
    registry = make_registry(tmp_path)
    calls = []
    monkeypatch.setattr(courses, "ingest_recording", fake_ingest_factory(registry, calls))
    audio = tmp_path / "lesson.m4a"
    audio.write_bytes(b"a")
    fake = Fake()
    result = courses.add_source(registry, audio, "sample", origin="recording", runner=fake, lesson_date="2026-10-12", lesson_time="1204")
    assert result["status"] == "ingested" and result["lesson_key"] == "2026-10-12-1204"
    copies = fake.of("rclone", "copyto")
    assert len(copies) == 1 and copies[0][4:] == ["--ignore-existing", "--drive-root-folder-id", "folder-1"] and copies[0][3].startswith("gdrive:")
    assert calls[0][0] != audio and calls[0][0].parent.name == "sample" and calls[0][0].parent.parent.name == "sources" and calls[0][1]["course_slug"] == "sample"
    assert calls[0][1]["lesson_date"] == "2026-10-12" and calls[0][1]["lesson_time"] == "1204" and calls[0][1]["transcript_file"] is False
    record = reload(registry)["sources"][0]
    assert record["kind"] == "media" and record["drive"] is True and record["lesson_key"] == "2026-10-12-1204"
    assert record["notebook_source_id"] == "src-9" and Path(record["file"]).is_file()
    assert fake.of("nlm") == []  # NotebookLM upload belongs to ingest_recording


def test_transcript_add_source_passes_through_and_needs_date(tmp_path, monkeypatch):
    registry = make_registry(tmp_path)
    calls = []
    monkeypatch.setattr(courses, "ingest_recording", fake_ingest_factory(registry, calls))
    text = tmp_path / "t.txt"
    text.write_text("transcript", encoding="utf-8")
    with pytest.raises(courses.IngestError, match="--date"):
        courses.add_source(registry, text, "sample", runner=Fake(), transcript=True)
    courses.add_source(registry, text, "sample", runner=Fake(), transcript=True, lesson_date="2026-10-12", lesson_time="1204")
    assert calls[0][1]["transcript_file"] is True and reload(registry)["sources"][0]["kind"] == "media"


def test_add_source_passes_the_lesson_owner_to_ingest(tmp_path, monkeypatch):
    registry = make_registry(tmp_path)
    calls = []
    monkeypatch.setattr(courses, "ingest_recording", fake_ingest_factory(registry, calls))
    text = tmp_path / "t.txt"
    text.write_text("transcript", encoding="utf-8")
    courses.add_source(registry, text, "sample", runner=Fake(), transcript=True, lesson_date="2026-10-12", lesson_time="1204",
                       lesson_owner={"wispr_meeting_id": "m1"})
    assert calls[0][1]["lesson_owner"] == {"wispr_meeting_id": "m1"}


def test_media_add_source_resumes_without_second_drive_copy(tmp_path, monkeypatch):
    registry = make_registry(tmp_path)
    audio = tmp_path / "lesson.m4a"
    audio.write_bytes(b"a")
    def failing(*a, **k): raise courses.IngestError("nlm down")
    monkeypatch.setattr(courses, "ingest_recording", failing)
    fake = Fake()
    with pytest.raises(courses.IngestError):
        courses.add_source(registry, audio, "sample", runner=fake)
    assert reload(registry)["sources"][0]["drive"] is True
    monkeypatch.setattr(courses, "ingest_recording", fake_ingest_factory(registry))
    courses.add_source(registry, audio, "sample", runner=fake)
    assert len(fake.of("rclone", "copyto")) == 1 and reload(registry)["sources"][0]["notebook_source_id"] == "src-9"


def media_checked(tmp_path, monkeypatch, status, **fake_kwargs):
    registry = make_registry(tmp_path)
    monkeypatch.setattr(courses, "ingest_recording", fake_ingest_factory(registry, status=status))
    audio = tmp_path / "lesson.m4a"
    audio.write_bytes(b"a")
    courses.add_source(registry, audio, "sample", runner=Fake())
    registry = courses.Registry(registry.directory)
    name = reload(registry)["sources"][0]["drive_path"]
    toc = [{"level": 1, "title": "תמלולי שיעורים", "page": 5}, {"level": 2, "title": "2026-10-12", "page": 6}]
    defaults = dict(drive=[name], nlm_list=[{"id": "src-9"}], toc=toc)
    defaults.update(fake_kwargs)
    fake = Fake(**defaults)
    original = fake.__call__
    def with_find(command, **kwargs):
        if command[:3] == ["trove", "items", "get"]:
            return subprocess.CompletedProcess(command, 0, "# a\n# b\n# c\n# d\n# e\n# f\n" + courses.LESSON_KEY_PREFIX + "2026-10-12-1204\n", "")
        return original(command, **kwargs)
    return courses.check_source(registry, "sample", runner=with_find)


def test_check_source_media_passes(tmp_path, monkeypatch):
    assert media_checked(tmp_path, monkeypatch, "done") == []


def test_check_source_media_fails_when_missing_in_drive_or_notebook_or_lesson(tmp_path, monkeypatch):
    problems = media_checked(tmp_path, monkeypatch, "done", drive=[], nlm_list=[])
    assert any("not in the Drive folder" in p for p in problems) and any("not in the notebook" in p for p in problems)
    (tmp_path / "b").mkdir()
    problems = media_checked(tmp_path / "b", monkeypatch, "done", toc=[{"level": 1, "title": "תמלולי שיעורים", "page": 5}])
    assert any("lesson page 6 is not a level-2 entry" in p for p in problems)


def test_check_source_media_pending_lesson(tmp_path, monkeypatch):
    problems = media_checked(tmp_path, monkeypatch, "queued")
    assert len(problems) == 1 and "lesson pending" in problems[0]


def done_source(tmp_path, registry=None, **extra):
    path = pdf(tmp_path)
    registry = registry or make_registry(tmp_path)
    courses.add_source(registry, path, "sample", runner=Fake())
    sha8 = reload(registry)["sources"][0]["sha8"]
    return registry, Path(reload(registry)["sources"][0]["file"]), sha8


def test_source_done_moves_job(tmp_path):
    registry, _, sha8 = done_source(tmp_path)
    job = registry.directory / "queue/sources" / f"sample-{sha8}.json"
    assert job.is_file()
    courses.source_done(registry, "sample", sha8, "book-1:4")
    record = reload(registry)["sources"][0]
    assert record["status"] == "done" and record["trove"] == {"book_id": "book-1", "page": 4}
    assert not job.exists() and (registry.directory / "queue/sources/done" / job.name).is_file()


def checked(tmp_path, trove="book-1:4", **fake_kwargs):
    registry, path, sha8 = done_source(tmp_path)
    courses.source_done(registry, "sample", sha8, trove)
    registry = courses.Registry(registry.directory)
    defaults = dict(drive=[reload(registry)["sources"][0]["drive_path"]], nlm_list=[{"id": "src-1"}])
    defaults.update(fake_kwargs)
    return courses.check_source(registry, "sample", sha8, runner=Fake(**defaults)), registry, sha8


def test_check_source_passes_and_uses_expected_argv(tmp_path):
    problems, registry, sha8 = checked(tmp_path)
    assert problems == []
    fake = Fake(drive=[reload(registry)["sources"][0]["drive_path"]], nlm_list=[{"id": "src-1"}])
    courses.check_source(registry, "sample", runner=fake)
    assert ["rclone", "lsjson", "gdrive:", "--drive-root-folder-id", "folder-1", "--files-only", "-R"] in fake.calls
    assert ["trove", "items", "toc", "book-1", "--json", "--no-session"] in fake.calls


def test_check_source_no_sources(tmp_path, capsys):
    registry = make_registry(tmp_path)
    assert courses.check_source(registry, "sample", runner=Fake()) == []
    assert courses.main(["--term", str(registry.directory), "check-source", "sample"]) == 0
    assert "no sources" in capsys.readouterr().out


def test_check_source_missing_in_drive(tmp_path):
    problems, _, _ = checked(tmp_path, drive=["other.pdf"])
    assert len(problems) == 1 and "Drive" in problems[0]


def test_check_source_missing_in_notebook(tmp_path):
    problems, _, _ = checked(tmp_path, nlm_list=[{"id": "zzz"}])
    assert len(problems) == 1 and "NotebookLM" in problems[0]


def test_check_source_not_nested(tmp_path):
    flat = [{"level": 1, "title": "חומרי קריאה", "page": 3}, {"level": 1, "title": "Reading One", "page": 4}]
    problems, _, _ = checked(tmp_path, toc=flat)
    assert len(problems) == 1 and "level-2" in problems[0]


def test_check_source_missing_readings_entry(tmp_path):
    problems, _, _ = checked(tmp_path, toc=[{"level": 1, "title": "Other", "page": 1}])
    assert len(problems) == 1 and "חומרי קריאה" in problems[0]


def test_check_source_requires_done(tmp_path):
    registry, path, sha8 = done_source(tmp_path)
    registry = courses.Registry(registry.directory)
    problems = courses.check_source(registry, "sample", sha8, runner=Fake(drive=[reload(registry)["sources"][0]["drive_path"]], nlm_list=[{"id": "src-1"}]))
    assert len(problems) == 1 and "not done" in problems[0]


def test_check_source_small_source_entry_must_be_titled_for_source(tmp_path):
    toc = [dict(e) for e in TOC]
    toc[1]["title"] = "Another Reading - hint"
    problems, _, _ = checked(tmp_path, toc=toc)
    assert len(problems) == 1 and "not titled" in problems[0]
    toc[1]["title"] = "Reading One - hint"
    (tmp_path / "ok").mkdir()
    problems, _, _ = checked(tmp_path / "ok", toc=toc)
    assert problems == []


def test_check_source_big_source_pointer(tmp_path):
    toc = [dict(e) for e in TOC]
    toc[1]["title"] = "Reading  One"
    problems, _, _ = checked(tmp_path, trove="big-book:1", toc=toc)
    assert problems == []


def test_check_source_big_source_missing_pointer(tmp_path):
    toc = [dict(e) for e in TOC]
    toc[1]["title"] = "Something else"
    problems, _, _ = checked(tmp_path, trove="big-book:1", toc=toc)
    assert len(problems) == 1 and "pointer" in problems[0]


def test_check_source_big_source_empty_book(tmp_path):
    problems, _, _ = checked(tmp_path, trove="big-book:1", other_toc=[])
    assert len(problems) == 1 and "empty ToC" in problems[0]


def test_entry_label_ignores_hint():
    import courses as c
    assert c.entry_label("חומרי קריאה - רשימת המקורות") == "חומרי קריאה"
    assert c.entry_label("תמלולי שיעורים") == "תמלולי שיעורים"


def test_entry_label_with_dash_in_source_title_matches_by_prefix():
    import courses as c
    wanted = c.normalise_name("Baumgarten - Reflections on Poetry (1954)")
    title = c.normalise_name("Baumgarten - Reflections on Poetry (1954) - Reading notes for the 1954 translation")
    assert title.startswith(wanted + " - ")


def test_second_add_source_waits_for_registration_lock_then_dedupes(tmp_path):
    import threading
    import time
    registry = make_registry(tmp_path)
    path = pdf(tmp_path)
    first, second = Fake(), Fake()
    results = []
    with courses._registration_lock(registry.directory, "sample"):
        thread = threading.Thread(target=lambda: results.append(courses.add_source(registry, path, "sample", runner=second)))
        thread.start()
        time.sleep(0.3)
        assert thread.is_alive() and not second.calls  # blocked on the per-course lock, nothing uploaded
        courses._add_source_locked(registry, path, "sample", title=None, origin="other", origin_ref=None, runner=first,
                                   transcript=False, lesson_date=None, lesson_time=None)
    thread.join(5)
    assert not thread.is_alive()
    assert results[0]["status"] == "already added"
    assert not second.of("nlm", "source", "add") and not second.of("rclone", "copyto")
    assert len(first.of("nlm", "source", "add")) == 1


class RecordingFake(Fake):
    def __call__(self, command, **kwargs):
        if command[:3] == ["nlm", "content", "source"]:
            self.calls.append(command)
            return subprocess.CompletedProcess(command, 0, json.dumps({"content": "words of the lesson"}), "")
        return super().__call__(command, **kwargs)


def test_explicit_media_kind_accepts_any_filename_real_ingest(tmp_path):
    registry = make_registry(tmp_path)
    stream = tmp_path / "stream.bin"
    stream.write_bytes(b"opaque recording bytes")
    result = courses.add_source(registry, stream, "sample", origin="lemida", runner=RecordingFake(), kind="media",
                                lesson_date="2026-10-12", lesson_time="1204")
    assert result["status"] == "ingested" and result["lesson_key"] == "2026-10-12-1204"
    queued = sorted(p.name for p in (registry.directory / "queue").glob("*.json"))
    assert queued == ["sample-2026-10-12-1204.json"]
    assert list((registry.directory / "queue" / "sources").glob("*.json")) == []
    assert reload(registry)["sources"][0]["kind"] == "media"


def test_auto_kind_for_unknown_extension_is_document_and_bad_kind_rejected(tmp_path):
    registry = make_registry(tmp_path)
    stream = tmp_path / "stream.bin"
    stream.write_bytes(b"opaque")
    result = courses.add_source(registry, stream, "sample", runner=Fake())
    assert result["status"] == "added" and list((registry.directory / "queue" / "sources").glob("*.json"))
    with pytest.raises(courses.IngestError, match="invalid kind"):
        courses.add_source(registry, stream, "sample", runner=Fake(), kind="video")


def test_media_ingests_snapshot_and_original_time_survives_deletion(tmp_path):
    registry = make_registry(tmp_path)
    original = tmp_path / "20261012 120430-ABCDEF12.m4a"
    original.write_bytes(b"voice memo bytes")
    result = courses.add_source(registry, original, "sample", origin="recording", runner=RecordingFake())
    original.unlink()
    assert result["lesson_key"] == "2026-10-12-1204" and result["date"] == "2026-10-12"
    snapshot = Path(reload(registry)["sources"][0]["file"])
    meta = json.loads((registry.directory / "lessons" / "sample" / "2026-10-12-1204" / "meta.json").read_text())
    assert Path(meta["audio_path"]) == snapshot.resolve() and snapshot.is_file() and snapshot.parent.name == "sample"
    assert meta["audio_path"] != str(original.resolve())
