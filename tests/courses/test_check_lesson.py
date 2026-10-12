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


def _runner(toc):
    def run(cmd, **kwargs):
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
