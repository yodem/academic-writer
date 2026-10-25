import json
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

sys.path.insert(0, str(Path(__file__).parents[2] / "src/scripts/courses"))
import courses


def make_registry(tmp_path):
    d = tmp_path / "2026"
    d.mkdir()
    (d / "term.json").write_text(json.dumps({
        "term": "T", "timezone": "Asia/Jerusalem",
        "naming": {"drive": "{name}", "notebook": "{name}", "manuscript": "Personal · {term} · {name}"},
        "drive_subject_folders": {"Philosophy": "subject-1"}, "drive_remote": "gdrive",
    }), encoding="utf-8")
    (d / "sample.json").write_text(json.dumps({
        "slug": "sample", "name": "Course  Name", "drive_subject": "Philosophy",
        "drive_folder_id": "drive-1", "notebook_id": "note-1", "book_id": "book-1",
    }), encoding="utf-8")
    return courses.Registry(d)


def test_normalise_name_collapses_space_and_quotes():
    assert courses.normalise_name('  א\u05f4  ב\tג  ') == 'א" ב ג'


def test_registry_loads_term_and_course(tmp_path):
    registry = make_registry(tmp_path)
    assert registry.term["timezone"] == "Asia/Jerusalem"
    assert registry.courses["sample"]["name"] == "Course  Name"


def test_mark_lesson_done_records_page_under_lock(tmp_path):
    registry = make_registry(tmp_path)
    registry.courses["sample"]["lessons"] = [{"lesson_key": "2026-10-12-1200", "status": "queued", "trove_page": None}]
    (registry.directory / "sample.json").write_text(json.dumps(registry.courses["sample"]))
    saved = courses.mark_lesson_done(registry, "sample", "2026-10-12-1200", 7)
    assert saved["status"] == "done" and saved["trove_page"] == 7
    assert json.loads((registry.directory / "sample.json").read_text())["lessons"][0] == saved


def test_validate_pass_and_fail_with_injected_runner(tmp_path):
    registry = make_registry(tmp_path)
    outputs = {
        "nlm": [{"id": "note-1", "title": "Course Name"}],
        "trove": [{"id": "book-1", "title": "Personal · T · Course Name"}],
        "rclone": [{"ID": "drive-1", "Name": "Course Name", "IsDir": True}],
    }

    def runner(command, **kwargs):
        if command[0] == "nlm": result = outputs["nlm"]
        elif command[0] == "trove": result = outputs["trove"]
        else: result = outputs["rclone"]
        return subprocess.CompletedProcess(command, 0, json.dumps(result), "")

    assert courses.validate_registry(registry, runner) == []
    outputs["nlm"] = [{"id": "note-1", "title": "Wrong"}]
    failures = courses.validate_registry(registry, runner)
    assert len(failures) == 1
    assert "NotebookLM name mismatch" in failures[0]


def test_validate_reports_missing_resource_id(tmp_path):
    registry = make_registry(tmp_path)
    registry.courses["sample"]["notebook_id"] = ""
    outputs = {"nlm": [], "trove": [{"id": "book-1", "title": "Personal · T · Course Name"}], "rclone": [{"ID": "drive-1", "Name": "Course Name"}]}

    def runner(command, **kwargs):
        key = "nlm" if command[0] == "nlm" else "trove" if command[0] == "trove" else "rclone"
        return subprocess.CompletedProcess(command, 0, json.dumps(outputs[key]), "")

    assert any("missing notebook_id" in x for x in courses.validate_registry(registry, runner))


def test_validate_rclone_uses_subject_folder_id(tmp_path):
    registry = make_registry(tmp_path)
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        if command[0] == "nlm": output = [{"id": "note-1", "title": "Course Name"}]
        elif command[0] == "trove": output = [{"id": "book-1", "title": "Personal · T · Course Name"}]
        else: output = [{"ID": "drive-1", "Name": "Course Name"}]
        return subprocess.CompletedProcess(command, 0, json.dumps(output), "")

    courses.validate_registry(registry, runner)
    assert ["trove", "items", "list", "--json", "--no-session"] in commands  # books, not manuscripts
    rclone = next(command for command in commands if command[0] == "rclone")
    assert rclone[rclone.index("--drive-root-folder-id") + 1] == "subject-1"


def test_validate_template_error_is_reported_and_does_not_abort(tmp_path):
    registry = make_registry(tmp_path)
    registry.term["naming"] = {"drive": "{name}", "notebook": "{missing}", "manuscript": "Personal · {term} · {name}"}
    registry.courses["term"] = {"slug": "term", "name": "Term", "term": "course-value"}
    outputs = {
        "nlm": [{"id": "note-1", "title": "Course Name"}],
        "trove": [{"id": "book-1", "title": "Personal · T · Course Name"}],
        "rclone": [{"ID": "drive-1", "Name": "Course Name"}],
    }

    def runner(command, **kwargs):
        key = "nlm" if command[0] == "nlm" else "trove" if command[0] == "trove" else "rclone"
        return subprocess.CompletedProcess(command, 0, json.dumps(outputs[key]), "")

    problems = courses.validate_registry(registry, runner)
    assert any(problem.startswith("term: naming template error:") for problem in problems)
    assert any(problem.startswith("sample: naming template error:") for problem in problems)


