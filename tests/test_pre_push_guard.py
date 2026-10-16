"""The pre-push guard (.githooks/pre-push) in a throwaway repo with a bare remote."""
import os
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".githooks" / "pre-push"
ZERO = "0" * 40


def git(cwd, *args, env=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
                               "GIT_COMMITTER_EMAIL": "t@x", **(env or {})}).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "--bare", "-b", "main", str(remote))
    git(tmp_path, "init", "-b", "main", str(work))
    git(work, "config", "commit.gpgsign", "false")
    git(work, "remote", "add", "origin", str(remote))
    (work / "a").write_text("1")
    git(work, "add", "a")
    git(work, "commit", "-m", "base")
    git(work, "push", "-q", "origin", "main")
    return work


def merge_run(work, run):
    git(work, "checkout", "-q", "-b", f"ale/{run}/T1")
    (work / f"{run}.txt").write_text(run)
    git(work, "add", ".")
    git(work, "commit", "-m", f"task of {run}")
    git(work, "checkout", "-q", "main")
    git(work, "merge", "--no-ff", "-m", f"Merge branch 'ale/{run}/T1' into main", f"ale/{run}/T1")


def run_hook(work, env=None):
    head = git(work, "rev-parse", "HEAD")
    remote_sha = git(work, "rev-parse", "origin/main")
    stdin = f"refs/heads/main {head} refs/heads/main {remote_sha}\n"
    return subprocess.run(["bash", str(HOOK), "origin", "unused"], cwd=work, input=stdin, capture_output=True, text=True,
                          env={**os.environ, "ALE_ALLOW_RUNS": "", **(env or {})})


def test_plain_commits_pass_and_are_listed(repo):
    (repo / "b").write_text("2")
    git(repo, "add", "b")
    git(repo, "commit", "-m", "plain change")
    out = run_hook(repo)
    assert out.returncode == 0, out.stderr
    assert "plain change" in out.stdout


def test_ale_merge_of_an_unlisted_run_aborts(repo):
    merge_run(repo, "other-2026-10-01")
    out = run_hook(repo)
    assert out.returncode == 1
    assert "other-2026-10-01" in out.stderr and "ALE_ALLOW_RUNS" in out.stderr
    assert "Merge branch 'ale/other-2026-10-01/T1'" in out.stdout  # the commits are printed first


@pytest.mark.parametrize("allow", ["other-2026-10-01", "x-1, other-2026-10-01", "other-2026-10-01,x-1"])
def test_listed_run_is_allowed(repo, allow):
    merge_run(repo, "other-2026-10-01")
    assert run_hook(repo, {"ALE_ALLOW_RUNS": allow}).returncode == 0


def test_one_unlisted_run_among_listed_still_aborts(repo):
    merge_run(repo, "mine-1")
    merge_run(repo, "theirs-2")
    assert run_hook(repo, {"ALE_ALLOW_RUNS": "mine-1"}).returncode == 1


def test_new_branch_push_is_checked_against_the_remote(repo):
    merge_run(repo, "theirs-2")
    head = git(repo, "rev-parse", "HEAD")
    out = subprocess.run(["bash", str(HOOK), "origin", "u"], cwd=repo, input=f"refs/heads/new {head} refs/heads/new {ZERO}\n",
                         capture_output=True, text=True, env={**os.environ, "ALE_ALLOW_RUNS": ""})
    assert out.returncode == 1


def test_no_verify_bypasses_the_hook_through_git(repo, tmp_path):
    merge_run(repo, "theirs-2")
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "pre-push").write_text(HOOK.read_text())
    (hooks / "pre-push").chmod(0o755)
    git(repo, "config", "core.hooksPath", str(hooks))
    blocked = subprocess.run(["git", "push", "origin", "main"], cwd=repo, capture_output=True, text=True, env={**os.environ, "ALE_ALLOW_RUNS": ""})
    assert blocked.returncode != 0
    assert subprocess.run(["git", "push", "--no-verify", "origin", "main"], cwd=repo, capture_output=True, text=True).returncode == 0
