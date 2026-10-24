import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src/scripts/courses"))
import courses
import drive_layout
from test_sources import Fake, checked, done_source, make_registry, pdf, reload

COURSE = {"slug": "sample", "lessons": [{"lesson_key": "2026-10-05-0900"}, {"lesson_key": "2026-10-12-1204"}],
          "tasks": [{"id": "t-a"}, {"id": "t-b"}]}
BARTON = "Barton, John. 1990. History. Oxford: OUP."


def src(**fields):
    base = {"sha256": "a" * 64, "file": "/s/abcd1234-notes.pdf", "title": "Notes", "origin": "other"}
    base.update(fields)
    return base


def listing(*paths):
    return [{"Path": p, "Name": p.rsplit("/", 1)[-1], "ID": f"id-{i}", "IsDir": False} for i, p in enumerate(paths)]


@pytest.mark.parametrize("fields, folder", [
    ({"kind": "media", "lesson_key": "2026-10-12-1204"}, "שיעורים/שיעור 02"),
    ({"kind": "media"}, "לא ממוין"),
    ({"tasks": ["t-b"], "title": "Essay"}, "מטלות/מטלה 2"),
    ({"origin": "library", "citation": BARTON}, "קריאות/Barton, John. 1990. History. Oxford: OUP"),
    ({"title": "סילבוס הקורס"}, "00 כללי"),
    ({"title": "Syllabus 2026"}, "00 כללי"),
    ({"title": "Notes"}, "לא ממוין"),
])
def test_folder_for_buckets(fields, folder):
    assert drive_layout.folder_for(COURSE, src(**fields)) == folder


def test_drive_path_for_uses_chicago_name_inside_folder():
    taken = {}
    path = drive_layout.drive_path_for(COURSE, src(origin="library", citation=BARTON, file="/s/abcd1234-x.pdf"), taken)
    assert path == f"קריאות/{BARTON.rstrip('.')}/{BARTON.rstrip('.')}.pdf"
    assert taken == {f"קריאות/{BARTON.rstrip('.')}": {f"{BARTON.rstrip('.')}.pdf"}}


def test_plan_reorg_moves_each_listed_source_and_skips_missing(tmp_path):
    course = dict(COURSE, sources=[
        src(sha256="1" * 64, file="/s/11111111-Reading One.pdf", title="Reading One", origin="library", citation=BARTON),
        src(sha256="2" * 64, file="/s/22222222-syllabus.pdf", title="Syllabus"),
        src(sha256="3" * 64, file="/s/33333333-lesson.m4a", title="Lesson 2", kind="media", lesson_key="2026-10-12-1204"),
        src(sha256="4" * 64, file="/s/44444444-missing.pdf", title="Missing"),
    ])
    plan = drive_layout.plan_reorg(course, listing("22222222-syllabus.pdf", "11111111-Reading One.pdf", "33333333-lesson.m4a", "other.docx"))
    by_sha = {step["sha256"]: step for step in plan}
    assert set(by_sha) == {"1" * 64, "2" * 64, "3" * 64}
    assert by_sha["2" * 64] == {"id": "id-0", "old": "22222222-syllabus.pdf", "new": "00 כללי/Syllabus.pdf", "sha256": "2" * 64}
    assert by_sha["3" * 64]["new"] == "שיעורים/שיעור 02/Lesson 2.m4a"
    assert by_sha["1" * 64]["new"] == f"קריאות/{BARTON.rstrip('.')}/{BARTON.rstrip('.')}.pdf"


def test_plan_reorg_collision_gets_suffix_against_listed_files():
    course = dict(COURSE, sources=[
        src(sha256="1" * 64, file="/s/11111111-a.pdf", title="Syllabus"),
        src(sha256="2" * 64, file="/s/22222222-b.pdf", title="Syllabus"),
    ])
    plan = drive_layout.plan_reorg(course, listing("11111111-a.pdf", "22222222-b.pdf", "00 כללי/Syllabus.pdf"))
    names = {step["sha256"]: step["new"] for step in plan}
    assert names["1" * 64] == "00 כללי/Syllabus (2).pdf"
    assert names["2" * 64] == "00 כללי/Syllabus (3).pdf"


def test_plan_reorg_file_already_at_its_target_is_not_moved():
    course = dict(COURSE, sources=[src(sha256="3" * 64, file="/s/33333333-syllabus.pdf", title="Syllabus", drive_path="00 כללי/Syllabus.pdf")])
    assert drive_layout.plan_reorg(course, listing("00 כללי/Syllabus.pdf")) == []


def test_apply_reorg_moves_and_logs_each_step(tmp_path):
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    log = tmp_path / "logs" / "drive-reorg.jsonl"
    plan = [{"id": "id-0", "old": "a.pdf", "new": "00 כללי/a.pdf", "sha256": "1" * 64}]
    drive_layout.apply_reorg(plan, "gdrive", "folder-1", log, runner=runner)
    assert calls == [["rclone", "moveto", "gdrive:a.pdf", "gdrive:00 כללי/a.pdf", "--drive-root-folder-id", "folder-1"]]
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [(e["old"], e["new"], e["id"]) for e in entries] == [("a.pdf", "00 כללי/a.pdf", "id-0")]


def _make(tmp_path):
    registry = make_registry(tmp_path, term={"drive_remote": "gdrive"})
    course = json.loads((registry.directory / "sample.json").read_text(encoding="utf-8"))
    course["sources"] = [src(sha256="1" * 64, file="/s/11111111-syllabus.pdf", title="Syllabus", notebook_source_id="nlm-1")]
    (registry.directory / "sample.json").write_text(json.dumps(course), encoding="utf-8")
    return registry.directory


