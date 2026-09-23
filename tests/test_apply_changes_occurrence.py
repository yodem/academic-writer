"""Coverage for the `occurrence` field: src/scripts/must-catch.py emits it for
a capped style-word change whose exact span repeats on the same line, and
src/scripts/apply-changes.py honours it to disambiguate which instance to
touch instead of reporting skipReason="ambiguous-match" (the previous
behaviour, still exercised here as the "absent" fallback).

Schema contract: src/skills/proofread/references/changes-schema.json
`$defs.change.properties.occurrence`.

Owns only this test file plus the `occurrence` handling inside
src/scripts/must-catch.py and src/scripts/apply-changes.py -- does not touch
any other test file or script.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MUST_CATCH = ROOT / "src" / "scripts" / "must-catch.py"
APPLY_CHANGES = ROOT / "src" / "scripts" / "apply-changes.py"


def run_script(script, *args):
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, timeout=30)


def make_change(**overrides):
    change = {
        "stage": "mechanical",
        "line": 1,
        "type": "word",
        "level": "word",
        "before": "כמו כן",
        "after": "נוסף על כך",
        "rationale": "capped connective",
        "meaningRisk": "low",
        "mustCatch": True,
    }
    change.update(overrides)
    return change


class ApplyOccurrenceTestCase(unittest.TestCase):
    def _run(self, changes, proof_base_text, extra_args=None):
        import tempfile

        extra_args = extra_args or []
        with tempfile.TemporaryDirectory() as tmpdir:
            changes_path = Path(tmpdir) / "changes.json"
            proof_base_path = Path(tmpdir) / "proof_base.md"
            changes_path.write_text(json.dumps({"stage": "mechanical", "changes": changes}), encoding="utf-8")
            proof_base_path.write_text(proof_base_text, encoding="utf-8")
            proc = run_script(
                APPLY_CHANGES, "--changes", str(changes_path), "--proof-base", str(proof_base_path), "--json", *extra_args
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads(proc.stdout)
            final_text = proof_base_path.read_text(encoding="utf-8")
        return result, final_text


class TestOccurrenceDisambiguatesSameLineDuplicate(ApplyOccurrenceTestCase):
    def test_second_occurrence_replaced_first_untouched(self):
        change = make_change(line=1, occurrence=2)
        proof_base = "כמו כן הוא טען. כמו כן הוא הוסיף.\n"
        result, final_text = self._run([change], proof_base)
        out = result["changes"][0]
        self.assertTrue(out["applied"], out)
        self.assertIsNone(out.get("skipReason"))
        self.assertEqual(final_text, "כמו כן הוא טען. נוסף על כך הוא הוסיף.\n")

    def test_first_occurrence_replaced_second_untouched(self):
        change = make_change(line=1, occurrence=1)
        proof_base = "כמו כן הוא טען. כמו כן הוא הוסיף.\n"
        result, final_text = self._run([change], proof_base)
        out = result["changes"][0]
        self.assertTrue(out["applied"], out)
        self.assertEqual(final_text, "נוסף על כך הוא טען. כמו כן הוא הוסיף.\n")

    def test_occurrence_beyond_available_count_is_no_match(self):
        change = make_change(line=1, occurrence=3)
        proof_base = "כמו כן הוא טען. כמו כן הוא הוסיף.\n"
        result, final_text = self._run([change], proof_base)
        out = result["changes"][0]
        self.assertFalse(out["applied"])
        self.assertEqual(out["skipReason"], "no-match")
        self.assertEqual(final_text, proof_base)


class TestOccurrenceAbsentFallsBackToAmbiguousMatch(ApplyOccurrenceTestCase):
    def test_no_occurrence_field_same_line_duplicate_is_still_ambiguous(self):
        change = make_change(line=1)
        self.assertNotIn("occurrence", change)
        proof_base = "כמו כן הוא טען. כמו כן הוא הוסיף.\n"
        result, final_text = self._run([change], proof_base)
        out = result["changes"][0]
        self.assertFalse(out["applied"])
        self.assertEqual(out["skipReason"], "ambiguous-match")
        self.assertEqual(final_text, proof_base)


class TestMustCatchIntoApplyChangesPipeline(unittest.TestCase):
    """End-to-end: real must-catch.py output piped into apply_changes(), not a
    hand-written change payload -- proves the field actually survives the
    producer/consumer boundary, not just a shape apply-changes.py was told to
    expect."""

    def test_capped_word_pipeline_replaces_only_the_over_cap_instance(self):
        import tempfile

        tmpdir = Path(tempfile.mkdtemp())
        text_path = tmpdir / "a.md"
        styles_path = tmpdir / "s.json"
        terms_path = tmpdir / "t.json"
        text = "כמו כן הוא טען. כמו כן הוא הוסיף.\n"
        text_path.write_text(text, encoding="utf-8")
        styles_path.write_text(
            json.dumps({"banned": [], "filler": [], "capped": [{"word": "כמו כן", "maxPer": "paragraph", "max": 1, "replacement": "נוסף על כך"}]}),
            encoding="utf-8",
        )
        terms_path.write_text(json.dumps({"canon": []}), encoding="utf-8")

        must_catch_proc = run_script(
            MUST_CATCH, "--text", str(text_path), "--style-words", str(styles_path), "--terms", str(terms_path), "--json"
        )
        self.assertEqual(must_catch_proc.returncode, 0, must_catch_proc.stderr)
        must_catch_out = json.loads(must_catch_proc.stdout)
        self.assertEqual(len(must_catch_out["changes"]), 1)
        self.assertEqual(must_catch_out["changes"][0]["occurrence"], 2)

        changes_path = tmpdir / "changes.json"
        changes_path.write_text(json.dumps({"stage": "mechanical", "changes": must_catch_out["changes"]}), encoding="utf-8")
        apply_proc = run_script(APPLY_CHANGES, "--changes", str(changes_path), "--proof-base", str(text_path), "--json")
        self.assertEqual(apply_proc.returncode, 0, apply_proc.stderr)
        applied = json.loads(apply_proc.stdout)
        self.assertTrue(applied["changes"][0]["applied"], applied)

        final_text = text_path.read_text(encoding="utf-8")
        self.assertEqual(final_text, "כמו כן הוא טען. נוסף על כך הוא הוסיף.\n")


if __name__ == "__main__":
    unittest.main()
