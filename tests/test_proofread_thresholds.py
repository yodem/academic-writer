"""Proofread pipeline gates live in thresholds.json, never inlined (CLAUDE.md convention)."""

import json
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THRESHOLDS = os.path.join(REPO, "src", "thresholds.json")
BUILD = os.path.join(REPO, "scripts", "build-plugins.sh")

REQUIRED = {
    "chunkWords": int,
    "maxPasses": int,
    "dryRounds": int,
    "concurrencyCap": int,
    "refuteVotes": int,
    "refuteMajority": int,
}


class TestProofreadThresholds(unittest.TestCase):
    def setUp(self):
        with open(THRESHOLDS, encoding="utf-8") as fh:
            self.data = json.load(fh)

    def test_proofread_block_present(self):
        self.assertIn("proofread", self.data, "thresholds.json missing 'proofread' block")

    def test_required_keys_and_types(self):
        block = self.data["proofread"]
        for key, kind in REQUIRED.items():
            self.assertIn(key, block, f"proofread.{key} missing")
            self.assertIsInstance(block[key], kind, f"proofread.{key} must be {kind.__name__}")
            self.assertGreater(block[key], 0, f"proofread.{key} must be positive")

    def test_refute_majority_reachable(self):
        block = self.data["proofread"]
        self.assertLessEqual(
            block["refuteMajority"],
            block["refuteVotes"],
            "refuteMajority cannot exceed refuteVotes — the gate would never fire",
        )

    def test_dry_rounds_within_max_passes(self):
        block = self.data["proofread"]
        self.assertLessEqual(
            block["dryRounds"],
            block["maxPasses"],
            "dryRounds > maxPasses means the loop can never exit 'converged'",
        )


class TestBuildCopiesWorkflows(unittest.TestCase):
    def test_build_script_copies_src_workflows(self):
        with open(BUILD, encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(
            re.search(r'cp -R "\$SRC_DIR/workflows"', text),
            "build-plugins.sh must copy src/workflows/ into the plugin "
            "(Workflow scriptPath targets live there)",
        )


if __name__ == "__main__":
    unittest.main()
