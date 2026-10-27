import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "courses"))
import chores
import courses


def make_registry(tmp_path):
    d = tmp_path / "reg"
    d.mkdir()
    (d / "term.json").write_text(json.dumps({"term": "T", "timezone": "Asia/Jerusalem"}), encoding="utf-8")
    (d / "kane.json").write_text(json.dumps({"slug": "kane", "name": "קאנט"}), encoding="utf-8")
    (d / "cohen.json").write_text(json.dumps({"slug": "cohen", "name": "הרמן כהן"}), encoding="utf-8")
    return courses.Registry(d)


def test_add_dedupes_and_updates_in_place(tmp_path):
    reg = make_registry(tmp_path)
    first = chores.add_chore(reg, course="kane", kind="assignment", ref="3251919", title="מטלה 1", time_left_text="נותרו 5 ימים")
    again = chores.add_chore(reg, course="kane", kind="assignment", ref="3251919", time_left_text="נותרו 4 ימים")
    stored = chores.load(reg)
    assert len(stored) == 1 and again["id"] == first["id"]
    assert stored[0]["time_left_text"] == "נותרו 4 ימים" and stored[0]["title"] == "מטלה 1"
    assert stored[0]["created"] == first["created"]
    chores.add_chore(reg, course="kane", kind="forum-post", ref="3251919")
    assert len(chores.load(reg)) == 2


def test_unchanged_readd_does_not_touch_updated(tmp_path):
    reg = make_registry(tmp_path)
    chores.add_chore(reg, course="kane", kind="manual", ref="x", title="t")
    before = (reg.directory / "chores.json").read_text()
    chores.add_chore(reg, course="kane", kind="manual", ref="x", title="t")
    assert (reg.directory / "chores.json").read_text() == before


def test_rejects_bad_kind_and_unknown_course(tmp_path):
    reg = make_registry(tmp_path)
    for kwargs in ({"course": "kane", "kind": "nope", "ref": "1"}, {"course": "ghost", "kind": "manual", "ref": "1"}):
        try:
            chores.add_chore(reg, **kwargs)
        except ValueError:
            continue
        raise AssertionError(kwargs)


def test_all_kinds_accepted(tmp_path):
    reg = make_registry(tmp_path)
    for kind in chores.KINDS:
        chores.add_chore(reg, course="kane", kind=kind, ref="r")
    assert {c["kind"] for c in chores.load(reg)} == {"assignment", "forum-post", "perusall-capture", "kotar-source", "missing-text", "manual", "exam", "reading"}


def test_done_stays_done_on_rescan(tmp_path):
    reg = make_registry(tmp_path)
    c = chores.add_chore(reg, course="kane", kind="manual", ref="x")
    chores.mark_done(reg, c["id"])
    chores.add_chore(reg, course="kane", kind="manual", ref="x", title="new title")
    assert chores.load(reg)[0]["status"] == "done"


def test_digest_sorted_by_due_hebrew_no_ids_no_tokens_and_only_two_files(tmp_path):
    reg = make_registry(tmp_path)
    (reg.directory / "digest").mkdir()
    (reg.directory / "digest" / "stray.txt").write_text("x")
    late = chores.add_chore(reg, course="cohen", kind="forum-post", ref="f1", title="פורום מאוחר", due_at="2026-11-30T23:00:00+02:00")
    soon = chores.add_chore(reg, course="kane", kind="assignment", ref="3251919", title="מטלה קרובה", due_at="2026-10-20T23:00:00+03:00",
                            time_left_text="נותרו 5 ימים", due_text="יום שלישי", core_texts=["קאנט, ביקורת התבונה"],
                            text="קראו https://x/f?token=SECRET123&a=1")
    nodue = chores.add_chore(reg, course="kane", kind="kotar-source", ref="k", title="בלי מועד")
    done = chores.add_chore(reg, course="kane", kind="manual", ref="d", title="כבר נעשה")
    chores.mark_done(reg, done["id"])
    folder = chores.write_digest(reg)
    assert sorted(p.name for p in folder.iterdir()) == ["chores.json", "chores.md"]
    md = (folder / "chores.md").read_text(encoding="utf-8")
    assert md.index("מטלה קרובה") < md.index("פורום מאוחר") < md.index("בלי מועד")
    assert "כבר נעשה" not in md and "נותרו 5 ימים" in md and "קאנט, ביקורת התבונה" in md
    assert "SECRET123" not in md and "token=[REDACTED]" in md
    for chore in (late, soon, nodue):
        assert chore["id"] not in md
    data = json.loads((folder / "chores.json").read_text(encoding="utf-8"))
    assert [c["ref"] for c in data] == ["3251919", "f1", "k"] and all("id" not in c for c in data)
    assert "SECRET123" not in json.dumps(data)


