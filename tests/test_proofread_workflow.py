"""Tests for the proofread Dynamic-Workflow script and its rewired skill.

Covers src/workflows/proofread.js (syntax, meta/phase contract, no fs access,
no bare threshold literals) and src/skills/proofread/SKILL.md (names all six
deterministic scripts + the workflow path, drops the stale "Option B" note,
and keeps Editorial -> Language -> Mechanical stage order).

`node --check` is run against a COPY of the workflow script in a directory
with no ancestor package.json. This repo's own package.json sets
"type": "module", which makes Node's checker apply strict ESM syntax rules
(no top-level `return`) -- but the Workflow tool's own house convention
(src/workflows/proofread.js here, and the two shipped reference templates
this was modeled on: orchestration's workflows/pipeline.js and ork's
audit-full-mapreduce.mjs) uses `export const meta` PLUS top-level
`return`/`await` together, which only ever parses under Node's more lenient
non-ESM-forced detection. Checking a package-json-free copy is what makes
`node --check` mean anything for this file, rather than failing on an
ambient repo setting the script itself has no control over.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(REPO, "src", "workflows", "proofread.js")
SKILL = os.path.join(REPO, "src", "skills", "proofread", "SKILL.md")

REQUIRED_PHASES = ["Editorial", "Language", "Mechanical", "Verify"]
REQUIRED_THRESHOLD_KEYS = [
    "chunkWords",
    "maxPasses",
    "dryRounds",
    "concurrencyCap",
    "refuteVotes",
    "refuteMajority",
]
REQUIRED_SCRIPTS = [
    "chunk-article.py",
    "spellcheck-candidates.py",
    "apply-changes.py",
    "citation-guard.py",
    "build-tracked-docx.py",
    "write-proof-report.py",
]


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
        tmp_dir = tempfile.mkdtemp(prefix="proofread-workflow-check-")
        try:
            tmp_copy = os.path.join(tmp_dir, "proofread.js")
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
        `args` and returns change lists. It must never require/import fs,
        or use any other node builtin module."""
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
        # Pure-literal guard: no function calls, spreads, or template
        # interpolation inside the meta object block itself.
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
            "meta.phases titles must be exactly ['Editorial', 'Language', 'Mechanical', 'Verify'] in order",
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

    def test_all_six_threshold_keys_read_from_args(self):
        for key in REQUIRED_THRESHOLD_KEYS:
            self.assertIn(
                f"thresholds.{key}",
                self.src,
                f"threshold key '{key}' must be read from args.thresholds.{key}, never a literal",
            )

    def test_no_bare_cap_literals(self):
        """No numeric literal appears where a threshold belongs -- the four
        default values from thresholds.json (chunkWords=1200, maxPasses=3,
        dryRounds=2, concurrencyCap=6) must never appear as bare tokens
        anywhere in the script, commented-out defaults included, since a
        literal default is exactly the WRK-14 violation this script exists
        to avoid."""
        forbidden = ["1200", "2", "3", "6"]
        for token in forbidden:
            pattern = re.compile(r"(?<![0-9A-Za-z_.])" + re.escape(token) + r"(?![0-9A-Za-z_.])")
            hits = pattern.findall(self.src)
            self.assertEqual(
                hits,
                [],
                f"bare cap-position literal '{token}' found in workflow script — caps must come only from args.thresholds",
            )

    def test_named_loop_exit_outcomes(self):
        self.assertIn("'converged'", self.src)
        self.assertIn("'cap-reached'", self.src)


class TestRefuteNeverDrops(unittest.TestCase):
    def setUp(self):
        self.src = _read(WORKFLOW)

    def test_refuted_downgrade_shape_present(self):
        self.assertIn("skipReason: 'refuted'", self.src)
        self.assertIn("refutedBy", self.src)

    def test_no_filter_call_drops_refuted_changes(self):
        """A majority-refute path must downgrade (push the change back with
        applied:false/skipReason), never `continue`/omit it from the
        returned list. Heuristic: every place a change is matched against a
        refute-majority condition, the same branch must still push/return
        that change object (i.e. 'refuted' always co-occurs with the change
        object being retained), not just log-and-skip."""
        # Every occurrence of the downgrade skipReason must be inside an
        # object literal that also still carries the original change's
        # fields (spread from `change`), proving it isn't dropped.
        for match in re.finditer(r"\{ \.\.\.change,[^}]*skipReason: 'refuted'", self.src):
            self.assertIn("applied: false", match.group(0))


class TestReturnShape(unittest.TestCase):
    def setUp(self):
        self.src = _read(WORKFLOW)

    def test_returns_expected_top_level_keys(self):
        for key in ["memo", "languageChanges", "mechanicalChanges", "outcome", "rounds", "gates"]:
            self.assertIn(key + ":", self.src, f"return object must carry `{key}`")

    def test_gates_recorded(self):
        self.assertIn("gates.push(", self.src)
        self.assertIn("ran:", self.src)
        self.assertIn("why:", self.src)


class TestSkillNamesEveryScriptAndWorkflow(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(SKILL), f"missing {SKILL}")
        self.src = _read(SKILL)

    def test_names_all_six_scripts(self):
        for script in REQUIRED_SCRIPTS:
            self.assertIn(script, self.src, f"SKILL.md must name {script}")

    def test_names_workflow_path(self):
        self.assertIn("workflows/proofread.js", self.src)

    def test_no_option_b_note(self):
        self.assertNotIn("Option B", self.src, "the stale 'future Option B' tracked-changes note must be removed — that capability now exists")

    def test_stage_order_editorial_language_mechanical(self):
        # Match the bolded stage markers in the numbered pipeline list
        # (e.g. "1. **Editorial**"), not any substring occurrence of the
        # word -- "targetLanguage" contains "Language" and would otherwise
        # false-positive an early match.
        editorial_idx = self.src.find("**Editorial**")
        language_idx = self.src.find("**Language**")
        mechanical_idx = self.src.find("**Mechanical**")
        self.assertNotEqual(editorial_idx, -1, "no bolded **Editorial** stage marker found")
        self.assertNotEqual(language_idx, -1, "no bolded **Language** stage marker found")
        self.assertNotEqual(mechanical_idx, -1, "no bolded **Mechanical** stage marker found")
        self.assertLess(editorial_idx, language_idx, "Editorial must be introduced before Language")
        self.assertLess(language_idx, mechanical_idx, "Language must be introduced before Mechanical")

    def test_frontmatter_has_use_when_trigger(self):
        match = re.match(r"^---\n(.*?\n)---", self.src, re.DOTALL)
        self.assertIsNotNone(match, "SKILL.md must have YAML frontmatter")
        self.assertIn("Use when", match.group(1))

    def test_skill_body_names_all_three_agents(self):
        # `agents:` is not a documented skill frontmatter key (ignored by Claude Code);
        # the skill body must still name every agent it dispatches.
        for expected in ["editor", "copyeditor", "proofreader"]:
            self.assertIn(expected, self.src)

if __name__ == "__main__":
    unittest.main()
