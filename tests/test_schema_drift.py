"""Schema-drift test: the inline CHANGES_SCHEMA/CHANGE_ITEM_SCHEMA duplicate in
src/workflows/proofread.js vs the canonical on-disk contract at
src/skills/proofread/references/changes-schema.json.

Design: docs/audits/2026-09-04-determinism-audit.md sections 1 and 3.5.

proofread.js:14-18/86-88 states, by its own header comment, that the script
"cannot Read changes-schema.json off disk ... by convention", so the shape
it hands to `agent(..., { schema: ... })` is an INLINE DUPLICATE of the
canonical JSON Schema file, "kept in sync ... by convention" -- i.e. by
nothing at all. Two copies of one contract, free to drift silently. This
test makes that drift detectable: it extracts the REAL JS object literals
(by executing them with `node`, not by regexing JSON out of JS source --
`changes: { type: 'array', items: CHANGE_ITEM_SCHEMA }` is an identifier
reference, not a JSON literal, so a text-level parse would either choke on
it or silently fail to resolve it) and compares them against the canonical
JSON on: required-field sets, enum members, and property names -- both at
the top level (stage/chunk_id/changes/summary) and for one change object
($defs.change in the canonical file).

Per TST-08 ("a gate is not trusted until proven able to fail"),
TestDriftIsDetectable below mutates a TEMPORARY COPY of proofread.js (never
the real file) in several independent ways and asserts the comparison
actually reports each mutation as drift.
"""

import json
import os
import re
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(REPO, "src", "workflows", "proofread.js")
CANONICAL_SCHEMA_PATH = os.path.join(
    REPO, "src", "skills", "proofread", "references", "changes-schema.json"
)


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _extract_decl(src, name):
    """Brace-matches the `const <name> = { ... };` declaration out of `src`,
    tolerant of internal formatting/whitespace/reordering -- it just needs to
    find the matching closing brace, not parse JS. Robust enough not to
    false-fail on formatting; genuinely fails (raises) if the declaration is
    missing entirely, which is itself a real drift signal."""
    marker = "const " + name + " = "
    start = src.index(marker)  # raises ValueError if the declaration is gone
    brace_start = src.index("{", start)
    depth = 0
    i = brace_start
    while True:
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    end = i + 1
    if src[end:end + 1] == ";":
        end += 1
    return src[start:end]


def _extract_inline_schemas(workflow_src_path):
    """Runs the ACTUAL `const CHANGE_ITEM_SCHEMA = {...}` and
    `const CHANGES_SCHEMA = {...}` declarations from proofread.js through
    node and returns the resolved objects as
    {"item": <CHANGE_ITEM_SCHEMA>, "top": <CHANGES_SCHEMA>}. Executing the
    real declarations (rather than regexing JSON text out of them) is what
    correctly resolves `items: CHANGE_ITEM_SCHEMA` -- an identifier
    reference, not a JSON literal -- for free."""
    src = _read(workflow_src_path)
    item_decl = _extract_decl(src, "CHANGE_ITEM_SCHEMA")
    top_decl = _extract_decl(src, "CHANGES_SCHEMA")
    script = (
        item_decl + "\n" + top_decl + "\n"
        "process.stdout.write(JSON.stringify({ item: CHANGE_ITEM_SCHEMA, top: CHANGES_SCHEMA }));\n"
    )
    tmp_dir = tempfile.mkdtemp(prefix="schema-drift-extract-")
    try:
        script_path = os.path.join(tmp_dir, "extract.js")
        with open(script_path, "w", encoding="utf-8") as fh:
            fh.write(script)
        proc = subprocess.run(
            ["node", script_path], capture_output=True, text=True, timeout=30
        )
        if proc.returncode != 0:
            raise AssertionError(
                "failed to execute the extracted inline schema declarations:\n"
                "stdout={}\nstderr={}".format(proc.stdout, proc.stderr)
            )
        return json.loads(proc.stdout)
    finally:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)


