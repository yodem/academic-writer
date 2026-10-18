"""Every feature and subfeature in features.json says how it is tested, and About data is generated from it.

`tested` is one of e2e | unit | manual | not tested yet. `scripts/gen-about.py` turns features.json and the
skills' frontmatter into src/scripts/courses/dashboard/about.json (the dashboard's About page);
`gen-about.py --check` must exit 0.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FEATURES = REPO / "features.json"
GEN = REPO / "scripts" / "gen-about.py"
ABOUT = REPO / "src" / "scripts" / "courses" / "dashboard" / "about.json"
ALLOWED = {"e2e", "unit", "manual", "not tested yet"}
NEW_FEATURES = {"home-workspaces", "brand", "agent-activity", "activity-pane", "setup-checks"}


def feature_nodes(features):
    """Yield every feature and subfeature node, at any depth."""
    for node in features:
        yield node
        yield from feature_nodes(node.get("subfeatures") or [])


class TestedField(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(FEATURES.read_text(encoding="utf-8"))
        self.nodes = list(feature_nodes(self.data["features"]))

    def test_every_node_has_tested(self):
        missing = [n.get("id") for n in self.nodes if "tested" not in n]
        self.assertEqual(missing, [], "features without a `tested` value: %s" % missing)

    def test_tested_values_allowed(self):
        bad = [(n.get("id"), n.get("tested")) for n in self.nodes if n.get("tested") not in ALLOWED]
        self.assertEqual(bad, [])

    def test_new_features_present(self):
        ids = {n["id"] for n in self.data["features"]}
        self.assertTrue(NEW_FEATURES <= ids, NEW_FEATURES - ids)

    def test_about_up_to_date(self):
        proc = subprocess.run([sys.executable, str(GEN), "--check"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_about_shape(self):
        about = json.loads(ABOUT.read_text(encoding="utf-8"))
        self.assertEqual(set(about), {"version", "features", "onboarding", "guide"})
        self.assertEqual(about["guide"], "/academic-writer:intro")
        self.assertEqual(set(about["onboarding"]), {"student", "lecturer", "researcher"})
        for role, steps in about["onboarding"].items():
            self.assertTrue(1 <= len(steps) <= 5, role)
        want = {"id", "name_he", "description_he", "command", "status", "tested", "subfeatures"}
        for feat in about["features"]:
            self.assertTrue(want <= set(feat), feat["id"])
            self.assertIn(feat["tested"], ALLOWED)
            for sub in feat["subfeatures"]:
                self.assertIn(sub["tested"], ALLOWED)
        ids = [f["id"] for f in about["features"]]
        self.assertEqual(ids, [n["id"] for n in self.data["features"]])

    def test_feature_without_subfeatures_is_valid(self):
        about = json.loads(ABOUT.read_text(encoding="utf-8"))
        flat = [f for f in about["features"] if not f["subfeatures"]]
        self.assertTrue(flat, "expected at least one feature without subfeatures (gemini-mcp-retirement)")

    def test_commands_come_from_user_invocable_skills(self):
        about = json.loads(ABOUT.read_text(encoding="utf-8"))
        by_id = {f["id"]: f for f in about["features"]}
        self.assertEqual(by_id["ingest"]["command"], "/academic-writer:ingest")
        self.assertEqual(by_id["course-dashboard"]["command"], "/academic-writer:dashboard")
        self.assertIsNone(by_id["citation-audit"]["command"])  # an agent, not a command

    def test_descriptions_are_hebrew_and_authored(self):
        about = json.loads(ABOUT.read_text(encoding="utf-8"))
        authored = {n["id"]: n.get("description_he") for n in self.data["features"]}
        for feat in about["features"]:
            self.assertRegex(feat["description_he"], r"[\u0590-\u05FF]", feat["id"])
            if authored[feat["id"]]:
                self.assertEqual(feat["description_he"], authored[feat["id"]], feat["id"])

    def test_command_only_from_the_primary_source(self):
        about = json.loads(ABOUT.read_text(encoding="utf-8"))
        by_id = {f["id"]: f for f in about["features"]}
        self.assertIsNone(by_id["gemini-mcp-retirement"]["command"])
        self.assertIsNone(by_id["synthesis"]["command"])
        self.assertEqual(by_id["editing"]["command"], "/academic-writer:edit-section")
        self.assertEqual(by_id["section-writing"]["command"], "/academic-writer:write")


if __name__ == "__main__":
    unittest.main()
