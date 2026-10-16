"""Structure of the library-route core: config schema, thresholds block, module layout."""

import json
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(REPO, "src", "schemas", "library-config.schema.json")
THRESHOLDS = os.path.join(REPO, "src", "thresholds.json")
LIBRARY_DIR = os.path.join(REPO, "src", "cli", "src", "library")
MAIN = os.path.join(REPO, "src", "cli", "src", "main.ts")
ROW_SCHEMA = os.path.join(REPO, "src", "schemas", "retrieval-row.schema.json")


def load(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def validator():
    try:
        import jsonschema
    except ImportError:  # the hand checks below still run
        return None
    schema = load(SCHEMA)
    jsonschema.Draft7Validator.check_schema(schema)
    return jsonschema.Draft7Validator(schema)


class TestLibraryConfigSchema(unittest.TestCase):
    def test_schema_parses_and_pins_the_route_words(self):
        schema = load(SCHEMA)
        self.assertEqual(schema["required"], ["route"])
        self.assertEqual(schema["properties"]["route"]["enum"], ["trove", "pageindex", "both"])
        self.assertEqual(schema["properties"]["primary"]["enum"], ["trove", "pageindex"])

    def test_every_object_level_is_closed(self):
        schema = load(SCHEMA)
        self.assertIs(schema["additionalProperties"], False)
        for name in ("pageindex", "shadow"):
            self.assertIs(schema["properties"][name]["additionalProperties"], False, name)

    def test_valid_configs_pass(self):
        check = validator()
        if check is None:
            self.skipTest("jsonschema not installed")
        for config in (
            {"route": "trove"},
            {"route": "both", "primary": "pageindex"},
            {"route": "pageindex", "pageindex": {"command": "pilib", "shelf": ".academic-helper/shelf.json"}},
            {"route": "both", "pageindex": {"command": ["example-wrapper", "--flag"]}, "shadow": {"enabled": False}},
        ):
            self.assertEqual(list(check.iter_errors(config)), [], config)

    def test_invalid_configs_fail(self):
        check = validator()
        if check is None:
            self.skipTest("jsonschema not installed")
        for config in (
            {},
            {"route": "other"},
            {"route": "both", "primary": "both"},
            {"route": "both", "extra": True},
            {"route": "both", "pageindex": {"host": "example-host"}},
            {"route": "both", "pageindex": {"command": []}},
            {"route": "both", "shadow": {"enabled": "yes"}},
        ):
            self.assertTrue(list(check.iter_errors(config)), config)

    def test_schema_has_no_machine_specific_defaults(self):
        text = open(SCHEMA, encoding="utf-8").read()
        self.assertNotRegex(text, r"/Users/|/home/|ssh |@")


class TestLibraryThresholds(unittest.TestCase):
    def test_block_has_positive_integers_and_no_inline_copies(self):
        block = load(THRESHOLDS)["library"]
        for key in ("maxBufferBytes", "maxRequestPages"):
            self.assertIsInstance(block[key], int)
            self.assertGreater(block[key], 0)
        for key in ("primary", "readAll", "check"):
            self.assertGreater(block["timeoutMs"][key], 0)
        self.assertGreater(block["timeoutMs"]["readAll"], block["timeoutMs"]["primary"])
        for key in ("readChunkPages", "chunkConcurrency", "metaScanMax", "metaScanConcurrency"):
            self.assertGreater(block["pageindex"][key], 0)

    def test_source_reads_numbers_from_thresholds(self):
        for name in ("backends.ts", "pages.ts", "adapter.ts"):
            source = open(os.path.join(LIBRARY_DIR, name), encoding="utf-8").read()
            self.assertIn("thresholds.json", source, name)


class TestLibraryModules(unittest.TestCase):
    def test_layout(self):
        for name in ("adapter.ts", "backends.ts", "cli.ts", "config.ts", "exec.ts", "pages.ts", "registry.ts", "types.ts"):
            self.assertTrue(os.path.isfile(os.path.join(LIBRARY_DIR, name)), name)

    def test_strict_typescript_no_any(self):
        for name in sorted(os.listdir(LIBRARY_DIR)):
            source = open(os.path.join(LIBRARY_DIR, name), encoding="utf-8").read()
            self.assertNotRegex(source, r":\s*any\b|\bas any\b|<any>|any\[\]", name)

    def test_commands_run_without_a_shell(self):
        source = open(os.path.join(LIBRARY_DIR, "exec.ts"), encoding="utf-8").read()
        self.assertNotRegex(source, r"shell\s*:\s*true|\bexec\(")

    def test_main_dispatches_library_once(self):
        source = open(MAIN, encoding="utf-8").read()
        self.assertEqual(len(re.findall(r"command === 'library'", source)), 1)
        self.assertIn("runLibraryCli", source)


TS = "2026-10-15T10:00:00.000Z"
CALL = {
    "route": "trove", "ok": True, "route_pages": "2", "latency_ms": 5, "bytes": 10, "chars": 10,
    "text_sha": "0123456789abcdef", "error": None, "error_code": None,
}
LOOKUP = {
    "row_type": "lookup", "schema": 1, "ts": TS, "lookup_id": "lk_1", "run_id": None, "claim_id": "P1", "op": "read",
    "source_id": "SRC", "mode": "both", "route_primary": "trove", "book_by_route": {"trove": "SRC", "pageindex": None},
    "request": {"printed": "3", "trove_pages": "4"}, "primary": CALL, "shadow_status": "pending",
}
SHADOW = {
    "row_type": "shadow", "schema": 1, "ts": TS, "lookup_id": "lk_1", "run_id": None, "route": "pageindex", "ok": True,
    "book": "lib", "route_pages": "4", "latency_ms": 90, "bytes": 10, "chars": 10, "text_sha": "0123456789abcdef",
    "error": None, "error_code": None, "timed_out": False,
    "agree": {"rate": 1.0, "compared": 1, "agreed": 1, "pages": [{"page": 4, "jaccard": 0.9, "agree": True}]},
}
VERDICT = {
    "row_type": "verdict", "schema": 1, "verdict_at": "1760526000000000001", "pid": 4242, "nonce": "0123456789abcdef", "ts": TS, "lookup_id": "lk_1", "run_id": None, "paragraph_id": "P1",
    "verdict": "PASS", "corrected_page": None, "shadow_supports": True, "shadow_supports_reason": "covered",
    "primary_route": "trove", "mode": "both",
}


def row_validator():
    try:
        import jsonschema
    except ImportError:
        return None
    schema = load(ROW_SCHEMA)
    jsonschema.Draft7Validator.check_schema(schema)
    return jsonschema.Draft7Validator(schema)


class TestRetrievalRowSchema(unittest.TestCase):
    def test_schema_has_the_three_row_types_and_closed_objects(self):
        schema = load(ROW_SCHEMA)
        self.assertEqual(len(schema["oneOf"]), 3)
        for name in ("lookup", "shadow", "verdict"):
            definition = schema["definitions"][name]
            self.assertIs(definition["additionalProperties"], False, name)
            self.assertEqual(definition["properties"]["row_type"]["const"], name)
            self.assertEqual(definition["properties"]["schema"]["const"], 1)
        self.assertEqual(schema["definitions"]["verdict"]["properties"]["verdict"]["enum"], ["PASS", "FAIL"])
        self.assertEqual(
            schema["definitions"]["verdict"]["properties"]["shadow_supports_reason"]["enum"],
            ["covered", "not_covered", "no_quote", "shadow_missing", "shadow_pending"],
        )
        self.assertEqual(schema["definitions"]["lookup"]["properties"]["op"]["enum"], ["list", "toc", "read", "get"])

    def test_valid_rows_pass(self):
        check = row_validator()
        if check is None:
            self.skipTest("jsonschema not installed")
        for row in (
            LOOKUP,
            {**LOOKUP, "shadow_status": "skipped:busy", "op": "toc", "source_id": None},
            {**LOOKUP, "primary": {**CALL, "ok": False, "text_sha": None, "route_pages": None, "error": "boom", "error_code": "exit"}},
            SHADOW,
            {**SHADOW, "ok": False, "agree": None, "timed_out": True, "error": "slow", "error_code": "timeout", "text_sha": None},
            VERDICT,
            {**VERDICT, "verdict": "FAIL", "corrected_page": 7, "shadow_supports": None, "shadow_supports_reason": "shadow_pending", "primary_route": None, "mode": None, "settled": True},
        ):
            self.assertEqual(list(check.iter_errors(row)), [], row)

    def test_invalid_rows_fail(self):
        check = row_validator()
        if check is None:
            self.skipTest("jsonschema not installed")
        for row in (
            {},
            {**LOOKUP, "extra": 1},
            {**LOOKUP, "op": "write"},
            {**LOOKUP, "mode": "neither"},
            {**LOOKUP, "shadow_status": "skipped:Bad Reason"},
            {**LOOKUP, "primary": {**CALL, "latency_ms": -1}},
            {**LOOKUP, "primary": {**CALL, "text_sha": "xyz"}},
            {**SHADOW, "agree": {"rate": 2, "compared": 1, "agreed": 1, "pages": []}},
            {**SHADOW, "timed_out": "no"},
            {**VERDICT, "verdict": "PARTIAL"},
            {**VERDICT, "shadow_supports_reason": "maybe"},
            {**VERDICT, "corrected_page": 0},
            {**VERDICT, "schema": 2},
            {**VERDICT, "verdict_at": "soon"},
            {**VERDICT, "pid": 0},
            {**VERDICT, "nonce": "x"},
            {k: v for k, v in VERDICT.items() if k != "verdict_at"},
            {**VERDICT, "seq": 1},
        ):
            self.assertTrue(list(check.iter_errors(row)), row)

    def test_token_estimate_fields_are_optional_so_old_rows_stay_valid(self):
        schema = load(ROW_SCHEMA)
        for name, holder in (("lookup", schema["definitions"]["routeCall"]), ("shadow", schema["definitions"]["shadow"])):
            self.assertNotIn("est_tokens", holder["required"], name)
            self.assertNotIn("tokens_basis", holder["required"], name)
            self.assertIn("est_tokens", holder["properties"], name)
            if name == "lookup":
                self.assertNotIn("pages_returned", holder["required"])
                self.assertEqual(schema["definitions"]["pagesReturned"]["minimum"], 0)
            self.assertIn("tokens_basis", holder["properties"], name)
        self.assertEqual(schema["definitions"]["tokensBasis"]["enum"], ["estimate"])
        self.assertEqual(schema["definitions"]["estTokens"]["minimum"], 0)
        self.assertEqual(schema["definitions"]["lookup"]["properties"]["schema"]["const"], 1)

    def test_rows_with_and_without_token_estimates(self):
        check = row_validator()
        if check is None:
            self.skipTest("jsonschema not installed")
        estimated = {**CALL, "est_tokens": 120, "tokens_basis": "estimate"}
        for row in (
            LOOKUP,
            {**LOOKUP, "primary": estimated},
            {**LOOKUP, "primary": {**CALL, "est_tokens": 0}},
            {**SHADOW, "est_tokens": 7, "tokens_basis": "estimate"},
            SHADOW,
        ):
            self.assertEqual(list(check.iter_errors(row)), [], row)
        for row in (
            {**LOOKUP, "primary": {**CALL, "est_tokens": -1}},
            {**LOOKUP, "primary": {**CALL, "est_tokens": 1.5}},
            {**LOOKUP, "primary": {**CALL, "est_tokens": "12"}},
            {**LOOKUP, "primary": {**CALL, "tokens_basis": "exact"}},
            {**LOOKUP, "est_tokens": 5},
            {**SHADOW, "tokens_basis": "counted"},
            {**VERDICT, "est_tokens": 5},
        ):
            self.assertTrue(list(check.iter_errors(row)), row)

    def test_rows_carry_metadata_only(self):
        text = open(ROW_SCHEMA, encoding="utf-8").read()
        for forbidden in ('"text"', '"quote"', '"content"'):
            self.assertNotIn(forbidden, text)
        self.assertNotRegex(text, r"/Users/|/home/|ssh |@")


class TestRetrievalThresholds(unittest.TestCase):
    def test_shadow_ledger_and_report_numbers_are_in_thresholds(self):
        block = load(THRESHOLDS)["library"]
        for key in ("shadow", "verdictSettle"):
            self.assertGreater(block["timeoutMs"][key], 0)
        self.assertEqual(block["shadow"]["ops"], ["list", "toc", "read"])
        for key in ("maxConcurrent", "readAllMaxPages", "lockStaleMs", "reapGraceMs", "pollMs"):
            self.assertGreater(block["shadow"][key], 0)
        self.assertGreater(block["spool"]["maxBytes"], 0)
        self.assertGreater(block["spool"]["ttlHours"], 0)
        for key in ("maxRowBytes", "maxErrorChars", "maxAgreePages"):
            self.assertGreater(block["ledger"][key], 0)
        for value in (block["agree"]["jaccardMin"], block["supports"]["tokenCoverageMin"]):
            self.assertTrue(0 < value <= 1)
        self.assertGreater(block["supports"]["minQuoteTokens"], 0)
        self.assertGreater(block["report"]["minLookups"], 0)

    def test_modules_read_numbers_from_thresholds(self):
        for name in ("shadow.ts", "ledger.ts", "verdict.ts", "report.ts"):
            source = open(os.path.join(LIBRARY_DIR, name), encoding="utf-8").read()
            self.assertIn("thresholds.json", source, name)
            self.assertNotRegex(source, r"jaccardMin\s*=\s*[0-9]|tokenCoverageMin\s*=\s*[0-9]", name)


class TestTokenEstimateAndForcedRoute(unittest.TestCase):
    def test_ratios_are_in_thresholds_and_hebrew_packs_tighter(self):
        block = load(THRESHOLDS)["library"]["tokens"]
        self.assertGreater(block["hebrewCharsPerToken"], 0)
        self.assertGreater(block["otherCharsPerToken"], block["hebrewCharsPerToken"])
        source = open(os.path.join(LIBRARY_DIR, "ledger.ts"), encoding="utf-8").read()
        self.assertIn("limits.tokens.hebrewCharsPerToken", source)
        self.assertIn("limits.tokens.otherCharsPerToken", source)
        self.assertNotRegex(source, r"CharsPerToken\s*=\s*[0-9]")

    def test_the_estimate_is_labelled_an_estimate_everywhere_it_is_written_or_shown(self):
        for name in ("ledger.ts", "report.ts"):
            source = open(os.path.join(LIBRARY_DIR, name), encoding="utf-8").read()
            self.assertIn("estimate", source, name)
        report = open(os.path.join(LIBRARY_DIR, "report.ts"), encoding="utf-8").read()
        self.assertIn("token figures are estimates", report)
        self.assertNotRegex(report, r"openrouter|@google/genai|anthropic|gemini", "the report calls no model")

    def test_forced_route_is_read_in_the_adapter_only(self):
        adapter = open(os.path.join(LIBRARY_DIR, "adapter.ts"), encoding="utf-8").read()
        self.assertEqual(adapter.count("'AW_LIBRARY_ROUTE'"), 1)
        self.assertIn("forced: this.forced", adapter)
        config = open(os.path.join(LIBRARY_DIR, "config.ts"), encoding="utf-8").read()
        self.assertNotIn("AW_LIBRARY_ROUTE", config)

    def test_report_reads_the_usage_ledger_steps_by_name(self):
        report = open(os.path.join(LIBRARY_DIR, "report.ts"), encoding="utf-8").read()
        self.assertIn("'library.eval.locate'", report)
        self.assertIn("'library.index'", report)
        self.assertIn("ledger-row.schema.json", report)
        self.assertTrue(os.path.isfile(os.path.join(REPO, "src", "schemas", "ledger-row.schema.json")))


class TestShadowModules(unittest.TestCase):
    def test_layout(self):
        for name in ("shadow.ts", "ledger.ts", "verdict.ts", "report.ts", "textmatch.ts", "jsonschema.ts"):
            self.assertTrue(os.path.isfile(os.path.join(LIBRARY_DIR, name)), name)

    def test_the_worker_is_detached_and_never_awaited(self):
        source = open(os.path.join(LIBRARY_DIR, "shadow.ts"), encoding="utf-8").read()
        self.assertRegex(source, r"detached:\s*true")
        self.assertIn("child.unref()", source)
        self.assertNotRegex(source, r"await\s+(?:new Promise[^;]*)?child")
        self.assertIn("'inline'", source)

    def test_verdicts_use_no_model(self):
        for name in ("verdict.ts", "textmatch.ts", "shadow.ts"):
            source = open(os.path.join(LIBRARY_DIR, name), encoding="utf-8").read()
            self.assertNotRegex(source, r"openrouter|@google/genai|anthropic|gemini", name)

    def test_worker_entry_override_is_test_only(self):
        source = open(os.path.join(LIBRARY_DIR, "shadow.ts"), encoding="utf-8").read()
        self.assertIn("NODE_TEST_CONTEXT", source)
        self.assertEqual(source.count("AW_LIBRARY_WORKER_ENTRY"), 2)  # the comment and the one read in workerEntry

    def test_the_ledger_has_no_lock_and_no_counter(self):
        for name in ("ledger.ts", "verdict.ts", "report.ts", "cli.ts"):
            source = open(os.path.join(LIBRARY_DIR, name), encoding="utf-8").read()
            self.assertNotRegex(source, r"withLedgerLock|verdict\.lock|\bseq\b", name)
        self.assertIn("compareVerdictKeys", open(os.path.join(LIBRARY_DIR, "report.ts"), encoding="utf-8").read())

    def test_ledger_never_creates_the_project_folder(self):
        source = open(os.path.join(LIBRARY_DIR, "ledger.ts"), encoding="utf-8").read()
        self.assertIn("hasProjectFolder", source)
        self.assertNotRegex(source, r"mkdir\([^)]*\.academic-helper'\)")


if __name__ == "__main__":
    unittest.main()
