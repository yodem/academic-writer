import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import toc_audit as ta  # noqa: E402


def e(title, page, level=1):
    return {"title": title, "page": page, "level": level}


GOOD = [e("A - a", 1), e("B - b", 2, 2), e("C - c", 3, 2), e("D - d", 4)]


def test_good():
    assert ta.audit_toc(GOOD, 4)["ok"]


def test_missing_page():
    r = ta.audit_toc([e("A - a", 1), e("C - c", 3)], 4)
    assert r["missing"] == [2, 4] and not r["ok"]


def test_duplicate():
    r = ta.audit_toc(GOOD + [e("D2 - x", 4, 2)], 4)
    assert r["duplicate"] == [4] and not r["ok"]


def test_no_hint():
    for bad in ("Title", "Title - ", "Title -  "):
        r = ta.audit_toc([e(bad, 1)], 1)
        assert len(r["no_hint"]) == 1 and not r["ok"], bad


def test_course_name_with_hyphen_is_not_a_hint():
    name = "חוויה והתנסות - שאלת אחדות התודעה"
    assert ta.audit_toc([e(f"Course · {name}", 1)], 1)["ok"]  # without the name it looks hinted
    r = ta.audit_toc([e(f"Course · {name}", 1)], 1, course_name=name)
    assert len(r["no_hint"]) == 1 and not r["ok"]
    assert ta.audit_toc([e(f"Course · {name} - סקירת הקורס", 1)], 1, course_name=name)["ok"]


def test_out_of_order():
    r = ta.audit_toc([e("A - a", 1), e("C - c", 3), e("B - b", 2)], 3)
    assert r["out_of_order"] == [{"index": 2, "prev_page": 3, "page": 2}] and not r["ok"]


def test_level_gap():
    r = ta.audit_toc([e("A - a", 1), e("B - b", 2, 3)], 2)
    assert r["level_gap"][0]["index"] == 1 and not r["ok"]


def test_first_level_must_be_one():
    assert ta.audit_toc([e("A - a", 1, 2)], 1)["level_gap"]


def test_level_can_drop_freely():
    assert ta.audit_toc([e("A - a", 1), e("B - b", 2, 2), e("C - c", 3, 3), e("D - d", 4)], 4)["ok"]


def test_cli_toc_json(tmp_path, capsys):
    f = tmp_path / "t.json"
    f.write_text(json.dumps({"items": [{"id": "x", "pageCount": 4, "toc": GOOD}]}))
    assert ta.main(["--toc-json", str(f)]) == 0
    f.write_text(json.dumps({"items": [{"id": "x", "pageCount": 5, "toc": GOOD}]}))
    assert ta.main(["--toc-json", str(f), "--json"]) == 1
    assert '"missing": [\n        5' in capsys.readouterr().out


def test_registry_skips(tmp_path, monkeypatch):
    tmp_path = tmp_path / "t1"
    tmp_path.mkdir()
    (tmp_path / "term.json").write_text('{"slug": "t"}')
    (tmp_path / "links.json").write_text('{"slug": "l"}')
    (tmp_path / "noslug.json").write_text('{"a": 1}')
    (tmp_path / "c.json").write_text('{"slug": "c", "book_id": "b"}')
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(tmp_path.parent))
    monkeypatch.delenv("ACADEMIC_TERM", raising=False)
    assert [c["slug"] for c in ta.load_registry()] == ["c"]


def test_all_uses_fetch(tmp_path, monkeypatch):
    tmp_path = tmp_path / "t1"
    tmp_path.mkdir()
    (tmp_path / "term.json").write_text('{"slug": "t"}')
    (tmp_path / "c.json").write_text('{"slug": "c", "book_id": "b1"}')
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(tmp_path.parent))
    monkeypatch.delenv("ACADEMIC_TERM", raising=False)
    monkeypatch.setattr(ta, "fetch_toc", lambda b: (GOOD, 4, b))
    assert ta.main(["--all"]) == 0
    monkeypatch.setattr(ta, "fetch_toc", lambda b: (GOOD, 6, b))
    assert ta.main(["--all"]) == 1


def test_tree_order_allows_lesson_appended_at_end():
    toc = [{"title": "C - h", "page": 1, "level": 1}, {"title": "L - h", "page": 2, "level": 1},
           {"title": "Lesson - h", "page": 4, "level": 2}, {"title": "R - h", "page": 3, "level": 1}]
    assert ta.audit_toc(toc, 4)["ok"]


def test_tree_order_rejects_sibling_going_back():
    toc = [{"title": "C - h", "page": 1, "level": 1}, {"title": "R - h", "page": 3, "level": 1},
           {"title": "X - h", "page": 2, "level": 1}]
    assert ta.audit_toc(toc, 3)["out_of_order"]


def _term_root(tmp_path, term="t1", extra=()):
    root = tmp_path / "courses"
    for name in (term, *extra):
        (root / name).mkdir(parents=True)
        (root / name / "term.json").write_text('{"slug": "%s"}' % name)
        (root / name / f"{name}-c.json").write_text('{"slug": "%s-c", "book_id": "b"}' % name)
    return root


def test_registry_root_with_term_env(tmp_path, monkeypatch):
    """Finding 4: ACADEMIC_COURSES_DIR is the root; ACADEMIC_TERM picks the term (as courses.py does)."""
    root = _term_root(tmp_path, "t1", extra=("t2",))
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(root))
    monkeypatch.setenv("ACADEMIC_TERM", "t2")
    assert ta.registry_dir() == root / "t2"
    assert [c["slug"] for c in ta.load_registry()] == ["t2-c"]


def test_registry_root_single_term_and_ambiguous(tmp_path, monkeypatch):
    root = _term_root(tmp_path, "t1")
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(root))
    monkeypatch.delenv("ACADEMIC_TERM", raising=False)
    assert [c["slug"] for c in ta.load_registry()] == ["t1-c"]
    root2 = _term_root(tmp_path / "x", "a", extra=("b",))
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(root2))
    import pytest
    with pytest.raises(ValueError):
        ta.registry_dir()


def test_all_tools_resolve_identically(tmp_path, monkeypatch):
    import book_audit
    from tools import toc_rebuild as tr
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "courses"))
    import courses
    root = _term_root(tmp_path, "t1", extra=("t2",))
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(root))
    monkeypatch.setenv("ACADEMIC_TERM", "t1")
    want = courses.registry_dir()
    assert ta.registry_dir() == book_audit.registry_dir() == tr.registry_dir() == want == root / "t1"
