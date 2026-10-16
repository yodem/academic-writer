import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import toc_rebuild as tr  # noqa: E402
from tools.toc_audit import audit_toc  # noqa: E402


def test_heading_strips_page_marker_and_hebrew():
    assert tr.extract_heading("\n# Schnytzer, Animals · p. 25\n\nx") == "Schnytzer, Animals"
    assert tr.extract_heading("# תמלולי שיעורים\n") == "תמלולי שיעורים"
    assert tr.extract_heading("no heading") == ""
    assert " - " not in tr.extract_heading("# A - B")


def test_hint_load_page_when():
    t = "# T\n\n> Load this page when: you need the overview.\n\nBody text."
    assert tr.extract_hint(t) == "you need the overview"


def test_hint_first_sentence_hebrew_and_cap():
    t = "# כותרת\n\nזהו משפט ראשון. ואחריו עוד.\n"
    assert tr.extract_hint(t) == "זהו משפט ראשון."[:-1]
    long = "# T\n\n" + "word " * 100
    assert len(tr.extract_hint(long)) <= tr.HINT_MAX


def test_hint_skips_lists_bold_and_quotes():
    t = "# T\n\n**Bold title**\n\n- item\n\n> abstract: x\n\nReal paragraph. More."
    assert tr.extract_hint(t) == "Real paragraph"


def test_no_hint():
    assert tr.extract_hint("# T\n") == ""
    plan = tr.build_plan(1, [], lambda p: "# Only title\n")
    assert plan["counts"]["needs_hint"] == 1
    assert plan["needs_hint"][0]["page"] == 1 and plan["needs_hint"][0]["title"] == "Only title"
    assert not audit_toc(plan["toc"], 1)["ok"]


PAGES = {
    1: "# Course · X\n\n> Load this page when: overview.\n",
    2: "# תמלולי שיעורים\n\n> Load this page when: lessons.\n",
    3: "# Course · Changelog\n\n> Load this page when: history.\n",
    4: "# חומרי קריאה\n\n> Load this page when: sources.\n",
    5: "# Smith, Paper · Reading guide\n\n> Load this page when: smith.\n",
    6: "# Smith, Paper · p. 3\n\nIntro sentence here. More.\n",
    7: "# שיעור 1 · 2026-10-11 · X\n\n> Load this page when: lesson one.\n",
}


def test_levels_and_order():
    plan = tr.build_plan(7, [], lambda p: PAGES[p])
    toc = plan["toc"]
    # Tree order: the lesson page (7, appended last) nests under the lessons index (2).
    assert [e["page"] for e in toc] == [1, 2, 7, 3, 4, 5, 6]
    assert [e["level"] for e in toc] == [1, 1, 2, 1, 1, 2, 3]
    assert toc[3]["title"].startswith("Course · Changelog - ")
    assert audit_toc(toc, 7)["ok"]
    assert plan["counts"]["derived"] == 7


def test_reuse_existing_hint_title_and_level():
    existing = [{"title": "My Title - kept hint", "page": 6, "level": 4},
                {"title": "x - y", "page": 5, "level": 2}]
    plan = tr.build_plan(7, existing, lambda p: PAGES[p])
    e6 = next(e for e in plan["toc"] if e["page"] == 6)
    assert e6["title"] == "My Title - kept hint" and e6["level"] == 3  # clamped to prev+1
    assert plan["counts"]["reused"] == 2 and plan["counts"]["derived"] == 5


def test_merge_same_page_shallowest_wins():
    existing = [{"title": "Deep - hint b", "page": 2, "level": 3},
                {"title": "Top - hint a", "page": 2, "level": 1},
                {"title": "Mid - hint c", "page": 2, "level": 2}]
    m = tr.merge_existing(existing)
    assert m["title"] == "Top" and m["level"] == 1 and m["hint"] == "hint a; hint b; hint c"
    plan = tr.build_plan(3, existing, lambda p: PAGES[p])
    assert plan["counts"]["merged"] == 1
    assert [e["page"] for e in plan["toc"]] == [1, 2, 3]
    assert plan["toc"][1]["title"] == "Top - hint a; hint b; hint c"


def test_hints_override_and_fill():
    plan = tr.build_plan(1, [], lambda p: "# T\n", {"1": "supplied hint"})
    assert plan["toc"][0]["title"] == "T - supplied hint"
    assert plan["counts"]["supplied"] == 1 and not plan["needs_hint"]


def test_out_of_range_existing_dropped():
    plan = tr.build_plan(1, [{"title": "A - b", "page": 9, "level": 1}], lambda p: PAGES[1])
    assert len(plan["toc"]) == 1


