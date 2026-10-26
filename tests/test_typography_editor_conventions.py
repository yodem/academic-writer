"""Editor-review conventions (author decisions of 2026-10-26) for the deterministic
typography layer: scripts/lib/typography_fixes.py, scripts/detect-ai-typography.py
and scripts/validate-hebrew-punctuation.py.

  Decision 1  The spaced em dash " — " is the default Hebrew dash for an aside.
              It is kept; a mid-line spaced hyphen used as a dash becomes one.
  Decision 2  Straight " around Hebrew quotations/terms/titles, curly for Latin,
              gershayim/geresh only inside abbreviations and numerals.
  R-70, R-03  The validator reports ",,", ", ,", a non-ellipsis "..", double
              spaces, a no-break space before ":" and mirrored parentheses.

Every fixer has negative cases: what it must NOT touch matters more than what it
changes, because a wrong automatic rewrite of an author's text is worse than a
missed fix.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "src" / "scripts"
LIB_DIR = SCRIPTS_DIR / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import typography_fixes as tf  # noqa: E402

DETECT = SCRIPTS_DIR / "detect-ai-typography.py"
VALIDATE = SCRIPTS_DIR / "validate-hebrew-punctuation.py"

EM = "—"
EN = "–"
GERSHAYIM = "״"
GERESH = "׳"
NBSP = " "
NNBSP = " "


def dash(text: str) -> str:
    return tf.fix_spaced_hyphen_dashes(text)[0]


def marks(text: str) -> str:
    return tf.fix_quotes(tf.fix_hebrew_marks(text)[0])[0]


def cli(text: str, *args: str) -> dict:
    out = subprocess.run(
        [sys.executable, str(DETECT), "--fix-and-output", "--json", *args],
        input=text, capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def validate(text: str) -> list[str]:
    """Violation codes reported by validate-hebrew-punctuation.py for `text`."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "article.md"
        path.write_text(text, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(VALIDATE), str(path)],
            capture_output=True, text=True,
        )
    codes = []
    for line in proc.stdout.splitlines():
        parts = line.split(": ", 2)
        if len(parts) >= 2 and parts[1].split(" ")[0].isupper():
            codes.append(parts[1].split(" ")[0])
    return codes


