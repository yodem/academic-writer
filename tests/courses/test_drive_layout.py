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
TOP = ("00 כללי", "שיעורים", "קריאות", "מטלות", "לא ממוין")


def src(**fields):
    base = {"sha256": "a" * 64, "file": "/s/abcd1234-notes.pdf", "title": "Notes", "origin": "other"}
    base.update(fields)
    return base


def item(path, is_dir=False, ident=None):
    return {"Path": path, "Name": path.rsplit("/", 1)[-1], "ID": ident or f"id-{path}", "IsDir": is_dir}


def listing(*paths):
    return [item(p) for p in paths]


def _apply_in_memory(paths, plan):
    """The listing after the plan's moves: a folder step carries everything under it, a file step renames one path."""
    dirs = {entry["Path"] for entry in paths if entry["IsDir"]}
    moved = {step["old"]: step["new"] for step in plan}
    out = []
    for entry in paths:
        path = entry["Path"]
        for old, new in moved.items():
            if path == old or (old in dirs and path.startswith(old + "/")):
                path = new + path[len(old):]
                break
        out.append(dict(entry, Path=path, Name=path.rsplit("/", 1)[-1]))
    return out


@pytest.mark.parametrize("fields, folder", [
    ({"kind": "media", "lesson_key": "2026-10-12-1204"}, "שיעורים/שיעור 02"),
    ({"kind": "media"}, "לא ממוין"),
    ({"tasks": ["t-b"], "title": "Essay"}, "מטלות/מטלה 2"),
    ({"origin": "library", "citation": BARTON}, "קריאות/Barton, John. 1990. History. Oxford: OUP"),
    ({"title": "סילבוס הקורס"}, "00 כללי"),
    ({"title": "Syllabus 2026"}, "00 כללי"),
    ({"title": "Notes"}, "קריאות/Notes"),
    ({"title": "Notes", "file": "/s/abcd1234-notes.zip"}, "לא ממוין"),
])
def test_folder_for_buckets(fields, folder):
    assert drive_layout.folder_for(COURSE, src(**fields)) == folder


def test_lesson_name_without_lesson_key_goes_to_lesson_folder():
    assert drive_layout.folder_for(COURSE, src(title="שיעור 1 תשפז", file="/s/121aac44-x.docx")) == "שיעורים/שיעור 01"
    assert drive_layout.folder_for(COURSE, src(title="Lesson 3", file="/s/x.pdf")) == "שיעורים/שיעור 03"


def test_task_name_without_task_list_goes_to_task_folder():
    assert drive_layout.folder_for(COURSE, src(title="מטלה 2 הגשה", file="/s/x.docx")) == "מטלות/מטלה 2"


def test_reading_without_citation_goes_to_readings_by_its_cleaned_stem():
    assert drive_layout.folder_for(COURSE, src(title="", file="/s/3211905 - CohenAttributes.pdf")) == "קריאות/CohenAttributes"


def test_media_by_date_goes_to_the_lesson_with_that_date():
    assert drive_layout.folder_for(COURSE, src(kind="media", title="", file="/s/talk 2026-10-12.m4a")) == "שיעורים/שיעור 02"
    assert drive_layout.folder_for(COURSE, src(kind="media", title="", file="/s/talk 2026-11-01.m4a")) == "לא ממוין"


def test_display_name_is_unquoted_and_loses_lemida_and_hash_prefixes():
    source = src(title="", file="/s/1a74cae8-lemida-cm3291152 - %D7%A2%D7%A8%D7%9A%20%D7%90.pdf")
    assert drive_layout.display_title(source) == "ערך א"
    assert drive_layout.folder_for(COURSE, source) == "קריאות/ערך א"


