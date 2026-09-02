"""The plugin version must agree everywhere, and every place it lives must be registered.

Two guards, both deterministic (TST-02 — no LLM judges a version number):

1. AGREEMENT — every location in scripts/version-locations.json holds the canonical value.
2. DISCOVERY — every version-ish field in a tracked JSON file is either registered as a
   plugin-version location or matched by the registry's `unrelatedVersionFields` allowlist.
   Guard 1 alone cannot catch a NEW manifest that nobody registered; guard 2 can. This is
   the failure that actually happened: features.json drifted to 0.5.0 while the other five
   locations said 0.6.3, because the release workflow's bump step wrote only three of them
   and check-version-consistency.sh deliberately scoped itself to a single pair.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import importlib.util

_spec = importlib.util.spec_from_file_location("version_sync", REPO / "scripts" / "version-sync.py")
version_sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(version_sync)

VERSION_KEY_RE = re.compile(r"^(version|pluginVersion)$")

def _workflow_code() -> str:
    """release.yml with YAML comment lines removed.

    Assertions below must test what the workflow DOES, not what its comments say —
    an earlier version of this test flagged its own explanatory comment about the
    removed `${PARTS[2]} + 1` arithmetic as if the arithmetic were still there.
    """
    lines = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8").splitlines()
    return "\n".join(ln for ln in lines if not ln.lstrip().startswith("#"))



def _tracked_json() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "*.json"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    return [p for p in out if "node_modules" not in p]


def _version_fields(doc, prefix=()):
    """Yield (path_tuple, value) for every scalar field whose key is version-ish."""
    if isinstance(doc, dict):
        for key, val in doc.items():
            here = prefix + (key,)
            if VERSION_KEY_RE.match(key) and not isinstance(val, (dict, list)):
                yield here, val
            else:
                yield from _version_fields(val, here)
    elif isinstance(doc, list):
        for i, val in enumerate(doc):
            yield from _version_fields(val, prefix + (i,))


class TestVersionConsistency(unittest.TestCase):
    def setUp(self):
        self.reg = version_sync.load_registry()
        self.expected = version_sync.canonical_version(self.reg)
        self.registered = {
            (loc["file"], tuple(loc["path"])) for loc in self.reg["locations"]
        }
        self.allow = [re.compile(p["pattern"]) for p in self.reg["unrelatedVersionFields"]]

    # ---- guard 1: agreement -------------------------------------------------
    def test_all_registered_locations_agree(self):
        drift = [
            f"{rel} {'.'.join(str(x) for x in path)} = {value or error}"
            for rel, path, value, error in version_sync.read_all(self.reg)
            if error or value != self.expected
        ]
        self.assertEqual(
            drift,
            [],
            f"plugin version drift (canonical {self.expected}); "
            f"run `python3 scripts/version-sync.py --fix`: {drift}",
        )

    def test_canonical_is_semver(self):
        self.assertRegex(self.expected, r"^\d+\.\d+\.\d+$")

    # ---- guard 2: discovery -------------------------------------------------
    def test_every_version_field_is_registered_or_allowlisted(self):
        unaccounted = []
        for rel in _tracked_json():
            path = REPO / rel
            if any(a.search(rel) for a in self.allow):
                continue
            try:
                with path.open(encoding="utf-8") as fh:
                    doc = json.load(fh)
            except (json.JSONDecodeError, FileNotFoundError):
                continue
            for field_path, _value in _version_fields(doc):
                if (rel, field_path) not in self.registered:
                    unaccounted.append(f"{rel} {'.'.join(str(x) for x in field_path)}")
        self.assertEqual(
            unaccounted,
            [],
            "version-ish field is neither a registered plugin-version location nor "
            "allowlisted in scripts/version-locations.json. Register it (so the bump "
            f"writes it) or allowlist it with a reason: {unaccounted}",
        )

    def test_registry_paths_are_unique(self):
        paths = [(loc["file"], tuple(loc["path"])) for loc in self.reg["locations"]]
        self.assertEqual(len(paths), len(set(paths)), "duplicate entry in version-locations.json")

    def test_canonical_is_itself_a_registered_location(self):
        c = (self.reg["canonical"]["file"], tuple(self.reg["canonical"]["path"]))
        self.assertIn(c, self.registered, "canonical location must also be listed in locations[]")


class TestBumpLogic(unittest.TestCase):
    def test_bump_levels(self):
        self.assertEqual(version_sync.bump("0.6.3", "patch"), "0.6.4")
        self.assertEqual(version_sync.bump("0.6.3", "minor"), "0.7.0")
        self.assertEqual(version_sync.bump("0.6.3", "major"), "1.0.0")
        self.assertEqual(version_sync.bump("1.9.9", "minor"), "1.10.0")

    def test_level_from_commit_message(self):
        cases = {
            "feat: add venue profiles": "minor",
            "feat(proofread): add venue profiles": "minor",
            "fix: correct a typo": "patch",
            "chore: tidy": "patch",
            "docs: readme": "patch",
            "feat!: drop the old api": "major",
            "refactor(core)!: rename": "major",
            "fix: thing\n\nBREAKING CHANGE: removed x": "major",
            "": "patch",
        }
        for msg, expected in cases.items():
            self.assertEqual(
                version_sync.level_from_message(msg), expected, f"message: {msg!r}"
            )

    def test_release_workflow_uses_the_script(self):
        """The workflow must not carry its own arithmetic — that is how three of six
        locations went unwritten in the first place."""
        wf = _workflow_code()
        self.assertIn("version-sync.py", wf, "release.yml must bump via scripts/version-sync.py")
        self.assertNotIn(
            "PARTS[2]", wf,
            "release.yml still does its own version arithmetic; it must call version-sync.py",
        )


if __name__ == "__main__":
    unittest.main()


class TestMultiCommitLevel(unittest.TestCase):
    """A push is many commits; head_commit is only the last one."""

    def test_highest_level_across_messages_wins(self):
        self.assertEqual(
            version_sync.level_from_messages(["fix: a", "feat: b", "docs: c"]), "minor"
        )
        self.assertEqual(
            version_sync.level_from_messages(["fix: a", "feat: b", "feat!: c"]), "major"
        )
        self.assertEqual(version_sync.level_from_messages(["fix: a", "chore: b"]), "patch")
        self.assertEqual(version_sync.level_from_messages([]), "patch")
        self.assertEqual(version_sync.level_from_messages([None, ""]), "patch")

    def test_merge_commit_push_still_sees_the_feature(self):
        """The regression this exists for: inferring from head_commit alone ships a
        patch for a merge that contains features."""
        import json as _json
        import tempfile

        payload = {
            "commits": [{"message": "fix: a"}, {"message": "feat: venue profiles"}],
            "head_commit": {"message": "Merge branch 'feat/x' into main"},
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            _json.dump(payload, fh)
            path = Path(fh.name)
        try:
            self.assertEqual(version_sync.level_from_message(payload["head_commit"]["message"]), "patch")
            self.assertEqual(
                version_sync.level_from_messages(version_sync.messages_from_event(path)), "minor"
            )
        finally:
            path.unlink()

    def test_workflow_derives_level_since_the_last_tag_not_from_the_push(self):
        """A push-scoped level (--level-from-event) is lost for good when that push's
        release job fails before a tag is cut — see TestLevelSinceTag below for the
        regression this guards. The workflow must derive the level from commits since
        the last release tag instead."""
        wf = _workflow_code()
        self.assertIn("--level-since-tag", wf, "level must come from commits since the last release tag")
        self.assertNotIn(
            "--level-from-event", wf,
            "the workflow must not infer the level from a single push's commits",
        )
        # head_commit is still fine for the "is this the bot's own bump commit?" guard —
        # what must NOT happen is deriving the BUMP LEVEL from a single commit message.
        self.assertNotIn(
            "--level-from-message", wf,
            "the workflow must not infer the level from a single commit message",
        )

    def test_workflow_fetches_tags_before_deriving_the_level(self):
        """--level-since-tag walks tag..HEAD; actions/checkout does not fetch tags by
        default even with fetch-depth: 0, so a missing fetch would silently fall back
        to 'no tags' and re-count everything a prior release already shipped."""
        wf = _workflow_code()
        self.assertIn("fetch-depth: 0", wf)
        self.assertRegex(wf, r"fetch\b.*--tags|--tags\b.*fetch")

    def test_workflow_exposes_a_manual_level_override(self):
        wf = _workflow_code()
        self.assertIn("workflow_dispatch", wf)
        self.assertIn("inputs.level", wf)


class TestLevelSinceTag(unittest.TestCase):
    """--level-since-tag must derive the bump level from commits since the last
    release tag, not from any single push — that is the whole point of the fix:
    a push whose release job fails never gets a tag, so a level computed only
    from THAT push's commits is discarded and can never come back. Deriving it
    from tag..HEAD means a feat: commit from a failed push is still counted once
    a later, unrelated push finally succeeds.

    Every repo here is a hermetic temp dir created with `git init` — never the
    real project history — so these tests can't drift with this repo's own log.
    """

    def _init_repo(self) -> Path:
        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp, check=True)
        return tmp

    def _commit(self, repo: Path, message: str) -> None:
        subprocess.run(
            ["git", "commit", "--allow-empty", "-q", "-m", message],
            cwd=repo, check=True,
        )

    def _tag(self, repo: Path, tag: str) -> None:
        subprocess.run(["git", "tag", tag], cwd=repo, check=True)

    def test_no_tags_considers_all_history(self):
        repo = self._init_repo()
        self._commit(repo, "chore: init")
        self._commit(repo, "feat: first feature")
        self.assertIsNone(version_sync.latest_release_tag(repo))
        self.assertEqual(version_sync.level_since_tag(repo), "minor")

    def test_no_tags_no_commits_is_patch(self):
        """An empty repo (no commits at all) must not raise — it has nothing to
        release, so it falls back to the same default as 'no messages'."""
        repo = self._init_repo()
        self.assertEqual(version_sync.level_since_tag(repo), "patch")

    def test_only_fix_commits_after_tag_is_patch(self):
        repo = self._init_repo()
        self._commit(repo, "feat: initial release")
        self._tag(repo, "v0.1.0")
        self._commit(repo, "fix: repair a bug")
        self._commit(repo, "docs: typo")
        self.assertEqual(version_sync.latest_release_tag(repo), "v0.1.0")
        self.assertEqual(version_sync.level_since_tag(repo), "patch")

    def test_feat_among_several_commits_after_tag_is_minor(self):
        repo = self._init_repo()
        self._commit(repo, "feat: initial release")
        self._tag(repo, "v0.1.0")
        self._commit(repo, "fix: a")
        self._commit(repo, "feat: b")
        self._commit(repo, "docs: c")
        self.assertEqual(version_sync.level_since_tag(repo), "minor")

    def test_breaking_bang_after_tag_is_major(self):
        repo = self._init_repo()
        self._commit(repo, "feat: initial release")
        self._tag(repo, "v0.1.0")
        self._commit(repo, "fix: a")
        self._commit(repo, "feat!: drop the old api")
        self.assertEqual(version_sync.level_since_tag(repo), "major")

    def test_breaking_change_footer_after_tag_is_major(self):
        repo = self._init_repo()
        self._commit(repo, "feat: initial release")
        self._tag(repo, "v0.1.0")
        self._commit(repo, "fix: a")
        self._commit(repo, "fix: repair the gate\n\nBREAKING CHANGE: removed the old flag")
        self.assertEqual(version_sync.level_since_tag(repo), "major")

    def test_feat_before_a_failed_release_is_still_counted(self):
        """THE REGRESSION. Push A ships a feat: commit but its release job fails,
        so no tag is cut — v0.1.0 stays the last tag. Push B is only a fix:, and
        its release succeeds. The level must be minor: it depends on distance
        from the tag (tag..HEAD), not on which single push is being evaluated."""
        repo = self._init_repo()
        self._commit(repo, "feat: initial release")
        self._tag(repo, "v0.1.0")
        # Push A: a feat:, but imagine its CI run failed before a tag was cut.
        self._commit(repo, "feat: venue profiles")
        # Push B: a fix:, whose CI run is the one that finally succeeds.
        self._commit(repo, "fix: repair the failing test")
        self.assertEqual(version_sync.latest_release_tag(repo), "v0.1.0")
        # A push-scoped view of push B alone would see only "fix:" -> patch.
        self.assertEqual(version_sync.level_from_messages(["fix: repair the failing test"]), "patch")
        # The since-tag view still sees push A's feat: -> minor.
        self.assertEqual(version_sync.level_since_tag(repo), "minor")

    def test_newest_tag_wins_by_version_order_not_lexical(self):
        """v0.6.9 < v0.6.10 by version order, but 'v0.6.10' < 'v0.6.9' lexically —
        picking the tag lexically would pick the wrong one and re-count v0.6.10's
        already-released commits."""
        repo = self._init_repo()
        self._commit(repo, "feat: a")
        self._tag(repo, "v0.6.9")
        self._commit(repo, "fix: b")
        self._tag(repo, "v0.6.10")
        self._commit(repo, "docs: c")
        self.assertEqual(version_sync.latest_release_tag(repo), "v0.6.10")
        self.assertEqual(version_sync.level_since_tag(repo), "patch")

    def test_non_ancestor_tag_is_ignored(self):
        """A v-tag that exists in the repo but sits on a different line of history
        (not an ancestor of HEAD) must not be treated as 'the last release'."""
        repo = self._init_repo()
        self._commit(repo, "feat: on main")
        self._tag(repo, "v0.1.0")
        subprocess.run(["git", "checkout", "-q", "-b", "other"], cwd=repo, check=True)
        self._commit(repo, "feat: on other branch only")
        self._tag(repo, "v9.9.9")
        subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, check=True)
        self._commit(repo, "fix: on main after the branch")
        self.assertEqual(version_sync.latest_release_tag(repo), "v0.1.0")
        self.assertEqual(version_sync.level_since_tag(repo), "patch")


class TestWriteModes(unittest.TestCase):
    """--fix / --set / --bump must actually WRITE.

    `--fix` shipped parsed-but-unwired: argparse accepted it, main() dispatched only on
    --set/--bump, so it silently fell through to the read-only check path and exited 1.
    A flag that is accepted and does nothing is worse than a missing flag.
    """

    def _temp_repo(self, versions):
        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        reg = version_sync.load_registry()
        for loc, value in zip(reg["locations"], versions):
            dest = tmp / loc["file"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            doc = json.loads(dest.read_text(encoding="utf-8")) if dest.exists() else {}
            node = doc
            for key in loc["path"][:-1]:
                if isinstance(key, int):
                    while len(node) <= key:
                        node.append({})
                    node = node[key]
                else:
                    node = node.setdefault(key, [] if isinstance(loc["path"][loc["path"].index(key) + 1], int) else {})
            if isinstance(loc["path"][-1], int):
                while len(node) <= loc["path"][-1]:
                    node.append({})
                node[loc["path"][-1]] = value
            else:
                node[loc["path"][-1]] = value
            dest.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return tmp, reg

    def _with_repo(self, tmp):
        original = version_sync.REPO
        version_sync.REPO = tmp
        self.addCleanup(lambda: setattr(version_sync, "REPO", original))

    def test_fix_writes_the_canonical_value_everywhere(self):
        reg = version_sync.load_registry()
        drifted = ["0.6.3"] * len(reg["locations"])
        drifted[-1] = "0.5.0"  # the features.json shape of the real bug
        tmp, reg = self._temp_repo(drifted)
        self._with_repo(tmp)

        rows = version_sync.read_all(reg)
        self.assertTrue(any(v == "0.5.0" for _, _, v, _ in rows), "fixture did not drift")

        version_sync.write_version(reg, version_sync.canonical_version(reg))
        values = {v for _, _, v, _ in version_sync.read_all(reg)}
        self.assertEqual(values, {"0.6.3"}, "--fix left a location unwritten")

    def test_bump_writes_every_location_not_just_three(self):
        reg = version_sync.load_registry()
        tmp, reg = self._temp_repo(["0.6.3"] * len(reg["locations"]))
        self._with_repo(tmp)

        target = version_sync.bump(version_sync.canonical_version(reg), "minor")
        version_sync.write_version(reg, target)
        values = {v for _, _, v, _ in version_sync.read_all(reg)}
        self.assertEqual(
            values, {"0.7.0"},
            "a bump must write ALL registered locations — writing three of six is the "
            "original defect",
        )

    def test_set_rejects_a_non_semver(self):
        reg = version_sync.load_registry()
        with self.assertRaises(SystemExit):
            version_sync.write_version(reg, "0.7")


class TestChangelogRoll(unittest.TestCase):
    """--release-changelog must be idempotent and must never emit an empty version heading."""

    def _repo_with_changelog(self, text):
        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "CHANGELOG.md").write_text(text, encoding="utf-8")
        original = version_sync.REPO
        version_sync.REPO = tmp
        self.addCleanup(lambda: setattr(version_sync, "REPO", original))
        return tmp

    POPULATED = (
        "# Changelog\n\n## [Unreleased]\n\n### Added\n\n- a shipped thing\n\n"
        "## [0.6.1] — 2026-08-09\n\n- older\n"
    )

    def test_roll_renames_and_opens_a_fresh_unreleased(self):
        tmp = self._repo_with_changelog(self.POPULATED)
        msg = version_sync.release_changelog("0.7.0", "2026-09-02")
        out = (tmp / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("0.7.0", msg)
        self.assertIn("## [0.7.0] — 2026-09-02", out)
        self.assertIn("## [Unreleased]", out)
        self.assertLess(
            out.index("## [Unreleased]"),
            out.index("## [0.7.0]"),
            "the fresh [Unreleased] must sit above the released section",
        )
        self.assertIn("- a shipped thing", out)

    def test_roll_is_idempotent(self):
        tmp = self._repo_with_changelog(self.POPULATED)
        version_sync.release_changelog("0.7.0", "2026-09-02")
        first = (tmp / "CHANGELOG.md").read_text(encoding="utf-8")
        msg = version_sync.release_changelog("0.7.0", "2026-09-02")
        self.assertEqual(first, (tmp / "CHANGELOG.md").read_text(encoding="utf-8"))
        self.assertIn("nothing to do", msg)

    def test_empty_unreleased_produces_no_version_heading(self):
        tmp = self._repo_with_changelog("# Changelog\n\n## [Unreleased]\n\n## [0.6.1] — 2026-08-09\n")
        msg = version_sync.release_changelog("0.7.0", "2026-09-02")
        out = (tmp / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertNotIn("## [0.7.0]", out, "an empty [Unreleased] must not become a version heading")
        self.assertIn("empty", msg)

    def test_missing_changelog_is_not_an_error(self):
        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        original = version_sync.REPO
        version_sync.REPO = tmp
        self.addCleanup(lambda: setattr(version_sync, "REPO", original))
        self.assertIn("nothing to do", version_sync.release_changelog("0.7.0", "2026-09-02"))

    def test_workflow_rolls_the_changelog_and_stages_it(self):
        wf = _workflow_code()
        self.assertIn("--release-changelog", wf)
        self.assertRegex(wf, r"git add[^\n]*CHANGELOG\.md")
