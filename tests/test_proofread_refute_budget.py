"""Tests for the refute-budget fan-out cap in src/workflows/proofread.js
(thresholds.proofread.refuteBudgetPerChunk).

Design: docs/audits/2026-09-04-determinism-audit.md sections 2, 3.4, 3.5.

Before this cap existed, `proofread.js:297` (language stage) and the
mechanical-stage twin looped over every finding a chunk returned and called
refuteChange once per finding, each spawning up to `refuteVotes` lens
agents, with nothing anywhere bounding how many findings a chunk could
return. A chunk returning 50 findings cost 150 verify calls. This file
proves the fix actually bounds the volume of refute calls made -- by
counting real calls through a stub, not by reading the source -- and that
the surplus beyond the budget is carried forward (never dropped), spent
highest-meaningRisk-first, and that a missing budget degrades to today's
unbounded behaviour with a visible log line rather than crashing or
silently capping anyway.

Approach (TST-09: no test may depend on an ambient binary being on PATH
without a stub -- the "binary" the real workflow needs is the Workflow
tool's own runtime, which does not exist as an installable binary at all;
this harness supplies a stub `agent`/`log`/`phase`/`parallel`/`pipeline`
in its place, the same shape tests/test_proofread_workflow.py's docstring
describes those primitives as): the ACTUAL current src/workflows/proofread.js
source is read, `export const meta` is rewritten to a bare `const meta`
(the only rewrite -- 'export' is a syntax error outside an ES module, which
this CommonJS harness deliberately is not), and the unmodified script body
is wrapped in an async IIFE so its top-level `return` becomes the IIFE's
return value. Stub globals are injected as free variables the IIFE closes
over, exactly like the real Workflow tool injects `args`/`agent`/`log`/
`phase`/`parallel`/`pipeline` at runtime. Every `agent()` call is logged by
label so the test can count exactly how many refute calls were made, not
merely infer it from the code.

Only the language stage is exercised (args.stages = ['language']) to keep
the stub surface small; the mechanical stage wires the identical
splitByRefuteBudget() helper (src/workflows/proofread.js) at its own call
site, verified separately by reading the source in
test_proofread_workflow.py-style structural tests is NOT done here on
purpose -- this file's job is to prove the language-stage behaviour by
actual execution, per the spec's "assert it by counting, not by
inspection."
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(REPO, "src", "workflows", "proofread.js")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _change(before, meaning_risk, line):
    return {
        "line": line,
        "type": "word",
        "level": "word",
        "before": before,
        "after": before + "-fixed",
        "rationale": "stub finding for " + before,
        "meaningRisk": meaning_risk,
    }


def _build_harness(src_text, args_obj, find_responses, mech_find_responses=None):
    """Wraps the real proofread.js body in a CommonJS async IIFE with stub
    `agent`/`log`/`phase`/`parallel`/`pipeline` globals injected, and prints
    {"result": <the workflow's return value>, "calls": {"agent": [...labels...], "log": [...msgs...]}}
    as its only stdout line.

    `find_responses` stubs the language-find stage, keyed by chunk id (one
    call per chunk, no rounds). `mech_find_responses` stubs the mechanical-
    find stage, keyed by the EXACT label ('mechanical-find:<chunkId>:round<N>')
    since that stage runs once per chunk PER ROUND -- the round number is part
    of the label, so a test controlling multi-round behaviour must address
    each round's response individually."""
    body = re.sub(r"^export const meta", "const meta", src_text, count=1, flags=re.MULTILINE)
    assert "export const meta" not in body, "failed to strip the ESM export keyword"

    harness = (
        "const __calls = { agent: [], log: [] };\n"
        "const args = " + json.dumps(args_obj) + ";\n"
        "const FIND_RESPONSES = " + json.dumps(find_responses) + ";\n"
        "const MECH_FIND_RESPONSES = " + json.dumps(mech_find_responses or {}) + ";\n"
        "async function agent(prompt, opts) {\n"
        "  const label = (opts && opts.label) || '';\n"
        "  __calls.agent.push(label);\n"
        "  if (label.indexOf('language-find:') === 0) {\n"
        "    const chunkId = label.slice('language-find:'.length);\n"
        "    if (Object.prototype.hasOwnProperty.call(FIND_RESPONSES, chunkId)) return FIND_RESPONSES[chunkId];\n"
        "    return { stage: 'language', chunk_id: chunkId, changes: [] };\n"
        "  }\n"
        "  if (label.indexOf('mechanical-find:') === 0) {\n"
        "    if (Object.prototype.hasOwnProperty.call(MECH_FIND_RESPONSES, label)) return MECH_FIND_RESPONSES[label];\n"
        "    return { stage: 'mechanical', changes: [] };\n"
        "  }\n"
        "  if (label.indexOf('refute:') === 0) {\n"
        "    return { outcome: 'uphold', reason: 'stub-uphold' };\n"
        "  }\n"
        "  if (label.indexOf('mechanical-verify:') === 0) {\n"
        "    return { outcome: 'uphold', reason: 'stub-uphold' };\n"
        "  }\n"
        "  return { stage: 'language', changes: [] };\n"
        "}\n"
        "function log(msg) { __calls.log.push(String(msg)); }\n"
        "function phase(name) {}\n"
        "async function parallel(thunks) {\n"
        "  return Promise.all(thunks.map(function (fn) { return fn(); }));\n"
        "}\n"
        "async function pipeline(items, stage1, stage2) {\n"
        "  return Promise.all(items.map(async function (item) {\n"
        "    const r1 = await stage1(item);\n"
        "    return await stage2(r1);\n"
        "  }));\n"
        "}\n"
        "(async () => {\n"
        + body +
        "\n})().then(function (result) {\n"
        "  process.stdout.write(JSON.stringify({ result: result, calls: __calls }));\n"
        "}).catch(function (err) {\n"
        "  process.stderr.write('HARNESS_ERROR: ' + (err && err.stack ? err.stack : String(err)));\n"
        "  process.exitCode = 1;\n"
        "});\n"
    )
    return harness


def _run_workflow(args_obj, find_responses, mech_find_responses=None):
    src_text = _read(WORKFLOW)
    harness = _build_harness(src_text, args_obj, find_responses, mech_find_responses)
    tmp_dir = tempfile.mkdtemp(prefix="proofread-refute-budget-")
    try:
        harness_path = os.path.join(tmp_dir, "harness.js")
        with open(harness_path, "w", encoding="utf-8") as fh:
            fh.write(harness)
        proc = subprocess.run(
            ["node", harness_path],
            cwd=tmp_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            raise AssertionError(
                "harness run failed (exit={}):\nstdout={}\nstderr={}".format(
                    proc.returncode, proc.stdout, proc.stderr
                )
            )
        return json.loads(proc.stdout)
    finally:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)


def _refute_calls(calls):
    return [label for label in calls["agent"] if label.startswith("refute:")]


def _find_change(changes, before):
    for c in changes:
        if c.get("before") == before:
            return c
    raise AssertionError("no change with before=%r in %r" % (before, changes))


BASE_THRESHOLDS = {
    "chunkWords": 1200,
    "maxPasses": 3,
    "dryRounds": 2,
    "concurrencyCap": 5,
    "refuteVotes": 3,
    "refuteMajority": 2,
}

CHUNK = [{"id": "c1", "text": "irrelevant stub chunk text", "startLine": 1, "endLine": 5}]


class TestRefuteBudgetSurplusCarriedNotDropped(unittest.TestCase):
    """chunk with refuteBudgetPerChunk + 1 findings -> the surplus is present
    in the output carrying skipReason: 'refute-budget-exhausted', and is NOT
    missing."""

    def test_surplus_present_with_skip_reason(self):
        thresholds = dict(BASE_THRESHOLDS, refuteBudgetPerChunk=3)
        changes = [
            _change("B1", "low", 1),
            _change("B2", "high", 2),
            _change("B3", "medium", 3),
            _change("B4", "low", 4),
        ]
        args_obj = {
            "language": "he",
            "thresholds": thresholds,
            "chunks": CHUNK,
            "stages": ["language"],
        }
        find_responses = {"c1": {"stage": "language", "chunk_id": "c1", "changes": changes}}
        out = _run_workflow(args_obj, find_responses)
        language_changes = out["result"]["languageChanges"]

        # Nothing is dropped: all 4 findings still appear in the output.
        self.assertEqual(len(language_changes), 4)

        # Budget=3, spend highest-meaningRisk first: B2(high), B3(medium),
        # B1(low, earlier index) get verified; B4(low, later index) is the
        # surplus and must carry the budget-exhaustion skip reason.
        surplus = _find_change(language_changes, "B4")
        self.assertEqual(surplus.get("skipReason"), "refute-budget-exhausted")
        self.assertEqual(surplus.get("applied"), False)

        for before in ("B1", "B2", "B3"):
            verified = _find_change(language_changes, before)
            self.assertNotEqual(
                verified.get("skipReason"),
                "refute-budget-exhausted",
                "%s was inside the budget and should have been refute-verified" % before,
            )

        # The gate ledger surfaces the exhaustion count (design section 3.4:
        # "Add the outcome to the workflow's returned gates array").
        language_gate = next(g for g in out["result"]["gates"] if g["stage"] == "language")
        self.assertIn("refute-budget-exhausted", language_gate["outcome"])
        self.assertIn("1 carried unverified", language_gate["outcome"])


class TestRefuteBudgetBoundsCallVolume(unittest.TestCase):
    """The number of refute calls actually made is <= budget * refuteVotes --
    asserted by counting real stub invocations, not by reading the source."""

    def test_refute_call_count_bounded(self):
        budget = 3
        refute_votes = 3
        thresholds = dict(BASE_THRESHOLDS, refuteVotes=refute_votes, refuteBudgetPerChunk=budget)
        # 10 findings, well beyond the budget -- pre-fix this would cost
        # 10 * refuteVotes = 30 refute calls.
        changes = [_change("F%d" % i, "low", i + 1) for i in range(10)]
        args_obj = {
            "language": "he",
            "thresholds": thresholds,
            "chunks": CHUNK,
            "stages": ["language"],
        }
        find_responses = {"c1": {"stage": "language", "chunk_id": "c1", "changes": changes}}
        out = _run_workflow(args_obj, find_responses)

        refute_calls = _refute_calls(out["calls"])
        self.assertLessEqual(len(refute_calls), budget * refute_votes)
        # Exact, not just bounded: budget items are verified, no more.
        self.assertEqual(len(refute_calls), budget * refute_votes)
        self.assertLess(len(refute_calls), len(changes) * refute_votes)

        language_changes = out["result"]["languageChanges"]
        self.assertEqual(len(language_changes), 10, "all 10 findings must still be present")
        exhausted = [c for c in language_changes if c.get("skipReason") == "refute-budget-exhausted"]
        self.assertEqual(len(exhausted), 10 - budget)


class TestRefuteBudgetSpendsHighestMeaningRiskFirst(unittest.TestCase):
    """Budget is spent highest-meaningRisk first, so exhaustion degrades
    gracefully rather than arbitrarily."""

    def test_high_and_medium_survive_low_is_exhausted(self):
        thresholds = dict(BASE_THRESHOLDS, refuteBudgetPerChunk=2)
        # Order deliberately scrambled relative to risk so a naive
        # first-N-in-list implementation would fail this test.
        changes = [
            _change("A", "low", 1),
            _change("B", "medium", 2),
            _change("C", "high", 3),
            _change("D", "low", 4),
            _change("E", "medium", 5),
        ]
        args_obj = {
            "language": "he",
            "thresholds": thresholds,
            "chunks": CHUNK,
            "stages": ["language"],
        }
        find_responses = {"c1": {"stage": "language", "chunk_id": "c1", "changes": changes}}
        out = _run_workflow(args_obj, find_responses)
        language_changes = out["result"]["languageChanges"]
        self.assertEqual(len(language_changes), 5, "nothing dropped")

        # Budget=2: the single 'high' and the earliest 'medium' win the
        # two slots; the later 'medium' (E) and both 'low' findings are
        # exhausted even though E outranks the two lows.
        verified_before = {"C", "B"}
        exhausted_before = {"E", "A", "D"}

        for before in verified_before:
            c = _find_change(language_changes, before)
            self.assertNotEqual(c.get("skipReason"), "refute-budget-exhausted", before)

        for before in exhausted_before:
            c = _find_change(language_changes, before)
            self.assertEqual(c.get("skipReason"), "refute-budget-exhausted", before)
            self.assertEqual(c.get("applied"), False, before)

        refute_calls = _refute_calls(out["calls"])
        self.assertEqual(len(refute_calls), 2 * BASE_THRESHOLDS["refuteVotes"])


class TestRefuteBudgetAbsentDegradesToUnbounded(unittest.TestCase):
    """refuteBudgetPerChunk absent from thresholds -> unbounded behaviour is
    preserved (today's pre-budget shape), and the log says so -- the missing
    cap must be visible, never silent."""

    def test_missing_budget_is_unbounded_and_logged(self):
        thresholds = dict(BASE_THRESHOLDS)  # deliberately no refuteBudgetPerChunk key
        self.assertNotIn("refuteBudgetPerChunk", thresholds)
        changes = [_change("U%d" % i, "low", i + 1) for i in range(5)]
        args_obj = {
            "language": "he",
            "thresholds": thresholds,
            "chunks": CHUNK,
            "stages": ["language"],
        }
        find_responses = {"c1": {"stage": "language", "chunk_id": "c1", "changes": changes}}
        out = _run_workflow(args_obj, find_responses)

        refute_calls = _refute_calls(out["calls"])
        # Unbounded: every finding gets the full refuteVotes fan-out.
        self.assertEqual(len(refute_calls), len(changes) * BASE_THRESHOLDS["refuteVotes"])

        language_changes = out["result"]["languageChanges"]
        self.assertEqual(len(language_changes), 5)
        for c in language_changes:
            self.assertNotEqual(c.get("skipReason"), "refute-budget-exhausted")

        # The missing cap must be visible in the log, not silent.
        joined_log = "\n".join(out["calls"]["log"]).lower()
        self.assertIn("refutebudgetperchunk", joined_log)
        self.assertIn("unbounded", joined_log)

        language_gate = next(g for g in out["result"]["gates"] if g["stage"] == "language")
        self.assertIn("unbounded", language_gate["outcome"].lower())


class TestMechanicalRefuteBudgetIsCumulativePerChunk(unittest.TestCase):
    """The mechanical stage runs a residual pass over the SAME chunks for
    up to maxPasses rounds. refuteBudgetPerChunk must bound the TOTAL number
    of changes sent for refute-verification for a given chunk across ALL
    rounds combined -- not reset the budget on every round -- otherwise a
    chunk-with-cap=budget still costs budget*maxPasses verify calls, which is
    exactly the unbounded-fan-out shape this cap exists to close (see
    thresholds.json's proofread._comment: "refuteBudgetPerChunk caps how many
    changes per chunk are sent for refute-verification AT ALL").

    Round 1 finds 3 changes for budget=2: the 2 highest-meaningRisk changes
    are verified, the 1 remaining is exhausted. Round 2 finds 2 MORE (fresh,
    never-seen-before) changes for the same chunk: since the budget is
    already fully spent from round 1, ALL of round 2's changes must be
    exhausted too -- zero further refute calls for this chunk."""

    def test_budget_persists_across_mechanical_rounds(self):
        thresholds = dict(BASE_THRESHOLDS, refuteVotes=1, refuteMajority=1, refuteBudgetPerChunk=2,
                           maxPasses=2, dryRounds=5)
        args_obj = {
            "language": "he",
            "thresholds": thresholds,
            "chunks": CHUNK,
            "stages": ["mechanical"],
        }
        round1 = {
            "stage": "mechanical",
            "chunk_id": "c1",
            "changes": [
                _change("M1", "high", 1),
                _change("M2", "medium", 2),
                _change("M3", "low", 3),
            ],
        }
        round2 = {
            "stage": "mechanical",
            "chunk_id": "c1",
            "changes": [
                _change("M4", "high", 4),
                _change("M5", "high", 5),
            ],
        }
        # NOTE: proofread.js labels the find-stage call
        # 'mechanical-find:<id>:round' + (mechanicalRounds + 1), and
        # mechanicalRounds is already incremented to 1 before the first
        # call -- so the FIRST actual round's label reads ':round2', the
        # second ':round3'. This is a pre-existing label/prompt-text
        # off-by-one in proofread.js, out of scope for this change; the
        # stub keys below match the workflow's actual (if confusingly
        # numbered) label strings, not the logical round number.
        mech_find_responses = {
            "mechanical-find:c1:round2": round1,
            "mechanical-find:c1:round3": round2,
        }
        out = _run_workflow(args_obj, {}, mech_find_responses)

        mechanical_changes = out["result"]["mechanicalChanges"]
        # Nothing dropped across either round: all 5 findings present.
        self.assertEqual(len(mechanical_changes), 5)

        for before in ("M1", "M2"):
            c = _find_change(mechanical_changes, before)
            self.assertNotEqual(c.get("skipReason"), "refute-budget-exhausted", before)

        # M3 lost round 1's tie-break (lowest meaningRisk); M4 and M5 arrive
        # in round 2 with the budget already fully spent by round 1.
        for before in ("M3", "M4", "M5"):
            c = _find_change(mechanical_changes, before)
            self.assertEqual(c.get("skipReason"), "refute-budget-exhausted", before)
            self.assertEqual(c.get("applied"), False, before)

        verify_calls = [label for label in out["calls"]["agent"] if label.startswith("mechanical-verify:")]
        budget = thresholds["refuteBudgetPerChunk"]
        votes = thresholds["refuteVotes"]
        # Exactly budget*votes calls total across BOTH rounds combined --
        # not budget*votes*maxPasses, which is what a per-round-reset budget
        # would cost.
        self.assertEqual(len(verify_calls), budget * votes)
        self.assertLessEqual(len(verify_calls), budget * votes)


if __name__ == "__main__":
    unittest.main()