class EmDashIsTheDefaultTest(unittest.TestCase):
    def test_default_dash_style_is_em(self):
        data = json.loads((ROOT_DIR / "src" / "thresholds.json").read_text(encoding="utf-8"))
        self.assertEqual(data["typography"]["dashReplacement"], "em")
        self.assertEqual(tf.load_default_dash_replacement(SCRIPTS_DIR), "em")

    def test_unreadable_thresholds_fall_back_to_em(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(tf.load_default_dash_replacement(Path(tmp) / "scripts"), "em")

    def test_em_dash_is_not_replaced_by_default(self):
        text = f"הטקסט שוזר תפיסות {EM} שזירה המעידה על מתח."
        fixed, fixes = tf.fix_dashes(text, "em")
        self.assertEqual(fixed, text)
        self.assertEqual(fixes, [])
        self.assertEqual(tf.fix_dashes(text, "keep"), (text, []))

    def test_cli_keeps_a_spaced_em_dash(self):
        text = f"זהו משפט {EM} עם הערת אגב."
        data = cli(text)
        self.assertEqual(data["fixed_text"], text)
        self.assertEqual(data["fixes"], [])

    def test_old_replacement_values_still_work(self):
        text = f"א {EM} ב {EN} ג, עמ׳ 12{EN}14"
        self.assertEqual(tf.fix_dashes(text, "hyphen")[0], f"א - ב - ג, עמ׳ 12{EN}14")
        self.assertEqual(tf.fix_dashes(text, "comma")[0], f"א , ב , ג, עמ׳ 12{EN}14")
        self.assertEqual(tf.fix_dashes(text, "remove")[0], f"א  ב  ג, עמ׳ 12{EN}14")
        data = cli(text, "--dash-replacement", "hyphen")
        self.assertEqual(data["fixed_text"], f"א - ב - ג, עמ׳ 12{EN}14")
        self.assertEqual({f["type"] for f in data["fixes"]}, {"em_dash", "en_dash"})

    def test_legacy_replacement_does_not_also_convert_hyphens(self):
        text = "א - ב"
        self.assertEqual(cli(text, "--dash-replacement", "hyphen")["fixed_text"], text)

    def test_keep_style_converts_nothing(self):
        text = "א - ב"
        self.assertEqual(cli(text, "--dash-replacement", "keep")["fixed_text"], text)

    def test_no_dashes_flag_disables_the_hyphen_fixer(self):
        self.assertEqual(cli("א - ב", "--no-dashes")["fixed_text"], "א - ב")


class SpacedHyphenToEmDashTest(unittest.TestCase):
    def test_spaced_hyphen_becomes_spaced_em_dash(self):
        self.assertEqual(dash("הטקסט שוזר תפיסות - שזירה המעידה."), f"הטקסט שוזר תפיסות {EM} שזירה המעידה.")

    def test_pair_of_asides(self):
        self.assertEqual(
            dash("שלושה מקורות - מלכים וישעיהו - לצד ניב."),
            f"שלושה מקורות {EM} מלכים וישעיהו {EM} לצד ניב.",
        )

    def test_dash_after_a_parenthetical_citation(self):
        self.assertEqual(
            dash("(שם, עמ׳ 47) - לפני שהצירוף כולו."), f"(שם, עמ׳ 47) {EM} לפני שהצירוף כולו."
        )

    def test_dash_before_a_quotation_or_parenthesis(self):
        self.assertEqual(dash('הוא כותב - "ענינה מענין" כך.'), f'הוא כותב {EM} "ענינה מענין" כך.')
        self.assertEqual(dash("הוא כותב - (ראו להלן) כך."), f"הוא כותב {EM} (ראו להלן) כך.")

    def test_reports_each_fix(self):
        _, fixes = tf.fix_spaced_hyphen_dashes("א - ב - ג")
        self.assertEqual([f["type"] for f in fixes], ["spaced_hyphen_dash"] * 2)
        self.assertEqual([f["position"] for f in fixes], [2, 6])

    def test_idempotent_and_leaves_an_existing_em_dash_alone(self):
        once = dash("א - ב")
        self.assertEqual(dash(once), once)
        text = f"א {EM} ב"
        self.assertEqual(dash(text), text)

    def test_line_initial_hyphen_is_a_markdown_bullet(self):
        text = "- פריט ראשון\n  - תת פריט\n    - עוד רמה\n-\tפריט עם טאב"
        self.assertEqual(dash(text), text)

    def test_hyphen_compounds_are_untouched(self):
        for text in ("אוניברסיטת בר-אילן", "תלת-שכבתית וגם אי-עקביות", "ו-X וכן ב-Y"):
            self.assertEqual(dash(text), text)

    def test_numeric_ranges_are_untouched(self):
        for text in ("עמ׳ 12 - 14 בלבד", "בשנים 1990 - 1995 כתב", "ראו 45-67", f"עמ׳ 45{EN}67"):
            self.assertEqual(dash(text), text)
        self.assertEqual(tf.fix_dashes(f"עמ׳ 45{EN}67", "hyphen")[0], f"עמ׳ 45{EN}67")

    def test_urls_and_links_are_untouched(self):
        for text in (
            "מתוך אתר על התורה - https://mg.alhatorah.org/Parshan/Ibn_Ezra - First",
            "ראו https://example.org/a-b - הקישור",
            "ראו [האתר](https://example.org/a - b) כאן",
            "ראו www.example.org - האתר",
        ):
            self.assertEqual(dash(text), text, text)

    def test_table_rows_are_untouched(self):
        text = "| שם - כינוי | ערך |\n|---|---|\n| א - ב | ג |\nשורה רגילה - עם דש"
        self.assertEqual(dash(text), text.replace("רגילה - עם", f"רגילה {EM} עם"))

    def test_frontmatter_and_code_are_untouched(self):
        text = "---\ntitle: א - ב\nauthor: ג - ד\n---\nגוף - טקסט\n```\nקוד - עברית\n```\nואחרי `קוד - מוטבע` - כן"
        want = "---\ntitle: א - ב\nauthor: ג - ד\n---\n" f"גוף {EM} טקסט\n```\nקוד - עברית\n```\n" f"ואחרי `קוד - מוטבע` {EM} כן"
        self.assertEqual(dash(text), want)

    def test_latin_only_text_is_untouched(self):
        for text in ("The Book - A Study of Things", "Dönitz, Saskia - Shemarya Ha-Ikriti."):
            self.assertEqual(dash(text), text)

    def test_hebrew_line_with_a_latin_title_keeps_the_latin_hyphen(self):
        text = "קראתי את Exegesis - Poetry במהדורה"
        self.assertEqual(dash(text), text)

    def test_a_source_quotation_keeps_its_own_hyphen(self):
        text = 'הוא כתב "אור - חושך" ואחר כך - המשך'
        self.assertEqual(dash(text), f'הוא כתב "אור - חושך" ואחר כך {EM} המשך')
        curly = "הוא כתב “אור - חושך” ועוד"
        self.assertEqual(dash(curly), curly)

    def test_bibliography_entries_keep_catalogue_hyphens_until_the_next_heading(self):
        text = (
            "# גוף\nטענה - ועוד\n"
            "# ביבליוגרפיה\nאהרן בן זאב ואורנים - בית הספר לחינוך.\n"
            "# נספח\nטענה - נוספת"
        )
        want = (
            f"# גוף\nטענה {EM} ועוד\n"
            "# ביבליוגרפיה\nאהרן בן זאב ואורנים - בית הספר לחינוך.\n"
            f"# נספח\nטענה {EM} נוספת"
        )
        self.assertEqual(dash(text), want)

    def test_plain_text_bibliography_heading_runs_to_the_end(self):
        text = "טענה - ועוד\nביבליוגרפיה\nאורנים - בית הספר"
        self.assertEqual(dash(text), f"טענה {EM} ועוד\nביבליוגרפיה\nאורנים - בית הספר")

    def test_double_hyphen_and_hyphen_next_to_dash_are_untouched(self):
        for text in ("א -- ב", f"א - {EM} ב", "א ---- ב"):
            self.assertEqual(dash(text), text)

    def test_doubled_spaces_around_a_hyphen_collapse_then_convert(self):
        # The pre-fix generate-docx output "  -  " in headings and TOC lines.
        data = cli("סעיף א: הרקע  -  ביזנטיון ור׳ שמריה")
        self.assertEqual(data["fixed_text"], f"סעיף א: הרקע {EM} ביזנטיון ור׳ שמריה")


class QuoteConventionTest(unittest.TestCase):
    def test_gershayim_between_hebrew_letters_is_an_abbreviation_mark(self):
        self.assertEqual(marks('תשכ"ב'), "תשכ" + GERSHAYIM + "ב")
        self.assertEqual(marks('הרמב"ם וגם ז"ל'), "הרמב" + GERSHAYIM + "ם וגם ז" + GERSHAYIM + "ל")

    def test_quoted_hebrew_term_stays_ascii(self):
        text = 'הוא אמר "שלום רב" ואז, והמונח "פרשה" חוזר.'
        self.assertEqual(marks(text), text)

    def test_abbreviation_and_quotation_on_one_line(self):
        self.assertEqual(
            marks('לפי הרמב"ם כתוב "שלום עולם" בתשכ"ב.'),
            'לפי הרמב' + GERSHAYIM + 'ם כתוב "שלום עולם" בתשכ' + GERSHAYIM + 'ב.',
        )

    def test_prefix_attached_openers_are_quotation_marks(self):
        for text in (
            'ראו ב"תשורי חדש" ועוד.',
            'המושג ה"יש מאין" נדון.',
            'מ"הקדמה למשנה" ועוד.',
            'כך ש"יפה כוחו" וגם.',
        ):
            self.assertEqual(marks(text), text, text)

    def test_prefix_attached_opener_without_a_closer_is_gershayim(self):
        self.assertEqual(marks('ראו ב"תשורי חדש.'), 'ראו ב' + GERSHAYIM + 'תשורי חדש.')

    def test_numerals_and_acronyms_are_not_mistaken_for_openers(self):
        # כ"ד, ש"ס, מו"ל: a one- or two-letter prefix shape, but one letter after.
        got = marks('בכ"ד בכסלו ובש"ס ובמו"ל וגם "ציטוט ארוך".')
        self.assertIn("כ" + GERSHAYIM + "ד", got)
        self.assertIn("ש" + GERSHAYIM + "ס", got)
        self.assertIn("מו" + GERSHAYIM + "ל", got)
        self.assertTrue(got.endswith('"ציטוט ארוך".'))

    def test_curly_quotes_around_hebrew_become_straight(self):
        self.assertEqual(marks("כתב “לא היו פירושים” כאן"), 'כתב "לא היו פירושים" כאן')
        self.assertEqual(marks("מהי “פרשה” אצל ר׳ שמריה"), 'מהי "פרשה" אצל ר׳ שמריה')

    def test_latin_quotations_become_curly(self):
        self.assertEqual(marks('He said "hello" loudly.'), "He said “hello” loudly.")
        self.assertEqual(marks("He said 'hello' loudly."), "He said “hello” loudly.")
        already = "In “Shemarya ha-Ikriti,” the editors write."
        self.assertEqual(marks(already), already)

    def test_hebrew_majority_span_with_a_latin_word_is_straight(self):
        self.assertEqual(marks("כתב “ספר The Bible הקדמון” שם"), 'כתב "ספר The Bible הקדמון" שם')

    def test_gershayim_used_as_a_quotation_mark_becomes_ascii(self):
        self.assertEqual(marks("הוא כתב ״וזהו כפירה בתורה״ שם"), 'הוא כתב "וזהו כפירה בתורה" שם')
        self.assertEqual(marks("המושג ה״יש מאין״ נדון"), 'המושג ה"יש מאין" נדון')

    def test_real_gershayim_abbreviations_are_untouched(self):
        text = "הרמב״ם ורש״י וז״ל, תשכ״ב, ה״יש מאין״ עצמו"
        got = marks(text)
        for word in ("הרמב״ם", "ורש״י", "וז״ל", "תשכ״ב"):
            self.assertIn(word, got)

    def test_unpaired_gershayim_at_a_word_boundary_is_left_alone(self):
        text = "ראו ״בלי סוף"
        self.assertEqual(marks(text), text)

    def test_hebrew_single_quoted_span_is_left_as_typed(self):
        # Possibly a nested quotation; turning it into double quotes would nest
        # double inside double.
        text = "לפי 'פיידון' ולפי 'מדינה' לאפלטון"
        self.assertEqual(marks(text), text)

    def test_curly_apostrophe_after_hebrew_letter_is_geresh(self):
        self.assertEqual(marks("שוורץ, לר’ שמריה"), "שוורץ, לר" + GERESH + " שמריה")
        self.assertEqual(marks("כתב ג’ון על אתרח’סיס"), "כתב ג" + GERESH + "ון על אתרח" + GERESH + "סיס")

    def test_closing_curly_single_quote_is_not_a_geresh(self):
        text = "זהו ‘חכמת ישראל’ וכך"
        self.assertEqual(marks(text), text)

    def test_english_possessive_curly_apostrophe_is_untouched(self):
        text = "the writer’s text"
        self.assertEqual(marks(text), text)

    def test_ascii_geresh_still_folds(self):
        self.assertEqual(marks("כך כתב ר' יוסף בעמ' 12."), "כך כתב ר" + GERESH + " יוסף בעמ" + GERESH + " 12.")

    def test_footnote_marker_right_after_a_closing_quote(self):
        # The drafter puts [^KEY] immediately after the sentence it supports.
        for text in (
            'המושג ה"יש מאין"[^1] נדון.',
            'ראו ב"תשורי חדש"[^2].',
            'הוא כתב "שלום עולם"[^3] ועוד.',
        ):
            self.assertEqual(marks(text), text, text)
        self.assertEqual(marks('המושג ה״יש מאין״[^1] נדון.'), 'המושג ה"יש מאין"[^1] נדון.')
        self.assertEqual(marks('He said "hello"[^1].'), "He said “hello”[^1].")
        self.assertEqual(marks('כ"ד[^3] בכסלו'), 'כ' + GERSHAYIM + 'ד[^3] בכסלו')

    def test_nested_quotations_keep_the_source_marks(self):
        for text in (
            '"הוא אמר ״שלום״ ושב"',
            'הוא כתב "אמר ר׳ "שלום" ושב" כאן',
            'He said “a "b" c” ok',
            'הוא כתב "ציטוט עם \'פנימי\' בתוכו" כאן',
        ):
            self.assertEqual(marks(text), text, text)

    def test_mark_fixes_are_idempotent(self):
        text = 'לפי הרמב"ם כתוב “שלום עולם” בתשכ"ב וב"תשורי חדש" וגם ה״יש מאין״.'
        once = marks(text)
        self.assertEqual(marks(once), once)


class ReversedParenthesesTest(unittest.TestCase):
    """fix_rtl_punctuation used a bare ")...(" regex, which also matched the gap
    between two CORRECT pairs and rewrote "(א) ב (ג)" to "(א( ב )ג)"."""

    def rtl(self, text: str) -> str:
        return tf.fix_rtl_punctuation(text)[0]

    def test_two_correct_parenthetical_citations_are_untouched(self):
        text = "טענה (שם, עמ׳ 5) ועוד טענה (שם, עמ׳ 6) ועוד."
        self.assertEqual(self.rtl(text), text)
        self.assertEqual(cli(text)["fixed_text"], text)

    def test_enumerator_and_a_later_pair_are_untouched(self):
        text = "1) פריט ראשון (בסוגריים) ועוד"
        self.assertEqual(self.rtl(text), text)

    def test_a_truly_reversed_pair_is_swapped_back(self):
        self.assertEqual(self.rtl(")הערה( הפוכה בטקסט."), "(הערה) הפוכה בטקסט.")
        self.assertEqual(self.rtl("ראו )שם, עמ׳ 5( ועוד (הערה)."), "ראו (שם, עמ׳ 5) ועוד (הערה).")

    def test_reversed_pair_around_latin_only_text_is_left_alone(self):
        text = "x )abc( y"
        self.assertEqual(self.rtl(text), text)


class WhitespaceTest(unittest.TestCase):
    def test_double_spaces_between_words_collapse(self):
        fixed, fixes = tf.fix_whitespace("טקסט  עם   רווחים כפולים.")
        self.assertEqual(fixed, "טקסט עם רווחים כפולים.")
        self.assertEqual({f["type"] for f in fixes}, {"double_space"})

    def test_indentation_hard_breaks_tables_and_code_are_untouched(self):
        text = "    הזחה  פנימית\nשבירה קשיחה  \n| א  | ב |\n```\nקוד  כפול\n```"
        fixed, _ = tf.fix_whitespace(text)
        self.assertEqual(fixed, "    הזחה פנימית\nשבירה קשיחה  \n| א  | ב |\n```\nקוד  כפול\n```")

    def test_no_break_space_before_a_colon_is_removed(self):
        for sp in (NBSP, NNBSP):
            fixed, fixes = tf.fix_whitespace(f"אהבת עולם אהבתיך{sp}: קריאה חדשה")
            self.assertEqual(fixed, "אהבת עולם אהבתיך: קריאה חדשה")
            self.assertEqual(fixes[0]["type"], "nbsp_before_colon")

    def test_no_break_space_elsewhere_is_untouched(self):
        text = f"עמ׳{NBSP}12 וגם {NNBSP}שם: כך"
        self.assertEqual(tf.fix_whitespace(text)[0], text)

    def test_no_whitespace_flag(self):
        self.assertEqual(cli("א  ב", "--no-whitespace")["fixed_text"], "א  ב")
        self.assertEqual(cli("א  ב")["fixed_text"], "א ב")


class ValidatorDetectorsTest(unittest.TestCase):
    def test_clean_correctly_quoted_text_has_no_violations(self):
        text = (
            'הוא כתב "תשורי" וכן הרמב"ם ותשכ"ב וב"תשורי חדש" ועוד (הערה) וגם [ציון].\n\n'
            'הרמב״ם כתב "שלום עולם" בתשכ״ב.\n\n'
            f"קטע {EM} עם דש, ועם שלוש נקודות... וגם […] ו[..] ו(..).\n"
        )
        self.assertEqual(validate(text), [])

    def test_mixed_quote_character_no_longer_fires_on_acronym_gershayim_plus_quote(self):
        self.assertNotIn("MIXED_QUOTE_CHARACTER", validate('הרמב״ם כתב "שלום עולם" ועוד.\n'))
        self.assertNotIn("MIXED_QUOTE_CHARACTER", validate('"שלום עולם" אמר הרמב״ם.\n'))

    def test_mixed_quote_character_fires_when_both_styles_delimit_quotations(self):
        self.assertIn("MIXED_QUOTE_CHARACTER", validate('ה״יש מאין״ וגם "ערך" ועוד.\n'))
        self.assertIn("MIXED_QUOTE_CHARACTER", validate('הוא כתב ״שלום עולם" ועוד.\n'))

    def test_gershayim_used_as_quotation_marks_is_reported(self):
        self.assertIn("GERSHAYIM_AS_QUOTE", validate("הוא כתב ״וזהו כפירה בתורה״ שם.\n"))

    def test_footnote_marker_after_a_closing_quote_is_balanced(self):
        self.assertEqual(validate('המושג ה"יש מאין"[^1] נדון.\n'), [])
        self.assertEqual(validate('ראו ב"תשורי חדש"[^2] ועוד.\n'), [])

    def test_dangling_prefix_attached_opener_is_an_unbalanced_quote(self):
        self.assertIn("UNBALANCED_QUOTE", validate('ראו ב"תשורי חדש ועוד.\n'))

    def test_nested_gershayim_quotation_inside_a_straight_one_is_not_reported(self):
        self.assertEqual(validate('"הוא אמר ״שלום״ ושב" ועוד.\n'), [])

    def test_unbalanced_quote_still_reported_but_not_for_acronyms(self):
        self.assertIn("UNBALANCED_QUOTE", validate('הוא כתב "שלום עולם ועוד.\n'))
        self.assertNotIn("UNBALANCED_QUOTE", validate('כתב הרמב"ם בתשכ"ב ועוד.\n'))
        self.assertNotIn("UNBALANCED_QUOTE", validate('ראו ב"תשורי חדש" ועוד.\n'))

    def test_double_comma(self):
        self.assertIn("DOUBLE_COMMA", validate("הקדמה,, ועוד.\n"))
        self.assertIn("DOUBLE_COMMA", validate("שמריה , , תשכ״ב.\n"))
        self.assertNotIn("DOUBLE_COMMA", validate("א, ב, ג.\n"))

    def test_double_period_but_not_ellipsis_or_bracketed(self):
        self.assertIn("DOUBLE_PERIOD", validate("זהו המשפט.. וממשיך.\n"))
        for ok in ("זהו המשפט... וממשיך.", "זהו המשפט… וממשיך.", "וכך [..] ממשיך.", "וכך (..) ממשיך.", "ראו ../קובץ"):
            self.assertNotIn("DOUBLE_PERIOD", validate(ok + "\n"), ok)

    def test_double_space(self):
        self.assertIn("DOUBLE_SPACE", validate("טקסט  עם רווח כפול.\n"))
        for ok in ("    שורה מוזחת רגילה.", "שבירה קשיחה בסוף  ", "| א  | ב |", "שורה רגילה."):
            self.assertNotIn("DOUBLE_SPACE", validate(ok + "\n"), ok)
        self.assertNotIn("DOUBLE_SPACE", validate("```\nקוד  כפול\n```\n"))

    def test_nbsp_before_colon(self):
        for sp in (NBSP, NNBSP):
            self.assertIn("NBSP_BEFORE_COLON", validate(f"אהבת עולם אהבתיך{sp}: קריאה חדשה\n"))
        self.assertNotIn("NBSP_BEFORE_COLON", validate("אהבת עולם אהבתיך: קריאה חדשה\n"))
        self.assertNotIn("NBSP_BEFORE_COLON", validate(f"עמ׳{NBSP}12: ראו\n"))

    def test_mirrored_parentheses(self):
        self.assertIn("MIRRORED_PARENTHESES", validate(")הערה( הפוכה בטקסט.\n"))
        self.assertNotIn("MIRRORED_PARENTHESES", validate("(הערה) תקינה בטקסט.\n"))
        # a list enumerator is a ")" with no "(": not bidi debris
        self.assertNotIn("MIRRORED_PARENTHESES", validate("1) פריט ראשון (בסוגריים) ועוד (שוב).\n"))

    def test_unbalanced_parentheses_still_reported(self):
        self.assertIn("UNBALANCED_BRACKET", validate("טקסט (פתוח בלבד.\n"))


class GuidanceFilesTest(unittest.TestCase):
    """The prose that steers the drafter agrees with the code."""

    def read(self, *parts: str) -> str:
        return (ROOT_DIR.joinpath(*parts)).read_text(encoding="utf-8")

    def test_linking_word_quota_is_gone_from_both_reference_lists(self):
        for name in ("words-hebrew.md", "words-english.md"):
            text = self.read("src", name)
            self.assertNotIn("at least 2", text, name)
            self.assertNotIn("Minimum density", text, name)
            self.assertIn("Precision, not a quota", text, name)
            self.assertIn("no minimum", text, name)

    def test_hebrew_list_names_the_vague_links_to_flag(self):
        text = self.read("src", "words-hebrew.md")
        for vague in ("וכך", "והוא", "ממנו"):
            self.assertIn(vague, text)

    def test_no_code_enforces_a_linking_word_count(self):
        thresholds = json.loads(self.read("src", "thresholds.json"))
        flat = json.dumps(thresholds, ensure_ascii=False).lower()
        for key in ("linkingword", "connective", "minlinking"):
            self.assertNotIn(key, flat)

    def test_anti_ai_reference_no_longer_lists_the_em_dash_as_a_tell(self):
        text = self.read("src", "skills", "write", "references", "anti-ai-patterns-hebrew.md")
        self.assertIn("is **not** an AI tell", text)
        self.assertIn("true aside", text)
        self.assertNotIn("Replace with ` - `", text)

    def test_draft_prompt_uses_straight_quotes_and_points_at_the_conventions(self):
        text = self.read("src", "cli", "src", "prompts", "write-draft.md")
        self.assertNotIn("״…״", text)
        self.assertIn("a straight", text)
        self.assertIn("hebrew-editorial-conventions.md", text)


if __name__ == "__main__":
    unittest.main()


def test_whitespace_findings_are_advisory_and_do_not_fail_the_gate(tmp_path):
    md = tmp_path / "a.md"
    md.write_text("טענה  ראשונה ושנייה.\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(VALIDATE), str(md)], capture_output=True, text=True)
    assert "DOUBLE_SPACE" in result.stdout
    assert result.returncode == 0
    bad = tmp_path / "b.md"
    bad.write_text("טענה ראשונה,, ושנייה.\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(VALIDATE), str(bad)], capture_output=True, text=True)
    assert result.returncode == 1


def test_dash_fixer_leaves_tables_without_outer_pipes_alone():
    text = "שם | ערך\n---|---\nא - ב | ג\n\nטענה - והסבר.\n"
    fixed, _ = tf.fix_spaced_hyphen_dashes(text)
    assert "א - ב | ג" in fixed
    assert "טענה — והסבר." in fixed


def test_whitespace_fixer_leaves_inline_code_and_urls_alone():
    text = "טענה  ראשונה `א  ב` ועוד  מילה https://x.org/a  b\n"
    fixed, _ = tf.fix_whitespace(text)
    assert "`א  ב`" in fixed
    assert "טענה ראשונה" in fixed and "ועוד מילה" in fixed


def test_whitespace_fixer_respects_multi_backtick_code_spans():
    text = "לפני ``א  ב ` ג`` אחרי  סוף\n"
    fixed, _ = tf.fix_whitespace(text)
    assert "``א  ב ` ג``" in fixed
    assert "אחרי סוף" in fixed


def _detect(text):
    out = subprocess.run([sys.executable, str(SCRIPTS_DIR / "detect-ai-typography.py"), "--json", "--fix-and-output"],
                         input=text, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)["fixed_text"]


def test_em_dash_decision_is_hebrew_only_english_keeps_the_hyphen_convention():
    assert _detect("The argument — weak — fails.") == "The argument - weak - fails."
    assert _detect("הטענה — החלשה — נופלת, וגם - כאן.") == "הטענה — החלשה — נופלת, וגם — כאן."
