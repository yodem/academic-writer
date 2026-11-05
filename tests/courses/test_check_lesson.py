import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "courses"))
import courses  # noqa: E402


def _registry(tmp_path, lessons):
    (tmp_path / "term.json").write_text(json.dumps({"term": "T", "naming": {}}), encoding="utf-8")
    (tmp_path / "c1.json").write_text(json.dumps({"slug": "c1", "name": "Course", "book_id": "book-1", "lessons": lessons}), encoding="utf-8")
    return courses.Registry(tmp_path)


def _read_reply(text_or_pages, nxt=None):
    """A `trove items read --json` reply: a book text split on '# ' headings, or {page: content}."""
    if isinstance(text_or_pages, str):
        chunks = ["# " + c for c in text_or_pages.split("# ") if c.strip()] if text_or_pages.startswith("# ") else []
        pages = [{"pageNum": i, "content": c, "part": 1, "parts": 1} for i, c in enumerate(chunks, 1)]
    else:
        pages = text_or_pages
    return json.dumps({"items": [{"id": "book-1", "pages": pages, "next": nxt}]})


def _runner(toc, book=None):
    def run(cmd, **kwargs):
        if cmd[:3] == ["trove", "items", "read"]:
            text = book if book is not None else "# a\n# b\n# c\n- מפתח שיעור: 2026-01-05-1204\n# d\n"
            return subprocess.CompletedProcess(cmd, 0, _read_reply(text), "")
        assert cmd[:3] == ["trove", "items", "toc"]
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"items": [{"id": "book-1", "toc": toc}]}), "")
    return run


TOC = [
    {"title": "Course · Index", "page": 1, "level": 1},
    {"title": "תמלולי שיעורים", "page": 2, "level": 1},
    {"title": "שיעור 01 · 2026-01-05", "page": 3, "level": 2},
    {"title": "Course · Changelog", "page": 4, "level": 1},
]


def test_done_and_nested(tmp_path):
    reg = _registry(tmp_path, [{"date": "2026-01-05", "lesson_key": "2026-01-05-1204", "status": "done", "trove_page": 3}])
    assert courses.check_lesson(reg, "c1", "2026-01-05", runner=_runner(TOC)) == []


def test_not_done(tmp_path):
    reg = _registry(tmp_path, [{"date": "2026-01-05", "lesson_key": "2026-01-05-1204", "status": "queued", "trove_page": None}])
    assert "not done" in courses.check_lesson(reg, "c1", "2026-01-05", runner=_runner(TOC))[0]


def test_not_nested(tmp_path):
    reg = _registry(tmp_path, [{"date": "2026-01-05", "lesson_key": "2026-01-05-1204", "status": "done", "trove_page": 4}])
    assert "not a level-2 entry" in courses.check_lesson(reg, "c1", "2026-01-05", runner=_runner(TOC))[0]


def test_missing_lesson(tmp_path):
    reg = _registry(tmp_path, [])
    assert "no lesson recorded" in courses.check_lesson(reg, "c1", "2026-01-05", runner=_runner(TOC))[0]


def test_exact_key_ignores_other_queued_lesson_same_day(tmp_path):
    lessons = [
        {"date": "2026-01-05", "lesson_key": "2026-01-05-1204", "status": "done", "trove_page": 3},
        {"date": "2026-01-05", "lesson_key": "2026-01-05-1610", "status": "queued", "trove_page": None},
    ]
    reg = _registry(tmp_path, lessons)
    assert courses.check_lesson(reg, "c1", "2026-01-05-1204", runner=_runner(TOC)) == []
    assert "not done" in courses.check_lesson(reg, "c1", "2026-01-05", runner=_runner(TOC))[0]


def test_legacy_key_field(tmp_path):
    reg = _registry(tmp_path, [{"date": "2026-01-05", "key": "2026-01-05-1204", "status": "done", "trove_page": 3}])
    assert courses.check_lesson(reg, "c1", "2026-01-05-1204", runner=_runner(TOC)) == []


def test_rejects_partial_selectors(tmp_path):
    reg = _registry(tmp_path, [{"date": "2026-01-05", "lesson_key": "2026-01-05-1204", "status": "done", "trove_page": 3}])
    for bad in ("", "2026", "2026-01", "2026-01-05-12"):
        assert "invalid lesson selector" in courses.check_lesson(reg, "c1", bad, runner=_runner(TOC))[0]


def test_appended_lesson_verifies_before_done(tmp_path):
    reg = _registry(tmp_path, [{"date": "2026-01-05", "lesson_key": "2026-01-05-1204", "status": "appended", "trove_page": 3}])
    assert courses.check_lesson(reg, "c1", "2026-01-05-1204", runner=_runner(TOC)) == []


