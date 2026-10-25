import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "courses"))
import chores
import courses
import lemida_coverage

DATE = "2026-10-24"
RUN_ID = "2026-10-24T030000-4242"
NOTIFICATIONS_URL = "https://lemida.biu.ac.il/message/output/popup/notifications.php"


def make_registry(tmp_path, extra=()):
    d = tmp_path / "term"
    d.mkdir()
    (d / "term.json").write_text(json.dumps({"term": "T", "timezone": "Asia/Jerusalem"}), encoding="utf-8")
    (d / "cohen.json").write_text(json.dumps({"slug": "cohen", "name": "הרמן כהן", "lemida_course_id": 11}), encoding="utf-8")
    (d / "kane.json").write_text(json.dumps({"slug": "kane", "name": "קאנט", "lemida_course_id": 12}), encoding="utf-8")
    for course in extra:
        (d / f"{course['slug']}.json").write_text(json.dumps(course), encoding="utf-8")
    return courses.Registry(d)


def clean_payload(**overrides):
    payload = {
        "date": DATE,
        "run_id": RUN_ID,
        "courses": {
            "cohen": {"visited": True, "new_assign_modules": [101], "assign_handled": [101]},
            "kane": {"visited": True, "new_assign_modules": [], "assign_handled": []},
        },
        "notifications": {
            "page": NOTIFICATIONS_URL,
            "complete": True,
            "listed": [1, 2, 3],
            "opened": [3, 1, 2],
        },
    }
    payload.update(overrides)
    return payload


def write_coverage(reg, payload, date=DATE):
    path = reg.directory / "logs" / f"lemida-coverage-{date}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def check(reg, **kwargs):
    kwargs.setdefault("run_id", RUN_ID)
    return lemida_coverage.check(reg, DATE, **kwargs)


def test_clean_run_has_no_gaps(tmp_path):
    reg = make_registry(tmp_path)
    write_coverage(reg, clean_payload())
    assert check(reg) == []
    assert chores.load(reg) == []


def test_missing_coverage_file_is_a_gap(tmp_path):
    reg = make_registry(tmp_path)
    gaps = check(reg)
    assert len(gaps) == 1 and "missing" in gaps[0] and "lemida-coverage-2026-10-24.json" in gaps[0]


def test_active_course_without_lemida_id_is_a_gap_and_adds_a_chore(tmp_path):
    reg = make_registry(tmp_path, extra=[{"slug": "levy", "name": "לוי"}])
    write_coverage(reg, clean_payload(courses={
        "cohen": {"visited": True, "new_assign_modules": [], "assign_handled": []},
        "kane": {"visited": True, "new_assign_modules": [], "assign_handled": []},
    }))
    gaps = check(reg)
    assert len(gaps) == 1 and "levy" in gaps[0] and "lemida_course_id" in gaps[0]
    stored = chores.load(reg)
    assert len(stored) == 1
    assert stored[0]["course"] == "levy" and stored[0]["kind"] == "manual" and stored[0]["ref"] == "lemida-id-levy"
    check(reg)  # a rerun updates the same chore
    assert len(chores.load(reg)) == 1


def test_finished_course_without_lemida_id_is_not_a_gap(tmp_path):
    old = {"slug": "old", "name": "ישן", "status": "finished"}
    reg = make_registry(tmp_path, extra=[old])
    write_coverage(reg, clean_payload())
    assert check(reg) == []
    assert not any(c["course"] == "old" for c in chores.load(reg))