def _load_canonical():
    with open(CANONICAL_SCHEMA_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _enum_of(properties, key):
    spec = properties.get(key)
    if not isinstance(spec, dict):
        return None
    enum = spec.get("enum")
    return set(enum) if isinstance(enum, list) else None


def diff_inline_vs_canonical(inline, canonical):
    """Returns a list of human-readable difference strings; empty means the
    two schemas are structurally equivalent on the compared dimensions
    (required-field sets, enum members, property names -- both at the top
    level and for one change object)."""
    diffs = []

    top = inline["top"]
    item = inline["item"]
    change = canonical["$defs"]["change"]

    # -- top-level required-field set --------------------------------------
    top_required = set(top.get("required", []))
    canonical_top_required = set(canonical.get("required", []))
    if top_required != canonical_top_required:
        diffs.append(
            "top-level required set differs: inline=%s canonical=%s"
            % (sorted(top_required), sorted(canonical_top_required))
        )

    # -- top-level property names --------------------------------------------
    top_props = set(top.get("properties", {}).keys())
    canonical_top_props = set(canonical.get("properties", {}).keys())
    if top_props != canonical_top_props:
        diffs.append(
            "top-level property names differ: inline=%s canonical=%s"
            % (sorted(top_props), sorted(canonical_top_props))
        )

    # -- top-level 'stage' enum ----------------------------------------------
    top_stage_enum = _enum_of(top.get("properties", {}), "stage")
    canonical_top_stage_enum = _enum_of(canonical.get("properties", {}), "stage")
    if (top_stage_enum or canonical_top_stage_enum) and top_stage_enum != canonical_top_stage_enum:
        diffs.append(
            "top-level 'stage' enum differs: inline=%s canonical=%s"
            % (top_stage_enum, canonical_top_stage_enum)
        )

    # -- change object: required-field set -----------------------------------
    item_required = set(item.get("required", []))
    canonical_change_required = set(change.get("required", []))
    if item_required != canonical_change_required:
        diffs.append(
            "change required set differs: inline=%s canonical=%s"
            % (sorted(item_required), sorted(canonical_change_required))
        )

    # -- change object: property names ---------------------------------------
    item_props = set(item.get("properties", {}).keys())
    canonical_change_props = set(change.get("properties", {}).keys())
    if item_props != canonical_change_props:
        diffs.append(
            "change property names differ: inline=%s canonical=%s"
            % (sorted(item_props), sorted(canonical_change_props))
        )

    # -- change object: enum members for every enum-bearing property ---------
    for key in ("stage", "type", "level", "meaningRisk"):
        inline_enum = _enum_of(item.get("properties", {}), key)
        canonical_enum = _enum_of(change.get("properties", {}), key)
        if (inline_enum or canonical_enum) and inline_enum != canonical_enum:
            diffs.append(
                "change '%s' enum differs: inline=%s canonical=%s"
                % (key, inline_enum, canonical_enum)
            )

    return diffs


class TestInlineSchemaMatchesCanonical(unittest.TestCase):
    """The real, current state: the two files must agree on every dimension
    this test checks. If this test is red, the inline duplicate in
    proofread.js has drifted from the canonical contract and must be fixed
    there (proofread.js cannot Read the canonical file off disk, by its own
    documented design -- see the module docstring)."""

    def setUp(self):
        self.inline = _extract_inline_schemas(WORKFLOW)
        self.canonical = _load_canonical()

    def test_canonical_schema_itself_parses(self):
        self.assertIn("$defs", self.canonical)
        self.assertIn("change", self.canonical["$defs"])

    def test_no_drift(self):
        diffs = diff_inline_vs_canonical(self.inline, self.canonical)
        self.assertEqual(
            diffs,
            [],
            "inline CHANGES_SCHEMA/CHANGE_ITEM_SCHEMA in proofread.js has drifted "
            "from src/skills/proofread/references/changes-schema.json:\n  "
            + "\n  ".join(diffs),
        )


class TestDriftIsDetectable(unittest.TestCase):
    """TST-08: a gate is not trusted until it has been proven able to fail.
    Each case here plants ONE realistic drift in a TEMPORARY COPY of
    proofread.js (the real file is never touched) and asserts the same
    diff_inline_vs_canonical() used above actually reports it."""

    def setUp(self):
        self.canonical = _load_canonical()
        self.src = _read(WORKFLOW)
        self.tmp_dir = tempfile.mkdtemp(prefix="schema-drift-mutate-")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _mutated_copy(self, mutated_src):
        self.assertNotEqual(mutated_src, self.src, "mutation did not change the source")
        path = os.path.join(self.tmp_dir, "proofread.js")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(mutated_src)
        return path

    def test_detects_missing_required_field(self):
        mutated = self.src.replace(
            "required: ['stage', 'line', 'type', 'level', 'before', 'rationale', 'meaningRisk'],",
            "required: ['line', 'type', 'level', 'before', 'rationale', 'meaningRisk'],",
        )
        path = self._mutated_copy(mutated)
        inline = _extract_inline_schemas(path)
        diffs = diff_inline_vs_canonical(inline, self.canonical)
        self.assertTrue(
            any("change required set differs" in d for d in diffs),
            "dropping 'stage' from the change-item required list must be caught: %r" % diffs,
        )

    def test_detects_missing_enum_member(self):
        mutated = self.src.replace(
            "'term-undefined', 'insider-reference', 'genre-fit', 'idea-flag', 'voice-flag',",
            "'term-undefined', 'insider-reference', 'genre-fit', 'idea-flag',",
        )
        path = self._mutated_copy(mutated)
        inline = _extract_inline_schemas(path)
        diffs = diff_inline_vs_canonical(inline, self.canonical)
        self.assertTrue(
            any("change 'type' enum differs" in d for d in diffs),
            "dropping 'voice-flag' from the inline type enum must be caught: %r" % diffs,
        )

    def test_detects_missing_property(self):
        mutated = self.src.replace(
            "    refutedBy: { type: 'array', items: { type: 'string' } },\n",
            "",
        )
        path = self._mutated_copy(mutated)
        inline = _extract_inline_schemas(path)
        diffs = diff_inline_vs_canonical(inline, self.canonical)
        self.assertTrue(
            any("change property names differ" in d for d in diffs),
            "dropping the 'refutedBy' property must be caught: %r" % diffs,
        )

    def test_detects_top_level_stage_enum_drift(self):
        mutated = self.src.replace(
            "    stage: { type: 'string', enum: ['editorial', 'language', 'mechanical'] },\n"
            "    chunk_id: { type: 'string' },",
            "    stage: { type: 'string' },\n"
            "    chunk_id: { type: 'string' },",
        )
        path = self._mutated_copy(mutated)
        inline = _extract_inline_schemas(path)
        diffs = diff_inline_vs_canonical(inline, self.canonical)
        self.assertTrue(
            any("top-level 'stage' enum differs" in d for d in diffs),
            "dropping the top-level stage enum must be caught: %r" % diffs,
        )

    def test_a_harmless_reformat_is_not_flagged(self):
        """Sanity check the other direction: whitespace-only reformatting of
        the same declarations must NOT be reported as drift (the extractor
        must be tolerant of formatting, per the task's own requirement)."""
        mutated = self.src.replace(
            "const CHANGE_ITEM_SCHEMA = {\n  type: 'object',",
            "const CHANGE_ITEM_SCHEMA = {\n\n  type: 'object',\n",
        )
        path = self._mutated_copy(mutated)
        inline = _extract_inline_schemas(path)
        diffs = diff_inline_vs_canonical(inline, self.canonical)
        self.assertEqual(diffs, [])


class TestCanonicalSchemaFileUntouched(unittest.TestCase):
    """This test file must never mutate the real on-disk canonical schema --
    only ever a temp copy of proofread.js. Regression guard against a future
    edit accidentally pointing a mutation at CANONICAL_SCHEMA_PATH."""

    def test_canonical_file_unchanged_after_full_run(self):
        before = _read(CANONICAL_SCHEMA_PATH)
        # Exercise the full drift + mutation flow once more inline.
        inline = _extract_inline_schemas(WORKFLOW)
        canonical = _load_canonical()
        diff_inline_vs_canonical(inline, canonical)
        after = _read(CANONICAL_SCHEMA_PATH)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