def test_cli_digest_with_registry_flag(tmp_path, capsys):
    reg = make_registry(tmp_path)
    assert courses.main(["chores", "add", "--registry", str(reg.directory), "--course", "kane", "--kind", "assignment", "--ref", "1",
                         "--title", "t", "--core-text", "a", "--core-text", "b"]) == 0
    capsys.readouterr()
    assert courses.main(["chores", "digest", "--registry", str(reg.directory)]) == 0
    assert (reg.directory / "digest" / "chores.md").is_file()
    capsys.readouterr()
    assert courses.main(["chores", "list", "--registry", str(reg.directory), "--status", "open"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1
    chore_id = chores.load(reg)[0]["id"]
    assert chores.load(reg)[0]["core_texts"] == ["a", "b"]
    assert courses.main(["chores", "done", chore_id, "--registry", str(reg.directory)]) == 0
    assert chores.load(reg)[0]["status"] == "done"


def test_general_pseudo_course_accepted(tmp_path):
    reg = make_registry(tmp_path)
    chore = chores.add_chore(reg, course="general", kind="manual", ref="chrome", title="Open Chrome")
    assert chore["course"] == "general"


def test_canonical_ref_spellings():
    assert {chores.canonical_ref(r) for r in ("3251589", "cm:3251589", " CMID-3251589 ",
            "https://lemida.biu.ac.il/mod/url/view.php?id=3251589")} == {"3251589"}
    for ref in ("login", "Lemida-Signin-2026-10-15", "sign in", "lemida_login"):
        assert chores.canonical_ref(ref) == chores.SIGNIN_REF
    assert chores.canonical_ref("toc-audit-2026-10-15") == "toc-audit-2026-10-15"


def test_reworded_refs_do_not_duplicate(tmp_path):
    reg = make_registry(tmp_path)
    first = chores.add_chore(reg, course="kane", kind="perusall-capture", ref="cm:3251589", title="a")
    chores.add_chore(reg, course="kane", kind="perusall-capture", ref="3251589", title="b")
    assert len(chores.load(reg)) == 1 and chores.load(reg)[0]["id"] == first["id"]


def test_signin_chores_collapse_to_one_general_chore(tmp_path):
    reg = make_registry(tmp_path)
    for course, ref in (("kane", "login"), ("cohen", "login"), ("kane", "lemida-signin-2026-10-15")):
        chores.add_chore(reg, course=course, kind="manual", ref=ref, title="Sign in to Lemida in Chrome")
    stored = chores.load(reg)
    assert len(stored) == 1 and (stored[0]["course"], stored[0]["ref"]) == ("general", "lemida-signin")


def test_legacy_stored_ref_matches_canonical(tmp_path):
    reg = make_registry(tmp_path)
    legacy = [{"id": "abc", "kind": "manual", "course": "kane", "ref": "cm:42", "title": "t", "text": "",
               "core_texts": [], "time_left_text": "", "due_text": "", "due_at": None, "status": "open",
               "created": "x", "updated": "x"}]
    (reg.directory / "chores.json").write_text(json.dumps(legacy), encoding="utf-8")
    assert chores.add_chore(reg, course="kane", kind="manual", ref="42", title="t")["id"] == "abc"
    assert len(chores.load(reg)) == 1


def test_exam_chore_derives_exam_task_with_room(tmp_path):
    import tasks
    reg = make_registry(tmp_path)
    chore = chores.add_chore(reg, course="kane", kind="exam", ref="exam-1", title="בחינה סופית",
                             due_at="2027-02-10T09:00:00+02:00", room="בניין 502, חדר 14", material="פרקים 1-6")
    assert chore["room"] == "בניין 502, חדר 14" and chore["material"] == "פרקים 1-6"
    derived = tasks.sync_tasks(reg.directory, "kane")
    assert len(derived) == 1
    assert derived[0]["kind"] == "exam" and derived[0]["due_at"] == "2027-02-10T09:00:00+02:00"
    assert derived[0]["room"] == "בניין 502, חדר 14" and derived[0]["material"] == "פרקים 1-6"
    plain = chores.add_chore(reg, course="cohen", kind="exam", ref="exam-2", due_at="2027-02-11T09:00:00+02:00")
    assert "room" not in tasks.derive_tasks([], [plain])[0][0]
    assert "בחינה" in chores.render_digest(reg, [chore])


def test_cli_chores_add_exam_with_room_and_material(tmp_path):
    reg = make_registry(tmp_path)
    assert courses.main(["chores", "add", "--registry", str(reg.directory), "--course", "kane", "--kind", "exam",
                         "--ref", "exam-cli", "--due-at", "2027-02-10T09:00:00+02:00",
                         "--room", "Building 502, room 14", "--material", "chapters 1-6"]) == 0
    [chore] = chores.load(reg)
    assert chore["kind"] == "exam" and chore["room"] == "Building 502, room 14" and chore["material"] == "chapters 1-6"


@pytest.mark.parametrize("text,expected", [
    ("יום שני, 2 נובמבר 2026, 00:00", "2026-11-02T00:00:00+02:00"),
    ("יום ראשון, 25 באוקטובר 2026, 23:59", "2026-10-25T23:59:00+02:00"),
    ("Monday, 2 November 2026, 11:59 PM", "2026-11-02T23:59:00+02:00"),
    ("Sunday, 1 March 2026, 12:00 AM", "2026-03-01T00:00:00+02:00"),
    ("נותר 5 ימים 15 שעות", None),
    ("", None),
    (None, None),
])
def test_due_at_from_lemida_text(text, expected):
    assert chores.due_at_from_text(text) == expected
