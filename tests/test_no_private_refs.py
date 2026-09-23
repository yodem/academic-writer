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
            env = os.environ.copy()
            env["CHECK_NO_PRIVATE_REFS_EXTRA_FILES"] = os.path.relpath(planted, REPO)
            proc = subprocess.run(["bash", SCRIPT], cwd=REPO, env=env, capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0, "planted identifier was not caught")
            self.assertIn("absolute macOS home path", proc.stdout)
        finally:
            os.unlink(planted)

    def test_repo_is_clean_again_after_the_probe(self):
        proc = subprocess.run(["bash", SCRIPT], cwd=REPO, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout)


if __name__ == "__main__":
    unittest.main()


class TestShareability(unittest.TestCase):
    """The repo must stay shareable: no machine-local state or personal drafts tracked."""

    def test_no_local_state_is_tracked(self):
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.split()
        import re

        banned = re.compile(
            r"^(\.claude/(state|memory|agents|context|orchestration)/|\.claude/HANDOFF\.md$"
            r"|\.instance/|\.removal-log/|past-articles/|logs/|pitch-)"
        )
        offenders = [p for p in tracked if banned.match(p)]
        self.assertEqual(
            offenders,
            [],
            "machine-local state or personal drafts are tracked; "
            f"git rm -r --cached them (files stay on disk): {offenders}",
        )

    def test_gitignore_covers_them(self):
        with open(os.path.join(REPO, ".gitignore"), encoding="utf-8") as fh:
            ignore = fh.read()
        for entry in (".claude/state/", ".instance/", ".removal-log/", "pitch-*.md"):
            self.assertIn(entry, ignore, f".gitignore must exclude {entry}")

    def test_no_unrelated_private_project_in_shipped_files(self):
        shipped = subprocess.run(
            ["git", "ls-files", "src/", "plugins/", "manifests/"],
            cwd=REPO, capture_output=True, text=True, check=True,
        ).stdout.split()
        offenders = []
        for rel in shipped:
            path = os.path.join(REPO, rel)
            try:
                with open(path, encoding="utf-8") as fh:
                    if "mikdashim" in fh.read().lower():
                        offenders.append(rel)
            except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
                continue
        self.assertEqual(
            offenders,
            [],
            "a shipped file names an unrelated private project; describe the failure "
            f"mode, not the project: {offenders}",
        )


class TestUnpublishedCorrespondenceNotCommitted(unittest.TestCase):
    """The rejection letter must never be committed.

    It is unpublished correspondence about an unpublished article: it names the author's
    personal relationship with the subject, quotes the article's own prose, and is the
    single most sensitive artifact this work touched. Its CONTENT shaped the fixture's
    expectations, which is the legitimate use; the letter itself stays out.
    """

    def test_no_letter_file_is_tracked(self):
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.split()
        import re

        offenders = [
            p for p in tracked
            if re.search(r"(rejection[-_]?letter|letter\.(md|txt|docx)$)", p, re.I)
        ]
        self.assertEqual(offenders, [], f"unpublished correspondence is tracked: {offenders}")

    def test_no_tracked_file_quotes_the_editor_at_length(self):
        """A distinctive phrase from the letter, as a canary for a paste-in."""
        canaries = ("חברי המערכת", "ממין העניין", "בתוך עמי אנכי יושב")
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.split()
        offenders = []
        for rel in tracked:
            if "node_modules" in rel or rel == "tests/test_no_private_refs.py":
                continue
            try:
                with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
                    body = fh.read()
            except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
                continue
            if any(c in body for c in canaries):
                offenders.append(rel)
        self.assertEqual(offenders, [], f"letter text pasted into tracked files: {offenders}")
