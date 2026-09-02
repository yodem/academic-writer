"""Tokenizer guards for spellcheck-candidates.py — three measured noise classes.

Each of these was found by running the wrapper against the real 6,584-token article
and comparing to the Phase 0 hand measurement:

1. ABBREVIATION STEMS. פרופ׳ / התנ״ך / הרמב״ם tokenize to the stem once the geresh
   is handled, hspell has no entry for the stem, and every one reports as a
   misspelling. 10 of the original 60 flags were this class.
2. SINGLE LETTERS. A standalone `א` is not a misspelling.
3. MAQAF IS A SEPARATOR. דו־צדדית is two valid words. The Phase 0 measurement's
   regex swallowed U+05BE into the token and iconv then dropped it, FABRICATING a
   non-word `דוצדדית` that was briefly recorded as a real error. It was not.
"""

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "src" / "scripts" / "spellcheck-candidates.py"
ALLOWLIST = REPO / "src" / "skills" / "proofread" / "references" / "hspell-allowlist.txt"

_spec = importlib.util.spec_from_file_location("spellcheck_candidates", SCRIPT)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


def _tokens(text):
    return sc._tokenize(sc._normalize_for_hspell(text))


class TestTokenizer(unittest.TestCase):
    def test_abbreviation_stem_is_not_a_candidate(self):
        for text in ("פרופ׳ דוד הרטמן", "התנ״ך", "הרמב״ם כתב", "ר׳ עקיבא"):
            toks = _tokens(text)
            self.assertNotIn("פרופ", toks)
            self.assertNotIn("התנ", toks)
            self.assertNotIn("הרמב", toks)
            self.assertNotIn("ר", toks)

    def test_internal_gershayim_word_survives(self):
        """ר״מ-style words with INTERNAL gershayim are real tokens, not stems."""
        self.assertIn("סולוביצ'יק", _tokens("סולוביצ׳יק אמר"))

    def test_single_letter_is_never_a_candidate(self):
        self.assertEqual(_tokens("א ב ג"), [])
        self.assertIn("אבג", _tokens("אבג"))

    def test_maqaf_separates_words(self):
        toks = _tokens("דו־צדדית")
        self.assertNotIn("דוצדדית", toks, "maqaf must not be swallowed into the token")
        self.assertIn("דו", toks)
        self.assertIn("צדדית", toks)

    def test_niqqud_does_not_truncate_or_split(self):
        self.assertIn("שלום", _tokens("שָׁלוֹם"))


class TestAllowlistInclusionRule(unittest.TestCase):
    """A deficient pre-2017 spelling must never be allowlisted — it is a real error."""

    DEFICIENT = ("נסיונותיהם", "האשה", "הדוגמא", "תכנית", "אמתי", "לעתים", "בנין")

    def test_no_deficient_spelling_is_allowlisted(self):
        entries = {
            ln.strip()
            for ln in ALLOWLIST.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        }
        leaked = sorted(entries & set(self.DEFICIENT))
        self.assertEqual(
            leaked,
            [],
            "pre-2017 deficient spellings in the allowlist hide real finds behind a "
            f"list meant to hide noise: {leaked}",
        )

    def test_allowlist_keeps_the_genuine_false_positives(self):
        entries = {
            ln.strip()
            for ln in ALLOWLIST.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        }
        for tok in ("אמיתי", "איתו", "אזי", "אידיאולוגיה"):
            self.assertIn(tok, entries, f"{tok} is standard modern Hebrew hspell rejects")


class TestSkipsCleanlyWithoutHspell(unittest.TestCase):
    def test_missing_hspell_exits_zero_with_skipped_payload(self):
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write("שלום עולם\n")
            src = fh.name
        try:
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--input", src, "--hspell-bin", "/nonexistent/hspell"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout).get("skipped"), "no checker")
        finally:
            os.unlink(src)


if __name__ == "__main__":
    unittest.main()
