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


def _run_with_planted(text, name="_private_ref_probe.md"):
    planted = os.path.join(REPO, "docs", name)
    with open(planted, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    try:
        env = os.environ.copy()
        env["CHECK_NO_PRIVATE_REFS_EXTRA_FILES"] = os.path.relpath(planted, REPO)
        return subprocess.run(["bash", SCRIPT], cwd=REPO, env=env, capture_output=True, text=True)
    finally:
        os.unlink(planted)


class TestExtendedIdentityRules(unittest.TestCase):
    """Each identity rule must fail on a planted string (VER-08) and allow safe ones."""

    CASES = [
        ("session path -Users-yotamfromm-dev", "maintainer username slug"),
        ("contact someone@sefaria.org", "work email domain"),
        ("mail jane.doe@gmail.com", "personal email address"),
        ("ssh dev-server", "dev-server host name"),
        ("host box.tail1234.ts.net", "tailscale host name"),
        ("Tailscale box", "tailscale host name"),
        ("see .team/state.md", "internal team handoff state path"),
    ]

    def test_each_rule_fires_on_a_planted_string(self):
        for text, reason in self.CASES:
            with self.subTest(text=text):
                proc = _run_with_planted(text)
                self.assertNotEqual(proc.returncode, 0, f"not caught: {text}")
                self.assertIn(reason, proc.stdout)

    def test_safe_strings_pass(self):
        safe = "Author: Yotam Fromm. Mail you@example.com or noreply@anthropic.com."
        proc = _run_with_planted(safe)
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_tracked_path_deny_covers_every_untracked_dir(self):
        with open(SCRIPT, encoding="utf-8") as fh:
            text = fh.read()
        for frag in (r"^\.team/", "refactor|superpowers|audits|reviews|plans|benchmarks",
                     "^node_modules/", r"^\.claude/settings\.json$"):
            self.assertIn(frag, text)

    def test_tracked_path_patterns_match_planted_paths(self):
        """Each untracked location must actually be matched by a TRACKED_PATH_DENY regex."""
        with open(SCRIPT, encoding="utf-8") as fh:
            text = fh.read()
        block = text.split("TRACKED_PATH_DENY=(", 1)[1].split("\n)", 1)[0]
        patterns = [ln.strip().strip("'").split("::", 1)[0]
                    for ln in block.splitlines() if ln.strip().startswith("'")]
        planted = [".team/state.md", "docs/refactor/STATUS.md", "docs/superpowers/plans/x.md",
                   "docs/audits/a.md", "docs/reviews/r.md", "docs/plans/p.md",
                   "docs/benchmarks/b.md", "node_modules/.package-lock.json",
                   ".claude/settings.json"]
        for path in planted:
            with self.subTest(path=path):
                hit = any(subprocess.run(["grep", "-qE", "--", pat], input=path + "\n",
                                         text=True).returncode == 0 for pat in patterns)
                self.assertTrue(hit, f"no TRACKED_PATH_DENY rule matches {path}")
        # and a shipped guide doc must not be caught
        for ok in ("docs/first-time-flow.md", ".claude/rules/antipatterns.md"):
            with self.subTest(ok=ok):
                hit = any(subprocess.run(["grep", "-qE", "--", pat], input=ok + "\n",
                                         text=True).returncode == 0 for pat in patterns)
                self.assertFalse(hit, f"{ok} wrongly denied")

    def test_internal_paths_are_untracked_and_ignored(self):
        tracked = subprocess.run(
            ["git", "ls-files", ".team", "node_modules", ".claude/settings.json",
             "docs/refactor", "docs/superpowers", "docs/audits", "docs/reviews",
             "docs/plans", "docs/benchmarks"],
            cwd=REPO, capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(tracked, [])
        with open(os.path.join(REPO, ".gitignore"), encoding="utf-8") as fh:
            ignore = fh.read()
        for entry in (".team/", "docs/refactor/", "docs/superpowers/", "docs/audits/",
                      "docs/reviews/", "docs/plans/", "docs/benchmarks/", ".claude/settings.json"):
            self.assertIn(entry, ignore)

    def test_guide_html_is_not_ignored(self):
        for p in ("src/guide/index.html", "plugins/academic-writer/guide/index.html"):
            proc = subprocess.run(["git", "check-ignore", "-q", p], cwd=REPO)
            self.assertEqual(proc.returncode, 1, f"{p} must not be gitignored")


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