def test_lesson_done_records_appended_then_done(tmp_path):
    reg = _registry(tmp_path, [{"date": "2026-01-05", "lesson_key": "2026-01-05-1204", "status": "queued", "trove_page": None}])
    assert courses.mark_lesson_done(reg, "c1", "2026-01-05-1204", 3, status="appended")["status"] == "appended"
    assert courses.mark_lesson_done(reg, "c1", "2026-01-05-1204", 3)["status"] == "done"
    import pytest
    with pytest.raises(ValueError):
        courses.mark_lesson_done(reg, "c1", "2026-01-05-1204", 3, status="bogus")


def _book_runner(text):
    def run(cmd, **kwargs):
        assert cmd[:3] == ["trove", "items", "read"]
        return subprocess.CompletedProcess(cmd, 0, _read_reply(text), "")
    return run


BOOK = """# Course · Course
intro
# תמלולי שיעורים
entry
# שיעור 01 · 2026-01-05
- מפתח שיעור: 2026-01-05-0000-2
body
# שיעור 02 · 2026-01-05
- מפתח שיעור: 2026-01-05-0000
body
"""


def test_find_lesson_page_exact_key_not_prefix(tmp_path):
    reg = _registry(tmp_path, [])
    assert courses.find_lesson_page(reg, "c1", "2026-01-05-0000", runner=_book_runner(BOOK)) == 4
    assert courses.find_lesson_page(reg, "c1", "2026-01-05-0000-2", runner=_book_runner(BOOK)) == 3
    assert courses.find_lesson_page(reg, "c1", "2026-01-05-1204", runner=_book_runner(BOOK)) is None



def test_exact_key_rejects_page_of_another_lesson(tmp_path):
    reg = _registry(tmp_path, [{"date": "2026-01-05", "lesson_key": "2026-01-05-1204", "status": "appended", "trove_page": 3}])
    other = "# a\n# b\n# c\n- מפתח שיעור: 2026-01-05-1610\n# d\n"
    assert "does not carry lesson key" in courses.check_lesson(reg, "c1", "2026-01-05-1204", runner=_runner(TOC, other))[0]


def _paged_runner(replies):
    """Serve `trove items read` replies keyed by (--pages, --part); record the calls."""
    calls = []

    def run(cmd, **kwargs):
        assert cmd[:3] == ["trove", "items", "read"]
        rng = cmd[cmd.index("--pages") + 1]
        part = cmd[cmd.index("--part") + 1] if "--part" in cmd else None
        calls.append((rng, part))
        return subprocess.CompletedProcess(cmd, 0, replies[(rng, part)], "")
    run.calls = calls
    return run


def _page(n, content, part=1, parts=1):
    return {"pageNum": n, "content": content, "part": part, "parts": parts}


def test_find_lesson_page_follows_the_cursor_past_the_byte_limit(tmp_path):
    # the old `items get` stopped at ~20 KB: a key on a later page was "found on None"
    reg = _registry(tmp_path, [])
    runner = _paged_runner({
        ("all", None): _read_reply([_page(1, "# Course · C\n"), _page(2, "# תמלולי שיעורים\n")], {"pages": "3-4"}),
        ("3-4", None): _read_reply([_page(3, "# x\n")], {"pages": "4"}),
        ("4", None): _read_reply([_page(4, "# שיעור 1\n- מפתח שיעור: 2026-01-05-0000\n")]),
    })
    assert courses.find_lesson_page(reg, "c1", "2026-01-05-0000", runner=runner) == 4
    assert runner.calls == [("all", None), ("3-4", None), ("4", None)]


def test_read_book_pages_joins_parts_of_a_long_page():
    runner = _paged_runner({
        ("all", None): _read_reply([_page(1, "# a\n"), _page(2, "# long\nfirst half ", 1, 2)], {"pages": "2-3", "part": 2}),
        ("2-3", "2"): _read_reply([_page(2, "second half\n", 2, 2), _page(3, "# c\n")]),
    })
    pages = courses.read_book_pages("book-1", runner=runner)
    assert pages == {1: "# a\n", 2: "# long\nfirst half second half\n", 3: "# c\n"}


def test_read_book_pages_rejects_a_repeating_cursor():
    import pytest
    runner = _paged_runner({
        ("all", None): _read_reply([_page(1, "# a\n")], {"pages": "2"}),
        ("2", None): _read_reply([_page(2, "# b\n")], {"pages": "2"}),
    })
    with pytest.raises(ValueError, match="cursor repeated"):
        courses.read_book_pages("book-1", runner=runner)


def test_find_lesson_page_uses_page_numbers_not_heading_count(tmp_path):
    # a page with two '# ' headings no longer shifts every later page number
    reg = _registry(tmp_path, [])
    runner = _paged_runner({("all", None): _read_reply([
        _page(1, "# Course · C\n# second heading on page 1\n"),
        _page(2, "# שיעור 1\n- מפתח שיעור: 2026-01-05-0000\n"),
    ])})
    assert courses.find_lesson_page(reg, "c1", "2026-01-05-0000", runner=runner) == 2

