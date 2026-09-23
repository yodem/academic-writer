"""The canonical proofread changes contract must parse and stay single-source."""

import json
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(REPO, "src", "skills", "proofread", "references", "changes-schema.json")
CLI = os.path.join(REPO, "src", "cli", "src", "proofread.ts")


class TestCanonicalSchema(unittest.TestCase):
    def test_canonical_contract_parses(self):
        with open(SCHEMA, encoding="utf-8") as stream:
            schema = json.load(stream)
        self.assertIn("changes", schema["properties"])
        self.assertIn("change", schema["$defs"])
        self.assertIn("meaningRisk", schema["$defs"]["change"]["properties"])

    def test_cli_has_no_inline_copy_of_changes_contract(self):
        with open(CLI, encoding="utf-8") as stream:
            source = stream.read()
        # The responseSchema objects for model transport are intentionally small;
        # the apply contract is loaded by gate.py from the canonical JSON file.
        self.assertNotRegex(source, r"(?:const|let)\s+(?:CHANGES_SCHEMA|CHANGE_ITEM_SCHEMA)\b")
        self.assertNotRegex(source, r"\$defs\s*:\s*\{\s*change\s*:")
        self.assertIn("changes-schema", source)


if __name__ == "__main__":
    unittest.main()