class ReorgFake:
    def __init__(self, drive):
        self.drive = drive
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if command[:2] == ["rclone", "lsjson"]:
            out = json.dumps(self.drive)
        else:
            out = ""
        return subprocess.CompletedProcess(command, 0, out, "")


def test_drive_reorg_without_apply_only_returns_manifest(tmp_path):
    registry = courses.Registry(_make(tmp_path))
    fake = ReorgFake(listing("11111111-syllabus.pdf"))
    manifests = courses.drive_reorg(registry, ["sample"], apply=False, runner=fake)
    assert manifests[0]["slug"] == "sample"
    assert manifests[0]["moves"][0]["new"] == "00 כללי/Syllabus.pdf"
    assert manifests[0]["moves"][0]["nlm_title"] == "Syllabus"
    assert [c[:2] for c in fake.calls] == [["rclone", "lsjson"]]
    assert not (registry.directory / "logs").exists()
    assert json.loads((registry.directory / "sample.json").read_text(encoding="utf-8"))["sources"][0].get("drive_path") is None


def test_drive_reorg_apply_moves_renames_nlm_and_records_drive_path(tmp_path):
    registry = courses.Registry(_make(tmp_path))
    fake = ReorgFake(listing("11111111-syllabus.pdf"))
    courses.drive_reorg(registry, ["sample"], apply=True, runner=fake)
    assert ["rclone", "moveto", "gdrive:11111111-syllabus.pdf", "gdrive:00 כללי/Syllabus.pdf", "--drive-root-folder-id", "folder-1"] in fake.calls
    assert ["nlm", "source", "rename", "nlm-1", "Syllabus", "--notebook", "nb-1"] in fake.calls
    source = json.loads((registry.directory / "sample.json").read_text(encoding="utf-8"))["sources"][0]
    assert source["drive_path"] == "00 כללי/Syllabus.pdf"
    assert len(list((registry.directory / "logs").glob("drive-reorg-*.jsonl"))) == 1


def test_drive_reorg_cli_prints_manifest_without_apply(tmp_path, monkeypatch, capsys):
    directory = _make(tmp_path)
    fake = ReorgFake(listing("11111111-syllabus.pdf"))
    monkeypatch.setattr(courses.subprocess, "run", fake)
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(directory.parent))
    monkeypatch.setenv("ACADEMIC_TERM", directory.name)
    assert courses.main(["drive-reorg", "--course", "sample"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed[0]["moves"][0]["new"] == "00 כללי/Syllabus.pdf"
    assert not any(c[1:2] == ["moveto"] for c in fake.calls)


def test_check_source_recursive_matches_drive_path_in_subfolder(tmp_path):
    registry, path, sha8 = done_source(tmp_path)
    courses.source_done(registry, "sample", sha8, "book-1:4")
    registry = courses.Registry(registry.directory)
    sha = reload(registry)["sources"][0]["sha256"]
    courses._update_source(registry, "sample", sha, drive_path="קריאות/Reading One/Reading One.pdf")
    registry = courses.Registry(registry.directory)
    drive = [{"Path": "קריאות/Reading One/Reading One.pdf", "Name": "Reading One.pdf"}]
    fake = Fake(drive=drive, nlm_list=[{"id": "src-1"}])
    assert courses.check_source(registry, "sample", sha8, runner=fake) == []
    assert ["rclone", "lsjson", "gdrive:", "--drive-root-folder-id", "folder-1", "--files-only", "-R"] in fake.calls
    missing = Fake(drive=[{"Path": "Reading One.pdf", "Name": "Reading One.pdf"}], nlm_list=[{"id": "src-1"}])
    assert any("is not in the Drive folder" in p for p in courses.check_source(registry, "sample", sha8, runner=missing))


def test_add_source_uploads_into_kind_folder_with_chicago_name(tmp_path):
    registry = make_registry(tmp_path, term={"drive_remote": "gdrive"})
    path = pdf(tmp_path, "syllabus.pdf")
    fake = Fake()
    courses.add_source(registry, path, "sample", title="Syllabus", origin="other", runner=fake)
    copies = fake.of("rclone", "copyto")
    assert len(copies) == 1
    assert copies[0][3] == "gdrive:00 כללי/Syllabus.pdf" and copies[0][4:] == ["--drive-root-folder-id", "folder-1"]
    assert fake.of("nlm", "source", "add")[0][-4:-2] == ["--title", "Syllabus"]
    assert reload(registry)["sources"][0]["drive_path"] == "00 כללי/Syllabus.pdf"


def test_add_source_collision_in_drive_folder_gets_suffix(tmp_path):
    registry = make_registry(tmp_path, term={"drive_remote": "gdrive"})
    fake = Fake()
    fake_listing = {"gdrive:00 כללי": ["Syllabus.pdf"]}

    def runner(command, **kwargs):
        if command[:2] == ["rclone", "lsjson"] and command[2] == "gdrive:00 כללי":
            return subprocess.CompletedProcess(command, 0, json.dumps([{"Name": n} for n in fake_listing["gdrive:00 כללי"]]), "")
        return fake(command, **kwargs)

    courses.add_source(registry, pdf(tmp_path, "syllabus.pdf", b"%PDF other"), "sample", title="Syllabus", origin="other", runner=runner)
    assert fake.of("rclone", "copyto")[0][3] == "gdrive:00 כללי/Syllabus (2).pdf"