def test_drive_name_is_short_citation_and_nlm_title_is_full_chicago():
    ref = {"meta": {"authors": ["John Barton"], "year": 1990, "title": "History and Rhetoric in the Prophets",
                    "place": "Oxford", "publisher": "OUP"}}
    source = src(title="", ref=ref, file="/s/bc16a3f6-barton.pdf")
    assert drive_layout.drive_name(source) == "Barton, History and Rhetoric in the Prophets (1990)"
    assert drive_layout.display_title(source) == "Barton, John. 1990. History and Rhetoric in the Prophets. Oxford: OUP"
    assert drive_layout.drive_path_for(COURSE, source, {}) == (
        "קריאות/Barton, History and Rhetoric in the Prophets (1990)/Barton, History and Rhetoric in the Prophets (1990).pdf")


def test_short_name_also_holds_when_the_citation_string_is_recorded():
    full = 'Barton, John. 1990. "History and Rhetoric in the Prophets." In The Bible as Rhetoric, edited by Martin Warner, 51–64. London and New York: Routledge.'
    ref = {"citation": full, "meta": {"authors": ["John Barton"], "year": 1990, "title": "History and Rhetoric in the Prophets"}}
    source = src(title="", ref=ref, file="/s/bc16a3f6-barton.md")
    assert drive_layout.drive_name(source) == "Barton, History and Rhetoric in the Prophets (1990)"
    assert drive_layout.display_title(source) == full.rstrip(".")


def test_drive_path_for_uses_chicago_name_inside_folder():
    taken = {}
    path = drive_layout.drive_path_for(COURSE, src(origin="library", citation=BARTON, file="/s/abcd1234-x.pdf"), taken)
    assert path == f"קריאות/{BARTON.rstrip('.')}/{BARTON.rstrip('.')}.pdf"
    assert taken == {f"קריאות/{BARTON.rstrip('.')}": {f"{BARTON.rstrip('.')}.pdf"}}


def test_plan_reorg_moves_each_listed_source_and_skips_missing():
    course = dict(COURSE, sources=[
        src(sha256="1" * 64, file="/s/11111111-Reading One.pdf", title="Reading One", origin="library", citation=BARTON),
        src(sha256="2" * 64, file="/s/22222222-syllabus.pdf", title="Syllabus"),
        src(sha256="3" * 64, file="/s/33333333-lesson.m4a", title="Lesson 2", kind="media", lesson_key="2026-10-12-1204"),
        src(sha256="4" * 64, file="/s/44444444-missing.pdf", title="Missing"),
    ])
    plan = drive_layout.plan_reorg(course, listing("22222222-syllabus.pdf", "11111111-Reading One.pdf", "33333333-lesson.m4a"))
    by_sha = {step["sha256"]: step for step in plan}
    assert set(by_sha) == {"1" * 64, "2" * 64, "3" * 64}
    assert by_sha["2" * 64] == {"id": "id-22222222-syllabus.pdf", "old": "22222222-syllabus.pdf", "new": "00 כללי/Syllabus.pdf", "sha256": "2" * 64}
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


def test_unregistered_root_file_with_a_registry_stem_follows_its_source():
    name = "Barton, History and Rhetoric in the Prophets (1990)"
    course = dict(COURSE, sources=[src(sha256="b" * 64, file="/s/bc16a3f6-barton-1990-history-rhetoric.md", title=name, origin="library")])
    plan = drive_layout.plan_reorg(course, listing("barton-1990-history-rhetoric.pdf"))
    assert plan == [{"id": "id-barton-1990-history-rhetoric.pdf", "old": "barton-1990-history-rhetoric.pdf",
                     "new": f"קריאות/{name}/{name}.pdf", "sha256": ""}]


def test_unregistered_root_lesson_document_goes_to_its_lesson_folder():
    plan = drive_layout.plan_reorg(COURSE, listing("שיעור 1 תשפז.docx"))
    assert [step["new"] for step in plan] == ["שיעורים/שיעור 01/שיעור 1 תשפז.docx"]


