"""Every JSON example in the proofread agent prompts must validate against the shared contract.

An agent copies the example in its own prompt. A prompt whose example violates
src/skills/proofread/references/changes-schema.json therefore teaches the agent to emit invalid
output, and nothing downstream would notice until apply-changes.py silently skipped the batch.
Two such defects shipped in wave A/B of 0.7.0 — a top-level "language" key against
additionalProperties:false, and "line": 0 against minimum:1 — both caught by an LLM reviewer.
This test replaces that reviewer with a mechanical gate (TST-02: deterministic over LLM).
"""

import json
import os
import re
import unittest

import jsonschema

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(
    REPO, "src", "skills", "proofread", "references", "changes-schema.json"
)
AGENTS = ("editor", "copyeditor", "proofreader")

FENCE_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)
# Prompt examples use <angle-bracket> placeholders and "a | b | c" enum menus. Substitute a
# schema-legal concrete value so the STRUCTURE is what gets validated, not the placeholder text.
PLACEHOLDER_RE = re.compile(r"^<.*>$", re.DOTALL)


def _load_schema():
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _concretize(node, enum_map, key=None):
    """Replace placeholder strings with a legal value, resolving 'a | b' menus against the schema."""
    if isinstance(node, dict):
        return {k: _concretize(v, enum_map, k) for k, v in node.items()}
    if isinstance(node, list):
        return [_concretize(v, enum_map, key) for v in node]
    if isinstance(node, str):
        enums = enum_map.get(key, ())
        if "|" in node:
            first = node.split("|")[0].strip()
            if not enums or first in enums:
                return first
        if PLACEHOLDER_RE.match(node.strip()):
            return enums[0] if enums else "placeholder"
    return node


class TestPromptExamplesValidate(unittest.TestCase):
    def setUp(self):
        self.schema = _load_schema()
        change_props = self.schema["$defs"]["change"]["properties"]
        self.enums = {
            key: tuple(spec["enum"])
            for key, spec in change_props.items()
            if "enum" in spec
        }
        self.enums.update(
            {
                key: tuple(spec["enum"])
                for key, spec in self.schema["properties"].items()
                if "enum" in spec
            }
        )

    def test_schema_is_itself_valid(self):
        jsonschema.Draft202012Validator.check_schema(self.schema)

    def test_every_agent_json_example_validates(self):
        failures = []
        for name in AGENTS:
            path = os.path.join(REPO, "src", "agents", f"{name}.md")
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            blocks = FENCE_RE.findall(text)
            self.assertTrue(blocks, f"{name}.md declares no ```json example to validate")
            for i, raw in enumerate(blocks):
                try:
                    doc = json.loads(raw)
                except json.JSONDecodeError as exc:
                    failures.append(f"{name}.md block {i}: not JSON ({exc})")
                    continue
                if not isinstance(doc, dict) or "changes" not in doc:
                    continue  # not a changes-contract example
                try:
                    jsonschema.validate(_concretize(doc, self.enums), self.schema)
                except jsonschema.ValidationError as exc:
                    where = "/".join(str(p) for p in exc.absolute_path) or "<root>"
                    failures.append(f"{name}.md block {i} at {where}: {exc.message}")
        self.assertEqual(failures, [], "Prompt JSON examples violate changes-schema.json: " + str(failures))

    def test_no_zero_line_numbers_in_examples(self):
        """line:0 is a contract violation, not 'unknown' — it must not appear in any prompt."""
        offenders = [
            name
            for name in AGENTS
            if re.search(
                r'"line"\s*:\s*0\b',
                open(os.path.join(REPO, "src", "agents", f"{name}.md"), encoding="utf-8").read(),
            )
        ]
        self.assertEqual(offenders, [], f"'line': 0 present in: {offenders}")


if __name__ == "__main__":
    unittest.main()
