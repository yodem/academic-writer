"""Tests for the write-sections Dynamic-Workflow script.

Covers src/workflows/write-sections.js (syntax, meta/phase contract, no fs
access, thresholds read from args rather than inlined, the AUDIT_MODE:
external contract, and the returned object's shape).

`node --check` is run against a COPY of the workflow script in a directory
with no ancestor package.json. This repo's own package.json sets
"type": "module", which makes Node's checker apply strict ESM syntax rules
(no top-level `return`) -- but the Workflow tool's own house convention
(src/workflows/proofread.js, the style reference for this file) uses
`export const meta` PLUS top-level `return`/`await` together, which only
ever parses under Node's more lenient non-ESM-forced detection. Checking a
package-json-free copy is what makes `node --check` mean anything for this
file, rather than failing on an ambient repo setting the script itself has
no control over. See tests/test_proofread_workflow.py for the established
idiom this test reuses.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(REPO, "src", "workflows", "write-sections.js")

REQUIRED_PHASES = ["Draft", "Audit", "Synthesize", "Score"]
REQUIRED_THRESHOLD_KEYS = ["rewriteCycles", "writerUnit"]
REQUIRED_RETURN_KEYS = ["sections", "scorecard", "needsReview", "gates", "outcome"]


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


class TestWorkflowScriptExistsAndParses(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(WORKFLOW), f"missing {WORKFLOW}")
        self.src = _read(WORKFLOW)

    def test_node_check_passes_outside_this_repos_module_context(self):
        """node --check must pass on a copy isolated from this repo's
        package.json (type: module), which otherwise forces strict ESM
        rules the Workflow tool's own convention does not follow either
        (see module docstring)."""
        tmp_dir = tempfile.mkdtemp(prefix="write-sections-workflow-check-")
        try:
            tmp_copy = os.path.join(tmp_dir, "write-sections.js")
            shutil.copyfile(WORKFLOW, tmp_copy)
            result = subprocess.run(
                ["node", "--check", tmp_copy],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                result.returncode,
                0,
                f"node --check failed:\nstdout={result.stdout}\nstderr={result.stderr}",
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_no_filesystem_access(self):
        """The workflow script has NO filesystem access -- it reads only
        `args` and returns sections/scorecard/gates. It must never
        require/import fs, or use any other node builtin module."""
        self.assertNotRegex(self.src, r"require\(", "workflow script must not require() anything")
        self.assertNotRegex(self.src, r"^\s*import\s", "workflow script must not use ES import statements")
        self.assertNotIn('"fs"', self.src)
        self.assertNotIn("'fs'", self.src)
        self.assertNotRegex(self.src, r"\bprocess\.", "workflow script must not touch process")


class TestMetaPhaseContract(unittest.TestCase):
    def setUp(self):
        self.src = _read(WORKFLOW)

    def test_meta_is_pure_literal_export(self):
        self.assertRegex(
            self.src,
            r"export const meta\s*=\s*\{",
            "workflow script must begin with a pure-literal `export const meta = {...}`",
        )
        match = re.search(r"export const meta\s*=\s*(\{.*?\n\};)", self.src, re.DOTALL)
        self.assertIsNotNone(match, "could not isolate the meta object literal block")
        meta_block = match.group(1)
        self.assertNotIn("${", meta_block, "meta block must be a pure literal — no interpolation")
        self.assertNotIn("...", meta_block, "meta block must be a pure literal — no spreads")

    def test_meta_phases_titles_match_phase_calls_exactly(self):
        match = re.search(r"export const meta\s*=\s*(\{.*?\n\};)", self.src, re.DOTALL)
        self.assertIsNotNone(match)
        meta_block = match.group(1)
        titles = re.findall(r"title:\s*'([^']+)'", meta_block)
        self.assertEqual(
            titles,
            REQUIRED_PHASES,
            "meta.phases titles must be exactly ['Draft', 'Audit', 'Synthesize', 'Score'] in order",
        )
        phase_calls = re.findall(r"phase\('([^']+)'\)", self.src)
        self.assertEqual(
            phase_calls,
            REQUIRED_PHASES,
            "phase(...) calls must appear in the script, in the same order, exactly matching meta.phases titles",
        )


class TestThresholdsReadFromArgs(unittest.TestCase):
    def setUp(self):
        self.src = _read(WORKFLOW)

    def test_all_three_threshold_keys_read_from_args(self):
        for key in REQUIRED_THRESHOLD_KEYS:
            self.assertIn(
                f"thresholds.{key}",
                self.src,
                f"threshold key '{key}' must be read from args.thresholds.{key}, never a literal",
            )

    def test_rewrite_cycles_max_read_from_args(self):
        self.assertIn("rewriteCycles.max", self.src)

    def test_anti_ai_is_not_a_scored_gate(self):
        """The anti-AI numeric gate was removed in 0.9.0.

        It read `selfReviewScores.anti_ai` against `antiAi.passThreshold`, but
        nothing computed that score — `selfReviewScores` appears nowhere in the
        Gemini server source, so it was the drafting model rating its own
        unrevised draft. On a live 13-unit run it returned a flat 50/50 on
        every paragraph, including paragraphs the auditor then FAILED. A scorer
        pinned at maximum passes unconditionally.

        The auditor VERDICT is now the only per-paragraph hard gate.
        """
        self.assertNotIn(
            "thresholds.antiAi",
            self.src,
            "the removed anti-AI threshold must not be read from args again",
        )
        # The stage is still reported, so a caller diffing gate names sees it
        # was deliberately retired rather than silently dropped.
        self.assertIn("'anti-ai'", self.src)
        self.assertIn("not a gate", self.src)

    def test_writer_unit_bounds_read_from_args(self):
        self.assertIn("writerUnit.targetWords", self.src)
        self.assertIn("writerUnit.minWords", self.src)
        self.assertIn("writerUnit.maxWords", self.src)

    def test_named_loop_exit_outcomes(self):
        self.assertIn("'PASS'", self.src)
        self.assertIn("'NEEDS_REVIEW'", self.src)


class TestAuditModeExternalContract(unittest.TestCase):
    def setUp(self):
        self.src = _read(WORKFLOW)

    def test_audit_mode_external_present(self):
        self.assertIn("AUDIT_MODE", self.src)
        self.assertIn("external", self.src)

    def test_agent_types_present(self):
        self.assertIn("academic-writer:section-writer", self.src)
        self.assertIn("academic-writer:auditor", self.src)


class TestReturnShape(unittest.TestCase):
    def setUp(self):
        self.src = _read(WORKFLOW)

    def test_returns_expected_top_level_keys(self):
        for key in REQUIRED_RETURN_KEYS:
            self.assertIn(key + ":", self.src, f"return object must carry `{key}`")

    def test_gates_recorded(self):
        self.assertIn("gates.push(", self.src)
        self.assertIn("ran:", self.src)
        self.assertIn("why:", self.src)

    def test_single_await_barrier_comment_present(self):
        """The plan calls for exactly ONE await barrier over the whole
        per-unit pipeline array, ahead of the synthesizer and scorecard
        stages — assert the barrier exists and is documented as such."""
        self.assertIn("ONLY await barrier", self.src)
        self.assertIn("await Promise.all(", self.src)


if __name__ == "__main__":
    unittest.main()
