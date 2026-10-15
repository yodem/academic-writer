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
        for key in ("primary", "check"):
            self.assertGreater(block["timeoutMs"][key], 0)
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


if __name__ == "__main__":
    unittest.main()