def test_unregistered_root_task_syllabus_and_reading_rules():
    plan = drive_layout.plan_reorg(COURSE, listing("מטלה 1.pdf", "סילבוס 2026.pdf", "scan-12.pdf", "photo.zip"))
    assert sorted(step["new"] for step in plan) == sorted([
        "מטלות/מטלה 1/מטלה 1.pdf", "00 כללי/סילבוס 2026.pdf", "קריאות/scan-12/scan-12.pdf", "לא ממוין/photo.zip"])


def test_unregistered_root_media_by_date_and_undated_media():
    plan = drive_layout.plan_reorg(COURSE, listing("2026-10-12 talk.m4a", "random.mp3"))
    assert sorted(step["new"] for step in plan) == sorted(["שיעורים/שיעור 02/2026-10-12 talk.m4a", "לא ממוין/random.mp3"])


def test_legacy_root_folders_move_as_folders_and_keep_their_files():
    paths = [item("מטלה 1", True, "dir-1"), item("מטלה 1/notes.pdf"), item("שיעור 2", True, "dir-2")]
    assert drive_layout.plan_reorg(dict(COURSE, sources=[]), paths) == [
        {"id": "dir-1", "old": "מטלה 1", "new": "מטלות/מטלה 1", "sha256": ""},
        {"id": "dir-2", "old": "שיעור 2", "new": "שיעורים/שיעור 02", "sha256": ""},
    ]


def test_legacy_folder_whose_target_exists_merges_its_files_with_unique_names():
    paths = [item("מטלה 1", True), item("מטלה 1/notes.pdf", ident="id-n"), item("מטלות/מטלה 1", True),
             item("מטלות/מטלה 1/notes.pdf")]
    assert drive_layout.plan_reorg(dict(COURSE, sources=[]), paths) == [
        {"id": "id-n", "old": "מטלה 1/notes.pdf", "new": "מטלות/מטלה 1/notes (2).pdf", "sha256": ""}]


def test_files_inside_top_folders_are_never_moved():
    assert drive_layout.plan_reorg(COURSE, listing("שיעורים/שיעור 01/unknown.pdf", "לא ממוין/x.zip")) == []


def test_nevua_fixture_leaves_no_file_at_root():
    course = {"slug": "nevua", "lessons": [], "tasks": [], "sources": [
        src(sha256="1" * 64, file="/s/223a5648-פתיחה תשפז.docx", title="פתיחה והנחיות לקורס", origin="lemida"),
        src(sha256="2" * 64, file="/s/121aac44-תפיסות יסוד בספרות הנבואה שיעור 1 תשפז.docx", title="שיעור 1", origin="lemida"),
        src(sha256="3" * 64, file="/s/bc16a3f6-barton-1990-history-rhetoric.md", title="Barton, History and Rhetoric in the Prophets (1990)", origin="library"),
        src(sha256="4" * 64, file="/s/05bd5cad-hoffman-2001-yirmiyahu.md", title="הופמן, ירמיהו (מקרא לישראל) עמ' 23–26", origin="library"),
        src(sha256="5" * 64, file="/s/a2652412-pedersen-index.md", title="Bezemer, Index to the Biblical References in Pedersen's Israel (1983)", origin="library"),
        src(sha256="6" * 64, file="/s/4a9b728a-gilad-2011-sifrut-hanevua.md", title="גלעד, ספרות הנבואה (ספרות המקרא, תשע\"א) עמ' 307–324", origin="library"),
        src(sha256="7" * 64, file="/s/6b471b0d-malamat-1963-mari.md", title="מלמט, מארי (אנציקלופדיה מקראית ד) טורים 559–579", origin="library"),
    ]}
    names = ["223a5648-פתיחה תשפז.docx", "121aac44-תפיסות יסוד בספרות הנבואה שיעור 1 תשפז.docx",
             "bc16a3f6-barton-1990-history-rhetoric.md", "05bd5cad-hoffman-2001-yirmiyahu.md",
             "a2652412-pedersen-index.md", "4a9b728a-gilad-2011-sifrut-hanevua.md", "6b471b0d-malamat-1963-mari.md",
             "barton-1990-history-rhetoric.pdf", "gilad-2011-sifrut-hanevua.pdf", "hoffman-2001-yirmiyahu.pdf",
             "malamat-1963-mari.pdf", "pedersen-index.pdf"]
    paths = [item(n) for n in names] + [item("מטלה 1", True, "dir-1"), item("מטלה 1/ספר.pdf")]
    plan = drive_layout.plan_reorg(course, paths)
    assert len(plan) == 13  # 12 root files and the מטלה 1 folder
    after = _apply_in_memory(paths, plan)
    root_left = [entry["Path"] for entry in after if "/" not in entry["Path"] and entry["Path"] not in TOP]
    assert root_left == []


