"""Tests for the per-unit batched audit/rewrite loop in
src/workflows/write-sections.js.

Evidence (a real /write run, 2026-09-05): 356 agents / ~28M effective tokens,
218 of them auditor spawns and 122 section-writer rewrites, because the loop
spawned ONE auditor per paragraph per attempt and ONE rewrite per failed
paragraph per attempt, each paying a fixed ~25-35k cache-write cost to
re-discover its environment. The loop now runs per UNIT per ROUND: one auditor
call for every pending paragraph, one rewrite call for every failed paragraph.

Batching must not weaken the gate, so these tests pin, BY EXECUTION and by
counting agent() calls (not by reading the source):
  - spawn counts for a 4-paragraph unit where one paragraph fails once;
  - a paragraph omitted from the auditor's results is ERROR and still present;
  - a null auditor call errors every paragraph and stops the unit.

Approach (same idiom as tests/test_proofread_refute_budget.py): the ACTUAL
script source is read, `export const meta` is rewritten to `const meta`, the
body is wrapped in an async IIFE, and stub `agent`/`log`/`phase`/`parallel`/
`pipeline` globals are injected the way the Workflow tool injects them.
The stub auditor/rewrite responses are supplied per test as a JS function
body so a scenario can depend on the round and on which paragraphs a batch
actually contained.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(REPO, "src", "workflows", "write-sections.js")

THRESHOLDS = {
    "rewriteCycles": {"max": 3},
    "writerUnit": {"targetWords": 300, "minWords": 200, "maxWords": 400},
}

DRAFT = {
    "unitId": "u1",
    "paragraphs": [
        {"paragraphIndex": 1, "text": "Paragraph one."},
        {"paragraphIndex": 2, "text": "Paragraph two."},
        {"paragraphIndex": 3, "text": "Paragraph three."},
        {"paragraphIndex": 4, "text": "Paragraph four."},
    ],
}


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _build_harness(args_obj, draft, audit_js, rewrite_js):
    """`audit_js` / `rewrite_js` are JS function bodies with `round` (int),
    `indices` (paragraphIndex values found in the prompt) and `prompt` in
    scope; each must `return` the stub agent() result."""
    body = re.sub(r"^export const meta", "const meta", _read(WORKFLOW), count=1, flags=re.MULTILINE)
    assert "export const meta" not in body, "failed to strip the ESM export keyword"
    return (
        "const __calls = { agent: [], log: [] };\n"
        "const args = " + json.dumps(args_obj) + ";\n"
        "const DRAFT = " + json.dumps(draft) + ";\n"
        "function __indices(prompt) {\n"
        "  const out = []; const re = /^PARAGRAPH_INDEX: (\\d+)$/gm; let m;\n"
        "  while ((m = re.exec(prompt)) !== null) out.push(Number(m[1]));\n"
        "  return out;\n"
        "}\n"
        "function __audit(round, indices, prompt) {\n" + audit_js + "\n}\n"
        "function __rewrite(round, indices, prompt) {\n" + rewrite_js + "\n}\n"
        "async function agent(prompt, opts) {\n"
        "  const label = (opts && opts.label) || '';\n"
        "  __calls.agent.push({ label: label, agentType: opts && opts.agentType, hasSchema: !!(opts && opts.schema), indices: __indices(prompt) });\n"
        "  if (label.indexOf('draft:') === 0) return DRAFT;\n"
        "  let m = /^audit:[^:]+:r(\\d+)$/.exec(label);\n"
        "  if (m) return __audit(Number(m[1]), __indices(prompt), prompt);\n"
        "  m = /^rewrite:[^:]+:r(\\d+)$/.exec(label);\n"
        "  if (m) return __rewrite(Number(m[1]), __indices(prompt), prompt);\n"
        "  if (label === 'synthesize') return 'synthesized';\n"
        "  if (label === 'abstract') return { abstract: 'abstract text' };\n"
        "  if (label === 'scorecard') return { dimensions: [{ id: 'structure', score: 5 }], total: 30 };\n"
        "  throw new Error('unexpected agent label: ' + label);\n"
        "}\n"
        "function log(msg) { __calls.log.push(String(msg)); }\n"
        "function phase(name) {}\n"
        "async function parallel(thunks) { return Promise.all(thunks.map(function (fn) { return fn(); })); }\n"
        "async function pipeline(items, stage1, stage2) {\n"
        "  return Promise.all(items.map(async function (item) { return await stage2(await stage1(item)); }));\n"
        "}\n"
        "(async () => {\n" + body + "\n})().then(function (result) {\n"
        "  process.stdout.write(JSON.stringify({ result: result, calls: __calls }));\n"
        "}).catch(function (err) {\n"
        "  process.stderr.write('HARNESS_ERROR: ' + (err && err.stack ? err.stack : String(err)));\n"
        "  process.exitCode = 1;\n"
        "});\n"
    )


def _run(audit_js, rewrite_js="throw new Error('rewrite must not be called');", draft=DRAFT):
    args_obj = {"outline": {"units": [{"id": "u1", "title": "Unit One", "claim": "c1", "evidence": ["e1"]}]},
                "thresholds": THRESHOLDS}
    tmp_dir = tempfile.mkdtemp(prefix="write-audit-batching-")
    try:
        harness_path = os.path.join(tmp_dir, "harness.js")
        with open(harness_path, "w", encoding="utf-8") as fh:
            fh.write(_build_harness(args_obj, draft, audit_js, rewrite_js))
        proc = subprocess.run(["node", harness_path], cwd=tmp_dir, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0 or not proc.stdout.strip():
            raise AssertionError("harness run failed (exit={}):\nstdout={}\nstderr={}".format(
                proc.returncode, proc.stdout, proc.stderr))
        return json.loads(proc.stdout)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _labels(out, prefix):
    return [c for c in out["calls"]["agent"] if c["label"].startswith(prefix)]


def _paragraphs(out):
    sections = out["result"]["sections"]
    assert len(sections) == 1, sections
    return sections[0]["paragraphs"]


# Every auditor stub below answers only for the paragraphs actually present in
# its batch prompt, so a test also proves which paragraphs each round carried.
PASS_ALL_BUT_P2_IN_ROUND_1 = """
return { results: indices.map(function (i) {
  if (round === 1 && i === 2) return { paragraphIndex: i, verdict: 'FAIL', feedback: 'page mismatch in footnote 1' };
  return { paragraphIndex: i, verdict: 'PASS', feedback: 'verified' };
}) };
"""


class TestOneFailureCostsOneExtraRoundNotOneExtraSpawnPerParagraph(unittest.TestCase):
    """AC3: 1 unit, 4 paragraphs, cap 3; p2 FAILs in round 1, everything else
    passes -> exactly 2 auditor calls, 1 rewrite call, no other spawns."""

    @classmethod
    def setUpClass(cls):
        cls.out = _run(
            PASS_ALL_BUT_P2_IN_ROUND_1,
            "return { paragraphs: indices.map(function (i) { return { paragraphIndex: i, text: 'Rewritten paragraph ' + i + '.' }; }) };",
        )

    def test_spawn_counts(self):
        audits = _labels(self.out, "audit:")
        rewrites = _labels(self.out, "rewrite:")
        self.assertEqual([c["label"] for c in audits], ["audit:u1:r1", "audit:u1:r2"])
        self.assertEqual([c["label"] for c in rewrites], ["rewrite:u1:r1"])
        other = [c["label"] for c in self.out["calls"]["agent"]
                 if not c["label"].startswith(("audit:", "rewrite:"))]
        self.assertEqual(sorted(other), sorted(["draft:u1", "synthesize", "abstract", "scorecard"]),
                         "no spawns beyond draft, the batched audit/rewrite calls, and the post-audit stages")

    def test_batches_carry_the_right_paragraphs(self):
        audits = _labels(self.out, "audit:")
        self.assertEqual(audits[0]["indices"], [1, 2, 3, 4], "round 1 audits every paragraph in one call")
        self.assertEqual(audits[1]["indices"], [2], "round 2 re-audits only the paragraph that failed")
        self.assertEqual(_labels(self.out, "rewrite:")[0]["indices"], [2])
        for c in audits:
            self.assertEqual(c["agentType"], "academic-writer:auditor")
            self.assertTrue(c["hasSchema"], "the batched auditor call must request structured output")
        rw = _labels(self.out, "rewrite:")[0]
        self.assertEqual(rw["agentType"], "academic-writer:section-writer")
        self.assertTrue(rw["hasSchema"])

    def test_outcomes_order_and_attempts(self):
        paragraphs = _paragraphs(self.out)
        self.assertEqual([p["paragraphIndex"] for p in paragraphs], [1, 2, 3, 4])
        self.assertEqual([p["outcome"] for p in paragraphs], ["PASS"] * 4)
        self.assertEqual([p["attempts"] for p in paragraphs], [1, 2, 1, 1])
        self.assertEqual(paragraphs[1]["text"], "Rewritten paragraph 2.", "the rewrite must actually land")
        self.assertEqual(paragraphs[0]["text"], "Paragraph one.")
        self.assertEqual(self.out["result"]["outcome"], "PASS")

    def test_per_paragraph_outcome_log_format_kept(self):
        outcome_lines = [l for l in self.out["calls"]["log"] if l.startswith("AUDIT_OUTCOME:")]
        self.assertIn("AUDIT_OUTCOME: unit=u1 paragraph=2 outcome=PASS attempts=2 lastVerdict=PASS", outcome_lines)
        self.assertEqual(len(outcome_lines), 4)


class TestOmittedParagraphIsErrorNeverPass(unittest.TestCase):
    """AC4a: the auditor's results omit paragraph 3 -> p3 is ERROR and still
    present; the other paragraphs are unaffected."""

    def test_omitted_paragraph_is_error_and_present(self):
        out = _run("""
