"""
Regression tests for the Hebrew inline-parenthetical citation example.

Academic Hebrew citation form is `(מחבר, עמ' N)` — author + page, no year.
These tests guard against a defect where the prompt-facing example carried
a 4-digit publication year (the correct form for English/APA-style
author-year citations, but wrong for Hebrew).

Run with: python3 -m pytest tests/test_hebrew_citation_example.py -v
"""

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WRITE_SECTION_TS = os.path.join(
    ROOT,
    "plugins",
    "academic-writer",
    "mcp",
    "gemini-server",
    "src",
    "tools",
    "write_section.ts",
)
SECTION_WRITER_MD = os.path.join(ROOT, "src", "agents", "section-writer.md")

FOUR_DIGIT_YEAR = re.compile(r"\b\d{4}\b")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestWriteSectionTsHebrewCitationExample(unittest.TestCase):
    """gemini-server's write_section tool must emit a year-free Hebrew example."""

    def setUp(self):
        self.text = _read(WRITE_SECTION_TS)

    def test_file_exists(self):
        self.assertTrue(os.path.isfile(WRITE_SECTION_TS))

    def test_has_hebrew_branch_keyed_on_target_language(self):
        # Case-insensitive match: profile-schema.md documents the stored
        # value as `targetLanguage: Hebrew` (capitalized), so the check must
        # not be a bare `=== 'hebrew'` that only matches lowercase input.
        self.assertIn("targetLanguage.toLowerCase() === 'hebrew'", self.text)

    def test_hebrew_example_uses_page_marker(self):
        # The Hebrew-branch example must contain the Hebrew page abbreviation.
        hebrew_branch = self._extract_hebrew_branch()
        self.assertIn("עמ'", hebrew_branch)

    def test_hebrew_example_contains_no_year_token(self):
        hebrew_branch = self._extract_hebrew_branch()
        years = FOUR_DIGIT_YEAR.findall(hebrew_branch)
        self.assertEqual(
            years,
            [],
            f"Hebrew inline-parenthetical example must omit the publication "
            f"year, found: {years}",
        )

    def test_non_hebrew_example_keeps_author_year_form(self):
        # The non-Hebrew branch is unchanged: `(Author Year, page)`.
        non_hebrew_branch = self._extract_non_hebrew_branch()
        self.assertIn("Author Year, page", non_hebrew_branch)

    def _extract_hebrew_branch(self):
        # Grab the ternary's Hebrew (truthy) branch: the string literal right
        # after `targetLanguage.toLowerCase() === 'hebrew' ? ... : ...`.
        match = re.search(
            r"targetLanguage\.toLowerCase\(\) === 'hebrew'\s*\?\s*(\".*?\")\s*:",
            self.text,
            re.DOTALL,
        )
        self.assertIsNotNone(
            match, "Could not locate Hebrew ternary branch in write_section.ts"
        )
        return match.group(1)

    def _extract_non_hebrew_branch(self):
        match = re.search(
            r"targetLanguage\.toLowerCase\(\) === 'hebrew'\s*\?\s*\".*?\"\s*:\s*(\'.*?\')",
            self.text,
            re.DOTALL,
        )
        self.assertIsNotNone(
            match, "Could not locate non-Hebrew ternary branch in write_section.ts"
        )
        return match.group(1)


class TestSectionWriterMdHebrewCitationExample(unittest.TestCase):
    """The non-Gemini fallback path (section-writer.md) must already be
    year-free for its Hebrew inline-parenthetical examples — this locks in
    that correctness so a future edit can't silently reintroduce a year."""

    def setUp(self):
        self.text = _read(SECTION_WRITER_MD)

    def test_file_exists(self):
        self.assertTrue(os.path.isfile(SECTION_WRITER_MD))

    def test_hebrew_citation_example_lines_contain_no_year(self):
        offending = []
        for line in self.text.splitlines():
            if "עמ'" in line:
                years = FOUR_DIGIT_YEAR.findall(line)
                if years:
                    offending.append((line.strip(), years))
        self.assertEqual(
            offending,
            [],
            f"Hebrew citation example lines in section-writer.md must not "
            f"carry a publication year: {offending}",
        )

    def test_hebrew_inline_parenthetical_uses_page_marker(self):
        self.assertIn("עמ'", self.text)


if __name__ == "__main__":
    unittest.main()
