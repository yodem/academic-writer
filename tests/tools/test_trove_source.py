import importlib.util
from pathlib import Path

import pytest

SRC = Path.home() / "dev/jewish-studies/bar-ilan/courses-tashpaz/tools/trove_source.py"
if not SRC.exists():
    pytest.skip("trove_source.py not present", allow_module_level=True)
_spec = importlib.util.spec_from_file_location("trove_source", SRC)
ts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ts)


def e(title, page, level=1):
    return {"title": title, "page": page, "level": level}


def pages(entries):
    return [x["page"] for x in entries]


def run(toc, new_entries):
    head, named, rest = ts.blocks(toc)
    readings = named.get(ts.READINGS)
    return ts.assemble(head, named, readings, new_entries, rest)


def l1_pages(entries):
    return [x["page"] for x in entries if x["level"] == 1]


@pytest.mark.parametrize("lessons", [True, False])
def test_changelog_in_rest_is_placed_by_page(lessons):
    toc = [e("Guide - g", 1), e("Course · Changelog - c", 3)]
    if lessons:
        toc.insert(1, e(f"{ts.LESSONS} - l", 2))
    toc.append(e(f"{ts.READINGS} - r", 4))
    # blocks() puts Changelog (p.3) in rest, after readings (p.4) in the old assembly
    out = run(toc, [e("Src - s", 5, 2)])
    assert l1_pages(out) == sorted(l1_pages(out))
    assert pages(out)[-1] == 5 and out[-1]["level"] == 2


def test_changelog_with_children_stay_attached():
    toc = [e("Guide - g", 1), e(f"{ts.READINGS} - r", 4), e("Course · Changelog - c", 3), e("Entry - x", 3, 2)]
    out = run(toc, [])
    titles = [x["title"] for x in out]
    assert titles.index("Entry - x") == titles.index("Course · Changelog - c") + 1
    assert l1_pages(out) == [1, 3, 4]


def test_already_ordered_unchanged():
    toc = [e("Guide - g", 1), e(f"{ts.LESSONS} - l", 2), e("L1 - a", 3, 2),
           e(f"{ts.READINGS} - r", 4), e("Old - o", 5, 2), e("Course · Changelog - c", 6)]
    assert run(toc, []) == toc


def test_new_entries_land_under_readings():
    toc = [e("Guide - g", 1), e(f"{ts.READINGS} - r", 2), e("Old - o", 3, 2), e("Course · Changelog - c", 4)]
    new = [e("Src - s", 5, 2), e("Sec - t", 6, 3)]
    out = run(toc, new)
    assert [x["title"] for x in out] == [
        "Guide - g", f"{ts.READINGS} - r", "Old - o", "Src - s", "Sec - t", "Course · Changelog - c"]
