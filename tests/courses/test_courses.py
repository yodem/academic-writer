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
        "drive_folder_id": "drive-1", "notebook_id": "note-1", "manuscript_id": "book-1",
    }), encoding="utf-8")
    return courses.Registry(d)


def test_normalise_name_collapses_space_and_quotes():
    assert courses.normalise_name('  א\u05f4  ב\tג  ') == 'א" ב ג'


def test_registry_loads_term_and_course(tmp_path):
    registry = make_registry(tmp_path)
    assert registry.term["timezone"] == "Asia/Jerusalem"
    assert registry.courses["sample"]["name"] == "Course  Name"


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
