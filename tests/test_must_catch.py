import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent.parent


def test_terms_style_and_caps(tmp_path):
    (tmp_path / "a.md").write_text("שמואל אבן תבון כתב.\nכמו כן הוא טען. כמו כן הוא הוסיף.\nיתרה מזאת, זה.\n", encoding="utf-8")
    (tmp_path / "s.json").write_text(json.dumps({"banned": [{"word": "יתרה מזאת", "replacement": "זאת ועוד"}], "capped": [{"word": "כמו כן", "maxPer": "paragraph", "max": 1}], "filler": []}), encoding="utf-8")
    (tmp_path / "t.json").write_text(json.dumps({"canon": [{"form": "אבן תיבון", "variants": ["אבן תבון"]}]}), encoding="utf-8")
    out = json.loads(subprocess.check_output([sys.executable, ROOT / "src/scripts/must-catch.py", "--text", tmp_path / "a.md", "--style-words", tmp_path / "s.json", "--terms", tmp_path / "t.json", "--json"]))
    classes = sorted(c["class"] for c in out["changes"])
    assert classes == ["names_terms", "style_words", "style_words"]
    assert all(c["mustCatch"] for c in out["changes"])

def test_capped_word_beyond_cap_takes_replacement(tmp_path):
    (tmp_path/"a.md").write_text("כמו כן הוא טען. כמו כן הוא הוסיף.\n", encoding="utf-8")
    (tmp_path/"s.json").write_text(json.dumps({"banned":[],"filler":[],
        "capped":[{"word":"כמו כן","maxPer":"paragraph","max":1,"replacement":"נוסף על כך"}]}), encoding="utf-8")
    (tmp_path/"t.json").write_text(json.dumps({"canon":[]}), encoding="utf-8")
    out = json.loads(subprocess.check_output([sys.executable, ROOT/"src/scripts/must-catch.py", "--text", tmp_path/"a.md",
        "--style-words", tmp_path/"s.json", "--terms", tmp_path/"t.json", "--json"]))
    assert [c["after"] for c in out["changes"]] == ["נוסף על כך"]  # first use kept, second replaced
    # Both occurrences share line 1: apply-changes.py cannot tell them apart
    # by text alone, so the over-cap change must carry the 1-based position
    # of THIS instance among all occurrences of the word on that line.
    assert out["changes"][0]["line"] == 1
    assert out["changes"][0]["occurrence"] == 2


def test_capped_word_occurrence_is_position_on_its_own_line_when_alone(tmp_path):
    (tmp_path/"a.md").write_text("כמו כן הוא טען.\nכמו כן הוא הוסיף.\n", encoding="utf-8")
    (tmp_path/"s.json").write_text(json.dumps({"banned":[],"filler":[],
        "capped":[{"word":"כמו כן","maxPer":"chapter","max":1,"replacement":"נוסף על כך"}]}), encoding="utf-8")
    (tmp_path/"t.json").write_text(json.dumps({"canon":[]}), encoding="utf-8")
    out = json.loads(subprocess.check_output([sys.executable, ROOT/"src/scripts/must-catch.py", "--text", tmp_path/"a.md",
        "--style-words", tmp_path/"s.json", "--terms", tmp_path/"t.json", "--json"]))
    # The capped rule always reports its position on the line -- harmless
    # (and correctly resolved) when it is the line's only instance, and the
    # field apply-changes.py needs when a sibling instance shares the line.
    assert len(out["changes"]) == 1
    assert out["changes"][0]["occurrence"] == 1


def _run(tmp_path, text, terms=None, styles=None):
    (tmp_path / "a.md").write_text(text, encoding="utf-8")
    (tmp_path / "s.json").write_text(json.dumps(styles or {"banned": [], "capped": [], "filler": []}), encoding="utf-8")
    (tmp_path / "t.json").write_text(json.dumps(terms or {"canon": []}), encoding="utf-8")
    out = subprocess.check_output([sys.executable, ROOT / "src/scripts/must-catch.py", "--text", tmp_path / "a.md",
                                   "--style-words", tmp_path / "s.json", "--terms", tmp_path / "t.json", "--json"])
    return json.loads(out)["changes"]


def test_a_stem_inside_a_longer_word_is_never_replaced(tmp_path):
    # The 2026-09 residue: a banned stem replaced inside its inflected form made a non-word.
    styles = {"banned": [{"word": "הילומורפי", "replacement": "המאחד חומר וצורה"}], "capped": [], "filler": []}
    changes = _run(tmp_path, "הוא דן בהילומורפי, ולא בהילומורפיזם או להילומורפיות.\n", styles=styles)
    assert [(c["before"], c["line"]) for c in changes] == [("הילומורפי", 1)]


