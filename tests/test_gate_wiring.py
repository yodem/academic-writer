"""Every gate.py subcommand must have a caller in a skill or agent definition.

WHY THIS EXISTS
---------------
The 2026-09-04 determinism audit's central finding was that the plugin's guard
scripts and its enforcement surface could not reach each other: ten of eleven
deterministic scripts fired only because a SKILL.md sentence told a model to run
them, and nothing checked that the sentence was still there. A guard script with
no caller is dead code that reads as a safeguard.

`gate.py` adds four more such scripts, so this test closes the loop for them: it
discovers the subcommands from argparse itself (not from a hardcoded list, so a
subcommand added later is covered automatically) and asserts each one is invoked
somewhere under src/skills/ or src/agents/.

The matching is deliberately quote-tolerant. The 2026-09-02 audit found a real
instance of this exact trap: `proofreader.md` referenced `spellcheck-candidates.py`
without its literal path, so `test_referenced_scripts_exist`'s regex never matched
it and the test passed while the script did not exist. A pattern that only matches
`gate.py <subcommand>` silently misses the equally valid
`"${CLAUDE_PLUGIN_ROOT}/scripts/gate.py" <subcommand>` form — which is the house
style in proofread/SKILL.md. A wiring test that can be defeated by a quote
character is the kind of check that cannot fail, which is what TST-08 is about.
"""

import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_SCRIPT = REPO_ROOT / "src" / "scripts" / "gate.py"
SEARCH_ROOTS = [REPO_ROOT / "src" / "skills", REPO_ROOT / "src" / "agents"]


def discover_subcommands():
    """Read the subcommand list off gate.py's own argparse, not a hardcoded copy."""
    proc = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    # argparse renders the choices as "{a,b,c}" in its usage/positional block.
    match = re.search(r"\{([a-z0-9-]+(?:,[a-z0-9-]+)+)\}", proc.stdout)
    assert match, (
        "could not find the subcommand choices in gate.py --help output; "
        "if argparse's rendering changed, fix this discovery rather than "
        "hardcoding the list.\n--- stdout ---\n" + proc.stdout
    )
    return match.group(1).split(",")


def markdown_sources():
    for root in SEARCH_ROOTS:
        yield from root.rglob("*.md")


class GateWiringTests(unittest.TestCase):
    def test_gate_script_exists(self):
        self.assertTrue(GATE_SCRIPT.is_file(), f"{GATE_SCRIPT} is missing")

    def test_subcommands_are_discoverable(self):
        self.assertGreater(
            len(discover_subcommands()), 0, "no gate.py subcommands discovered"
        )

    def test_every_subcommand_has_a_caller(self):
        subcommands = discover_subcommands()
        texts = {p: p.read_text(encoding="utf-8") for p in markdown_sources()}

        uncalled = {}
        for sub in subcommands:
            # Tolerate an optional closing quote after gate.py — both
            #   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gate.py <sub>
            #   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gate.py" <sub>
            # are real invocations used in this repo.
            pattern = re.compile(r"gate\.py\"?\s+" + re.escape(sub) + r"\b")
            callers = [p.relative_to(REPO_ROOT) for p, t in texts.items() if pattern.search(t)]
            if not callers:
                uncalled[sub] = None

        self.assertEqual(
            uncalled,
            {},
            "gate.py subcommand(s) with no caller under src/skills/ or src/agents/: "
            + ", ".join(sorted(uncalled))
            + ". A guard script nothing invokes is dead code that reads as a safeguard.",
        )


class WiringTestCanFailTests(unittest.TestCase):
    """TST-08: prove the check above can actually fail."""

    def test_a_fabricated_subcommand_is_reported_as_uncalled(self):
        texts = {p: p.read_text(encoding="utf-8") for p in markdown_sources()}
        bogus = "definitely-not-a-real-subcommand"
        pattern = re.compile(r"gate\.py\"?\s+" + re.escape(bogus) + r"\b")
        callers = [p for p, t in texts.items() if pattern.search(t)]
        self.assertEqual(
            callers, [], "the negative control matched something; the pattern is too loose"
        )

    def test_quote_tolerance_actually_matters(self):
        """The quoted form must match — the bug this test exists to prevent."""
        quoted = 'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gate.py" changes-schema /tmp/x.json'
        naive = re.compile(r"gate\.py changes-schema")
        tolerant = re.compile(r"gate\.py\"?\s+changes-schema\b")
        self.assertIsNone(
            naive.search(quoted), "naive pattern unexpectedly matched; premise changed"
        )
        self.assertIsNotNone(
            tolerant.search(quoted), "tolerant pattern must match the quoted invocation form"
        )


if __name__ == "__main__":
    unittest.main()
