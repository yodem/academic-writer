import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location("cg", pathlib.Path(__file__).parent.parent / "src/scripts/citation-guard.py")
cg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cg)


def test_two_gereshes_do_not_form_a_quote():
    line = "ר׳ יוחנן אמר להתפשר אם יריביו, עמ׳ 45"
    ch = {"line": 1, "before": "להתפשר אם", "after": "להתפשר עם"}
    assert cg.change_overlaps_guard_token(ch, [line]) is False


def test_real_quotation_still_protected():
    line = "הכתוב אומר ״ויאמר משה אל העם״ ומכאן"
    ch = {"line": 1, "before": "משה אל", "after": "משה על"}
    assert cg.change_overlaps_guard_token(ch, [line]) is True


def test_prose_with_commas_is_not_a_verse_ref():
    assert not cg.BOOK_CHAPTER_VERSE_RE.search("הדבר לא, אך")
