import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "courses"))
import chores
import courses
import lemida_coverage
import tasks

DATE = "2026-10-24"
RUN_ID = "2026-10-24T030000-4242"
BASE = "https://lemida.example.org"


def make_reg(tmp_path):
    d = tmp_path / "term"
    d.mkdir()
    (d / "term.json").write_text(json.dumps({"term": "T", "timezone": "Asia/Jerusalem", "lemida": {"base_url": BASE}}), encoding="utf-8")
    (d / "kane.json").write_text(json.dumps({
        "slug": "kane", "name": "Kane", "lemida_course_id": 12,
        "watch_seen": {"modules": {"801": {"type": "quiz"}, "701": {"type": "assign"}}}}), encoding="utf-8")
    (d / "cohen.json").write_text(json.dumps({"slug": "cohen", "name": "Cohen", "lemida_course_id": 11}), encoding="utf-8")
    (d / "levy.json").write_text(json.dumps({"slug": "levy", "name": "Levy"}), encoding="utf-8")
    return courses.Registry(d)


def add(reg, course, kind, ref, title="T"):
    return chores.add_chore(reg, course=course, kind=kind, ref=ref, title=title, due_at="2026-11-01T00:00:00+02:00")["id"]


def write_cov(reg, rows, run_id=RUN_ID, date=DATE):
    path = reg.directory / "logs" / f"lemida-coverage-{date}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"date": date, "run_id": run_id, "submissions": {"complete": True, "checked": rows}}), encoding="utf-8")


def status_of(reg, slug, tid):
    return next(t for t in tasks.sync_tasks(reg.directory, slug, write=False) if t["id"] == tid)["status"]


def test_open_handins_lists_open_assignment_with_url_and_type(tmp_path):
    reg = make_reg(tmp_path)
    tid = add(reg, "kane", "assignment", "701", "Essay")
    add(reg, "kane", "forum-post", "702", "Post")
    out = tasks.open_handins(reg.directory)
    rows = {r["task"]: r for r in out["handins"]}
    assert rows[tid]["type"] == "assign" and rows[tid]["cmid"] == "701" and rows[tid]["course"] == "kane"
    assert rows[tid]["url"] == f"{BASE}/mod/assign/view.php?id=701" and rows[tid]["title"] == "Essay"
    assert {r["type"] for r in out["handins"]} == {"assign", "forum"}
    assert out["skipped"] == []


def test_open_handins_skips_non_numeric_refs_missing_ids_and_closed_tasks(tmp_path):
    reg = make_reg(tmp_path)
    ev = add(reg, "kane", "exam", "ev123")
    post = add(reg, "kane", "assignment", "d1-p2")
    nolemida = add(reg, "levy", "assignment", "900")
    done = add(reg, "kane", "assignment", "703")
    tasks.task_submit(reg.directory, "kane", done)
    out = tasks.open_handins(reg.directory)
    assert out["handins"] == []
    reasons = {s["task"]: s["reason"] for s in out["skipped"]}
    assert set(reasons) == {ev, post, nolemida}
    assert "numeric" in reasons[ev] and "lemida_course_id" in reasons[nolemida]


def test_open_handins_respects_only_and_quiz_via_watch_seen(tmp_path):
    reg = make_reg(tmp_path)
    quiz = add(reg, "kane", "exam", "801", "Quiz 1")
    add(reg, "kane", "exam", "802", "Paper exam")  # no quiz type in watch_seen: not a Lemida hand-in
    other = add(reg, "cohen", "assignment", "901")
    out = tasks.open_handins(reg.directory)
    assert {r["task"] for r in out["handins"]} == {quiz, other}
    assert next(r for r in out["handins"] if r["task"] == quiz)["type"] == "quiz"
    assert [r["task"] for r in tasks.open_handins(reg.directory, ["cohen"])["handins"]] == [other]


def row(tid, **kw):
    return {"task": tid, "course": "kane", "cmid": "701", "type": "assign", **kw}


