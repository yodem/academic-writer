import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import book_audit  # noqa: E402


def course(slug="a", lid=123):
    return {"slug": slug, "lemida_course_id": lid, "notebook_id": "nb-1",
            "drive_folder_id": "DRV", "book_id": "b1"}


def registry(tmp_path, monkeypatch, courses):
    root = tmp_path
    tmp_path = root / "t1"
    tmp_path.mkdir(exist_ok=True)
    for c in courses:
        (tmp_path / f"{c['slug']}.json").write_text(json.dumps(c))
    (tmp_path / "term.json").write_text(json.dumps({"slug": "x"}))
    (tmp_path / "links.json").write_text("{}")
    (tmp_path / "noslug.json").write_text("{}")
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(root))
    monkeypatch.delenv("ACADEMIC_TERM", raising=False)


def test_block_contents():
    b = book_audit.render_ids_block(course())
    assert "למדה: מזהה 123" in b and "nb-1" in b
    assert "https://drive.google.com/drive/folders/DRV" in b


def test_null_lemida_renders_none_line():
    assert book_audit.NO_LEMIDA in book_audit.render_ids_block(course(lid=None))


def test_block_passes_check():
    for c in (course(), course(lid=None)):
        assert book_audit.check_page(c, "# Course\n" + book_audit.render_ids_block(c)) == []


def test_missing_items_reported():
    assert book_audit.check_page(course(), "nothing") == ["lemida_id", "notebook_id", "drive_link"]
    assert book_audit.check_page(course(lid=None), "nb-1 DRV") == ["lemida_id"]


def test_registry_skips(tmp_path, monkeypatch):
    registry(tmp_path, monkeypatch, [course("a"), course("b")])
    assert [c["slug"] for c in book_audit.load_courses()] == ["a", "b"]


def test_cli_offline(tmp_path, monkeypatch, capsys):
    registry(tmp_path, monkeypatch, [course("a"), course("b")])
    d = tmp_path / "t1" / "pages"
    d.mkdir()
    (d / "a.md").write_text(book_audit.render_ids_block(course("a")))
    assert book_audit.main(["--pages-dir", str(d)]) == 1  # b missing
    (d / "b.md").write_text(book_audit.render_ids_block(course("b")))
    capsys.readouterr()
    assert book_audit.main(["--pages-dir", str(d), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert book_audit.main(["--pages-dir", str(d), "--course", "zzz"]) == 2
