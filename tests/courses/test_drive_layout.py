import hashlib
import fcntl
import json
import subprocess
import sys
import threading
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
    moved = {step["old"]: step["new"] for step in plan if step["op"] == "move"}
    removed = {step["old"] for step in plan if step["op"] == "rmdir"}
    out = []
    for entry in paths:
        path = entry["Path"]
        if path in removed:
            continue
        for old, new in moved.items():
            if path == old or (old in dirs and path.startswith(old + "/")):
                path = new + path[len(old):]
                break
        out.append(dict(entry, Path=path, Name=path.rsplit("/", 1)[-1]))
    # Emptied legacy folders are kept on purpose (no deletes); a folder with no file under it does not count as left over.
    files = [e["Path"] for e in out if not e["IsDir"]]
    return [e for e in out if not e["IsDir"] or any(f.startswith(e["Path"] + "/") for f in files)]


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
    assert by_sha["2" * 64] == {"op": "move", "id": "id-22222222-syllabus.pdf", "old": "22222222-syllabus.pdf", "new": "00 כללי/Syllabus.pdf",
                                "sha256": "2" * 64, "final": True}
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
    assert plan == [{"op": "move", "id": "id-barton-1990-history-rhetoric.pdf", "old": "barton-1990-history-rhetoric.pdf",
                     "new": f"קריאות/{name}/{name}.pdf", "sha256": "", "final": True}]


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


def test_legacy_root_folders_are_emptied_file_by_file_then_removed():
    paths = [item("מטלה 1", True, "dir-1"), item("מטלה 1/notes.pdf", ident="id-n"), item("שיעור 2", True, "dir-2")]
    assert drive_layout.plan_reorg(dict(COURSE, sources=[]), paths) == [
        {"op": "move", "id": "id-n", "old": "מטלה 1/notes.pdf", "new": "מטלות/מטלה 1/notes.pdf", "sha256": "", "final": True},
    ]


def test_legacy_folder_whose_target_exists_merges_its_files_with_unique_names():
    paths = [item("מטלה 1", True), item("מטלה 1/notes.pdf", ident="id-n"), item("מטלות/מטלה 1", True),
             item("מטלות/מטלה 1/notes.pdf")]
    assert drive_layout.plan_reorg(dict(COURSE, sources=[]), paths) == [
        {"op": "move", "id": "id-n", "old": "מטלה 1/notes.pdf", "new": "מטלות/מטלה 1/notes (2).pdf", "sha256": "", "final": True},
    ]


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
    assert len([s for s in plan if s["op"] == "move"]) == 13  # 12 root files and the file inside מטלה 1
    assert [s for s in plan if s["op"] == "rmdir"] == []  # emptied legacy folders are kept
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
    done = {step["sha256"]: step["new"] for step in plan if step["sha256"] and step["op"] == "move"}
    recorded = dict(course, sources=[dict(s, drive_path=done[s["sha256"]]) if s["sha256"] in done else s for s in course["sources"]])
    assert drive_layout.plan_reorg(recorded, after) == []


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
    assert fake.calls[0] == ["rclone", "lsjson", "gdrive:", "--drive-root-folder-id", "folder-1", "-R", "--hash"]


