"""Structure of the blind library evaluation: schemas, the judge-visible file, module layout and rules."""

import json
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMAS = os.path.join(REPO, "src", "schemas")
EVAL_DIR = os.path.join(REPO, "src", "cli", "src", "library", "eval")
THRESHOLDS = os.path.join(REPO, "src", "thresholds.json")
NAMES = ("plan", "run", "pairs", "judgments", "mapping")
SHA = "a" * 64
TS = "2026-10-16T10:00:00.000Z"

# The keywords src/cli/src/library/jsonschema.ts understands; a schema that uses another one would be checked by
# Python's jsonschema but silently not by the plugin.
SUPPORTED = {
    "$schema", "$ref", "title", "description", "type", "enum", "const", "required", "properties", "additionalProperties",
    "items", "oneOf", "minimum", "maximum", "minLength", "maxLength", "pattern", "definitions",
}


def load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def schema(name):
    return load(os.path.join(SCHEMAS, f"library-eval-{name}.schema.json"))


def validator(name, ref=None):
    try:
        import jsonschema
    except ImportError:
        return None
    root = schema(name)
    jsonschema.Draft7Validator.check_schema(root)
    target = {"$ref": ref, "definitions": root["definitions"]} if ref else root
    return jsonschema.Draft7Validator(target)