def test_a_variant_with_a_hebrew_prefix_is_caught_and_the_prefix_kept(tmp_path):
    terms = {"canon": [{"form": "האיקריטי", "variants": ["האקריטי"]}]}
    changes = _run(tmp_path, "פירושו של ר׳ שמריה והאקריטי ושל האקריטי.\n", terms=terms)
    assert len(changes) == 2 and all(c["before"] == "האקריטי" for c in changes)
    assert [c["occurrence"] for c in changes] == [1, 2]
    # The prefixed reading is a guess, so it is reported, not applied; the bare word is applied.
    assert [(c["mustCatch"], c["meaningRisk"]) for c in changes] == [(False, "medium"), (True, "low")]


def test_a_word_glued_to_a_non_prefix_cluster_is_not_a_match(tmp_path):
    terms = {"canon": [{"form": "תיבון", "variants": ["תבון"]}]}
    assert _run(tmp_path, "המילה נתבונן אינה שם.\n", terms=terms) == []


def test_quoted_source_text_footnotes_and_bibliography_keep_their_spelling(tmp_path):
    terms = {"canon": [{"form": "האיקריטי", "variants": ["האקריטי"]}]}
    text = ('ר׳ שמריה האקריטי כתב "פירוש שמריה האקריטי" ו“האקריטי”.\n'
            '[^1]: שוורץ, "הערות על פירושי שיר השירים לר׳ שמריה האקריטי".\n'
            '\n## ביבליוגרפיה\n\nשוורץ, ד׳. הערות לר׳ שמריה האקריטי.\n')
    changes = _run(tmp_path, text, terms=terms)
    assert [(c["line"], c["occurrence"]) for c in changes] == [(1, 1)]


def test_an_acronym_mark_is_not_a_quotation_and_does_not_hide_prose(tmp_path):
    terms = {"canon": [{"form": "אריסטו", "variants": ["ארסטו"]}]}
    changes = _run(tmp_path, 'לדעת הרמב"ם ארסטו טעה בשנת תשכ"ב.\n', terms=terms)
    assert [c["before"] for c in changes] == ["ארסטו"]


def test_latin_variants_match_whole_words_only(tmp_path):
    terms = {"canon": [{"form": "Maimonides", "variants": ["Maimonid"]}]}
    assert _run(tmp_path, "See Maimonidean thought.\n", terms=terms) == []


def test_an_adjective_built_on_an_acronym_does_not_open_a_quotation(tmp_path):
    styles = {"banned": [{"word": "מהווה", "replacement": "הוא"}], "capped": [], "filler": []}
    changes = _run(tmp_path, 'העקרונות הרמב"מיים שנדונו ומהווה דפוס, וה"יש מאין" מהווה מושג.\n', styles=styles)
    # The acronym-shaped הרמב"מיים does not open a quotation. After וה"יש the reading of
    # that mark as an acronym leaves the closing mark open, so the rest is left alone.
    assert [c["occurrence"] for c in changes] == [1]


BANNED = {"banned": [{"word": "מהווה", "replacement": "הוא"}], "capped": [], "filler": []}


def test_a_quotation_that_runs_across_lines_is_protected_on_every_line(tmp_path):
    assert _run(tmp_path, "הוא כתב “ציטוט\nמהווה מקור”.\n", styles=BANNED) == []
    changes = _run(tmp_path, "הוא כתב “ציטוט\nמהווה מקור”.\n\nזה מהווה דפוס.\n", styles=BANNED)
    assert [c["line"] for c in changes] == [4]


def test_a_quotation_glued_to_a_three_letter_prefix_is_protected(tmp_path):
    assert _run(tmp_path, 'זה נאמר ובש"מהווה מקור" בספר.\n', styles=BANNED) == []


def test_code_fences_close_only_on_a_matching_fence(tmp_path):
    text = "````\n```\nמהווה\n````\n~~~\n```\nמהווה\n~~~\nזה מהווה דפוס.\n"
    assert [c["line"] for c in _run(tmp_path, text, styles=BANNED)] == [9]


def test_tables_without_outer_pipes_are_left_alone(tmp_path):
    text = "עמודה | עמודה\n--- | ---\nמהווה | מקור\n\nזה מהווה דפוס.\n"
    assert [c["line"] for c in _run(tmp_path, text, styles=BANNED)] == [5]


