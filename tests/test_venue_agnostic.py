"""The plugin must hardcode no journal and must work with no venue profile at all.

The editorial stage was designed against one real pre-submission rejection. That is a
legitimate source for the CHECKS, and an illegitimate source for a shipped venue: a
researcher submits to their own journals, not the one that happened to reject the article
this feature was built from. So the venue-specific list lives in the researcher's own
`.academic-helper/venues/<slug>.md`, and everything venue-independent lives in
src/skills/proofread/references/editorial-checks.md, which is always loaded.
"""

import os
import re
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKS = os.path.join(REPO, "src", "skills", "proofread", "references", "editorial-checks.md")
MEMO = os.path.join(REPO, "src", "cli", "src", "prompts", "proofread-memo.md")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestGlobalEditorialChecks(unittest.TestCase):
    def test_checks_file_exists_and_is_venue_agnostic(self):
        self.assertTrue(os.path.isfile(CHECKS), "the global editorial checklist must exist")
        text = _read(CHECKS)
        self.assertIn("venue-agnostic", text.lower())

    def test_all_six_checks_present(self):
        text = _read(CHECKS)
        for cat in (
            "genre-fit",
            "term-undefined",
            "insider-reference",
            "cut",
            "refocus",
        ):
            self.assertIn(cat, text, f"global checklist missing category {cat}")
        self.assertRegex(text, r"### 6\.", "the checklist must enumerate six checks")

    def test_language_work_is_explicitly_out_of_scope_here(self):
        """Recorded in the checklist for context, but assigned to the other two stages."""
        text = _read(CHECKS)
        self.assertIn("language finder", text)
        self.assertIn("mechanical pass", text)


class TestMemoUsesGlobalChecks(unittest.TestCase):
    def test_editorial_memo_always_loads_global_checks(self):
        text = _read(MEMO)
        self.assertIn("editorial-checks.md", text)
        self.assertIn("always", text.lower())

    def test_venue_profile_is_optional_and_additive(self):
        text = _read(MEMO)
        low = text.lower()
        self.assertIn("optional", low)
        self.assertIn("additive", low)
        self.assertIn("never remove", low)

    def test_memo_keeps_language_work_out_of_scope(self):
        text = _read(MEMO).lower()
        self.assertIn("language", text)
        self.assertTrue("out of scope" in text or "not" in text)


class TestNoHardcodedVenue(unittest.TestCase):
    """No shipped file may name a specific journal."""

    # Journals the plugin must not privilege. Extend if a name ever creeps in.
    BANNED = ("katharsis", "קתרסיס")

    def test_no_shipped_file_names_a_specific_journal(self):
        shipped = subprocess.run(
            ["git", "ls-files", "src/", "plugins/", "manifests/", "features.json"],
            cwd=REPO, capture_output=True, text=True, check=True,
        ).stdout.split()
        offenders = []
        for rel in shipped:
            try:
                body = _read(os.path.join(REPO, rel)).lower()
            except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
                continue
            if any(b in body for b in self.BANNED):
                offenders.append(rel)
        self.assertEqual(
            offenders,
            [],
            "a shipped file names a specific journal; venues belong in the researcher's "
            f"own .academic-helper/venues/: {offenders}",
        )

    def test_no_venue_profile_is_shipped(self):
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.split()
        shipped_venues = [
            p for p in tracked
            if re.search(r"^(src|plugins)/.*/venues/", p)
        ]
        self.assertEqual(
            shipped_venues, [], f"the plugin must ship no venue profile: {shipped_venues}"
        )


if __name__ == "__main__":
    unittest.main()
