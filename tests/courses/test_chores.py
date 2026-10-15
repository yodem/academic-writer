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
    assert {c["kind"] for c in chores.load(reg)} == {"assignment", "forum-post", "perusall-capture", "kotar-source", "missing-text", "manual"}


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