def test_plan_reorg_is_idempotent_after_its_moves_are_applied():
    course = dict(COURSE, sources=[
        src(sha256="1" * 64, file="/s/11111111-syllabus.pdf", title="Syllabus"),
        src(sha256="2" * 64, file="/s/22222222-x.pdf", title="Reading Two", origin="library", citation=BARTON),
    ])
    paths = listing("11111111-syllabus.pdf", "22222222-x.pdf", "scan.pdf", "סילבוס.pdf") + [item("מטלה 1", True), item("מטלה 1/n.pdf")]
    plan = drive_layout.plan_reorg(course, paths)
    assert plan
    after = _apply_in_memory(paths, plan)
    done = {step["sha256"]: step["new"] for step in plan if step["sha256"]}
    recorded = dict(course, sources=[dict(s, drive_path=done[s["sha256"]]) if s["sha256"] in done else s for s in course["sources"]])
    assert drive_layout.plan_reorg(recorded, after) == []


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


def test_drive_reorg_lists_the_root_recursively_with_dirs(tmp_path):
    registry = courses.Registry(_make(tmp_path))
    fake = ReorgFake(listing("11111111-syllabus.pdf"))
    courses.drive_reorg(registry, ["sample"], apply=False, runner=fake)
    assert fake.calls[0] == ["rclone", "lsjson", "gdrive:", "--drive-root-folder-id", "folder-1", "-R"]


def test_drive_reorg_apply_moves_renames_nlm_and_records_drive_path(tmp_path):
    registry = courses.Registry(_make(tmp_path))
    fake = ReorgFake(listing("11111111-syllabus.pdf"))
    courses.drive_reorg(registry, ["sample"], apply=True, runner=fake)
    assert ["rclone", "moveto", "gdrive:11111111-syllabus.pdf", "gdrive:00 כללי/Syllabus.pdf", "--drive-root-folder-id", "folder-1"] in fake.calls
    assert ["nlm", "source", "rename", "nlm-1", "Syllabus", "--notebook", "nb-1"] in fake.calls
    source = json.loads((registry.directory / "sample.json").read_text(encoding="utf-8"))["sources"][0]
    assert source["drive_path"] == "00 כללי/Syllabus.pdf"
    assert len(list((registry.directory / "logs").glob("drive-reorg-*.jsonl"))) == 1


def test_drive_reorg_manifest_gives_no_notebook_title_to_unregistered_files(tmp_path):
    registry = courses.Registry(_make(tmp_path))
    fake = ReorgFake(listing("11111111-syllabus.pdf", "scan.pdf"))
    manifests = courses.drive_reorg(registry, ["sample"], apply=False, runner=fake)
    scan = next(move for move in manifests[0]["moves"] if move["old"] == "scan.pdf")
    assert scan["sha256"] == "" and scan["notebook_source_id"] is None and scan["nlm_title"] is None
    assert scan["new"] == "קריאות/scan/scan.pdf"


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


def test_slides_go_under_lessons():
    assert drive_layout.folder_for({}, {"title": "Cohen", "file": "/x/3271974 - Cohen.pptx"}) == "שיעורים/שקפים"
    assert drive_layout.folder_for({}, {"title": "שיעור 3", "file": "/x/s.pptx"}) == "שיעורים/שיעור 03"
