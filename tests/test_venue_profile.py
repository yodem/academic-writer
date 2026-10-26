"""The bundled, opt-in venue profile and the Hebrew editorial conventions reference.

Structure only: the profile ships inside the plugin, the build copies it, `aw proofread` falls back
to it when the project has no profile with that slug (the project file wins), the conventions file
covers every rule that was routed to plugin guidance or to the profile, and neither carries personal
data. The default footnote and ibid style is not touched by any of it.
"""
import json
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(REPO, "src", "venues", "bar-ilan-seminar-apa-he.md")
CONVENTIONS = os.path.join(REPO, "src", "skills", "write", "references", "hebrew-editorial-conventions.md")
BUILD = os.path.join(REPO, "scripts", "build-plugins.sh")
PROOFREAD_TS = os.path.join(REPO, "src", "cli", "src", "proofread.ts")
FIND_PROMPT = os.path.join(REPO, "src", "cli", "src", "prompts", "proofread-find.md")
EDITORIAL_CHECKS = os.path.join(REPO, "src", "skills", "proofread", "references", "editorial-checks.md")
PROOFREAD_SKILL = os.path.join(REPO, "src", "skills", "proofread", "SKILL.md")

# Rule ids routed to "plugin guidance" (the conventions file) and "venue profile" (the bundled profile),
# plus R-42 (part a in the conventions file, part b in the profile). R-32 and R-01/R-02/R-08 are plugin
# defaults owned elsewhere, summarised in the conventions file for one place to read.
GUIDANCE = ["R-04", "R-05", "R-06", "R-13", "R-14", "R-15", "R-16", "R-17", "R-18", "R-20", "R-21", "R-22",
            "R-24", "R-26", "R-27", "R-28", "R-29", "R-30", "R-31", "R-33", "R-34", "R-35", "R-36", "R-37",
            "R-57", "R-58", "R-65", "R-66"]
PROJECT_TERMS = ["R-25", "R-69"]
SUMMARISED = ["R-01", "R-02", "R-07", "R-08", "R-32"]
VENUE = ["R-10", "R-11", "R-19", "R-23", "R-38", "R-39", "R-40", "R-41", "R-43", "R-47", "R-48", "R-49",
         "R-50", "R-51", "R-52", "R-53", "R-54", "R-56"]


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestConventionsReference(unittest.TestCase):
    def setUp(self):
        self.text = _read(CONVENTIONS)

    def test_every_guidance_rule_is_tagged(self):
        missing = [r for r in GUIDANCE + PROJECT_TERMS + SUMMARISED + ["R-42"] if r not in self.text]
        self.assertEqual(missing, [], f"conventions file lacks rule tags: {missing}")

    def test_suggestions_only_and_no_auto_replace(self):
        low = self.text.lower()
        self.assertIn("suggestion", low)
        self.assertIn("nothing here is auto-replaced", low)
        self.assertIn('"medium"', self.text)

    def test_false_positive_cautions_are_present(self):
        for needle in ("בפני", "לפני", "על מנת", "לא רק"):
            self.assertIn(needle, self.text)
        self.assertIn("both correct", self.text)

    def test_substitution_caution_and_project_terms_registry(self):
        self.assertIn("agreement", self.text)
        self.assertIn("inflected or prefixed", self.text)
        self.assertIn(".academic-helper/terms.json", self.text)
        self.assertIn("substring", self.text)

    def test_is_concise(self):
        self.assertLess(len(self.text.splitlines()), 350)


class TestBundledVenueProfile(unittest.TestCase):
    def setUp(self):
        self.text = _read(PROFILE)

    def test_profile_exists_in_src_venues(self):
        self.assertTrue(os.path.isfile(PROFILE))
        self.assertIn("bar-ilan-seminar-apa-he", self.text)

    def test_is_opt_in_project_wins_and_default_unchanged(self):
        self.assertIn("opt-in", self.text)
        self.assertIn("wins", self.text)
        self.assertIn("unchanged", self.text)

    def test_every_venue_rule_is_tagged(self):
        missing = [r for r in VENUE + ["R-42"] if r not in self.text]
        self.assertEqual(missing, [], f"venue profile lacks rule tags: {missing}")

    def test_key_conventions_present(self):
        for needle in ("מובאים על פי", "אוחזר ב־", "מאגרים", "APA 7", "עמ׳", "נוסח כתב יד",
                       "לא נקרא במקורו", "LTR", "מקורות ראשוניים", "מקורות משניים", "ibid=false"):
            self.assertIn(needle, self.text, f"profile missing: {needle}")

    def test_cover_fields_are_labels_only(self):
        # No digit run that could be an ID, no e-mail address.
        self.assertNotRegex(self.text, r"\b\d{7,}\b")
        self.assertNotRegex(self.text, r"[\w.]+@[\w.]+")
        for label in ("מאת:", "מוגשת:", "במסגרת הקורס:"):
            self.assertIn(label, self.text)

    def test_sections_for_the_memo(self):
        for heading in ("## Citation in the text", "## Reference list", "## What this profile flags",
                        "## What this profile does not do"):
            self.assertIn(heading, self.text)


class TestWiring(unittest.TestCase):
    def test_build_script_copies_the_venues_folder(self):
        text = _read(BUILD)
        self.assertIn('"$SRC_DIR/venues"', text)
        self.assertRegex(text, r'cp -R "\$SRC_DIR/venues" "\$PLUGIN_DIR/"')

    def test_proofread_falls_back_to_the_bundled_profile_project_first(self):
        text = _read(PROOFREAD_TS)
        self.assertIn("resolveVenueProfile", text)
        m = re.search(r"candidates = \[(.*?)\];", text, re.S)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertLess(body.index("join(project"), body.index("join(root"), "project file must come first")

    def test_prompts_and_skills_point_at_the_new_files(self):
        self.assertIn("hebrew-editorial-conventions.md", _read(FIND_PROMPT))
        self.assertIn('"medium"', _read(FIND_PROMPT))
        self.assertIn("bar-ilan-seminar-apa-he", _read(EDITORIAL_CHECKS))
        self.assertIn("bar-ilan-seminar-apa-he", _read(PROOFREAD_SKILL))

    def test_no_absolute_user_paths_in_new_files(self):
        for path in (PROFILE, CONVENTIONS):
            self.assertNotRegex(_read(path), r"/Users/|/home/[a-z]")


class TestCatalogueDestinations(unittest.TestCase):
    """If the author's verified catalogue is on this machine, check no routed rule is missing."""

    CATALOGUE = os.environ.get("AW_VERIFIED_CATALOGUE", "")

    @unittest.skipUnless(os.environ.get("AW_VERIFIED_CATALOGUE") and os.path.isfile(os.environ.get("AW_VERIFIED_CATALOGUE", "")),
                         "set AW_VERIFIED_CATALOGUE to a verified-catalogue.json to run")
    def test_each_routed_rule_lands_in_a_new_file(self):
        rules = json.load(open(self.CATALOGUE, encoding="utf-8"))
        conventions, profile = _read(CONVENTIONS), _read(PROFILE)
        missing = []
        for rule in rules:
            dest = rule["destination"]
            if dest.startswith("plugin guidance") and rule["id"] not in conventions:
                missing.append(rule["id"])
            if dest.startswith("venue profile") and rule["id"] not in profile:
                missing.append(rule["id"])
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
