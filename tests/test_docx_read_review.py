import json, subprocess, sys, pathlib
import pytest

ROOT = pathlib.Path(__file__).parent.parent
SCRIPT = ROOT / "src/scripts/docx-read-review.py"
sys.path.insert(0, str(ROOT / "tests/fixtures/docx"))
import editor_fixture  # noqa: E402

OLD_KEYS = {"id", "kind", "anchorText", "text", "author", "date"}


def _read(path):
    return json.loads(subprocess.check_output([sys.executable, SCRIPT, path, "--json"]))


@pytest.fixture(scope="module")
def edited(tmp_path_factory):
    return editor_fixture.build(tmp_path_factory.mktemp("rr") / "edited.docx", edited=True)


def test_reads_all_review_kinds():
    out = _read(ROOT / "tests/fixtures/docx/review-sample.docx")
    kinds = sorted(i["kind"] for i in out["items"])
    assert kinds == ["comment", "comment", "delete", "move", "replace"]
    assert all(i["anchorText"] for i in out["items"])


def test_old_output_shape_is_kept():
    out = _read(ROOT / "tests/fixtures/docx/review-sample.docx")
    assert set(out) >= {"items"}
    for item in out["items"]:
        assert OLD_KEYS <= set(item)
    replace = next(i for i in out["items"] if i["kind"] == "replace")
    assert (replace["anchorText"], replace["text"]) == ("old", "new")
    assert len({i["id"] for i in out["items"]}) == len(out["items"])


def test_every_item_has_paragraph_context(edited):
    out = _read(edited)
    for item in out["items"]:
        assert OLD_KEYS <= set(item)
        assert item["part"] in ("body", "footnote", "endnote")
        assert item["location"]
        assert "paragraphBefore" in item and "paragraphAfter" in item
    swap = next(i for i in out["items"] if i["kind"] == "replace" and i["text"] == "swift")
    assert swap["paragraphBefore"] == "The quick fox jumps[^1]"
    assert swap["paragraphAfter"] == "The swift fox jumps[^1]"
    assert swap["section"] == "Introduction"
    assert len({i["id"] for i in out["items"]}) == len(out["items"])


def test_footnote_revision_is_reported(edited):
    notes = [i for i in _read(edited)["items"] if i["part"] == "footnote"]
    replace = next(i for i in notes if i["kind"] == "replace")
    assert (replace["anchorText"], replace["text"]) == ("p. 4", "pp. 4-5")
    assert replace["location"] == "footnote:1"
    assert replace["citedIn"] == "body:1"
    assert "See Smith, p. 4" in replace["paragraphBefore"]
    assert "See Smith, pp. 4-5" in replace["paragraphAfter"]


def test_formatting_revisions_are_reported(edited):
    items = _read(edited)["items"]
    fmt = [i for i in items if i["kind"] == "format"]
    assert {(i["part"], i["anchorText"], i["text"]) for i in fmt} == {
        ("body", "important", "+b"), ("footnote", "Journal", "+i")}
    assert any(i["kind"] == "paragraph-format" and "jc" in i["text"] for i in items)


def test_split_is_listed_and_noise_is_counted(edited):
    out = _read(edited)
    marks = [i for i in out["items"] if i["kind"] == "paragraph-mark"]
    assert [(m["anchorText"], m["text"]) for m in marks] == [("First half", "split")]
    assert out["summary"]["blankParagraphMarks"] == 1
    assert out["summary"]["fontChurn"] == {"font set to David": editor_fixture.CHURN_RUNS}
    assert not any(i["anchorText"].startswith("w0") for i in out["items"])