return { results: indices.filter(function (i) { return i !== 3; }).map(function (i) {
  return { paragraphIndex: i, verdict: 'PASS', feedback: 'verified' };
}) };
""")
        paragraphs = _paragraphs(out)
        self.assertEqual([p["paragraphIndex"] for p in paragraphs], [1, 2, 3, 4])
        self.assertEqual([p["outcome"] for p in paragraphs], ["PASS", "PASS", "ERROR", "PASS"])
        self.assertEqual(paragraphs[2]["errorReason"], "auditor batch omitted this paragraph")
        self.assertEqual(paragraphs[2]["text"], "Paragraph three.")
        self.assertEqual(len(_labels(out, "audit:")), 1)
        self.assertEqual(out["result"]["outcome"], "ERROR")

    def test_duplicate_index_is_treated_as_omitted(self):
        out = _run("""
return { results: indices.map(function (i) { return { paragraphIndex: i, verdict: 'PASS', feedback: 'ok' }; })
  .concat([{ paragraphIndex: 3, verdict: 'FAIL', feedback: 'contradictory second verdict' }]) };
""")
        paragraphs = _paragraphs(out)
        self.assertEqual([p["outcome"] for p in paragraphs], ["PASS", "PASS", "ERROR", "PASS"])
        self.assertEqual(paragraphs[2]["errorReason"], "auditor batch omitted this paragraph")


class TestNullAuditorErrorsEveryParagraphAndStops(unittest.TestCase):
    """AC4b: agent() -> null for the batched auditor -> every paragraph ERROR
    with the terminal-API-error reason, no rewrite, no second round."""

    def test_null_auditor(self):
        out = _run("return null;")
        paragraphs = _paragraphs(out)
        self.assertEqual([p["paragraphIndex"] for p in paragraphs], [1, 2, 3, 4])
        for p in paragraphs:
            self.assertEqual(p["outcome"], "ERROR")
            self.assertEqual(p["attempts"], 1)
            self.assertIn("terminal API error", p["errorReason"])
        self.assertEqual(len(_labels(out, "audit:")), 1)
        self.assertEqual(len(_labels(out, "rewrite:")), 0)
        self.assertEqual(out["result"]["outcome"], "ERROR")


class TestCapAndRewriteEdgeCases(unittest.TestCase):
    def test_persistent_fail_reaches_needs_review_at_cap(self):
        out = _run(
            """
