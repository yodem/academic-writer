"""Tests for src/hooks/src/lifecycle/gate-enforce.ts — the plugin's first hook
that actually blocks (registered on the Stop event).

Design spec: docs/audits/2026-09-04-determinism-audit.md sections 3.2 and 5.

Per TST-08, a hook that always returns continue: true has not been proven to
be a gate at all — every test below drives the BUILT hook through
`node src/hooks/bin/run-hook.mjs lifecycle/gate-enforce` in a real temp
project directory with CLAUDE_PROJECT_DIR set, and at least one case must
observe continue: false to prove the hook can actually block (VER-18).

Per TST-09, no test here may skip because an ambient binary (node) is
missing from PATH — `node` is a hard prerequisite of this whole plugin
(package.json engines.node >= 20), so its absence is an environment defect
to report loudly, not silently route around.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_HOOK = os.path.join(ROOT, "src", "hooks", "bin", "run-hook.mjs")
LIFECYCLE_BUNDLE = os.path.join(ROOT, "src", "hooks", "dist", "lifecycle.mjs")

HOOK_NAME = "lifecycle/gate-enforce"

PROFILE_MD = "---\nfieldOfStudy: test\n---\n"


def _require_node():
    node = shutil.which("node")
    if not node:
        raise RuntimeError(
            "`node` not found on PATH. This plugin requires Node >= 20 "
            "(package.json engines.node) — this is an environment defect, "
            "not a reason to skip gate-enforce tests (TST-09)."
        )
    return node


_BUILD_ATTEMPTED = False


def _require_built_bundle():
    """Ensure the compiled hook bundle exists, building it once if it does not.

    TST-09: an environment-dependent test is invisible until something finally
    runs the suite somewhere else. This test drives the COMPILED bundle (that is
    the point — it exercises what Claude Code actually loads), but
    `src/hooks/dist/` is gitignored and `.github/workflows/ci.yml` deliberately
    builds nothing, checking the tree as pushed. So the bundle exists on a
    developer machine that has run `npm run build:hooks` and does not exist on a
    fresh clone or on CI.

    Raising told you the environment was wrong; it still let the suite pass
    locally and fail on CI — which is exactly the failure TST-09 names, and it
    happened here on 2026-09-04. The fix is to CONTROL the environment: build the
    bundle on demand. A genuine build failure still raises loudly, naming the
    build output, so a broken build can never be mistaken for a missing one.
    """
    global _BUILD_ATTEMPTED
    if os.path.isfile(LIFECYCLE_BUNDLE):
        return
    if _BUILD_ATTEMPTED:
        raise RuntimeError(
            f"{LIFECYCLE_BUNDLE} still missing after a build attempt — see the "
            "build output reported by the first failure."
        )
    _BUILD_ATTEMPTED = True
    proc = subprocess.run(
        ["npm", "run", "build:hooks"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if not os.path.isfile(LIFECYCLE_BUNDLE):
        raise RuntimeError(
            "`npm run build:hooks` did not produce "
            f"{LIFECYCLE_BUNDLE} (exit {proc.returncode}). The hook must be "
            "built, not just typechecked, since this test drives the runner "
            "against the compiled bundle exactly as Claude Code would.\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )


class GateEnforceTestCase(unittest.TestCase):
    """Base class: sets up a scratch .academic-helper/ project dir per test."""

    def setUp(self):
        _require_node()
        _require_built_bundle()
        self.project_dir = tempfile.mkdtemp(prefix="gate-enforce-test-")
        self.helper_dir = os.path.join(self.project_dir, ".academic-helper")
        os.makedirs(self.helper_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def _write_profile(self):
        with open(os.path.join(self.helper_dir, "profile.md"), "w", encoding="utf-8") as fh:
            fh.write(PROFILE_MD)

    def _write_session_state(self, state):
        with open(
            os.path.join(self.helper_dir, "session-state.json"), "w", encoding="utf-8"
        ) as fh:
            if isinstance(state, str):
                fh.write(state)
            else:
                json.dump(state, fh)

    def _run_hook(self, payload=None):
        """Invoke the built hook via the real CLI runner, exactly as Claude
        Code's Stop event would, with CLAUDE_PROJECT_DIR pointed at the
        scratch project dir."""
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = self.project_dir
        stdin_data = json.dumps(payload if payload is not None else {})
        node = _require_node()
        result = subprocess.run(
            [node, RUN_HOOK, HOOK_NAME],
            input=stdin_data,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"run-hook.mjs exited {result.returncode}; stderr={result.stderr!r}",
        )
        try:
            return json.loads(result.stdout.strip())
        except json.JSONDecodeError as exc:
            self.fail(f"Hook output was not valid JSON: {result.stdout!r} ({exc})")


class TestNoProfileSkipsSilently(GateEnforceTestCase):
    """No .academic-helper/profile.md -> continue: true, no output. This is
    the hard project convention every hook in this directory follows."""

    def test_no_profile_no_academic_helper_dir_at_all(self):
        # Not even .academic-helper/ exists: run-hook.mjs's own outer guard
        # (line ~54) short-circuits before the hook ever runs.
        shutil.rmtree(self.helper_dir)
        result = self._run_hook({})
        self.assertTrue(result["continue"])

    def test_academic_helper_dir_without_profile(self):
        # .academic-helper/ exists (so run-hook.mjs's outer guard passes
        # through to the hook) but profile.md is absent -> the hook's own
        # profile-scoped skip must fire.
        session_state = {
            "run": {
                "id": "run-1",
                "skill": "write",
                "requiredGates": ["argument-graph"],
                "completed": False,
            },
            "gates": {},
        }
        self._write_session_state(session_state)
        result = self._run_hook({})
        self.assertTrue(result["continue"])
        self.assertTrue(result.get("suppressOutput"))


class TestLoopGuard(GateEnforceTestCase):
    """stop_hook_active: true must win over any failing gate — mandatory,
    or a gate that cannot be satisfied traps the session forever."""

    def test_stop_hook_active_wins_over_failing_gate(self):
        self._write_profile()
        self._write_session_state(
            {
                "run": {
                    "id": "run-1",
                    "skill": "write",
                    "requiredGates": ["argument-graph"],
                    "completed": False,
                },
                "gates": {
                    "argument-graph": {"status": "fail", "detail": "cycle detected"}
                },
            }
        )
        result = self._run_hook({"stop_hook_active": True})
        self.assertTrue(result["continue"])


class TestNoRunInFlight(GateEnforceTestCase):
    def test_missing_session_state_file(self):
        self._write_profile()
        # No session-state.json written at all.
        result = self._run_hook({})
        self.assertTrue(result["continue"])

    def test_no_run_object(self):
        self._write_profile()
        self._write_session_state({"gates": {"argument-graph": {"status": "fail"}}})
        result = self._run_hook({})
        self.assertTrue(result["continue"])

    def test_run_completed_true(self):
        self._write_profile()
        self._write_session_state(
            {
                "run": {
                    "id": "run-1",
                    "skill": "write",
                    "requiredGates": ["argument-graph"],
                    "completed": True,
                },
                "gates": {"argument-graph": {"status": "fail"}},
            }
        )
        result = self._run_hook({})
        self.assertTrue(result["continue"])


class TestMalformedSessionStateFailsOpen(GateEnforceTestCase):
    """Infrastructure problems (unreadable/malformed JSON) must fail OPEN,
    never turn into a false block."""

    def test_malformed_json(self):
        self._write_profile()
        self._write_session_state("{ this is not valid json ]")
        result = self._run_hook({})
        self.assertTrue(result["continue"])

    def test_session_state_is_a_json_array_not_object(self):
        self._write_profile()
        self._write_session_state("[1, 2, 3]")
        result = self._run_hook({})
        self.assertTrue(result["continue"])


class TestGateFailure(GateEnforceTestCase):
    """The core blocking behavior — proves the hook can actually fail
    closed (TST-08)."""

    def test_missing_required_gate_blocks(self):
        self._write_profile()
        self._write_session_state(
            {
                "run": {
                    "id": "run-42",
                    "skill": "write",
                    "requiredGates": ["argument-graph", "citation-floor"],
                    "completed": False,
                },
                "gates": {
                    "argument-graph": {"status": "pass"},
                    # citation-floor never ran -> absent from ledger.
                },
            }
        )
        result = self._run_hook({})
        self.assertFalse(result["continue"])
        self.assertIn("citation-floor", result["systemMessage"])
        self.assertIn("MISSING", result["systemMessage"])

    def test_failing_status_blocks_and_names_gate(self):
        self._write_profile()
        self._write_session_state(
            {
                "run": {
                    "id": "run-42",
                    "skill": "write",
                    "requiredGates": ["argument-graph"],
                    "completed": False,
                },
                "gates": {
                    "argument-graph": {
                        "status": "fail",
                        "detail": "cycle: A depends_on B, B depends_on A",
                        "violations": ["node-a", "node-b"],
                    }
                },
            }
        )
        result = self._run_hook({})
        self.assertFalse(result["continue"])
        msg = result["systemMessage"]
        self.assertIn("argument-graph", msg)
        self.assertIn("cycle: A depends_on B, B depends_on A", msg)
        self.assertIn("node-a", msg)

    def test_error_status_also_blocks(self):
        self._write_profile()
        self._write_session_state(
            {
                "run": {
                    "id": "run-1",
                    "skill": "proofread",
                    "requiredGates": ["changes-schema"],
                    "completed": False,
                },
                "gates": {"changes-schema": {"status": "error", "detail": "jsonschema not installed"}},
            }
        )
        result = self._run_hook({})
        self.assertFalse(result["continue"])
        self.assertIn("changes-schema", result["systemMessage"])

    def test_message_includes_rerun_command(self):
        self._write_profile()
        self._write_session_state(
            {
                "run": {
                    "id": "run-1",
                    "skill": "write",
                    "requiredGates": ["citation-floor"],
                    "completed": False,
                },
                "gates": {},
            }
        )
        result = self._run_hook({})
        self.assertFalse(result["continue"])
        self.assertIn("gate.py", result["systemMessage"])
        self.assertIn("citation-floor", result["systemMessage"])


class TestAllGatesPass(GateEnforceTestCase):
    def test_all_required_gates_pass(self):
        self._write_profile()
        self._write_session_state(
            {
                "run": {
                    "id": "run-1",
                    "skill": "write",
                    "requiredGates": ["argument-graph", "citation-floor"],
                    "completed": False,
                },
                "gates": {
                    "argument-graph": {"status": "pass", "at": "2026-09-04T00:00:00Z"},
                    "citation-floor": {"status": "pass", "at": "2026-09-04T00:01:00Z"},
                    # An extra, non-required gate present in the ledger must
                    # not affect the verdict either way.
                    "coverage": {"status": "fail"},
                },
            }
        )
        result = self._run_hook({})
        self.assertTrue(result["continue"])

    def test_no_required_gates_declared(self):
        # requiredGates: [] means nothing to enforce -- data-driven, no
        # hardcoded knowledge of which gates belong to which skill.
        self._write_profile()
        self._write_session_state(
            {
                "run": {
                    "id": "run-1",
                    "skill": "ideate",
                    "requiredGates": [],
                    "completed": False,
                },
                "gates": {},
            }
        )
        result = self._run_hook({})
        self.assertTrue(result["continue"])


if __name__ == "__main__":
    unittest.main()
