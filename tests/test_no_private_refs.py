"""No personal identifier may reach a shipped or published file.

github.com/yodem/academic-writer is a PUBLIC repository. Delegating this to a shell
script rather than reimplementing the denylist keeps one source of truth for what
counts as an identifier — the release workflow runs the same script.
"""

import os
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "check-no-private-refs.sh")


class TestNoPrivateRefs(unittest.TestCase):
    def test_script_exists_and_is_executable(self):
        self.assertTrue(os.path.isfile(SCRIPT))
        self.assertTrue(os.access(SCRIPT, os.X_OK), "check-no-private-refs.sh must be executable")

    def test_no_private_refs_in_tracked_published_files(self):
        proc = subprocess.run(["bash", SCRIPT], cwd=REPO, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"\n{proc.stdout}\n{proc.stderr}")

    def test_denylist_uses_a_separator_that_is_not_regex_alternation(self):
        """An earlier version used '|' as both the field separator and the regex
        alternation operator, so only the first alternative of each pattern ever ran
        and two whole classes of leak passed silently."""
        with open(SCRIPT, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("::", text)
        self.assertIn('"${entry%%::*}"', text)

    def test_the_gate_actually_catches_a_planted_identifier(self):
        """A gate that cannot fail proves nothing (VER-08)."""
        planted = os.path.join(REPO, "docs", "_private_ref_probe.md")
        with open(planted, "w", encoding="utf-8") as fh:
            fh.write("path: /Users/someone/dev/thing\n")
        try:
            subprocess.run(["git", "add", "-N", planted], cwd=REPO, capture_output=True)
            proc = subprocess.run(["bash", SCRIPT], cwd=REPO, capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0, "planted identifier was not caught")
            self.assertIn("absolute macOS home path", proc.stdout)
        finally:
            subprocess.run(["git", "rm", "--cached", "-q", planted], cwd=REPO, capture_output=True)
            os.unlink(planted)

    def test_repo_is_clean_again_after_the_probe(self):
        proc = subprocess.run(["bash", SCRIPT], cwd=REPO, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout)


if __name__ == "__main__":
    unittest.main()
