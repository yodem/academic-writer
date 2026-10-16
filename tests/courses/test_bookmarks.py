import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "courses"))
import bookmarks
import chores
import courses


def make_registry(tmp_path):
    d = tmp_path / "2026"
    d.mkdir()
    (d / "term.json").write_text(json.dumps({
        "term": "תשפ״ז", "timezone": "Asia/Jerusalem",
        "lemida": {"base_url": "https://lemida.example"},
    }), encoding="utf-8")
    (d / "kane.json").write_text(json.dumps({
        "slug": "kane", "name": "ספר הקנה", "notebook_id": "nb-1", "book_id": "book-1", "lemida_course_id": 117904,
        "sources": [],
    }), encoding="utf-8")
    (d / "levinas.json").write_text(json.dumps({
        "slug": "levinas", "name": "לוינס", "notebook_id": "nb-2", "book_id": "book-2", "lemida_course_id": None,
    }), encoding="utf-8")
    return courses.Registry(d)


def _titles(plan):
    return [item["title"] for item in plan["items"]]


def test_plan_skips_empty_fields(tmp_path):
    reg = make_registry(tmp_path)
    assert "Lemida" not in _titles(bookmarks.plan(reg, "levinas"))
    assert all(item["url"] and item["title"] for item in bookmarks.plan(reg, "levinas")["items"])


def test_plan_urls_follow_the_known_forms(tmp_path):
    reg = make_registry(tmp_path)
    chores.add_chore(reg, course="kane", kind="assignment", ref="3251919", title="מטלה 1", due_at="2026-10-18T08:00:00+03:00")
    items = {i["title"]: i["url"] for i in bookmarks.plan(reg, "kane")["items"]}
    assert items["NotebookLM"] == "https://notebooklm.google.com/notebook/nb-1"
    assert items["Lemida"] == "https://lemida.example/course/view.php?id=117904"
    assert items["מטלה 1"] == "https://lemida.example/mod/view.php?id=3251919"


def test_earliest_dated_chore_wins(tmp_path):
    reg = make_registry(tmp_path)
    chores.add_chore(reg, course="kane", kind="assignment", ref="1", title="late", due_at="2026-11-01T23:59:00+02:00")
    chores.add_chore(reg, course="kane", kind="assignment", ref="2", title="soon", due_at="2026-10-18T08:00:00+03:00")
    chores.add_chore(reg, course="kane", kind="manual", ref="3", title="undated")
    chores.add_chore(reg, course="levinas", kind="assignment", ref="4", title="other course", due_at="2026-10-01T08:00:00+03:00")
    assert bookmarks.current_task(reg, "kane")["title"] == "soon"


def test_undated_chore_is_the_fallback(tmp_path):
    reg = make_registry(tmp_path)
    chores.add_chore(reg, course="kane", kind="manual", ref="first", title="first undated")
    chores.add_chore(reg, course="kane", kind="manual", ref="second", title="second undated")
    assert bookmarks.current_task(reg, "kane")["title"] == "first undated"


def test_script_escapes_quotes_and_backslashes_and_keeps_hebrew(tmp_path):
    reg = make_registry(tmp_path)
    chores.add_chore(reg, course="kane", kind="assignment", ref="9", title='מטלה "א" \\ ב', due_at="2026-10-18T08:00:00+03:00")
    script = bookmarks.build_script([bookmarks.plan(reg, "kane")])
    assert 'title:"מטלה \\"א\\" \\\\ ב"' in script
    assert 'BIU תשפ״ז' in script


def test_same_registry_gives_byte_identical_script(tmp_path):
    reg = make_registry(tmp_path)
    first = bookmarks.build_script([bookmarks.plan(reg, s) for s in sorted(reg.courses)])
    second = bookmarks.build_script([bookmarks.plan(reg, s) for s in sorted(reg.courses)])
    assert first == second


def _fake_osascript(stdout="", returncode=0, stderr=""):
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    runner.calls = calls
    return runner


def test_check_passes_when_folders_match_the_plan(tmp_path):
    reg = make_registry(tmp_path)
    plans = [bookmarks.plan(reg, "kane")]
    matching = "".join(bookmarks._record(p) for p in plans) + "\n"
    assert bookmarks.check(plans, _fake_osascript(stdout=matching)) is True
    assert bookmarks.run(reg, slug="kane", check_only=True, runner=_fake_osascript(stdout=matching)) == 0


def test_check_fails_when_the_folder_is_absent(tmp_path):
    reg = make_registry(tmp_path)
    absent = "ספר הקנה" + bookmarks.US + bookmarks.ABSENT + bookmarks.RS + "\n"
    assert bookmarks.run(reg, slug="kane", check_only=True, runner=_fake_osascript(stdout=absent)) == 1