return { results: indices.map(function (i) {
  return { paragraphIndex: i, verdict: i === 4 ? 'PARTIAL' : 'PASS', feedback: 'x' };
}) };
""",
            "return { paragraphs: indices.map(function (i) { return { paragraphIndex: i, text: 'R' + round }; }) };",
        )
        paragraphs = _paragraphs(out)
        self.assertEqual([p["outcome"] for p in paragraphs], ["PASS", "PASS", "PASS", "NEEDS_REVIEW"])
        self.assertEqual(paragraphs[3]["attempts"], THRESHOLDS["rewriteCycles"]["max"])
        self.assertEqual(paragraphs[3]["lastVerdict"], "PARTIAL")
        # cap rounds of audit, cap-1 rewrites -- never a rewrite after the last audit.
        self.assertEqual(len(_labels(out, "audit:")), THRESHOLDS["rewriteCycles"]["max"])
        self.assertEqual(len(_labels(out, "rewrite:")), THRESHOLDS["rewriteCycles"]["max"] - 1)

    def test_rewrite_missing_a_paragraph_is_a_degraded_retry(self):
        out = _run(
            """
return { results: indices.map(function (i) {
  if (round === 1 && (i === 1 || i === 2)) return { paragraphIndex: i, verdict: 'FAIL', feedback: 'fix' };
  return { paragraphIndex: i, verdict: 'PASS', feedback: 'ok' };
}) };
""",
            "return { paragraphs: [{ paragraphIndex: 1, text: 'New one.' }] };",
        )
        paragraphs = _paragraphs(out)
        self.assertEqual([p["outcome"] for p in paragraphs], ["PASS"] * 4)
        self.assertEqual(paragraphs[0]["text"], "New one.")
        self.assertEqual(paragraphs[1]["text"], "Paragraph two.", "missing rewrite -> re-audited unchanged")
        self.assertTrue(any("degraded retry" in l and "paragraph 2" in l for l in out["calls"]["log"]))
        self.assertEqual(_labels(out, "audit:")[1]["indices"], [1, 2])

    def test_null_rewrite_errors_only_the_failed_paragraphs(self):
        out = _run(PASS_ALL_BUT_P2_IN_ROUND_1, "return null;")
        paragraphs = _paragraphs(out)
        self.assertEqual([p["outcome"] for p in paragraphs], ["PASS", "ERROR", "PASS", "PASS"])
        self.assertIn("rewrite call did not return", paragraphs[1]["errorReason"])
        self.assertEqual(len(_labels(out, "audit:")), 1)


if __name__ == "__main__":
    unittest.main()