def test_import_docx_continuation_extends_previous_stub_end(tmp_path):
    docx = tmp_path / "continued.docx"
    doc = Element(courses.W + "document")
    body = SubElement(doc, courses.W + "body")
    table = SubElement(body, courses.W + "tbl")
    row = SubElement(table, courses.W + "tr")
    _cell(row, "שעה")
    _cell(row, "יום שני")
    row = SubElement(table, courses.W + "tr")
    _cell(row, "12:00-14:00")
    course = _cell(row, "31182-02\nפילוסופיה של הרגשות\nד״ר נועם הופר")
    props = course.find("./" + courses.W + "tcPr")
    if props is None:
        props = SubElement(course, courses.W + "tcPr")
    SubElement(props, courses.W + "vMerge", {courses.W + "val": "restart"})
    row = SubElement(table, courses.W + "tr")
    _cell(row, "14:00-16:00")
    continuation = _cell(row, "")
    props = continuation.find("./" + courses.W + "tcPr")
    if props is None:
        props = SubElement(continuation, courses.W + "tcPr")
    SubElement(props, courses.W + "vMerge")
    with zipfile.ZipFile(docx, "w") as zf:
        zf.writestr("word/document.xml", tostring(doc))

    stubs = courses.parse_docx(docx)
    assert len(stubs) == 1
    assert stubs[0]["slots"][0]["start"] == "12:00"
    assert stubs[0]["slots"][0]["end"] == "16:00"


def test_main_bad_zip_file_exits_two_with_error(tmp_path, capsys):
    broken = tmp_path / "broken.docx"
    broken.write_text("not a docx", encoding="utf-8")
    assert courses.main(["import-docx", str(broken)]) == 2
    assert "error:" in capsys.readouterr().err


def _cell(row, text, span=1):
    tc = SubElement(row, courses.W + "tc")
    if span > 1:
        props = SubElement(tc, courses.W + "tcPr")
        SubElement(props, courses.W + "gridSpan", {courses.W + "val": str(span)})
    for line in text.split("\n"):
        p = SubElement(tc, courses.W + "p")
        r = SubElement(p, courses.W + "r")
        SubElement(r, courses.W + "t").text = line
    return tc


def make_docx(path):
    doc = Element(courses.W + "document")
    body = SubElement(doc, courses.W + "body")
    tbl = SubElement(body, courses.W + "tbl")
    row = SubElement(tbl, courses.W + "tr")
    _cell(row, "שעה")
    _cell(row, "יום ראשון", span=2)
    row = SubElement(tbl, courses.W + "tr")
    _cell(row, "12:00-14:00")
    _cell(row, "174003-01\nהמחשבה היהודית\nפרופ' חנוך בן-פזי", span=1)
    _cell(row, "מגדר\nד״ר פלונית", span=1)
    row = SubElement(tbl, courses.W + "tr")
    _cell(row, "14:00-16:00")
    _cell(row, "קריאות נבחרות: ספר הקנה", span=2)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", tostring(doc))


def test_import_docx_semester_subcolumns_and_yearly_span(tmp_path):
    docx = tmp_path / "schedule.docx"
    make_docx(docx)
    stubs = courses.parse_docx(docx)
    first = [x for x in stubs if x["slots"][0]["start"] == "12:00"]
    assert [(x["name"], x["slots"][0]["semester"]) for x in first] == [
        ("המחשבה היהודית", "A"), ("מגדר", "B")]
    yearly = [x for x in stubs if x["slots"][0]["start"] == "14:00"]
    assert len(yearly) == 1
    assert yearly[0]["slots"][0]["semester"] == "yearly"


def test_help_runs():
    result = subprocess.run([sys.executable, str(Path(__file__).parents[2] / "src/scripts/courses/courses.py"), "--help"], capture_output=True, text=True)
    assert result.returncode == 0


def test_registry_skips_json_without_slug(tmp_path):
    registry = make_registry(tmp_path)
    (registry.directory / "links.json").write_text(json.dumps({"sample": {"name": "x", "lemida_url": "u"}}), encoding="utf-8")
    (registry.directory / "chores.json").write_text("[]", encoding="utf-8")
    loaded = courses.Registry(registry.directory)
    assert list(loaded.courses) == ["sample"]


def test_lemida_blocked_detects_captcha_html():
    assert courses.lemida_blocked([{"slug": "kane", "error": "Moodle request failed: Expecting value: line 1 column 1 (char 0)"}])
    assert courses.lemida_blocked(["Radware Bot Manager Captcha"])
    assert not courses.lemida_blocked([{"slug": "kane", "error": "Moodle error invalidtoken: bad"}])


