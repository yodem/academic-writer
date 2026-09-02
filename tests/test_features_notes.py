"""Every `status: "partial"` entry in features.json must say what is missing.

A standing audit finding: ten entries were marked partial with no explanation, so
"partial" carried no information — a reader could not tell whether the gap was a
missing test, a stubbed code path, or a deliberate scope limit. This test makes the
explanation structural rather than a convention someone remembers.

"unverified — needs an owner to confirm what is missing" is an ACCEPTABLE note. An
honest admission that the gap is unknown is information; an invented reason is not.
"""

import json
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEATURES = os.path.join(REPO, "features.json")
MIN_NOTE_CHARS = 20


def _walk(node, path=""):
    if isinstance(node, dict):
        yield path, node
        for key, val in node.items():
            yield from _walk(val, f"{path}/{key}")
    elif isinstance(node, list):
        for i, val in enumerate(node):
            yield from _walk(val, f"{path}[{i}]")


class TestPartialFeaturesHaveNotes(unittest.TestCase):
    def setUp(self):
        with open(FEATURES, encoding="utf-8") as fh:
            self.data = json.load(fh)
        self.partials = [
            (node.get("name") or path, node)
            for path, node in _walk(self.data)
            if isinstance(node, dict) and node.get("status") == "partial"
        ]

    def test_there_are_partial_entries_to_check(self):
        """If this ever hits zero, the test below becomes vacuous — say so loudly."""
        self.assertGreater(len(self.partials), 0, "no partial entries; is the status enum still 'partial'?")

    def test_every_partial_entry_has_a_substantive_note(self):
        missing = [
            name
            for name, node in self.partials
            if not isinstance(node.get("notes"), str)
            or len(node["notes"].strip()) < MIN_NOTE_CHARS
        ]
        self.assertEqual(
            missing,
            [],
            "features.json entries marked 'partial' with no substantive notes field. "
            "State what is incomplete, or write 'unverified — needs an owner to confirm "
            f"what is missing' if you genuinely do not know: {missing}",
        )

    def test_notes_are_not_placeholders(self):
        banned = ("tbd", "todo", "n/a", "none", "-", "?")
        lazy = [
            name
            for name, node in self.partials
            if isinstance(node.get("notes"), str) and node["notes"].strip().lower() in banned
        ]
        self.assertEqual(lazy, [], f"placeholder notes are not an explanation: {lazy}")

    def test_plugin_version_is_not_hand_edited_here(self):
        """The release workflow owns the bump; version-sync.py writes all six locations."""
        self.assertRegex(str(self.data.get("pluginVersion", "")), r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