def test_apply_reorg_moves_by_id_and_journals_intent_before_done(tmp_path):
    calls = []
    moved = []

    def runner(command, **kwargs):
        calls.append(command)
        if command[:3] == ["rclone", "backend", "moveid"]:
            moved.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if "--stat" in command:  # before the move: 3, nothing there; after it: the moved file's id
            return subprocess.CompletedProcess(command, 0, json.dumps({"ID": "id-0"}), "") if moved else subprocess.CompletedProcess(command, 3, "", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    log = tmp_path / "logs" / "drive-reorg.jsonl"
    plan = [{"op": "move", "id": "id-0", "old": "a.pdf", "new": "00 כללי/a.pdf", "sha256": "1" * 64, "final": True}]
    drive_layout.apply_reorg(plan, "gdrive", "folder-1", log, runner=runner, slug="sample")
    assert calls == [
        ["rclone", "mkdir", "gdrive:00 כללי", "--drive-root-folder-id", "folder-1"],
        ["rclone", "lsjson", "gdrive:00 כללי/a.pdf", "--stat", "--drive-root-folder-id", "folder-1"],
        ["rclone", "backend", "moveid", "gdrive:", "id-0", "gdrive:00 כללי/a.pdf", "--ignore-existing", "--drive-server-side-across-configs", "--drive-root-folder-id", "folder-1"],
        ["rclone", "lsjson", "gdrive:00 כללי/a.pdf", "--stat", "--drive-root-folder-id", "folder-1"],
    ]
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [line["phase"] for line in lines] == ["plan", "intent", "done"]
    assert [(line["phase"], line["kind"]) for line in lines[1:]] == [("intent", "drive_move"), ("done", "drive_move")]
    for line in lines[1:]:
        assert {"remote", "root", "slug", "op_id", "seq", "file_id", "old", "new"} <= set(line)
        assert (line["remote"], line["root"], line["slug"]) == ("gdrive", "folder-1", "sample")
    assert lines[1]["op_id"] == lines[2]["op_id"] and [line["seq"] for line in lines] == [1, 2, 3]


def test_apply_refuses_a_step_without_a_drive_id_before_any_move(tmp_path):
    calls = []
    log = tmp_path / "logs" / "drive-reorg.jsonl"
    plan = [{"op": "move", "id": "", "old": "a.pdf", "new": "00 כללי/a.pdf", "sha256": "", "final": True}]
    with pytest.raises(drive_layout.ReorgError):
        drive_layout.apply_reorg(plan, "gdrive", "folder-1", log, runner=lambda c, **k: calls.append(c))
    assert calls == [] and not log.exists()


class FakeDrive:
    """A stateful Drive keyed by file id. Paths may repeat (Drive allows duplicate names), a move onto an occupied
    path is recorded as a violation and refused, and faults can fail a call before or after it changes anything."""

    def __init__(self, items, *, nightly=False):
        self.items = {}
        self.calls = []
        self.violations = []
        self.faults = {}
        self.counts = {}
        self.nightly = nightly
        self.nlm = []
        self.nlm_fail = 0
        self.list_calls = 0
        self.on_list = None
        self.on_stat = None
        self.on_moveid = None  # called at the start of each moveid: a file can appear after the destination check
        self.skipped = []  # (file id, destination) of each moveid that --ignore-existing skipped
        self.lock_file = None
        self.lock_probe = []
        self._serial = 0
        for path, is_dir in items:
            self.add(path, is_dir)

    def add(self, path, is_dir=False, ident=None):
        self._serial += 1
        ident = ident or f"id-{self._serial}-{path}"
        self.items[ident] = {"Path": path, "Name": path.rsplit("/", 1)[-1], "ID": ident, "IsDir": is_dir}
        return ident

    def path_of(self, ident):
        return self.items[ident]["Path"]

    def paths(self):
        return sorted(item["Path"] for item in self.items.values())

    def files(self):
        return sorted(item["Path"] for item in self.items.values() if not item["IsDir"])

    def id_at(self, path):
        return next(ident for ident, item in self.items.items() if item["Path"] == path)

    def _probe(self):
        if self.lock_file is None:
            return
        handle = open(self.lock_file, "a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            self.lock_probe.append(False)
        except BlockingIOError:
            self.lock_probe.append(True)
        finally:
            handle.close()

    def _fault(self, verb, when):
        n = self.counts[verb]
        if self.faults.get((verb, n)) == when:
            raise subprocess.CalledProcessError(1, verb, "injected fault")

    def _fail(self, command, why):
        self.violations.append((command, why))
        raise subprocess.CalledProcessError(1, command, why)

    def __call__(self, command, **kwargs):
        self.calls.append(list(command))
        ok = subprocess.CompletedProcess(command, 0, "", "")
        if command[:1] == ["pgrep"]:
            return subprocess.CompletedProcess(command, 0, "4242\n", "") if self.nightly else subprocess.CompletedProcess(command, 1, "", "")
        if command[:2] == ["rclone", "lsjson"] and "--stat" in command:
            # the destination check: the entry at exactly this path, or rclone's "not found" (exit 3)
            path = command[2].split(":", 1)[1]
            if self.on_stat:
                self.on_stat(self, path)
            hit = next((item for item in self.items.values() if item["Path"] == path), None)
            if hit is None:
                return subprocess.CompletedProcess(command, 3, "", "object not found")
            return subprocess.CompletedProcess(command, 0, json.dumps(hit), "")
        if command[:2] == ["rclone", "lsjson"]:
            self.list_calls += 1
            if self.on_list:
                self.on_list(self)
            self._probe()
            return subprocess.CompletedProcess(command, 0, json.dumps(list(self.items.values())), "")
        if command[:2] == ["rclone", "mkdir"]:
            path = command[2].split(":", 1)[1]
            for index in range(1, len(path.split("/")) + 1):
                folder = "/".join(path.split("/")[:index])
                if not any(item["Path"] == folder and item["IsDir"] for item in self.items.values()):
                    self.add(folder, True)
            return ok
        if command[:3] == ["rclone", "backend", "moveid"]:
            self.counts["moveid"] = self.counts.get("moveid", 0) + 1
            self._probe()
            if self.on_moveid:
                self.on_moveid(self)
            self._fault("moveid", "before")
            ident, dest = command[4], command[5]
            if ":" not in dest:
                self._fail(command, f"destination {dest!r} has no remote prefix: rclone would treat it as a local path")
            dest = dest.split(":", 1)[1]
            if ident not in self.items:
                self._fail(command, "no such id")
            parent = dest.rpartition("/")[0]
            if parent and not any(item["Path"] == parent and item["IsDir"] for item in self.items.values()):
                self._fail(command, f"parent folder {parent!r} does not exist")
            if any(item["Path"] == dest for item in self.items.values()):
                if "--ignore-existing" in command:  # rclone moveto: skip, leave both files where they are
                    self.skipped.append((ident, dest))
                    return ok
                self._fail(command, f"destination {dest!r} is occupied")
            self.items[ident]["Path"] = dest
            self.items[ident]["Name"] = dest.rsplit("/", 1)[-1]
            self._fault("moveid", "after")
            return ok
        if command[:2] == ["rclone", "rmdir"]:
            path = command[2].split(":", 1)[1]
            if any(item["Path"].startswith(path + "/") or item["Path"] == path and not item["IsDir"] for item in self.items.values()):
                self._fail(command, "directory not empty")
            ident = next((i for i, item in self.items.items() if item["Path"] == path and item["IsDir"]), None)
            if ident is None:
                self._fail(command, "directory not found")
            del self.items[ident]
            return ok
        if command[:3] == ["nlm", "source", "rename"]:
            if self.nlm_fail:
                self.nlm_fail -= 1
                raise subprocess.CalledProcessError(1, command, "injected nlm failure")
            self.nlm.append(command)
        return ok


def _registry_with(tmp_path, sources, tasks=None):
    registry = make_registry(tmp_path, term={"drive_remote": "gdrive"}, tasks=tasks or [])
    course = reload(registry)
    course["sources"] = sources
    (registry.directory / "sample.json").write_text(json.dumps(course), encoding="utf-8")
    return courses.Registry(registry.directory)


def _moves(drive):
    return [c for c in drive.calls if c[:3] == ["rclone", "backend", "moveid"]]


def test_drive_reorg_apply_moves_by_id_renames_nlm_and_records_drive_path(tmp_path):
    registry = _registry_with(tmp_path, [src(sha256="1" * 64, file="/s/11111111-syllabus.pdf", title="Syllabus", notebook_source_id="nlm-1")])
    drive = FakeDrive([("11111111-syllabus.pdf", False)])
    courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    ident = drive.id_at("00 כללי/Syllabus.pdf")
    assert _moves(drive) == [["rclone", "backend", "moveid", "gdrive:", ident, "gdrive:00 כללי/Syllabus.pdf", "--ignore-existing", "--drive-server-side-across-configs", "--drive-root-folder-id", "folder-1"]]
    assert ["nlm", "source", "rename", "nlm-1", "Syllabus", "--notebook", "nb-1"] in drive.nlm
    assert json.loads((registry.directory / "sample.json").read_text(encoding="utf-8"))["sources"][0]["drive_path"] == "00 כללי/Syllabus.pdf"
    assert len(list((registry.directory / "logs").glob("drive-reorg-*-sample.jsonl"))) == 1
    assert drive.violations == []


def test_swap_of_two_registered_files_is_resolved_with_a_temporary_name(tmp_path):
    a = src(sha256="a" * 64, file="/s/aaaa1111-a.pdf", title="Syllabus", drive_path="00 כללי/Syllabus Old.pdf")
    b = src(sha256="b" * 64, file="/s/bbbb2222-b.pdf", title="Syllabus Old", drive_path="00 כללי/Syllabus.pdf")
    registry = _registry_with(tmp_path, [a, b])
    drive = FakeDrive([("00 כללי", True), ("00 כללי/Syllabus Old.pdf", False), ("00 כללי/Syllabus.pdf", False)])
    id_a, id_b = drive.id_at("00 כללי/Syllabus Old.pdf"), drive.id_at("00 כללי/Syllabus.pdf")
    courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    assert drive.violations == []
    assert drive.path_of(id_a) == "00 כללי/Syllabus.pdf" and drive.path_of(id_b) == "00 כללי/Syllabus Old.pdf"
    assert len(_moves(drive)) == 3  # one temporary move breaks the cycle
    recorded = {s["sha256"]: s["drive_path"] for s in json.loads((registry.directory / "sample.json").read_text(encoding="utf-8"))["sources"]}
    assert recorded == {"a" * 64: "00 כללי/Syllabus.pdf", "b" * 64: "00 כללי/Syllabus Old.pdf"}
    again = drive_layout.plan_reorg(json.loads((registry.directory / "sample.json").read_text(encoding="utf-8")), drive.items.values())
    assert again == []


def test_stationary_file_keeps_its_name_and_the_mover_gets_a_suffix(tmp_path):
    registry = _registry_with(tmp_path, [src(sha256="1" * 64, file="/s/11111111-syllabus.pdf", title="Syllabus")])
    drive = FakeDrive([("00 כללי", True), ("00 כללי/Syllabus.pdf", False), ("11111111-syllabus.pdf", False)])
    courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    assert drive.violations == []
    assert sorted(p for p in drive.paths() if p.startswith("00 כללי/")) == ["00 כללי/Syllabus (2).pdf", "00 כללי/Syllabus.pdf"]


def test_duplicate_root_names_are_each_moved_by_their_own_id(tmp_path):
    registry = _registry_with(tmp_path, [])
    drive = FakeDrive([("scan.pdf", False), ("scan.pdf", False)])
    ids = [i for i in drive.items]
    courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    assert drive.violations == []
    assert sorted(drive.path_of(i) for i in ids) == ["קריאות/scan/scan (2).pdf", "קריאות/scan/scan.pdf"]


def test_registered_source_on_a_duplicated_name_moves_nothing(tmp_path):
    registry = _registry_with(tmp_path, [src(sha256="1" * 64, file="/s/11111111-syllabus.pdf", title="Syllabus")])
    drive = FakeDrive([("11111111-syllabus.pdf", False), ("11111111-syllabus.pdf", False)])
    with pytest.raises(drive_layout.ReorgError):
        courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    assert _moves(drive) == [] and not any(c[:2] == ["rclone", "mkdir"] for c in drive.calls)


def test_duplicated_destination_folder_moves_nothing(tmp_path):
    registry = _registry_with(tmp_path, [src(sha256="1" * 64, file="/s/11111111-syllabus.pdf", title="Syllabus")])
    drive = FakeDrive([("00 כללי", True), ("00 כללי", True), ("11111111-syllabus.pdf", False)])
    with pytest.raises(drive_layout.ReorgError):
        courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    assert _moves(drive) == [] and drive.paths() == ["00 כללי", "00 כללי", "11111111-syllabus.pdf"]


def test_legacy_folder_with_a_subfolder_and_a_registered_source_inside(tmp_path):
    task = src(sha256="5" * 64, file="/s/55555555-essay.pdf", title="Essay", tasks=["t-a"], drive_path="מטלה 1/essay.pdf")
    registry = _registry_with(tmp_path, [task], tasks=[{"id": "t-a"}])
    drive = FakeDrive([("מטלה 1", True), ("מטלה 1/sub", True), ("מטלה 1/sub/x.pdf", False), ("מטלה 1/essay.pdf", False)])
    courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    assert drive.violations == []
    assert drive.paths() == ["מטלה 1", "מטלה 1/sub", "מטלות", "מטלות/מטלה 1", "מטלות/מטלה 1/Essay.pdf", "מטלות/מטלה 1/sub", "מטלות/מטלה 1/sub/x.pdf"]  # emptied legacy folders kept
    recorded = json.loads((registry.directory / "sample.json").read_text(encoding="utf-8"))["sources"][0]["drive_path"]
    assert recorded == "מטלות/מטלה 1/Essay.pdf"


def test_legacy_folder_merges_into_an_existing_target_with_unique_names(tmp_path):
    registry = _registry_with(tmp_path, [])
    drive = FakeDrive([("מטלה 1", True), ("מטלה 1/notes.pdf", False), ("מטלות", True), ("מטלות/מטלה 1", True), ("מטלות/מטלה 1/notes.pdf", False)])
    courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    assert drive.violations == []
    assert sorted(drive.paths()) == ["מטלה 1", "מטלות", "מטלות/מטלה 1", "מטלות/מטלה 1/notes (2).pdf", "מטלות/מטלה 1/notes.pdf"]  # emptied legacy folder kept


def test_listing_that_changes_before_the_moves_aborts_without_moving(tmp_path):
    registry = _registry_with(tmp_path, [])
    drive = FakeDrive([("11111111-syllabus.pdf", False)])

    def add_late_file(fake):
        if fake.list_calls == 2:
            fake.add("late.pdf")
    drive.on_list = add_late_file
    with pytest.raises(drive_layout.ReorgError):
        courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    assert _moves(drive) == []


def test_plan_is_applied_while_the_course_lock_is_held(tmp_path):
    registry = _registry_with(tmp_path, [src(sha256="1" * 64, file="/s/11111111-syllabus.pdf", title="Syllabus")])
    drive = FakeDrive([("11111111-syllabus.pdf", False)])
    drive.lock_file = registry.directory / ".lock"
    courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    assert drive.lock_probe and all(drive.lock_probe)


def test_apply_refuses_while_the_nightly_job_runs_unless_forced(tmp_path):
    registry = _registry_with(tmp_path, [src(sha256="1" * 64, file="/s/11111111-syllabus.pdf", title="Syllabus")])
    drive = FakeDrive([("11111111-syllabus.pdf", False)], nightly=True)
    with pytest.raises(drive_layout.ReorgError, match="nightly"):
        courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    assert _moves(drive) == []
    assert courses.drive_reorg(registry, ["sample"], apply=False, runner=drive)[0]["moves"]
    courses.drive_reorg(registry, ["sample"], apply=True, force=True, runner=drive)
    assert len(_moves(drive)) == 1


def test_a_rerun_after_a_full_apply_plans_nothing(tmp_path):
    registry = _registry_with(tmp_path, [src(sha256="1" * 64, file="/s/11111111-syllabus.pdf", title="Syllabus")])
    drive = FakeDrive([("11111111-syllabus.pdf", False)])
    courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    rerun = courses.drive_reorg(courses.Registry(registry.directory), ["sample"], apply=True, runner=drive)
    assert rerun[0]["moves"] == [] and len(_moves(drive)) == 1


def _two_unregistered(tmp_path):
    registry = _registry_with(tmp_path, [])
    drive = FakeDrive([("alpha.pdf", False), ("beta.pdf", False)])
    return registry, drive


def test_failed_move_leaves_an_unfinished_intent_and_resume_finishes_it(tmp_path, monkeypatch):
    registry, drive = _two_unregistered(tmp_path)
    drive.faults[("moveid", 2)] = "before"
    with pytest.raises(subprocess.CalledProcessError):
        courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    journal = next((registry.directory / "logs").glob("drive-reorg-*-sample.jsonl"))
    pending = drive_layout.pending_ops(drive_layout.read_journal(journal))
    assert [(op["kind"], op["old"]) for op in pending] == [("drive_move", "beta.pdf")]
    drive.faults.clear()
    before = len(_moves(drive))
    result = courses.drive_reorg_resume(courses.Registry(registry.directory), journal, runner=drive)
    assert result["pending"] == 1 and len(_moves(drive)) == before + 1
    assert drive.violations == [] and sorted(drive.files()) == ["קריאות/alpha/alpha.pdf", "קריאות/beta/beta.pdf"]
    assert drive_layout.pending_ops(drive_layout.read_journal(journal)) == []


def test_crash_after_a_move_is_resumed_by_checking_the_file_id(tmp_path):
    registry, drive = _two_unregistered(tmp_path)
    drive.faults[("moveid", 1)] = "after"
    with pytest.raises(subprocess.CalledProcessError):
        courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    journal = next((registry.directory / "logs").glob("drive-reorg-*-sample.jsonl"))
    drive.faults.clear()
    before = len(_moves(drive))
    courses.drive_reorg_resume(courses.Registry(registry.directory), journal, runner=drive)
    assert len(_moves(drive)) == before + 1  # alpha was already at its new path (only its done line is written); beta moves
    assert sorted(drive.files()) == ["קריאות/alpha/alpha.pdf", "קריאות/beta/beta.pdf"] and drive.violations == []
    assert drive_layout.pending_ops(drive_layout.read_journal(journal)) == []


def test_resume_refuses_a_file_found_somewhere_else(tmp_path):
    registry, drive = _two_unregistered(tmp_path)
    drive.faults[("moveid", 1)] = "before"
    with pytest.raises(subprocess.CalledProcessError):
        courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    journal = next((registry.directory / "logs").glob("drive-reorg-*-sample.jsonl"))
    drive.faults.clear()
    drive.items[drive.id_at("alpha.pdf")]["Path"] = "elsewhere/alpha.pdf"
    before = len(_moves(drive))
    with pytest.raises(drive_layout.ReorgError, match="not touching"):
        courses.drive_reorg_resume(courses.Registry(registry.directory), journal, runner=drive)
    assert len(_moves(drive)) == before


def test_journal_is_fsynced_once_per_line_in_order(tmp_path, monkeypatch):
    synced = []
    real = drive_layout.os.fsync
    monkeypatch.setattr(drive_layout.os, "fsync", lambda fd: (synced.append(fd), real(fd)))
    registry, drive = _two_unregistered(tmp_path)
    courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    journal = next((registry.directory / "logs").glob("drive-reorg-*-sample.jsonl"))
    lines = drive_layout.read_journal(journal)
    assert len(synced) == len(lines) == 5  # the plan, then two moves: an intent and a done line each, every one fsynced
    assert lines[0]["phase"] == "plan"
    assert [(l["phase"], l["kind"]) for l in lines[1:3]] == [("intent", "drive_move"), ("done", "drive_move")]


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
    assert copies[0][3] == "gdrive:00 כללי/Syllabus.pdf" and copies[0][4:] == ["--ignore-existing", "--drive-root-folder-id", "folder-1"]
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


def test_moveid_destination_stays_on_the_drive_remote():
    calls = []
    moved = []
    def runner(argv, **kw):
        calls.append(argv)
        if argv[:3] == ["rclone", "backend", "moveid"]:
            moved.append(argv)
            return subprocess.CompletedProcess(argv, 0, "", "")
        if "--stat" in argv and moved:
            return subprocess.CompletedProcess(argv, 0, json.dumps({"ID": "FILEID"}), "")
        return subprocess.CompletedProcess(argv, 3 if "--stat" in argv else 0, "", "")
    drive_layout.move_file("gdrive-biu", "ROOT", "FILEID", "קריאות/A/a.pdf", runner=runner)
    moveid = [c for c in calls if c[:3] == ["rclone", "backend", "moveid"]][0]
    assert moveid[5] == "gdrive-biu:קריאות/A/a.pdf"
    assert all(not a.startswith("קריאות") for a in moveid)


def test_a_file_that_appears_after_the_destination_check_is_never_replaced(tmp_path):
    registry, drive = _two_unregistered(tmp_path)
    original = drive.id_at("alpha.pdf")
    squatter = {}

    def appear(fake):
        # after the destination check and just before moveid: someone creates a file at the planned destination
        if not squatter:
            squatter["id"] = fake.add("קריאות/alpha/alpha.pdf")
    drive.on_moveid = appear
    with pytest.raises(drive_layout.ReorgError, match="not moved"):
        courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    assert squatter and drive.path_of(squatter["id"]) == "קריאות/alpha/alpha.pdf"  # the other file is untouched
    assert drive.path_of(original) == "alpha.pdf"  # moveto skipped rather than replaced; the source stays put
    assert drive.skipped == [(original, "קריאות/alpha/alpha.pdf")] and drive.violations == []
    assert drive.path_of(drive.id_at("beta.pdf")) == "beta.pdf"  # the run stopped at the failure
    lines = drive_layout.read_journal(_journal_of(registry))
    assert [(l["phase"], l["kind"]) for l in lines if l["phase"] != "plan"] == [("intent", "drive_move"), ("failed", "drive_move")]


def _lock_is_held(path):
    """True when another open file description holds the flock on `path` (probed without blocking)."""
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return False
    except BlockingIOError:
        return True
    finally:
        handle.close()


def _journal_of(registry):
    return next((registry.directory / "logs").glob("drive-reorg-*-sample.jsonl"))


def test_plan_is_journaled_before_the_first_move(tmp_path):
    registry, drive = _two_unregistered(tmp_path)
    seen = []

    def runner(command, **kwargs):
        if command[:3] == ["rclone", "backend", "moveid"] and not seen:
            seen.append([json.loads(line)["phase"] for line in _journal_of(registry).read_text(encoding="utf-8").splitlines()])
        return drive(command, **kwargs)
    courses.drive_reorg(registry, ["sample"], apply=True, runner=runner)
    assert seen and seen[0] == ["plan", "intent"][:len(seen[0])] and seen[0][0] == "plan"  # the plan is on disk before the move


def test_failure_at_b_resume_completes_b_and_c(tmp_path):
    registry = _registry_with(tmp_path, [])
    drive = FakeDrive([("alpha.pdf", False), ("beta.pdf", False), ("gamma.pdf", False)])
    drive.faults[("moveid", 2)] = "before"
    with pytest.raises(subprocess.CalledProcessError):
        courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    journal = _journal_of(registry)
    drive.faults.clear()
    result = courses.drive_reorg_resume(courses.Registry(registry.directory), journal, runner=drive)
    assert result["pending"] == 2 and len(result["done"]) == 2
    assert sorted(drive.files()) == ["קריאות/alpha/alpha.pdf", "קריאות/beta/beta.pdf", "קריאות/gamma/gamma.pdf"]
    assert drive.violations == [] and drive_layout.pending_ops(drive_layout.read_journal(journal)) == []


def test_resume_finishes_a_temporary_name_cycle_broken_midway(tmp_path):
    a = src(sha256="a" * 64, file="/s/aaaa1111-a.pdf", title="Syllabus", drive_path="00 כללי/Syllabus Old.pdf")
    b = src(sha256="b" * 64, file="/s/bbbb2222-b.pdf", title="Syllabus Old", drive_path="00 כללי/Syllabus.pdf")
    registry = _registry_with(tmp_path, [a, b])
    drive = FakeDrive([("00 כללי", True), ("00 כללי/Syllabus Old.pdf", False), ("00 כללי/Syllabus.pdf", False)])
    id_a, id_b = drive.id_at("00 כללי/Syllabus Old.pdf"), drive.id_at("00 כללי/Syllabus.pdf")
    drive.faults[("moveid", 2)] = "before"
    with pytest.raises(subprocess.CalledProcessError):
        courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    drive.faults.clear()
    courses.drive_reorg_resume(courses.Registry(registry.directory), _journal_of(registry), runner=drive)
    assert drive.violations == []
    assert drive.path_of(id_a) == "00 כללי/Syllabus.pdf" and drive.path_of(id_b) == "00 כללי/Syllabus Old.pdf"
    recorded = {s["sha256"]: s["drive_path"] for s in json.loads((registry.directory / "sample.json").read_text(encoding="utf-8"))["sources"]}
    assert recorded == {"a" * 64: "00 כללי/Syllabus.pdf", "b" * 64: "00 כללי/Syllabus Old.pdf"}


def test_a_file_that_appears_at_a_destination_before_its_move_is_refused(tmp_path):
    registry, drive = _two_unregistered(tmp_path)
    original = drive.id_at("alpha.pdf")

    def squat(fake, path):
        # someone puts a file on the planned destination after the plan, just before the move
        if path == "קריאות/alpha/alpha.pdf" and not any(i["Path"] == path for i in fake.items.values()):
            fake.add(path)
    drive.on_stat = squat
    with pytest.raises(drive_layout.ReorgError, match="occupied"):
        courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    assert _moves(drive) == [] and drive.violations == []
    assert drive.path_of(original) == "alpha.pdf"  # nothing replaced, nothing moved
    assert drive.path_of(drive.id_at("קריאות/alpha/alpha.pdf")) == "קריאות/alpha/alpha.pdf"
    lines = drive_layout.read_journal(_journal_of(registry))
    assert [(l["phase"], l["kind"]) for l in lines if l["phase"] != "plan"] == [("intent", "drive_move"), ("failed", "drive_move")]


def test_add_source_uploads_while_the_registry_lock_is_held(tmp_path):
    registry = make_registry(tmp_path, term={"drive_remote": "gdrive"})
    path = pdf(tmp_path, "syllabus.pdf")
    fake = Fake()
    seen = []

    def runner(command, **kwargs):
        if command[:2] == ["rclone", "copyto"]:
            seen.append(_lock_is_held(registry.directory / ".lock"))
        return fake(command, **kwargs)
    courses.add_source(registry, path, "sample", title="Syllabus", origin="other", runner=runner)
    assert seen == [True]


def test_add_source_blocks_while_a_reorg_holds_the_lock(tmp_path):
    registry = make_registry(tmp_path, term={"drive_remote": "gdrive"})
    path = pdf(tmp_path, "syllabus.pdf")
    fake = Fake()
    holder = (registry.directory / ".lock").open("a+")
    fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
    worker = threading.Thread(target=courses.add_source, args=(registry, path, "sample"),
                              kwargs={"title": "Syllabus", "origin": "other", "runner": fake}, daemon=True)
    try:
        worker.start()
        worker.join(0.5)
        blocked_while_held = worker.is_alive() and fake.of("rclone", "copyto") == []
    finally:
        fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
        holder.close()
    worker.join(30)
    assert blocked_while_held
    assert not worker.is_alive() and len(fake.of("rclone", "copyto")) == 1


def test_resume_after_a_crash_past_the_move_finishes_its_nlm_rename_and_checkpoint(tmp_path):
    registry = _registry_with(tmp_path, [src(sha256="1" * 64, file="/s/11111111-syllabus.pdf", title="Syllabus", notebook_source_id="nlm-1")])
    drive = FakeDrive([("11111111-syllabus.pdf", False)])
    drive.faults[("moveid", 1)] = "after"
    with pytest.raises(subprocess.CalledProcessError):
        courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    journal = _journal_of(registry)
    drive.faults.clear()
    drive.nlm_fail = 1
    with pytest.raises(subprocess.CalledProcessError):
        courses.drive_reorg_resume(courses.Registry(registry.directory), journal, runner=drive)
    recorded = json.loads((registry.directory / "sample.json").read_text(encoding="utf-8"))["sources"][0]
    assert recorded.get("drive_path") is None  # the checkpoint did not run past the failed rename
    courses.drive_reorg_resume(courses.Registry(registry.directory), journal, runner=drive)
    assert drive.nlm == [["nlm", "source", "rename", "nlm-1", "Syllabus", "--notebook", "nb-1"]]
    recorded = json.loads((registry.directory / "sample.json").read_text(encoding="utf-8"))["sources"][0]
    assert recorded["drive_path"] == "00 כללי/Syllabus.pdf"
    assert drive_layout.pending_ops(drive_layout.read_journal(journal)) == [] and drive.violations == []


def test_a_torn_last_line_is_cut_before_the_next_record_is_appended(tmp_path):
    path = tmp_path / "logs" / "j.jsonl"
    path.parent.mkdir()
    intent = {"phase": "intent", "seq": 1, "op_id": "a" * 32, "kind": "drive_move", "file_id": "x", "old": "o", "new": "n",
              "sha256": "", "final": True, "remote": "gdrive", "root": "folder-1", "slug": "sample"}
    path.write_text(json.dumps(intent) + "\n" + '{"phase": "done", "seq": 2, "op_', encoding="utf-8")
    journal = drive_layout.Journal(path, remote="gdrive", root="folder-1", slug="sample")
    journal.run("drive_move", {"file_id": "y", "old": "p", "new": "q", "sha256": "", "final": True}, lambda: None)
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n") and '{"phase": "done", "seq": 2, "op_' not in text
    lines = drive_layout.read_journal(path)
    assert [line["phase"] for line in lines] == ["intent", "repair", "intent", "done"]
    assert lines[1]["action"] == "truncated"


def test_resume_appends_readably_after_a_torn_journal_tail(tmp_path):
    registry, drive = _two_unregistered(tmp_path)
    drive.faults[("moveid", 2)] = "before"
    with pytest.raises(subprocess.CalledProcessError):
        courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    journal = _journal_of(registry)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write('{"phase": "done", "seq": 99, "op_id": "tor')  # a crash mid-write
    drive.faults.clear()
    courses.drive_reorg_resume(courses.Registry(registry.directory), journal, runner=drive)
    text = journal.read_text(encoding="utf-8")
    assert text.endswith("\n") and '"op_id": "tor' not in text
    for line in text.splitlines():
        json.loads(line)  # every line is a complete record
    assert drive_layout.pending_ops(drive_layout.read_journal(journal)) == []
    assert sorted(drive.files()) == ["קריאות/alpha/alpha.pdf", "קריאות/beta/beta.pdf"]


def test_media_upload_copies_while_the_registry_lock_is_held(tmp_path, monkeypatch):
    from test_sources import fake_ingest_factory
    registry = make_registry(tmp_path, term={"drive_remote": "gdrive"})
    audio = tmp_path / "lesson.m4a"
    audio.write_bytes(b"a")
    monkeypatch.setattr(courses, "ingest_recording", fake_ingest_factory(registry))
    fake = Fake()
    seen = []

    def runner(command, **kwargs):
        if command[:2] == ["rclone", "copyto"]:
            seen.append(_lock_is_held(registry.directory / ".lock"))
        return fake(command, **kwargs)
    courses.add_source(registry, audio, "sample", origin="recording", runner=runner, lesson_date="2026-10-12", lesson_time="1204")
    assert seen == [True]


def test_read_journal_keeps_the_prefix_when_the_tail_is_cut_inside_a_hebrew_character(tmp_path):
    path = tmp_path / "j.jsonl"
    prefix = (json.dumps({"phase": "plan", "seq": 1, "note": "קריאות"}, ensure_ascii=False) + "\n").encode("utf-8")
    fragment = '{"phase": "done", "note": "ק'.encode("utf-8")
    path.write_bytes(prefix + fragment[:-1])  # the crash splits the two-byte letter
    assert drive_layout.read_journal(path) == [{"phase": "plan", "seq": 1, "note": "קריאות"}]


def test_resume_repairs_a_journal_torn_inside_a_hebrew_character_and_continues(tmp_path):
    registry, drive = _two_unregistered(tmp_path)
    drive.faults[("moveid", 2)] = "before"
    with pytest.raises(subprocess.CalledProcessError):
        courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    journal = _journal_of(registry)
    drive.faults.clear()
    fragment = '{"phase": "done", "note": "קריאות"}'.encode("utf-8")
    with journal.open("ab") as handle:
        handle.write(fragment[:fragment.index("ק".encode("utf-8")) + 1])  # cut one byte into the letter
    courses.drive_reorg_resume(courses.Registry(registry.directory), journal, runner=drive)
    data = journal.read_bytes()
    assert data.endswith(b"\n")
    for line in data.decode("utf-8").splitlines():
        json.loads(line)  # every line is a complete record
    assert [line["action"] for line in drive_layout.read_journal(journal) if line["phase"] == "repair"] == ["truncated"]
    assert drive_layout.pending_ops(drive_layout.read_journal(journal)) == []
    assert sorted(drive.files()) == ["קריאות/alpha/alpha.pdf", "קריאות/beta/beta.pdf"] and drive.violations == []


def test_resume_refuses_a_journal_for_another_drive_folder(tmp_path):
    registry = make_registry(tmp_path)
    journal = tmp_path / "j.jsonl"
    journal.write_text(json.dumps({"kind": "plan", "phase": "plan", "slug": "sample", "remote": "gdrive",
                                   "root": "OTHER-ROOT", "steps": []}) + "\n", encoding="utf-8")
    with pytest.raises(drive_layout.ReorgError, match="select the right term"):
        courses.drive_reorg_resume(registry, journal, force=True, runner=lambda *a, **k: subprocess.CompletedProcess(a, 0, "[]", ""))


def test_add_source_refuses_an_upload_drive_does_not_confirm(tmp_path):
    registry = make_registry(tmp_path)

    class Clobbered(Fake):
        def __call__(self, command, **kwargs):
            if command[:2] == ["rclone", "lsjson"] and "--stat" in command:
                self.calls.append(command)
                return subprocess.CompletedProcess(command, 0, json.dumps({"Size": 14, "Hashes": {"md5": "0" * 32}}), "")
            return super().__call__(command, **kwargs)

    with pytest.raises(courses.IngestError, match="not confirmed"):
        courses.add_source(registry, pdf(tmp_path, "Syllabus.pdf"), "sample", runner=Clobbered())


def test_add_source_reuses_a_copy_already_on_drive_instead_of_uploading_twice(tmp_path):
    registry = make_registry(tmp_path)
    source = pdf(tmp_path, "Syllabus.pdf")
    md5 = hashlib.md5(source.read_bytes()).hexdigest()
    fake = Fake(drive=[{"Name": "Syllabus.pdf", "Path": "Syllabus.pdf", "Hashes": {"md5": md5}}])
    courses.add_source(registry, source, "sample", runner=fake)
    assert fake.of("rclone", "copyto") == []


def test_a_fresh_apply_refuses_while_an_earlier_reorg_is_unfinished(tmp_path):
    registry, drive = _two_unregistered(tmp_path)
    drive.faults[("moveid", 2)] = "before"
    with pytest.raises(subprocess.CalledProcessError):
        courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    drive.faults.clear()
    before = len(_moves(drive))
    with pytest.raises(drive_layout.ReorgError, match="--resume"):
        courses.drive_reorg(courses.Registry(registry.directory), ["sample"], apply=True, runner=drive)
    assert len(_moves(drive)) == before


def test_resume_never_deletes_a_folder_even_from_an_older_journal(tmp_path):
    registry, drive = _two_unregistered(tmp_path)
    journal = registry.directory / "logs" / "drive-reorg-old-sample.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    j = drive_layout.Journal(journal, remote="gdrive", root="folder-1", slug="sample")
    j.write_plan([{"op": "rmdir", "id": "dir-x", "old": "מטלה 1", "new": "", "sha256": "", "final": False}])
    courses.drive_reorg_resume(courses.Registry(registry.directory), journal, runner=drive, force=True)
    assert [c for c in drive.calls if c[:2] == ["rclone", "rmdir"]] == []


def test_a_fresh_apply_refuses_when_only_the_nlm_rename_and_checkpoint_are_left(tmp_path):
    registry = _registry_with(tmp_path, [src(sha256="1" * 64, file="/s/11111111-syllabus.pdf", title="Syllabus", notebook_source_id="nlm-1")])
    drive = FakeDrive([("11111111-syllabus.pdf", False)])
    drive.nlm_fail = 1
    with pytest.raises(subprocess.CalledProcessError):
        courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    with pytest.raises(drive_layout.ReorgError, match="--resume"):
        courses.drive_reorg(courses.Registry(registry.directory), ["sample"], apply=True, runner=drive)
    courses.drive_reorg_resume(courses.Registry(registry.directory), _journal_of(registry), runner=drive)
    recorded = json.loads((registry.directory / "sample.json").read_text(encoding="utf-8"))["sources"][0]
    assert recorded["drive_path"] == "00 כללי/Syllabus.pdf"
    courses.drive_reorg(courses.Registry(registry.directory), ["sample"], apply=True, runner=drive)  # finished: allowed again


def test_a_registry_write_whose_done_line_was_lost_is_closed_on_resume(tmp_path):
    registry = _registry_with(tmp_path, [src(sha256="1" * 64, file="/s/11111111-syllabus.pdf", title="Syllabus")])
    drive = FakeDrive([("11111111-syllabus.pdf", False)])
    courses.drive_reorg(registry, ["sample"], apply=True, runner=drive)
    journal = _journal_of(registry)
    lines = journal.read_text(encoding="utf-8").splitlines()
    last_done = max(i for i, l in enumerate(lines) if json.loads(l).get("kind") == "registry" and json.loads(l).get("phase") == "done")
    journal.write_text("\n".join(lines[:last_done] + lines[last_done + 1:]) + "\n", encoding="utf-8")  # lose that done line
    assert courses._unfinished_journals(courses.Registry(registry.directory), "sample",
                                        json.loads((registry.directory / "sample.json").read_text(encoding="utf-8")))
    courses.drive_reorg_resume(courses.Registry(registry.directory), journal, runner=drive)
    assert drive_layout.pending_ops(drive_layout.read_journal(journal)) == []
    courses.drive_reorg(courses.Registry(registry.directory), ["sample"], apply=True, runner=drive)  # no longer blocked


def test_lesson_numbers_never_shift_when_an_earlier_lesson_arrives_later():
    course = {"lessons": [{"lesson_key": "2026-10-12-1204"}],
              "sources": [{"lesson_key": "2026-10-12-1204", "drive_path": "שיעורים/שיעור 01/a.m4a"}]}
    assert drive_layout.lesson_number(course, "2026-10-12-1204") == 1
    assert drive_layout.lesson_number(course, "2026-10-05-1204") == 2   # earlier date, imported later: next number
    fresh = {"lessons": [{"lesson_key": "2026-10-12-1204"}, {"lesson_key": "2026-10-05-1204"}], "sources": []}
    assert drive_layout.lesson_number(fresh, "2026-10-05-1204") == 1    # nothing on Drive yet: by date


def test_a_file_in_a_legacy_folder_is_matched_to_its_source_by_sha256_not_by_name():
    course = {"sources": [{"sha256": "aa" * 32, "file": "/s/11111111-essay.pdf", "title": "Essay", "tasks": []}]}
    listing = [
        {"Path": "מטלה 1", "Name": "מטלה 1", "IsDir": True, "ID": "d1"},
        {"Path": "מטלה 1/renamed by me.pdf", "Name": "renamed by me.pdf", "IsDir": False, "ID": "f1", "Hashes": {"sha256": "aa" * 32}},
        {"Path": "מטלה 1/essay.pdf", "Name": "essay.pdf", "IsDir": False, "ID": "f2", "Hashes": {"sha256": "bb" * 32}},
    ]
    plan = drive_layout.plan_reorg(course, listing)
    matched = [s for s in plan if s.get("sha256") == "aa" * 32]
    assert matched and all(s["id"] == "f1" for s in matched)
    assert not [s for s in plan if s.get("id") == "f2" and s.get("sha256")]


def test_a_wispr_transcript_is_named_by_its_lesson_and_date():
    course = {"lessons": [{"lesson_key": "2026-10-16-1201"}, {"lesson_key": "2026-10-23-1201"}], "sources": []}
    source = {"file": "/s/1c9dd544-wispr-2026-10-23-1201-24673bab.txt", "title": "wispr-2026-10-23-1201-24673bab",
              "lesson_key": "2026-10-23-1201"}
    assert drive_layout.drive_path_for(course, source, {}) == "שיעורים/שיעור 02/תמלול שיעור 02 · 23.10.2026.txt"


def test_a_transcript_without_a_lesson_key_goes_to_its_lesson_by_date_or_the_transcripts_folder():
    course = {"lessons": [{"lesson_key": "2026-10-16-1201"}], "sources": []}
    dated = {"file": "/s/wispr-2026-10-16-1201-d5a4c087.txt", "title": "wispr-2026-10-16-1201-d5a4c087"}
    assert drive_layout.folder_for(course, dated) == "שיעורים/שיעור 01"
    undated = {"file": "/s/zoom-transcript.txt", "title": "zoom-transcript"}
    assert drive_layout.folder_for(course, undated) == "שיעורים/תמלולים"


def test_a_generic_title_gives_way_to_the_fuller_file_name():
    notes = {"file": "/s/121aac44-תפיסות יסוד בספרות הנבואה שיעור 1 תשפז.docx", "title": "שיעור 1"}
    assert drive_layout.drive_name(notes) == "תפיסות יסוד בספרות הנבואה שיעור 1 תשפז"
    syllabus = {"file": "/s/b34cc5eb-סילבוס פילוסופיה של הרגשות בעת החדשה.docx", "title": "סילבוס"}
    assert drive_layout.drive_name(syllabus) == "סילבוס פילוסופיה של הרגשות בעת החדשה"
    plain = {"file": "/s/414536ae-01 - Reading One.pdf", "title": "Reading One"}
    assert drive_layout.drive_name(plain) == "Reading One"


def test_a_titled_recording_keeps_its_title_and_a_machine_named_one_gets_its_lesson():
    course = {"lessons": [{"lesson_key": "2026-10-12-1204"}], "sources": []}
    titled = {"file": "/s/lesson.m4a", "title": "Lesson 2", "kind": "media", "lesson_key": "2026-10-12-1204"}
    assert drive_layout.drive_name(titled, course) == "Lesson 2"
    machine = {"file": "/s/ed73a9d2-20261012 120422.m4a", "title": "20261012 120422", "kind": "media", "lesson_key": "2026-10-12-1204"}
    assert drive_layout.drive_name(machine, course) == "הקלטת שיעור 01 · 12.10.2026"


def test_a_transcript_registered_as_media_is_still_named_a_transcript():
    course = {"lessons": [{"lesson_key": "2026-10-11-1405"}], "sources": []}
    source = {"file": "/s/f21f9f8b-kane__zoom-3263924__transcript-2026-10-11.txt", "title": "kane__zoom-3263924__transcript-2026-10-11",
              "kind": "media", "lesson_key": "2026-10-11-1405"}
    assert drive_layout.drive_name(source, course) == "תמלול שיעור 01 · 11.10.2026"



def test_moveid_is_server_side_so_the_file_keeps_its_id():
    calls = []
    def runner(argv, **kw):
        calls.append(argv)
        out = '{"ID": "FILEID"}' if "--stat" in argv and argv[2].endswith("a.pdf") else ""
        return subprocess.CompletedProcess(argv, 3 if "--stat" in argv and len(calls) == 2 else 0, out, "")
    try:
        drive_layout.move_file("gdrive-biu", "ROOT", "FILEID", "קריאות/A/a.pdf", runner=runner)
    except Exception:
        pass
    moveid = [c for c in calls if c[:3] == ["rclone", "backend", "moveid"]]
    assert moveid and "--drive-server-side-across-configs" in moveid[0]


@pytest.mark.parametrize("name, folder", [
    ("מבחן בית - יותם פרום.docx", "מטלות/מבחן בית - יותם פרום"),
    ("perception.assign.2025.pdf", "מטלות/perception.assign.2025"),
    ("סיכום הספר.docx", "קריאות/סיכום הספר"),
])
def test_exam_and_assignment_files_go_under_tasks(name, folder):
    assert drive_layout.folder_for({}, {"file": f"/s/{name}"}) == folder


def test_the_plan_does_not_depend_on_listing_order_with_duplicate_names():
    listing = [
        {"Path": "מטלה 1", "Name": "מטלה 1", "IsDir": True, "ID": "d1"},
        {"Path": "מטלה 1/a.docx", "Name": "a.docx", "IsDir": False, "ID": "f2"},
        {"Path": "מטלה 1/a.docx", "Name": "a.docx", "IsDir": False, "ID": "f1"},
    ]
    one = drive_layout.plan_reorg({"sources": []}, listing)
    two = drive_layout.plan_reorg({"sources": []}, list(reversed(listing)))
    assert one == two