def test_check_is_read_only(tmp_path):
    reg = make_registry(tmp_path)
    runner = _fake_osascript(stdout="")
    bookmarks.run(reg, slug="kane", check_only=True, runner=runner)
    sent = runner.calls[0][1]["input"]
    assert "make new" not in sent and "delete every" not in sent


def test_chrome_not_running_exits_5(tmp_path):
    reg = make_registry(tmp_path)
    assert bookmarks.run(reg, slug="kane", runner=_fake_osascript(stdout="not running\n")) == 5


def test_osascript_failure_exits_5(tmp_path):
    reg = make_registry(tmp_path)
    assert bookmarks.run(reg, slug="kane", runner=_fake_osascript(returncode=1, stderr="boom")) == 5
    assert bookmarks.run(reg, slug="kane", check_only=True, runner=_fake_osascript(returncode=1, stderr="boom")) == 5


def test_missing_osascript_exits_5(tmp_path):
    reg = make_registry(tmp_path)

    def no_binary(args, **kwargs):
        raise FileNotFoundError("osascript")

    assert bookmarks.run(reg, slug="kane", runner=no_binary) == 5


def test_apply_runs_one_osascript_and_reports(tmp_path, capsys):
    reg = make_registry(tmp_path)
    runner = _fake_osascript(stdout="ok\n")
    assert bookmarks.run(reg, slug="kane", runner=runner) == 0
    assert len(runner.calls) == 1 and runner.calls[0][0] == ["osascript", "-"]
    assert "1 folder(s) written" in capsys.readouterr().out


def test_trove_items_need_a_known_form(tmp_path, monkeypatch):
    reg = make_registry(tmp_path)
    reg.courses["kane"]["sources"] = [{"title": "ספר הקנה", "trove": {"book_id": "tb-1", "page": 7}}]
    chores.add_chore(reg, course="kane", kind="assignment", ref="5", title="task", core_texts=["ספר הקנה", "unmapped"],
                     due_at="2026-10-18T08:00:00+03:00")
    assert "Trove" not in _titles(bookmarks.plan(reg, "kane"))
    monkeypatch.setattr(bookmarks, "TROVE_URL_FORM", "https://trove.test/{book_id}/{page}")
    items = bookmarks.plan(reg, "kane")["items"]
    assert ("ספר הקנה", "https://trove.test/tb-1/7") in [(i["title"], i["url"]) for i in items]
    assert "unmapped" not in _titles(bookmarks.plan(reg, "kane"))


def test_trove_book_stands_in_once_when_no_reading_maps(tmp_path, monkeypatch):
    reg = make_registry(tmp_path)
    chores.add_chore(reg, course="kane", kind="assignment", ref="5", title="task", core_texts=["unmapped"],
                     due_at="2026-10-18T08:00:00+03:00")
    monkeypatch.setattr(bookmarks, "TROVE_URL_FORM", "https://trove.test/{book_id}/{page}")
    titles = _titles(bookmarks.plan(reg, "kane"))
    assert titles.count("Trove") == 1


def test_cli_prints_script_without_touching_chrome(tmp_path, monkeypatch, capsys):
    make_registry(tmp_path)
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(tmp_path))
    def no_osascript(*args, **kwargs):
        raise AssertionError("Chrome must not be touched by --print-script")

    monkeypatch.setattr(subprocess, "run", no_osascript)
    assert courses.main(["--term", "2026", "bookmarks", "kane", "--print-script"]) == 0
    assert "on run" in capsys.readouterr().out


def test_cli_needs_a_slug_or_all(tmp_path, monkeypatch, capsys):
    make_registry(tmp_path)
    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(tmp_path))
    assert courses.main(["--term", "2026", "bookmarks", "--print-script"]) == 2


def test_cli_add_source_accepts_origin_library(tmp_path, monkeypatch, capsys):
    registry_dir = make_registry(tmp_path).directory
    reading = tmp_path / "reading.pdf"
    reading.write_bytes(b"%PDF-1.4\n%%EOF\n")
    seen = {}

    def fake_add_source(registry_, file, course_slug, **kwargs):
        seen.update(course=course_slug, origin=kwargs["origin"])
        return {"status": "added", "title": "Reading One"}

    monkeypatch.setenv("ACADEMIC_COURSES_DIR", str(registry_dir.parent))
    monkeypatch.setattr(courses, "add_source", fake_add_source)
    assert "library" in courses.ORIGINS
    code = courses.main(["--term", registry_dir.name, "add-source", str(reading), "--course", "kane", "--origin", "library"])
    assert code == 0
    assert seen == {"course": "kane", "origin": "library"}
    assert "added: Reading One" in capsys.readouterr().out
