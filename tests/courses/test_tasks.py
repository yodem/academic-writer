import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "courses"))
import chores
import courses
import refs
import tasks


def make_reg(tmp_path):
    d = tmp_path / "reg"
    (d / "refs").mkdir(parents=True)
    (d / "term.json").write_text(json.dumps({"term": "T", "timezone": "Asia/Jerusalem"}), encoding="utf-8")
    (d / "kane.json").write_text(json.dumps({
        "slug": "kane", "name": "קאנט",
        "sources": [{"sha256": "a" * 64, "sha8": "aaaaaaaa", "title": "Cohen Attributes", "file": str(tmp_path / "x.pdf"),
                     "notebook_source_id": "nb-1", "trove": {"book_id": "bk", "page": 4}, "status": "done"}],
    }), encoding="utf-8")
    (d / "refs" / "kane.json").write_text(json.dumps({"course": "kane", "_note": "keep", "refs": [
        {"key": "r1", "citation": "Pedersen Israel its life and culture", "status": "downloaded", "annas": "not-found", "sha8": "aaaaaaaa"},
        {"key": "r2", "citation": "שצ'ופק הנבואה במצרים", "status": "pending", "found_in": "lesson 1"},
        {"key": "r3", "citation": "גלעד ספרות הנבואה", "status": "pending", "found_in": "מטלה 1"},
    ]}, ensure_ascii=False), encoding="utf-8")
    reg = courses.Registry(d)
    c = chores.add_chore(reg, course="kane", kind="assignment", ref="111", title="מטלה 1", due_at="2026-11-01T00:00:00+02:00")
    chores.add_chore(reg, course="kane", kind="manual", ref="login", title="sign in")
    return d, c


def test_sync_derives_tasks_from_chores_only(tmp_path):
    d, c = make_reg(tmp_path)
    t = tasks.sync_tasks(d, "kane")
    assert [x["id"] for x in t] == [c["id"]]
    assert t[0]["chore_ids"] == [c["id"]] and t[0]["status"] == "open" and t[0]["due_at"] == c["due_at"]
    assert json.loads((d / "kane.json").read_text())["tasks"][0]["id"] == c["id"]
    assert len(tasks.sync_tasks(d, "kane")) == 1  # idempotent


def test_link_show_and_unified_status(tmp_path):
    d, c = make_reg(tmp_path)
    tasks.task_link(d, "kane", c["id"][:5], ref="r1")
    tasks.task_link(d, "kane", c["id"], source="aaaaaaaa")
    assert tasks.task_link(d, "kane", c["id"], ref="r1")["linked"] is False
    data = tasks.task_show(d, "kane", c["id"])
    by_key = {s["key"]: s for s in data["sources"]}
    r1 = by_key["r1"]
    assert r1["downloaded"] and r1["in_notebooklm"] and r1["notebook_source_id"] == "nb-1" and r1["in_trove"] and r1["annas"] == "not-found"
    assert by_key["aaaaaaaa"]["type"] == "source" and by_key["aaaaaaaa"]["in_trove"]
    stored = json.loads((d / "refs" / "kane.json").read_text())
    assert stored["_note"] == "keep" and stored["refs"][0]["tasks"] == [c["id"]] and "tasks" not in stored["refs"][1]


def test_submit_closes_chores_and_is_idempotent(tmp_path):
    d, c = make_reg(tmp_path)
    out = tasks.task_submit(d, "kane", c["id"])
    assert out["status"] == "submitted" and out["closed_chores"] == [c["id"]]
    assert [x for x in chores.load(courses.Registry(d)) if x["id"] == c["id"]][0]["status"] == "done"
    again = tasks.task_submit(d, "kane", c["id"])
    assert again["closed_chores"] == [] and again["submitted_at"] == out["submitted_at"]


def test_unknown_task_errors(tmp_path):
    d, _ = make_reg(tmp_path)
    with pytest.raises(tasks.TaskError):
        tasks.task_show(d, "kane", "nope")


