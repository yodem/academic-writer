"""voice.ruleCoverage bands must stay contiguous — warn == block is correct, not a bug.

The 2026-09-01 improvements page filed `warn == block == 6.0` as finding 8, "warn and block
voice.ruleCoverage thresholds share the same value", implying they should differ. They must not.
The consumers define three bands (voice/rules.md):

    score >= pass                 -> pass
    warn <= score < pass          -> warn
    score < block                 -> block

Setting warn=7.0 with block=6.0 would leave 6.0 <= score < 7.0 matching NO band: not a pass, not
a warn (below warn), not a block (not below block). warn == block is what makes the bands cover
the whole range exactly once. This test exists so the finding is not "fixed" into a real gap.
"""

import json
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bands():
    with open(os.path.join(REPO, "src", "thresholds.json"), encoding="utf-8") as fh:
        return json.load(fh)["voice"]["ruleCoverage"]


def _classify(score, b):
    """Exactly the consumers' logic, in order."""
    if score >= b["pass"]:
        return "pass"
    if score >= b["warn"]:
        return "warn"
    if score < b["block"]:
        return "block"
    return "UNCLASSIFIED"


class TestRuleCoverageBands(unittest.TestCase):
    def test_bands_are_ordered(self):
        b = _bands()
        self.assertLessEqual(b["block"], b["warn"], "block must not exceed warn")
        self.assertLess(b["warn"], b["pass"], "warn must be below pass or the warn band is empty")

    def test_every_score_lands_in_exactly_one_band(self):
        b = _bands()
        gaps = [
            round(s / 10, 1)
            for s in range(0, 101)
            if _classify(round(s / 10, 1), b) == "UNCLASSIFIED"
        ]
        self.assertEqual(
            gaps,
            [],
            "scores matching no band — this is what raising warn above block causes: " f"{gaps}",
        )

    def test_raising_warn_above_block_would_open_a_gap(self):
        """Guards the reasoning, not just the current values."""
        broken = {"pass": 8.0, "warn": 7.0, "block": 6.0}
        gaps = [
            round(s / 10, 1)
            for s in range(0, 101)
            if _classify(round(s / 10, 1), broken) == "UNCLASSIFIED"
        ]
        self.assertTrue(
            gaps, "the counter-example must actually produce a gap, or this test proves nothing"
        )
        self.assertIn(6.5, gaps)

    def test_current_values_are_the_contiguous_choice(self):
        b = _bands()
        self.assertEqual(
            b["warn"],
            b["block"],
            "warn == block is deliberate (contiguous bands). If you intend to change it, "
            "change the rules contract first.",
        )


if __name__ == "__main__":
    unittest.main()
