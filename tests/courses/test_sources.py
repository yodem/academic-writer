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
              "manuscript_id": "ms-1", "book_id": "book-1", "drive_folder_id": "folder-1", "lessons": []}
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
            out = ""
        elif command[0] == "rclone" and command[1] == "lsjson":
            out = json.dumps([{"Name": n} for n in self.drive])
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
    assert fake.of("rclone", "copyto") == [["rclone", "copyto", str(path), "mydrive:01 - Reading One.pdf", "--drive-root-folder-id", "folder-1"]]
    assert fake.of("nlm", "source", "add") == [["nlm", "source", "add", "nb-1", "--file", str(path), "--title", "Reading One", "--wait", "--json"]]
    record = reload(registry)["sources"][0]
    assert record["sha256"] == sha and record["sha8"] == sha[:8]
    assert (record["title"], record["origin"], record["origin_ref"]) == ("Reading One", "lemida", "mod/42")
    assert record["drive"] is True and record["notebook_source_id"] == "src-1" and record["trove"] is None
    assert record["status"] == "queued" and record["added_at"]
    job = json.loads((registry.directory / "queue/sources" / f"sample-{sha[:8]}.json").read_text())
    assert job == {"slug": "sample", "sha8": sha[:8], "title": "Reading One", "file": str(path.resolve()), "pages": 7,
                   "kind": "pdf", "book_id": "book-1", "manuscript_id": "ms-1", "course_name": "Sample Course"}


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


def test_audio_delegates_to_ingest(tmp_path, monkeypatch):
    registry = make_registry(tmp_path)
    seen = {}
    def fake_ingest(reg, audio, **kwargs):
        seen.update(audio=audio, kwargs=kwargs)
        return {"status": "ingested"}
    monkeypatch.setattr(courses, "ingest_recording", fake_ingest)
    audio = tmp_path / "lesson.m4a"
    audio.write_bytes(b"a")
    fake = Fake()
    assert courses.add_source(registry, audio, "sample", runner=fake) == {"status": "ingested"}
    assert seen["kwargs"]["course_slug"] == "sample" and fake.calls == []


def done_source(tmp_path, registry=None, **extra):
    path = pdf(tmp_path)
    registry = registry or make_registry(tmp_path)
    courses.add_source(registry, path, "sample", runner=Fake())
    sha8 = reload(registry)["sources"][0]["sha8"]
    return registry, path, sha8


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
    defaults = dict(drive=[path.name], nlm_list=[{"id": "src-1"}])
    defaults.update(fake_kwargs)
    return courses.check_source(registry, "sample", sha8, runner=Fake(**defaults)), registry, sha8


def test_check_source_passes_and_uses_expected_argv(tmp_path):
    problems, registry, sha8 = checked(tmp_path)
    assert problems == []
    fake = Fake(drive=["01 - Reading One.pdf"], nlm_list=[{"id": "src-1"}])
    courses.check_source(registry, "sample", runner=fake)
    assert ["rclone", "lsjson", "gdrive:", "--drive-root-folder-id", "folder-1", "--files-only"] in fake.calls
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
    problems = courses.check_source(registry, "sample", sha8, runner=Fake(drive=[path.name], nlm_list=[{"id": "src-1"}]))
    assert len(problems) == 1 and "not done" in problems[0]


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
