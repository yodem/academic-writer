"""Coverage for src/scripts/jev-risk-shadow.py, the opt-in Jev second opinion on
proofread meaningRisk labels. It never changes a change, never blocks the
pipeline, and writes only to the project's .academic-helper/ ledger.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT_DIR, "src", "scripts", "jev-risk-shadow.py")
THRESHOLDS = os.path.join(ROOT_DIR, "src", "thresholds.json")

spec = importlib.util.spec_from_file_location("jev_risk_shadow", SCRIPT)
jrs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jrs)


def payload(*changes):
    return {"stage": "language", "chunk_id": "chunk-001", "changes": list(changes), "summary": ""}


def change(before, after, risk="low", stage="language", line=1):
    return {"stage": stage, "line": line, "type": "syntax", "level": "word",
            "before": before, "after": after, "rationale": "r", "meaningRisk": risk}


class ShadowRowTests(unittest.TestCase):
    def test_low_label_with_high_jev_score_is_a_disagreement(self):
        row = jrs.shadow_row(change("א", "ב", risk="low"), score=1.9, flag_score=1.5, model="jev-1.13.0")
        self.assertTrue(row["jevFlagsRisk"])
        self.assertTrue(row["disagree"])

    def test_medium_label_with_high_jev_score_agrees(self):
        row = jrs.shadow_row(change("א", "ב", risk="medium"), score=1.9, flag_score=1.5, model="jev-1.13.0")
        self.assertFalse(row["disagree"])

    def test_low_label_with_low_jev_score_agrees(self):
        row = jrs.shadow_row(change("א", "ב", risk="low"), score=0.2, flag_score=1.5, model="jev-1.13.0")
        self.assertFalse(row["jevFlagsRisk"])
        self.assertFalse(row["disagree"])

    def test_candidates_skip_comment_only_changes(self):
        cands = jrs.candidates(payload(change("א", "ב"), {**change("א", None), "after": None}))
        self.assertEqual(len(cands), 1)

    def test_run_with_fake_ask_writes_ledger_and_leaves_payload_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "changes.json")
            data = payload(change("א", "ב", risk="low"), change("ג", "ד", risk="medium", line=2))
            with open(src, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            ledger = os.path.join(d, ".academic-helper", "jev-shadow.jsonl")
            n = jrs.run(src, ledger, "art", flag_score=1.5, model="m",
                        ask=lambda ch: 1.9 if ch["line"] == 1 else 1.95)
            self.assertEqual(n, 2)
            rows = [json.loads(l) for l in open(ledger, encoding="utf-8")]
            self.assertEqual([r["disagree"] for r in rows], [True, False])
            self.assertEqual(rows[0]["filebase"], "art")
            with open(src, encoding="utf-8") as f:
                self.assertEqual(json.load(f), data)


class CliTests(unittest.TestCase):
    def test_disabled_by_default_exits_zero_without_network(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "changes.json")
            with open(src, "w", encoding="utf-8") as f:
                json.dump(payload(change("א", "ב")), f)
            env = {k: v for k, v in os.environ.items() if k not in ("AW_JEV_SHADOW", "TYPESAFE_API_KEY")}
            r = subprocess.run([sys.executable, SCRIPT, "--changes", src, "--filebase", "art",
                                "--ledger", os.path.join(d, "l.jsonl")],
                               capture_output=True, text=True, timeout=30, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("disabled", r.stdout)
            self.assertFalse(os.path.exists(os.path.join(d, "l.jsonl")))

    def test_enabled_but_missing_ledger_dir_skips_without_creating_it(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "changes.json")
            with open(src, "w", encoding="utf-8") as f:
                json.dump(payload(change("א", "ב")), f)
            env = {**os.environ, "AW_JEV_SHADOW": "1"}
            ledger = os.path.join(d, ".academic-helper", "jev-shadow.jsonl")
            r = subprocess.run([sys.executable, SCRIPT, "--changes", src, "--filebase", "art", "--ledger", ledger],
                               capture_output=True, text=True, timeout=30, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("does not exist", r.stdout)
            self.assertFalse(os.path.exists(os.path.join(d, ".academic-helper")))

    def test_threshold_block_exists_and_is_off(self):
        with open(THRESHOLDS, encoding="utf-8") as f:
            block = json.load(f)["proofread"]["jevShadow"]
        self.assertFalse(block["enabled"])
        self.assertEqual(block["flagScore"], 1.5)


if __name__ == "__main__":
    unittest.main()