def test_occurrence_matches_the_applier_on_decomposed_text(tmp_path):
    import unicodedata
    word = unicodedata.normalize("NFD", "café")
    terms = {"canon": [{"form": "Cafe", "variants": ["café"]}]}
    text = "“café” then " + word + " and " + word + ".\n"
    changes = _run(tmp_path, text, terms=terms)
    assert [c["occurrence"] for c in changes] == [2, 3]
    contract = [{"change_id": "c%d" % n, "stage": "mechanical", "line": c["line"], "type": "names_terms",
                 "level": "word", "before": c["before"], "after": c["after"], "rationale": "term",
                 "meaningRisk": "low", "occurrence": c["occurrence"]} for n, c in enumerate(changes)]
    (tmp_path / "changes.json").write_text(json.dumps(contract), encoding="utf-8")
    subprocess.run([sys.executable, ROOT / "src/scripts/apply-changes.py", "--changes", tmp_path / "changes.json",
                    "--proof-base", tmp_path / "a.md", "--output", tmp_path / "out.md", "--json"], check=True,
                   capture_output=True)
    out = (tmp_path / "out.md").read_text(encoding="utf-8")
    assert out.startswith("\u201ccafé\u201d then Cafe and Cafe")


def test_a_prefix_reading_of_another_word_is_never_auto_applied(tmp_path):
    styles = {"banned": [{"word": "ממש", "replacement": ""}], "capped": [], "filler": []}
    changes = _run(tmp_path, "הוא מממש את הרעיון. ממש כך.\n", styles=styles)
    assert [(c["occurrence"], c["mustCatch"]) for c in changes] == [(1, False), (2, True)]


def test_a_quote_mark_inside_inline_code_does_not_unpair_the_real_quotation(tmp_path):
    assert _run(tmp_path, 'קוד `"` ואז "מהווה מקור".\n', styles=BANNED) == []


def test_footnote_continuation_lines_are_protected(tmp_path):
    text = "[^1]: מקור\n    מהווה מקור מצוטט.\n\nזה מהווה דפוס.\n"
    assert [c["line"] for c in _run(tmp_path, text, styles=BANNED)] == [4]


def test_phrase_rules_that_run_into_the_next_word_still_match(tmp_path):
    styles = {"banned": [{"word": "חשוב לציין כי ", "replacement": ""}, {"word": "מן הראוי לציין ש", "replacement": ""}],
              "capped": [], "filler": []}
    changes = _run(tmp_path, "חשוב לציין כי הדבר נכון. מן הראוי לציין שהדבר נכון.\n", styles=styles)
    assert sorted(c["before"] for c in changes) == ["חשוב לציין כי ", "מן הראוי לציין ש"]
    # A space-ended rule is exact; a rule ending in a bare prefix glued to a word is only proposed.
    assert {c["before"]: c["mustCatch"] for c in changes} == {"חשוב לציין כי ": True, "מן הראוי לציין ש": False}


def test_inline_code_spanning_lines_is_protected(tmp_path):
    assert _run(tmp_path, "קוד `מהווה\nמקור` כאן.\n", styles=BANNED) == []


def test_a_prefix_reading_never_counts_toward_a_cap(tmp_path):
    styles = {"banned": [], "filler": [], "capped": [{"word": "ממש", "maxPer": "paragraph", "max": 1, "replacement": ""}]}
    assert _run(tmp_path, "הוא מממש רעיון. ממש כך.\n", styles=styles) == []


def test_a_trailing_prefix_rule_never_eats_the_next_word(tmp_path):
    styles = {"banned": [{"word": "מן הראוי לציין ש", "replacement": ""}], "capped": [], "filler": []}
    changes = _run(tmp_path, "מן הראוי לציין שינוי חשוב.\n", styles=styles)
    assert [c["mustCatch"] for c in changes] == [False]


def test_latin_words_with_accents_or_combining_marks_are_whole_words(tmp_path):
    import unicodedata
    terms = {"canon": [{"form": "Maimonides", "variants": ["Maimonid"]}]}
    assert _run(tmp_path, "Maimonidé and " + unicodedata.normalize("NFD", "Maimonidé") + ".\n", terms=terms) == []


def test_code_spans_pair_backtick_runs_of_equal_length(tmp_path):
    assert _run(tmp_path, "קוד ``תחילה ``` ואז ` מהווה סוף`` כאן.\n", styles=BANNED) == []


