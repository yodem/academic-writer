import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "courses"))
import watch_diff as wd  # noqa: E402


def mod(cmid, name="file", type_="file"):
    return {"cmid": cmid, "name": name, "type": type_, "url": f"https://lemida.biu.ac.il/mod/x/view.php?id={cmid}", "completion": "", "link": None}


def course(sections, declared=None):
    n = sum(len(s["modules"]) for s in sections)
    return {"kind": "course", "url": "https://lemida.biu.ac.il/course/view.php?id=1", "course_id": 1,
            "fetched_at": "2026-10-14T22:30:00+03:00", "sections": sections,
            "declared_module_count": declared if declared is not None else n}


def section(sid, modules, name=None):
    return {"id": sid, "name": name or f"unit {sid}", "modules": modules}


def forum(discussions):
    return {"kind": "forum", "url": "https://lemida.biu.ac.il/mod/forum/view.php?id=9", "course_id": 1,
            "fetched_at": "2026-10-14T22:30:00+03:00", "discussions": discussions}


def disc(did, replies=0):
    return {"id": did, "title": f"d{did}", "author": "lecturer", "date": "2026-10-10", "replies": replies}


def assign(cmid, due="נותרו 5 ימים", text="read pp. 308-322"):
    return {"kind": "assign", "url": f"https://lemida.biu.ac.il/mod/assign/view.php?id={cmid}", "course_id": 1,
            "fetched_at": "2026-10-14T22:30:00+03:00", "cmid": cmid, "title": "task", "text": text,
            "time_left_text": due, "due_text": due, "submission_status": "no attempt"}


def pages():
    return [course([section("s1", [mod("11"), mod("12")]), section("s2", [mod("21")])]), forum([disc("100")])]


def test_baseline_marks_everything_seen_and_emits_zero_new():
    p = pages()
    seen = wd.baseline(p)
    assert {"11", "12", "21"} <= set(seen["modules"])
    assert "100" in seen["discussions"]
    assert wd.diff_course(p, seen).is_empty()


def test_second_diff_on_identical_pages_is_empty():
    p = pages()
    seen = wd.baseline(p)
    assert wd.diff_course(copy.deepcopy(p), copy.deepcopy(seen)).is_empty()


def test_one_new_cmid_yields_exactly_one_new_module():
    p = pages()
    seen = wd.baseline(p)
    p[0]["sections"][1]["modules"].append(mod("22", "new reading"))
    p[0]["declared_module_count"] = 4
    d = wd.diff_course(p, seen)
    assert [m["cmid"] for m in d.new_modules] == ["22"]
    assert not d.new_discussions and not d.suspect


def test_legacy_lemida_seen_cmids_count_as_seen():
    p = pages()
    d = wd.diff_course(p, {"modules": {}, "discussions": {"100": 0}, "assigns": {}, "sections": {}},
                       legacy_seen={"11": 1791872898, "12": 0})
    assert [m["cmid"] for m in d.new_modules] == ["21"]


def test_source_origin_ref_counts_as_seen():
    p = pages()
    d = wd.diff_course(p, {"modules": {}, "discussions": {"100": 0}, "assigns": {}, "sections": {}},
                       legacy_seen={"11": 0, "12": 0}, sources=[{"origin_ref": "cm:21"}])
    assert d.new_modules == []


def test_suspect_page_does_not_delete_seen_ids():
    p = pages()
    seen = wd.baseline(p)
    broken = [course([section("s1", [mod("11")])], declared=3), p[1]]
    d = wd.diff_course(broken, seen)
    assert d.suspect is True and d.new_modules == []
    after = wd.advance(seen, d, set())
    assert {"11", "12", "21"} <= set(after["modules"])


def test_advance_only_moves_ok_ids():
    p = pages()
    seen = wd.baseline(p)
    p[0]["sections"][1]["modules"] += [mod("22"), mod("23")]
    p[0]["declared_module_count"] = 5
    d = wd.diff_course(p, seen)
    after = wd.advance(seen, d, {"22"})
    assert "22" in after["modules"] and "23" not in after["modules"]
    assert "23" not in seen["modules"]  # input is not mutated


def test_new_discussion_and_reply_growth():
    p = pages()
    seen = wd.baseline(p)
    p[1]["discussions"] = [disc("101"), disc("100", replies=2)]
    d = wd.diff_course(p, seen)
    assert [x["id"] for x in d.new_discussions] == ["101"]
    assert [x["id"] for x in d.reply_growth] == ["100"]


def test_changed_assignment_due_text_is_reported_once_it_changes():
    p = pages() + [assign("300")]
    seen = wd.baseline(p)
    assert wd.diff_course(p, seen).is_empty()
    p[2] = assign("300", due="נותרו 2 ימים")
    d = wd.diff_course(p, seen)
    assert [a["cmid"] for a in d.changed_assigns] == ["300"]
    p2 = pages() + [assign("301")]
    assert [a["cmid"] for a in wd.diff_course(p2, seen).new_assigns] == ["301"]


def test_last_content_section_is_the_last_section_with_modules():
    p = [course([section("s1", [mod("11")]), section("s2", [mod("21")]), section("s3", [])])]
    assert wd.diff_course(p, wd.baseline(p)).last_content_section == "s2"


def test_validate_page_rejects_bad_data():
    wd.validate_page(pages()[0])
    for bad in ({}, {"kind": "bogus", "url": "x"}, {"kind": "course", "url": "x"}):
        with pytest.raises(wd.WatchSchemaError):
            wd.validate_page(bad)
