import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "courses"))
import chores
import courses
import lemida_coverage

DATE = "2026-10-24"


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
        "courses": {
            "cohen": {"visited": True, "new_assign_modules": [101], "assign_handled": [101]},
            "kane": {"visited": True, "new_assign_modules": [], "assign_handled": []},
        },
        "notifications": {
            "page": "https://lemida.biu.ac.il/message/output/popup/notifications.php",
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


def test_clean_run_has_no_gaps(tmp_path):
    reg = make_registry(tmp_path)
    write_coverage(reg, clean_payload())
    assert lemida_coverage.check(reg, DATE) == []
    assert chores.load(reg) == []


def test_missing_coverage_file_is_a_gap(tmp_path):
    reg = make_registry(tmp_path)
    gaps = lemida_coverage.check(reg, DATE)
    assert len(gaps) == 1 and "missing" in gaps[0] and "lemida-coverage-2026-10-24.json" in gaps[0]


def test_active_course_without_lemida_id_is_a_gap_and_adds_a_chore(tmp_path):
    reg = make_registry(tmp_path, extra=[{"slug": "levy", "name": "לוי"}])
    write_coverage(reg, clean_payload(courses={
        "cohen": {"visited": True, "new_assign_modules": [], "assign_handled": []},
        "kane": {"visited": True, "new_assign_modules": [], "assign_handled": []},
    }))
    gaps = lemida_coverage.check(reg, DATE)
    assert len(gaps) == 1 and "levy" in gaps[0] and "lemida_course_id" in gaps[0]
    stored = chores.load(reg)
    assert len(stored) == 1
    assert stored[0]["course"] == "levy" and stored[0]["kind"] == "manual" and stored[0]["ref"] == "lemida-id-levy"
    lemida_coverage.check(reg, DATE)  # a rerun updates the same chore
    assert len(chores.load(reg)) == 1


def test_finished_course_without_lemida_id_is_not_a_gap(tmp_path):
    old = {"slug": "old", "name": "ישן", "status": "finished"}
    reg = make_registry(tmp_path, extra=[old])
    write_coverage(reg, clean_payload())
    assert lemida_coverage.check(reg, DATE) == []
    assert not any(c["course"] == "old" for c in chores.load(reg))


def test_active_course_not_visited_is_a_gap(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    payload["courses"]["kane"]["visited"] = False
    write_coverage(reg, payload)
    gaps = lemida_coverage.check(reg, DATE)
    assert len(gaps) == 1 and "kane" in gaps[0] and "not visited" in gaps[0]


def test_course_absent_from_coverage_is_not_visited(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    del payload["courses"]["cohen"]
    write_coverage(reg, payload)
    gaps = lemida_coverage.check(reg, DATE)
    assert len(gaps) == 1 and "cohen" in gaps[0] and "not visited" in gaps[0]


def test_new_assign_module_not_handled_is_a_gap(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    payload["courses"]["cohen"] = {"visited": True, "new_assign_modules": [101, 102], "assign_handled": [101]}
    write_coverage(reg, payload)
    gaps = lemida_coverage.check(reg, DATE)
    assert len(gaps) == 1 and "cohen" in gaps[0] and "102" in gaps[0] and "assign" in gaps[0]


def test_unlisted_notification_not_opened_is_a_gap(tmp_path):
    reg = make_registry(tmp_path)
    payload = clean_payload()
    payload["notifications"]["listed"] = [1, 2, 3, 4]
    payload["notifications"]["opened"] = [1, 3]
    write_coverage(reg, payload)
    gaps = lemida_coverage.check(reg, DATE)
    assert len(gaps) == 2 and all("notification" in g and "listed but not opened" in g for g in gaps)
    assert gaps == ["notification 2 listed but not opened", "notification 4 listed but not opened"]


def test_every_gap_is_reported_together(tmp_path):
    reg = make_registry(tmp_path, extra=[{"slug": "levy", "name": "לוי"}])
    payload = clean_payload()
    payload["courses"]["kane"]["visited"] = False
    payload["notifications"]["opened"] = [1]
    write_coverage(reg, payload)
    gaps = lemida_coverage.check(reg, DATE)
    assert len(gaps) == 4  # levy has no id, kane not visited, notifications 2 and 3 not opened


def test_cli_exit_codes_and_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(tmp_path))
    reg = make_registry(tmp_path)
    base = ["--term", reg.directory.name, "lemida-coverage-check", "--date", DATE]
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