def test_a_url_inside_a_quotation_does_not_swallow_its_closing_quote(tmp_path):
    for url in ("https://example.com", "www.example.com"):
        text = 'הוא ציטט "מקור ' + url + '" ואז "מהווה מקור".\n'
        assert _run(tmp_path, text, styles=BANNED) == []


def test_blockquotes_and_their_lazy_continuation_lines_are_protected(tmp_path):
    text = "> מהווה מקור מצוטט\nמהווה המשך הציטוט.\n\nזה מהווה דפוס.\n"
    assert [c["line"] for c in _run(tmp_path, text, styles=BANNED)] == [4]


def test_a_quotation_that_runs_across_paragraphs_stays_protected(tmp_path):
    text = "“מקור\n\nמהווה מקור” ואז מהווה דפוס.\n"
    changes = _run(tmp_path, text, styles=BANNED)
    assert [(c["line"], c["occurrence"]) for c in changes] == [(3, 2)]


def test_setext_bibliography_headings_are_recognised(tmp_path):
    text = "זה מהווה דפוס.\n\nביבליוגרפיה\n============\nמהווה מקור.\n"
    assert [c["line"] for c in _run(tmp_path, text, styles=BANNED)] == [1]


def test_a_blockquote_or_footnote_line_above_dashes_is_not_a_heading(tmp_path):
    assert _run(tmp_path, "> מהווה מקור\n---\n", styles=BANNED) == []
    assert _run(tmp_path, "[^1]: מקור\n    מהווה מקור\n---\n", styles=BANNED) == []


def test_curly_nesting_depth_carries_across_paragraphs(tmp_path):
    text = "“חיצוני “פנימי\n\nסוף” מהווה המשך”.\n"
    assert _run(tmp_path, text, styles=BANNED) == []


def test_a_match_that_overlaps_a_quotation_is_never_applied(tmp_path):
    terms = {"canon": [{"form": "ספר האיקריטי", "variants": ['ספר "האקריטי']}]}
    assert _run(tmp_path, 'ראו ספר "האקריטי" עצמו.\n', terms=terms) == []


def test_indented_atx_bibliography_headings_are_recognised(tmp_path):
    text = "זה מהווה דפוס.\n\n  ## ביבליוגרפיה\n\nמהווה מקור.\n"
    assert [c["line"] for c in _run(tmp_path, text, styles=BANNED)] == [1]


def test_an_acronym_on_a_prefix_like_stem_does_not_expose_a_quotation(tmp_path):
    for text in ('המו"לים כתבו "מהווה מקור".\n', 'השו"תים כתבו "מהווה מקור".\n'):
        assert _run(tmp_path, text, styles=BANNED) == []


def test_caps_reset_at_setext_and_tight_atx_headings(tmp_path):
    capped = {"banned": [], "filler": [], "capped": [{"word": "כמו כן", "maxPer": "chapter", "max": 1, "replacement": "נוסף על כך"}]}
    assert _run(tmp_path, "כמו כן א.\n\nפרק\n====\nכמו כן ב.\n", styles=capped) == []
    para = {"banned": [], "filler": [], "capped": [{"word": "כמו כן", "maxPer": "paragraph", "max": 1, "replacement": "נוסף על כך"}]}
    assert _run(tmp_path, "כמו כן א.\n## פרק\nכמו כן ב.\n", styles=para) == []


def test_mixed_readings_of_ambiguous_marks_keep_quoted_text_protected(tmp_path):
    assert _run(tmp_path, 'המו"לים כתבו ה"מהווה מקור".\n', styles=BANNED) == []
    assert _run(tmp_path, 'הוא כתב ה"מהווה מקור\n\nמהווה המשך".\n', styles=BANNED) == []


def test_heading_like_text_inside_code_does_not_reset_a_cap(tmp_path):
    capped = {"banned": [], "filler": [], "capped": [{"word": "כמו כן", "maxPer": "chapter", "max": 1, "replacement": "נוסף על כך"}]}
    changes = _run(tmp_path, "כמו כן א.\n\n```\n# דוגמה\n```\n\nכמו כן ב.\n", styles=capped)
    assert [c["line"] for c in changes] == [7]


def test_a_stray_open_quote_protects_only_the_next_paragraph(tmp_path):
    text = 'הוא כתב ב"חכמה "אחת\n\nמהווה המשך.\n\nזה מהווה דפוס.\n'
    assert [c["line"] for c in _run(tmp_path, text, styles=BANNED)] == [5]