def walk(node, path=""):
    """Every dict in a schema with its path, skipping the data under `properties` and `definitions` names."""
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            if key in ("properties", "definitions") and isinstance(value, dict):
                for name, inner in value.items():
                    yield from walk(inner, f"{path}/{key}/{name}")
            elif key in ("items", "oneOf", "additionalProperties"):
                yield from walk(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from walk(item, f"{path}[{index}]")


PLAN = {
    "schema": 1, "eval_id": "ev-20261016-a", "created_at": TS, "article": None, "seed": "s", "routes": ["trove", "pageindex"],
    "shelf": [{"id": "T-A", "title": "ספר א"}],
    "claims": [{
        "id": "c01", "text": "טענה על העיר.", "source_id": "T-A", "source_title": "ספר א", "cited_trove_pages": [3], "cited_printed_page": 1,
        "paragraph_id": "u1_p_1", "auditor_verdict": "PASS", "corrected_page": None,
    }, {
        "id": "c02", "text": "A claim.", "source_id": "T-A", "source_title": "Book A", "cited_trove_pages": [], "cited_printed_page": None,
        "paragraph_id": None, "auditor_verdict": None, "corrected_page": None,
    }],
    "skipped": {"too_short": 0, "no_source": 0, "multi_source": 0, "unresolved": 0, "over_cap": 0},
    "estimate": {"runs": 4, "usd": 0.4},
}
RUN = {
    "schema": 1, "eval_id": "ev-20261016-a", "claim_id": "c01", "route": "pageindex", "engine": "claude", "model": "m", "status": "ok", "attempts": 1,
    "started_at": TS, "answer": {"book": "T-A", "pages": [3, 5], "reason": "r"}, "tool_calls": ["<wrapper> toc --source T-A"], "n_reads": 1, "n_toc": 1,
    "pages_per_read": [2], "over_budget": False, "permission_denials": 0, "wall_ms": 4000, "agent_ms": 3000, "turns": 3, "input_tokens": 500,
    "output_tokens": 20, "cost_usd": 0.05, "returned_chars": 900, "returned_est_tokens": 250, "agent_version": "2.1.0", "error": None,
    "plan_sha256": SHA, "claim_sha256": SHA, "prompt_version": "locate-v2", "model_requested": "m", "fingerprint": SHA, "violations": [], "lookup_errors": [],
}
OPTION = {"book": "T-A", "book_title": "ספר א", "pages": [{"page": 3, "text": "Text. טקסט."}]}
PAIRS = {
    "schema": 1, "eval_id": "ev-20261016-a", "created_at": TS, "mapping_sha256": SHA,
    "pairs": [
        {"pair_id": "p01", "claim": {"id": "c01", "text": "טענה על העיר."}, "auto_same": False, "options": {"A": OPTION, "B": {"book": None, "book_title": None, "pages": []}}},
        {"pair_id": "p02", "claim": {"id": "c02", "text": "A claim."}, "auto_same": True, "options": {"A": OPTION, "B": OPTION}},
    ],
}
JUDGMENTS = {
    "schema": 1, "eval_id": "ev-20261016-a", "pairs_sha256": SHA, "mapping_sha256": SHA,
    "entries": [{"pair_id": "p01", "verdict": "A", "note": "עדיף", "source": "judge", "judged_at": TS, "imported_at": TS},
                {"pair_id": "p02", "verdict": "same", "note": "", "source": "auto", "judged_at": None, "imported_at": TS}],
}
MAPPING = {"schema": 1, "eval_id": "ev-20261016-a", "seed": "s", "nonce": SHA, "plan_sha256": SHA, "runs": [{"claim_id": "c01", "route": "trove", "sha256": SHA}], "pairs": [{"pair_id": "p01", "claim_id": "c01", "A": "trove", "B": "pageindex"}]}
FIXTURES = {"plan": PLAN, "run": RUN, "pairs": PAIRS, "judgments": JUDGMENTS, "mapping": MAPPING}


class TestSchemas(unittest.TestCase):
    def test_every_schema_parses_and_uses_only_supported_keywords(self):
        for name in NAMES:
            root = schema(name)
            self.assertEqual(root["type"], "object", name)
            for path, node in walk(root):
                self.assertLessEqual(set(node) - SUPPORTED, set(), f"{name}{path}")

    def test_every_object_is_closed(self):
        for name in NAMES:
            for path, node in walk(schema(name)):
                if node.get("type") == "object" and "properties" in node:
                    self.assertIs(node.get("additionalProperties"), False, f"{name}{path}")

    def test_enums_and_constants(self):
        self.assertEqual(schema("plan")["properties"]["routes"]["items"]["enum"], ["trove", "pageindex"])
        self.assertEqual(schema("mapping")["properties"]["pairs"]["items"]["properties"]["A"]["enum"], ["trove", "pageindex"])
        self.assertEqual(schema("judgments")["definitions"]["entry"]["properties"]["verdict"]["enum"], ["A", "B", "same", "neither", "skip"])
        self.assertEqual(schema("judgments")["definitions"]["import_item"]["properties"]["verdict"]["enum"], ["A", "B", "same", "neither", "skip"])
        self.assertEqual(schema("judgments")["definitions"]["entry"]["properties"]["note"]["maxLength"], 2000)
        self.assertEqual(schema("run")["properties"]["status"]["enum"], ["ok", "error"])
        self.assertEqual(schema("run")["properties"]["engine"]["enum"], ["claude", "codex"])
        for name in NAMES:
            self.assertEqual(schema(name)["properties"]["schema"], {"const": 1}, name)

    def test_fixtures_validate(self):
        for name, fixture in FIXTURES.items():
            check = validator(name)
            if check is None:
                self.skipTest("jsonschema not installed")
            self.assertEqual(list(check.iter_errors(fixture)), [], name)
        check = validator("judgments", "#/definitions/import")
        for body in ({"judgments": [{"pair_id": "p01", "verdict": "B", "note": "x", "at": TS}]}, {"schema": 1, "eval_id": "e", "judgments": []}):
            self.assertEqual(list(check.iter_errors(body)), [])

    def test_bad_documents_fail(self):
        if validator("plan") is None:
            self.skipTest("jsonschema not installed")
        bad = {
            "plan": [lambda d: d["claims"][0].update(id="x1"), lambda d: d["routes"].append("other"), lambda d: d.update(extra=1)],
            "run": [lambda d: d.update(status="maybe"), lambda d: d.update(fingerprint="x"), lambda d: d.update(violations="no"), lambda d: d.update(input_tokens=-1), lambda d: d["answer"].update(pages=["3"])],
            "pairs": [lambda d: d["pairs"][0].update(route="trove"), lambda d: d.update(mapping_sha256="short"), lambda d: d["pairs"][0]["options"]["A"].update(latency_ms=3),
                      lambda d: d["pairs"][0]["options"].update(C=OPTION), lambda d: d["pairs"][0].update(pair_id="pair-1")],
            "judgments": [lambda d: d["entries"][0].update(verdict="best"), lambda d: d["entries"][0].update(note="x" * 2001), lambda d: d["entries"][0].update(source="robot")],
            "mapping": [lambda d: d["pairs"][0].update(A="gemini"), lambda d: d.update(nonce="1234"), lambda d: d["runs"][0].update(sha256="x"), lambda d: d.pop("plan_sha256")],
        }
        for name, edits in bad.items():
            check = validator(name)
            for edit in edits:
                doc = json.loads(json.dumps(FIXTURES[name]))
                edit(doc)
                self.assertTrue(list(check.iter_errors(doc)), f"{name}: {edit}")
        check = validator("judgments", "#/definitions/import")
        for body in ({"judgments": [{"pair_id": "p01", "verdict": "good"}]}, {"judgments": [{"verdict": "A"}]}, {"rows": []}):
            self.assertTrue(list(check.iter_errors(body)), body)


class TestJudgeVisibleFile(unittest.TestCase):
    ROUTE_WORDS = re.compile(r"trove|pageindex|node|tree", re.IGNORECASE)

    def test_the_pairs_fixture_names_no_library_and_no_tool_vocabulary(self):
        self.assertIsNone(self.ROUTE_WORDS.search(json.dumps(PAIRS, ensure_ascii=False)))

    def test_the_pairs_schema_has_no_field_that_could_tell_the_judge_which_library_answered(self):
        names = set()

        def collect(node):
            if isinstance(node, dict):
                names.update(node.get("properties", {}).keys())
                for value in node.values():
                    collect(value)
            elif isinstance(node, list):
                for item in node:
                    collect(item)

        collect(schema("pairs"))
        for word in ("route", "engine", "model", "latency", "wall", "token", "cost", "reason", "tool", "turn", "seed", "nonce", "usage", "run"):
            self.assertEqual({name for name in names if word in name.lower()}, set(), word)
        self.assertEqual(names, {
            "schema", "eval_id", "created_at", "mapping_sha256", "pairs", "pair_id", "claim", "auto_same", "options", "id", "text", "A", "B",
            "book", "book_title", "pages", "page",
        })

    def test_only_the_sealed_mapping_names_a_library(self):
        for name in ("plan", "run", "mapping"):
            self.assertRegex(json.dumps(schema(name)), r"trove", name)
        self.assertIsNone(self.ROUTE_WORDS.search(json.dumps(schema("pairs"))))
        self.assertIsNone(re.search(r"trove|pageindex", json.dumps(schema("judgments")), re.IGNORECASE))


class TestModules(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(EVAL_DIR, name), encoding="utf-8") as stream:
            return stream.read()

    def test_layout(self):
        for name in ("plan.ts", "runner.ts", "pairs.ts", "seal.ts", "judgments.ts", "unblind.ts", "stats.ts", "cli.ts", "claims.ts", "agent.ts", "files.ts", "limits.ts", "types.ts", "aw.ts"):
            self.assertTrue(os.path.isfile(os.path.join(EVAL_DIR, name)), name)

    def test_entry_point_is_exported(self):
        self.assertRegex(self.read("cli.ts"), r"export async function runEvalCli\(argv: string\[\], io: EvalIo\)")

    def test_strict_typescript_no_any(self):
        for name in sorted(os.listdir(EVAL_DIR)):
            self.assertNotRegex(self.read(name), r":\s*any\b|\bas any\b|<any>|any\[\]", name)

    def test_no_model_call_except_through_claude_or_codex(self):
        for name in sorted(os.listdir(EVAL_DIR)):
            source = self.read(name)
            self.assertNotRegex(source, r"@google/genai|gemini\.ts|openrouter|picloud|PAGEINDEX_API_KEY|cloud", name)

    def test_commands_run_without_a_shell(self):
        for name in sorted(os.listdir(EVAL_DIR)):
            source = self.read(name)
            self.assertNotRegex(source, r"shell\s*:\s*true", name)
            self.assertNotRegex(source, r"import\s*\{[^}]*\bexec(Sync)?\b[^}]*\}\s*from\s*'node:child_process'", name)

    def test_agents_run_in_their_own_process_group_and_are_killed_as_one(self):
        source = self.read("agent.ts")
        self.assertIn("detached", source)
        self.assertIn("process.kill(-child.pid", source)
        self.assertIn("AW_EVAL_RUN_TAG", source)
        self.assertIn("reapTagged", self.read("runner.ts"))

    def test_the_usage_row_is_the_locate_step_and_the_run_id_ends_in_route_and_claim(self):
        runner = self.read("runner.ts")
        self.assertIn("step: 'library.eval.locate'", runner)
        self.assertIn("`${evalId}-${route}-${claimId}`", runner)
        with open(os.path.join(SCHEMAS, "ledger-row.schema.json"), encoding="utf-8") as stream:
            self.assertNotIn("library.eval", stream.read())  # free-text step, no enum to extend

    def test_numbers_come_from_thresholds(self):
        self.assertIn("thresholds.json", self.read("limits.ts"))
        self.assertNotRegex(self.read("limits.ts"), r"\?\?\s*\d")
        block = load(THRESHOLDS)["library"]["eval"]
        for key in ("maxClaims", "minPairs", "maxTurns", "maxBudgetUsdPerRun", "parallel", "locateModel", "expectedUsdPerRun", "maxPagesPerRead", "maxReads", "runTimeoutMs", "minClaimWords", "maxAnswerPages", "perSourceShare"):
            self.assertIn(key, block)
        self.assertRegex(self.read("runner.ts"), r"evalLimits\.maxTurns")
        self.assertRegex(self.read("unblind.ts"), r"evalLimits\.minPairs")

    def test_the_sealed_mapping_is_read_only_by_the_commitment_check_and_unblind(self):
        readers = [name for name in sorted(os.listdir(EVAL_DIR)) if re.search(r"paths\.mapping", self.read(name))]
        self.assertEqual(readers, ["judgments.ts", "pairs.ts"])
        for name in ("runner.ts", "plan.ts", "claims.ts", "agent.ts", "aw.ts"):
            self.assertNotIn("mapping", self.read(name).replace("normalise", ""), name)


if __name__ == "__main__":
    unittest.main()