def test_sync_submissions_submitted_and_team_submitted_close(tmp_path):
    reg = make_reg(tmp_path)
    a, b = add(reg, "kane", "assignment", "701"), add(reg, "kane", "assignment", "702")
    write_cov(reg, [row(a, status="submitted"), row(b, status="new", team_status="submitted")])
    report = tasks.sync_submissions(reg.directory, DATE, RUN_ID)
    assert {r["task"] for r in report["closed"]} == {a, b}
    assert status_of(reg, "kane", a) == status_of(reg, "kane", b) == "submitted"
    assert all(c["status"] == "done" for c in chores.load(reg))


def test_sync_submissions_draft_reopened_new_stay_open(tmp_path):
    reg = make_reg(tmp_path)
    ids = [add(reg, "kane", "assignment", str(710 + i)) for i in range(3)]
    write_cov(reg, [row(t, status=s) for t, s in zip(ids, ("draft", "reopened", "new"))])
    report = tasks.sync_submissions(reg.directory, DATE, RUN_ID)
    assert report["closed"] == [] and [r["status"] for r in report["kept_open"]] == ["draft", "reopened", "new"]
    assert all(status_of(reg, "kane", t) == "open" for t in ids)


def test_sync_submissions_quiz_review_link_closes_zero_stays(tmp_path):
    reg = make_reg(tmp_path)
    a, b = add(reg, "kane", "exam", "801"), add(reg, "kane", "exam", "803")
    write_cov(reg, [row(a, type="quiz", quiz_review_links=1), row(b, type="quiz", quiz_review_links=0)])
    tasks.sync_submissions(reg.directory, DATE, RUN_ID)
    assert status_of(reg, "kane", a) == "submitted" and status_of(reg, "kane", b) == "open"


def test_sync_submissions_forum_author_match_closes_mismatch_stays(tmp_path):
    reg = make_reg(tmp_path)
    ids = [add(reg, "kane", "forum-post", str(720 + i)) for i in range(4)]
    write_cov(reg, [row(ids[0], type="forum", my_user_id=55, author_ids=["9", "55"]),
                    row(ids[1], type="forum", my_user_id="55", author_ids=[9, 8]),
                    row(ids[2], type="forum", author_ids=[55]),
                    row(ids[3], type="forum", my_user_id="", author_ids=[""])])
    tasks.sync_submissions(reg.directory, DATE, RUN_ID)
    assert [status_of(reg, "kane", t) for t in ids] == ["submitted", "open", "open", "open"]


def test_sync_submissions_error_and_unknown_type_never_confirm(tmp_path):
    reg = make_reg(tmp_path)
    a, b = add(reg, "kane", "assignment", "701"), add(reg, "kane", "assignment", "702")
    write_cov(reg, [row(a, status="submitted", error="timeout"), row(b, type="wiki", status="submitted"),
                    row("nosuchtask", status="submitted")])
    report = tasks.sync_submissions(reg.directory, DATE, RUN_ID)
    assert report["closed"] == [] and len(report["kept_open"]) == 2 and len(report["errors"]) == 1
    assert status_of(reg, "kane", a) == status_of(reg, "kane", b) == "open"


def test_sync_submissions_stale_run_or_missing_file_closes_nothing_and_exits_1(tmp_path, capsys):
    reg = make_reg(tmp_path)
    a = add(reg, "kane", "assignment", "701")
    args = type("A", (), {"task_command": "sync-submissions", "date": DATE, "run_id": RUN_ID, "json": False})()
    assert tasks.run_task_command(reg.directory, args) == 1  # no file yet
    write_cov(reg, [row(a, status="submitted")], run_id="other-run")
    assert tasks.run_task_command(reg.directory, args) == 1
    assert "stale" in capsys.readouterr().out
    assert status_of(reg, "kane", a) == "open"


def test_sync_submissions_is_idempotent_and_handles_midnight_rollover(tmp_path):
    reg = make_reg(tmp_path)
    a = add(reg, "kane", "assignment", "701")
    write_cov(reg, [row(a, status="submitted")], date="2026-10-25")  # the watch ran past midnight
    first = tasks.sync_submissions(reg.directory, DATE, RUN_ID)
    second = tasks.sync_submissions(reg.directory, DATE, RUN_ID)
    assert len(first["closed"]) == 1 and second["closed"] == [] and status_of(reg, "kane", a) == "submitted"
    assert lemida_coverage.resolve_coverage_path(reg, DATE, RUN_ID)[1] == "2026-10-25"