def test_gate_refuses_missing_page():
    calls = []
    toc = [{"title": "A - a", "page": 1, "level": 1}, {"title": "C - c", "page": 3, "level": 1}]
    code, msg = tr.apply_plan("b", toc, 3, 5, 2, run=lambda *a, **k: calls.append(a), version_fn=lambda b: 5)
    assert code == 1 and "refused" in msg and not calls


def test_apply_refuses_version_change_and_applies_when_ok():
    toc = [{"title": "A - a", "page": 1, "level": 1}]
    calls = []

    class R:
        returncode, stdout, stderr = 0, "", ""

    def run(*a, **k):
        calls.append(a)
        return R()

    code, msg = tr.apply_plan("b", toc, 1, 5, 1, run=run, version_fn=lambda b: 6)
    assert code == 1 and not calls
    code, msg = tr.apply_plan("b", toc, 1, 5, 1, run=run, version_fn=lambda b: 5)
    assert code == 0 and calls and "enrich" in calls[0][0]


def test_registered_sources_nest_under_readings():
    pages = {1: "# Course · X\n\n> Load this page when: o.\n", 2: "# חומרי קריאה\n\n> Load this page when: s.\n",
             3: "# Syllabus · details\n\n> Load this page when: d.\n", 4: "# Syllabus · grades\n\n> Load this page when: g.\n",
             5: "# Baumgarten notes\n\n> Load this page when: b.\n"}
    existing = [{"title": f"E{p} - h", "page": p, "level": 1} for p in range(1, 6)]
    plan = tr.build_plan(5, existing, lambda p: pages[p], sources=[
        {"title": "Syllabus", "page": 3}, {"title": "Baumgarten - Poetry", "page": None}],
        overrides={5: {"title": "Baumgarten - Poetry"}})
    toc = plan["toc"]
    assert [e["level"] for e in toc] == [1, 1, 2, 3, 2]
    assert toc[2]["title"].startswith("Syllabus - ") and toc[4]["title"].startswith("Baumgarten - Poetry - ")
    assert audit_toc(toc, 5)["ok"]


def test_source_appended_after_lessons_groups_under_readings_even_when_readings_index_first():
    """Finding 3: readings index precedes lessons index; an appended source must not nest under lessons."""
    pages = {1: "# Course · X\n\n> Load this page when: o.\n",
             2: "# חומרי קריאה\n\n> Load this page when: sources.\n",
             3: "# תמלולי שיעורים\n\n> Load this page when: lessons.\n",
             4: "# שיעור 1 · 2026-10-11 · X\n\n> Load this page when: lesson one.\n",
             5: "# Baumgarten notes\n\n> Load this page when: b.\n",
             6: "# Baumgarten notes · p. 2\n\nIntro sentence. More.\n"}
    plan = tr.build_plan(6, [], lambda p: pages[p], sources=[{"title": "Baumgarten", "page": 5}])
    toc = plan["toc"]
    assert [e["page"] for e in toc] == [1, 2, 5, 6, 3, 4]
    assert [e["level"] for e in toc] == [1, 1, 2, 3, 1, 2]
    assert audit_toc(toc, 6, sources=["Baumgarten"])["ok"]


def test_audit_rejects_source_nested_under_lessons():
    toc = [{"title": "C - h", "page": 1, "level": 1}, {"title": "חומרי קריאה - h", "page": 2, "level": 1},
           {"title": "תמלולי שיעורים - h", "page": 3, "level": 1}, {"title": "שיעור 1 - h", "page": 4, "level": 2},
           {"title": "Baumgarten - h", "page": 5, "level": 2}]
    assert audit_toc(toc, 5)["ok"]  # structure alone is fine
    r = audit_toc(toc, 5, sources=["Baumgarten"])
    assert not r["ok"] and r["source_parent"][0]["title"] == "Baumgarten"


def test_audit_rejects_same_title_on_other_page_when_real_source_page_under_lessons():
    """Re-review: title-only match false-passes; the registered page must be the level-2 readings entry."""
    toc = [{"title": "C - h", "page": 1, "level": 1}, {"title": "חומרי קריאה - h", "page": 2, "level": 1},
           {"title": "Baumgarten - decoy", "page": 3, "level": 2},
           {"title": "תמלולי שיעורים - h", "page": 4, "level": 1}, {"title": "שיעור 1 - h", "page": 5, "level": 2},
           {"title": "Baumgarten - h", "page": 6, "level": 2}]
    r = audit_toc(toc, 6, sources=[{"title": "Baumgarten", "page": 6}])
    assert not r["ok"] and r["source_parent"][0]["page"] == 6
    assert audit_toc(toc, 6, sources=[{"title": "Baumgarten", "page": 3}])["ok"]