def test_cli_via_courses_and_refs(tmp_path, capsys, monkeypatch):
    d, c = make_reg(tmp_path)
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(d.parent))
    monkeypatch.setenv("ACADEMIC_TERM", d.name)
    assert courses.main(["task", "list", "--course", "kane"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["id"] == c["id"]
    assert refs.main(["--registry", str(d), "task", "link", "--course", "kane", "--task", c["id"], "--ref", "r1"]) == 0
    capsys.readouterr()
    assert refs.main(["--registry", str(d), "task", "show", "--course", "kane", "--task", c["id"], "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["sources"][0]["key"] == "r1"
    assert refs.main(["--registry", str(d), "task", "submit", "--course", "kane", "--task", c["id"]]) == 0


def make_specs(tmp_path):
    specs = tmp_path / "specs"
    specs.mkdir(exist_ok=True)
    (specs / "kane.json").write_text(json.dumps({"tasks": [
        {"key": "t1", "title": "מטלה 1", "page": 3,
         "primary": [{"page": 1, "title": "Cohen Attributes"}, {"page": 2, "title": "גלעד ספרות הנבואה"}],
         "secondary": [{"page": 3, "title": "ספר שלא קיים"}]},
        {"key": "t2", "title": "מטלה אחרת", "primary": [{"page": 1, "title": "הנבואה"}], "secondary": []},
    ]}, ensure_ascii=False), encoding="utf-8")
    return specs


def test_migrate_dry_run_writes_nothing(tmp_path, monkeypatch):
    d, c = make_reg(tmp_path)
    before = {p.name: p.read_text() for p in list(d.glob("*.json")) + list((d / "refs").glob("*.json"))}
    report = tasks.migrate(d, make_specs(tmp_path), dry_run=True)
    assert report["dry_run"] and report["courses"]["kane"]["links"]
    assert before == {p.name: p.read_text() for p in list(d.glob("*.json")) + list((d / "refs").glob("*.json"))}
    assert not list(d.rglob("*.bak-*"))


def test_migrate_links_unambiguous_backs_up_and_lists_the_rest(tmp_path):
    d, c = make_reg(tmp_path)
    report = tasks.migrate(d, make_specs(tmp_path))
    course = json.loads((d / "kane.json").read_text())
    ids = {t["id"]: t for t in course["tasks"]}
    assert c["id"] in ids and ids[c["id"]]["spec_key"] == "t1" and "s-t2" in ids
    stored = json.loads((d / "refs" / "kane.json").read_text())
    r = {x["key"]: x for x in stored["refs"]}
    assert r["r3"]["tasks"] == [c["id"]]                       # spec title match and found_in
    assert course["sources"][0]["tasks"] == [c["id"]]          # source title match
    assert "tasks" not in r["r1"]
    # "הנבואה" is contained in two citations (r2, r3): ambiguous, left unlinked
    assert any(a.get("task") == "t2" and a["type"] == "ref" for a in report["ambiguous"])
    assert {"course": "kane", "task": "t1", "item": "ספר שלא קיים"} in report["unmatched"]
    assert len(report["backups"]) == 2 and all(Path(b).is_file() for b in report["backups"])
    assert all(".bak-" in b for b in report["backups"])
    assert tasks.migrate(d, make_specs(tmp_path))["backups"] == []  # idempotent: nothing to write the second time
    assert not [p for p in d.glob("*.json") if ".bak" in p.name]


def test_token_match_not_substring_and_duplicates_listed(tmp_path):
    d, c = make_reg(tmp_path)
    refs_path = d / "refs" / "kane.json"
    data = json.loads(refs_path.read_text())
    data["refs"].append({"key": "r4", "citation": "x y z", "status": "pending", "found_in": "מטלה 10 עמ' 4"})
    refs_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    report = tasks.migrate(d, make_specs(tmp_path))
    stored = {x["key"]: x for x in json.loads(refs_path.read_text())["refs"]}
    assert "tasks" not in stored["r4"]                                   # 'מטלה 1' is not 'מטלה 10'
    assert {d_["spec_task"] for d_ in report["possible_duplicates"]} == {"s-t2"}


def test_fresh_chore_tasks_exclude_perusall(tmp_path):
    d, c = make_reg(tmp_path)
    chores.add_chore(courses.Registry(d), course="kane", kind="perusall-capture", ref="p1", title="reading")
    assert [t["id"] for t in tasks.sync_tasks(d, "kane")] == [c["id"]]


def test_migrate_cli(tmp_path, monkeypatch, capsys):
    d, _ = make_reg(tmp_path)
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(d.parent))
    monkeypatch.setenv("ACADEMIC_TERM", "reg")
    assert courses.main(["migrate-tasks", "--dry-run", "--specs-dir", str(make_specs(tmp_path))]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True


def _dup_reg(tmp_path, chores_spec, spec_tasks, slug="kane"):
    d, _ = make_reg(tmp_path)
    for f in (d / "chores.json",):
        f.write_text("[]", encoding="utf-8")
    reg = courses.Registry(d)
    ids = []
    for kind, ref, title, due in chores_spec:
        ids.append(chores.add_chore(reg, course=slug, kind=kind, ref=ref, title=title, due_at=due)["id"])
    specs = tmp_path / "specs2"
    specs.mkdir()
    (specs / f"{slug}.json").write_text(json.dumps({"tasks": spec_tasks}, ensure_ascii=False), encoding="utf-8")
    return d, specs, ids


def test_spec_task_merges_into_chore_task_by_due_date(tmp_path):
    d, specs, ids = _dup_reg(tmp_path, [("assignment", "1", "קריאה ושאלה", "2026-10-18T08:00:00+03:00"),
                                        ("assignment", "2", "אחרת", "2026-11-30T08:00:00+02:00")],
                             [{"key": "t1", "title": "מטלה (הגשה 18.10.2026, 08:00) - x", "primary": [{"page": 1, "title": "Cohen Attributes"}]}])
    report = tasks.migrate(d, specs)
    course = json.loads((d / "kane.json").read_text())
    assert not [t for t in course["tasks"] if t["id"].startswith("s-")]
    assert {t["id"]: t.get("spec_key") for t in course["tasks"]}[ids[0]] == "t1"
    assert course["sources"][0]["tasks"] == [ids[0]]
    assert report["merged"] == [{"course": "kane", "spec_task": "t1", "into": ids[0], "why": "due date"}]
    assert report["possible_duplicates"] == []


def test_spec_task_merges_into_only_open_chore_of_its_kind(tmp_path):
    d, specs, ids = _dup_reg(tmp_path, [("forum-post", "1", "תודעת השליחות", None), ("assignment", "2", "מטלה", None)],
                             [{"key": "פורום 1", "title": "פורום (שיעור 1)", "primary": []}])
    report = tasks.migrate(d, specs)
    assert report["merged"][0]["into"] == ids[0] and report["merged"][0]["why"] == "only open chore of its kind"


def test_ambiguous_spec_task_stays_a_possible_duplicate(tmp_path):
    d, specs, ids = _dup_reg(tmp_path, [("assignment", "1", "א", None), ("assignment", "2", "ב", None)],
                             [{"key": "מטלה 1", "title": "מטלה (ללא תאריך)", "primary": []}])
    report = tasks.migrate(d, specs)
    assert report["merged"] == [] and [x["spec_task"] for x in report["possible_duplicates"]] == ["s-מטלה 1"]


def test_unsubmit_reopens_only_what_submit_closed(tmp_path, capsys, monkeypatch):
    d, c = make_reg(tmp_path)
    tasks.task_submit(d, "kane", c["id"])
    stored = json.loads((d / "kane.json").read_text())["tasks"][0]
    assert stored["closed_chores"] == [c["id"]]
    tasks.task_submit(d, "kane", c["id"])  # a repeat submit keeps the first list
    assert json.loads((d / "kane.json").read_text())["tasks"][0]["closed_chores"] == [c["id"]]
    out = tasks.task_unsubmit(d, "kane", c["id"])
    assert out == {"task": c["id"], "status": "open", "reopened_chores": [c["id"]]}
    assert [x for x in chores.load(courses.Registry(d)) if x["id"] == c["id"]][0]["status"] == "open"
    stored = json.loads((d / "kane.json").read_text())["tasks"][0]
    assert stored["status"] == "open" and stored["submitted_at"] is None and "closed_chores" not in stored
    assert tasks.task_unsubmit(d, "kane", c["id"])["reopened_chores"] == []  # idempotent
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(d.parent))
    monkeypatch.setenv("ACADEMIC_TERM", d.name)
    tasks.task_submit(d, "kane", c["id"])
    assert courses.main(["task", "unsubmit", "--course", "kane", "--task", c["id"]]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "open"


def test_reopen_chore(tmp_path):
    d, c = make_reg(tmp_path)
    reg = courses.Registry(d)
    chores.mark_done(reg, c["id"])
    assert chores.reopen(reg, c["id"][:6])["status"] == "open"
    assert chores.reopen(reg, c["id"])["status"] == "open"


def test_explicit_date_that_conflicts_blocks_the_only_open_fallback(tmp_path):
    d, specs, ids = _dup_reg(tmp_path, [("assignment", "1", "קריאה", "2026-10-18T08:00:00+03:00")],
                             [{"key": "t1", "title": "מטלה (הגשה 30.11.2026, 08:00)", "primary": []}])
    report = tasks.migrate(d, specs)
    assert report["merged"] == [] and [x["spec_task"] for x in report["possible_duplicates"]] == ["s-t1"]


def test_explicit_date_may_fold_into_an_undated_only_open_chore(tmp_path):
    d, specs, ids = _dup_reg(tmp_path, [("forum-post", "1", "פורום", None)],
                             [{"key": "פורום 1", "title": "פורום (עד 25.10.2026)", "primary": []}])
    assert tasks.migrate(d, specs)["merged"][0]["into"] == ids[0]


def test_explicit_date_matching_two_chores_is_not_folded(tmp_path):
    d, specs, ids = _dup_reg(tmp_path, [("assignment", "1", "א", "2026-10-18T08:00:00+03:00"), ("assignment", "2", "ב", "2026-10-18T09:00:00+03:00")],
                             [{"key": "t1", "title": "מטלה (הגשה 18.10.2026)", "primary": []}])
    assert tasks.migrate(d, specs)["merged"] == []


def test_reading_chore_becomes_a_reading_task(tmp_path):
    d, c = make_reg(tmp_path)
    r = chores.add_chore(courses.Registry(d), course="kane", kind="reading", ref="1152530", title="קריאה לקראת שיעור הבא",
                         core_texts=["דן, תולדות תורת הסוד העברית יג, 322-341"], due_at="2026-10-25T14:00:00+02:00")
    by_id = {t["id"]: t for t in tasks.sync_tasks(d, "kane")}
    assert by_id[r["id"]]["kind"] == "reading"