def test_active_course_not_visited_is_a_gap(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    payload["courses"]["kane"]["visited"] = False
    write_coverage(reg, payload)
    gaps = check(reg)
    assert len(gaps) == 1 and "kane" in gaps[0] and "not visited" in gaps[0]


def test_course_absent_from_coverage_is_not_visited(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    del payload["courses"]["cohen"]
    write_coverage(reg, payload)
    gaps = check(reg)
    assert len(gaps) == 1 and "cohen" in gaps[0] and "not visited" in gaps[0]


def test_new_assign_module_not_handled_is_a_gap(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    payload["courses"]["cohen"] = {"visited": True, "new_assign_modules": [101, 102], "assign_handled": [101]}
    write_coverage(reg, payload)
    gaps = check(reg)
    assert len(gaps) == 1 and "cohen" in gaps[0] and "102" in gaps[0] and "assign" in gaps[0]


def test_unlisted_notification_not_opened_is_a_gap(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    payload["notifications"]["listed"] = [1, 2, 3, 4]
    payload["notifications"]["opened"] = [1, 3]
    write_coverage(reg, payload)
    gaps = check(reg)
    assert gaps == ["notification 2 listed but not opened", "notification 4 listed but not opened"]


def test_every_gap_is_reported_together(tmp_path):
    reg = make_registry(tmp_path, extra=[{"slug": "levy", "name": "לוי"}])
    payload = clean_payload()
    payload["courses"]["kane"]["visited"] = False
    payload["notifications"]["opened"] = [1]
    write_coverage(reg, payload)
    gaps = check(reg)
    assert len(gaps) == 4  # levy has no id, kane not visited, notifications 2 and 3 not opened


# --- binding to this run -------------------------------------------------------------------------

def test_report_from_another_run_is_a_stale_gap(tmp_path):
    reg = make_registry(tmp_path)
    write_coverage(reg, clean_payload(run_id="2026-10-23T030000-99"))
    gaps = check(reg)
    assert len(gaps) == 1 and "stale" in gaps[0] and RUN_ID in gaps[0]


def test_report_without_run_id_is_a_gap(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    del payload["run_id"]
    write_coverage(reg, payload)
    gaps = check(reg)
    assert len(gaps) == 1 and "run_id" in gaps[0]


def test_report_dated_another_day_is_a_gap(tmp_path):
    reg = make_registry(tmp_path)
    write_coverage(reg, clean_payload(date="2026-10-23"))
    gaps = check(reg)
    assert len(gaps) == 1 and "date" in gaps[0] and DATE in gaps[0]


def test_unreadable_file_is_a_gap(tmp_path):
    reg = make_registry(tmp_path)
    path = reg.directory / "logs" / f"lemida-coverage-{DATE}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    gaps = check(reg)
    assert len(gaps) == 1 and "unreadable" in gaps[0]


def test_non_object_file_is_a_gap(tmp_path):
    reg = make_registry(tmp_path)
    write_coverage(reg, ["cohen"])
    assert len(check(reg)) == 1


# --- schema: a missing or malformed section is a gap, never a silent pass -------------------------

def test_notifications_must_be_complete(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    payload["notifications"]["complete"] = False
    write_coverage(reg, payload)
    gaps = check(reg)
    assert len(gaps) == 1 and "notifications" in gaps[0] and "complete" in gaps[0]


def test_notifications_complete_must_be_true_not_truthy(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    payload["notifications"]["complete"] = "yes"
    write_coverage(reg, payload)
    assert any("complete" in g for g in check(reg))


def test_notifications_page_must_be_the_notifications_url(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    payload["notifications"]["page"] = "https://lemida.biu.ac.il/message/index.php"
    write_coverage(reg, payload)
    gaps = check(reg)
    assert len(gaps) == 1 and "notifications.php" in gaps[0]


def test_missing_notifications_section_is_a_gap(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    del payload["notifications"]
    write_coverage(reg, payload)
    gaps = check(reg)
    assert len(gaps) == 1 and "notifications" in gaps[0]


def test_notification_lists_must_be_lists(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    payload["notifications"]["listed"] = "1,2,3"
    del payload["notifications"]["opened"]
    write_coverage(reg, payload)
    gaps = check(reg)
    assert any("listed" in g for g in gaps) and any("opened" in g for g in gaps)


def test_courses_must_be_an_object(tmp_path):
    reg = make_registry(tmp_path)
    write_coverage(reg, clean_payload(courses=[]))
    gaps = check(reg)
    assert any("courses" in g for g in gaps)
    assert any("cohen" in g and "not visited" in g for g in gaps)


def test_visited_must_be_a_strict_bool(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    payload["courses"]["cohen"]["visited"] = "true"
    payload["courses"]["kane"]["visited"] = 1
    write_coverage(reg, payload)
    gaps = check(reg)
    assert len(gaps) == 2 and all("not visited" in g for g in gaps)


def test_assign_lists_must_be_lists(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    payload["courses"]["cohen"] = {"visited": True, "new_assign_modules": "101", "assign_handled": [101]}
    write_coverage(reg, payload)
    gaps = check(reg)
    assert len(gaps) == 1 and "cohen" in gaps[0] and "new_assign_modules" in gaps[0]


def test_missing_assign_handled_is_a_gap(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    payload["courses"]["kane"] = {"visited": True, "new_assign_modules": []}
    write_coverage(reg, payload)
    gaps = check(reg)
    assert len(gaps) == 1 and "kane" in gaps[0] and "assign_handled" in gaps[0]


def test_course_entry_that_is_not_an_object_is_a_gap(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    payload["courses"]["cohen"] = True
    write_coverage(reg, payload)
    gaps = check(reg)
    assert len(gaps) == 1 and "cohen" in gaps[0]


# --- scope: --courses checks only the named active courses -----------------------------------------

def test_only_named_courses_are_checked(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    del payload["courses"]["cohen"]  # would be a gap if checked
    write_coverage(reg, payload)
    assert check(reg, only=["kane"]) == []
    gaps = check(reg, only=["cohen"])
    assert len(gaps) == 1 and "cohen" in gaps[0] and "not visited" in gaps[0]


def test_named_course_that_is_finished_is_skipped(tmp_path):
    old = {"slug": "old", "name": "ישן", "status": "finished"}
    reg = make_registry(tmp_path, extra=[old])
    write_coverage(reg, clean_payload())
    assert check(reg, only=["old", "kane"]) == []


def test_named_unknown_course_is_a_gap(tmp_path):
    reg = make_registry(tmp_path)
    write_coverage(reg, clean_payload())
    gaps = check(reg, only=["nobody"])
    assert len(gaps) == 1 and "nobody" in gaps[0] and "unknown" in gaps[0]


def test_only_still_checks_notifications(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    payload["notifications"]["opened"] = []
    write_coverage(reg, payload)
    assert len(check(reg, only=["kane"])) == 3


# --- CLI ----------------------------------------------------------------------------------------------

def test_cli_exit_codes_and_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(tmp_path))
    reg = make_registry(tmp_path)
    base = ["--term", reg.directory.name, "lemida-coverage-check", "--date", DATE, "--run-id", RUN_ID]
    assert courses.main(base) == 1  # missing file
    write_coverage(reg, clean_payload())
    assert courses.main(base) == 0
    payload = clean_payload()
    payload["courses"]["cohen"]["visited"] = False
    write_coverage(reg, payload)
    capsys.readouterr()
    assert courses.main(base + ["--json"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["date"] == DATE and any("cohen" in g for g in out["gaps"])


def test_cli_requires_run_id(tmp_path, monkeypatch):
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(tmp_path))
    reg = make_registry(tmp_path)
    write_coverage(reg, clean_payload())
    try:
        courses.main(["--term", reg.directory.name, "lemida-coverage-check", "--date", DATE])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("--run-id must be required")


def test_cli_run_id_mismatch_and_courses_scope(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(tmp_path))
    reg = make_registry(tmp_path)
    payload = clean_payload()
    payload["courses"]["cohen"]["visited"] = False
    write_coverage(reg, payload)
    base = ["--term", reg.directory.name, "lemida-coverage-check", "--date", DATE]
    assert courses.main(base + ["--run-id", "other-run", "--courses", "kane"]) == 1
    assert "stale" in capsys.readouterr().out
    assert courses.main(base + ["--run-id", RUN_ID, "--courses", "kane"]) == 0
    assert courses.main(base + ["--run-id", RUN_ID, "--courses", "kane cohen"]) == 1
    assert "cohen" in capsys.readouterr().out


def test_empty_course_scope_is_a_gap_not_a_pass(tmp_path):
    reg = make_registry(tmp_path)
    write_coverage(reg, clean_payload())
    gaps = check(reg, only=[])
    assert len(gaps) == 1 and "nothing was checked" in gaps[0]
