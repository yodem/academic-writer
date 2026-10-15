import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import ms_audit  # noqa: E402


def course(slug="a", lid=123):
    return {"slug": slug, "lemida_course_id": lid, "notebook_id": "nb-1",
            "drive_folder_id": "DRV", "manuscript_id": "m1"}


def registry(tmp_path, monkeypatch, courses):
    for c in courses:
        (tmp_path / f"{c['slug']}.json").write_text(json.dumps(c))
    (tmp_path / "term.json").write_text(json.dumps({"slug": "x"}))
    (tmp_path / "links.json").write_text("{}")
    (tmp_path / "noslug.json").write_text("{}")
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(tmp_path))


def test_block_contents():
    b = ms_audit.render_instructions_block(course())
    assert "123" in b and "nb-1" in b
    assert "https://drive.google.com/drive/folders/DRV" in b
    assert ms_audit.TOC_RULE in b
    assert "תמלולי שיעורים" in b and "lesson-notes" in b


def test_null_lemida_renders_none():
    assert "none" in ms_audit.render_instructions_block(course(lid=None))


def test_block_passes_check():
    for c in (course(), course(lid=None)):
        assert ms_audit.check_instructions(c, ms_audit.render_instructions_block(c)) == []


def test_missing_items_reported():
    assert ms_audit.check_instructions(course(), "nothing") == [
        "lemida_id", "notebook_id", "drive_link", "toc_rule"]


def test_registry_skips(tmp_path, monkeypatch):
    registry(tmp_path, monkeypatch, [course("a"), course("b")])
    assert [c["slug"] for c in ms_audit.load_courses()] == ["a", "b"]


def test_cli_offline(tmp_path, monkeypatch, capsys):
    registry(tmp_path, monkeypatch, [course("a"), course("b")])
    d = tmp_path / "ins"
    d.mkdir()
    (d / "a.txt").write_text(ms_audit.render_instructions_block(course("a")))
    assert ms_audit.main(["--instructions-dir", str(d)]) == 1  # b missing
    (d / "b.txt").write_text(ms_audit.render_instructions_block(course("b")))
    capsys.readouterr()
    assert ms_audit.main(["--instructions-dir", str(d), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert ms_audit.main(["--instructions-dir", str(d), "--course", "zzz"]) == 2