def test_daily_blocked_still_scans_voice_memos(tmp_path, monkeypatch, capsys):
    import lemida
    registry = make_registry(tmp_path)
    memos = tmp_path / "memos"
    memos.mkdir()
    (memos / "20261012 120422.m4a").write_bytes(b"memo")
    term = json.loads((registry.directory / "term.json").read_text())
    term["voice_memos_dir"] = str(memos)
    (registry.directory / "term.json").write_text(json.dumps(term))
    course = registry.courses["sample"]
    course["lemida_course_id"] = 1
    (registry.directory / "sample.json").write_text(json.dumps(course))
    scanned = []
    monkeypatch.setattr(courses, "map_recording", lambda reg, when: scanned.append(when) or (None, "no slot"))

    def blocked(*a, **k):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")  # what json.loads says on the captcha HTML

    monkeypatch.setattr(lemida, "lemida_sync", blocked)
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(registry.directory.parent))
    code = courses.main(["--term", registry.directory.name, "daily"])
    out = capsys.readouterr().out
    assert code == 5 and "lemida: blocked, use chrome watcher" in out
    assert len(scanned) == 1


def test_watch_diff_advances_only_with_apply_and_ok(tmp_path, monkeypatch, capsys):
    import watch_diff as wd
    registry = make_registry(tmp_path)
    calls = {}

    def fake_diff(pages, seen, *, legacy_seen=None, sources=None):
        calls["args"] = (pages, seen, legacy_seen, sources)
        return wd.Diff(new_modules=[{"cmid": "22"}])

    def fake_advance(seen, diff, ok_ids):
        calls["ok"] = ok_ids
        return {"modules": {i: {} for i in ok_ids}, "discussions": {}, "assigns": {}, "sections": {}}

    monkeypatch.setattr(wd, "diff_course", fake_diff)
    monkeypatch.setattr(wd, "advance", fake_advance)
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(registry.directory.parent))
    pages = tmp_path / "pages.json"
    pages.write_text("[]")
    base = ["--term", registry.directory.name]
    saved = lambda: json.loads((registry.directory / "sample.json").read_text())  # noqa: E731

    assert courses.main(base + ["watch-diff", "sample", "--pages", str(pages)]) == 0
    assert json.loads(capsys.readouterr().out)["new_modules"] == [{"cmid": "22"}]
    assert "watch_seen" not in saved() and calls["args"][2] == {}
    assert courses.main(base + ["watch-diff", "sample", "--pages", str(pages), "--apply"]) == 2
    assert "watch_seen" not in saved()
    assert courses.main(base + ["watch-diff", "sample", "--pages", str(pages), "--apply", "--ok", "22"]) == 0
    assert saved()["watch_seen"]["modules"] == {"22": {}} and calls["ok"] == {"22"}
    assert courses.main(base + ["watch-diff", "ghost", "--pages", str(pages)]) == 2


def test_watch_diff_baseline_marks_everything_seen(tmp_path, monkeypatch, capsys):
    registry = make_registry(tmp_path)
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(registry.directory.parent))
    mods = [{"cmid": "11", "name": "f", "type": "file", "url": "u", "completion": "", "link": None}]
    page = {"kind": "course", "url": "u", "course_id": 1, "fetched_at": "2026-10-14T22:30:00+03:00",
            "sections": [{"id": "s1", "name": "unit", "modules": mods}], "declared_module_count": 1}
    pages = tmp_path / "pages.json"
    pages.write_text(json.dumps([page]))
    base = ["--term", registry.directory.name]
    assert courses.main(base + ["watch-diff", "sample", "--baseline", "--pages", str(pages)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["baseline"] is True and out["modules"] == 1
    saved = json.loads((registry.directory / "sample.json").read_text())
    assert "11" in saved["watch_seen"]["modules"]
    assert courses.main(base + ["watch-diff", "sample", "--pages", str(pages)]) == 0
    diff = json.loads(capsys.readouterr().out)
    assert diff["suspect"] is False and diff["new_modules"] == []
    assert courses.main(base + ["watch-diff", "ghost", "--baseline", "--pages", str(pages)]) == 2


def test_registry_active_courses(tmp_path):
    term = tmp_path / "term"
    term.mkdir()
    (term / "term.json").write_text(json.dumps({"term": "t", "status": "active"}))
    (term / "live.json").write_text(json.dumps({"slug": "live"}))
    (term / "done.json").write_text(json.dumps({"slug": "done", "status": "finished", "finished_at": "2026-10-01", "book_id": "B1"}))
    reg = courses.Registry(term)
    assert set(reg.courses) == {"live", "done"}
    assert set(reg.active_courses()) == {"live"}
    # the override keeps one named finished course, never the others
    assert set(reg.active_courses(include="done")) == {"live", "done"}
    # a finished term finishes every course in it
    (term / "term.json").write_text(json.dumps({"term": "t", "status": "finished"}))
    assert courses.Registry(term).active_courses() == {}
