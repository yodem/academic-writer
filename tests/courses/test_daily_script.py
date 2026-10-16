import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "courses-daily.sh.example"


def run_dry(tmp_path, chrome_running, extra_env=None, queue=False):
    home = tmp_path / "home"
    term = home / ".academic-writer" / "courses" / "term"
    (term / "queue").mkdir(parents=True)
    (term / "term.json").write_text(json.dumps({"term": "t"}))
    (term / "cohen.json").write_text(json.dumps({"slug": "cohen"}))
    if queue:
        (term / "queue" / "job.json").write_text("{}")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    pgrep = stubs / "pgrep"
    pgrep.write_text(f"#!/bin/sh\nexit {0 if chrome_running else 1}\n")
    pgrep.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "COURSES_TERM_DIR": str(term), "COURSES_DRY": "1",
           "PATH": f"{stubs}:{os.environ['PATH']}", **(extra_env or {})}
    out = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)
    return out, [line for line in out.stdout.splitlines() if line.startswith("PLAN: ")]


def test_syntax():
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0


def test_chrome_running_plans_watch_in_order(tmp_path):
    out, plans = run_dry(tmp_path, True, queue=True)
    assert out.returncode == 0, out.stderr
    keys = ["courses.py daily", "claude -p --chrome", "courses.py wispr-scan", "lesson-notes --pending", "toc_audit.py --all",
            "chores digest", "courses-sync-nanoclaw.sh"]
    idx = [next(i for i, p in enumerate(plans) if k in p) for k in keys]
    assert idx == sorted(idx) and len(plans) == len(keys)
    watch = plans[1]
    assert "courses.py wispr-scan" in plans[2]
    assert "/academic-writer:courses watch-lemida --all'" in watch
    assert "--model sonnet" in watch and "--plugin-dir" in watch
    for tool in ("mcp__claude-in-chrome__*", "Bash(rclone:*)", "Bash(pdftoppm:*)", "Bash(screencapture:*)", "Bash(trove ms show:*)"):
        assert tool in watch
    assert not any("chores add" in p for p in plans)
    assert not any("bookmarks" in p for p in plans)  # the Chrome bookmarks step is gone (it crashes Chrome; a dashboard replaces it)


def test_chrome_missing_adds_manual_chore_and_skips_watch(tmp_path):
    out, plans = run_dry(tmp_path, False)
    assert out.returncode == 0, out.stderr
    assert not any("claude -p --chrome" in p for p in plans)
    chore = next(i for i, p in enumerate(plans) if "chores add --kind manual" in p)
    assert "Open Chrome logged in to Lemida so tonight's scan can run" in plans[chore]
    assert chore == 1 and "courses.py daily" in plans[0]
    assert not any("lesson-notes" in p for p in plans)  # no queued jobs


def test_courses_only_is_appended_to_the_prompt(tmp_path):
    _, plans = run_dry(tmp_path, True, {"COURSES_ONLY": "cohen kane"})
    assert "watch-lemida cohen kane'" in next(p for p in plans if "claude -p --chrome" in p)


@pytest.mark.parametrize("chrome", [True, False])
def test_dry_run_writes_no_log(tmp_path, chrome):
    run_dry(tmp_path, chrome)
    assert not list((tmp_path / "home").rglob("daily-*.log"))


def run_live_with_failing_bookmarks(tmp_path):
    """Run the script for real (no COURSES_DRY) against a stub repo whose courses.py fails only `bookmarks`."""
    home = tmp_path / "home"
    term = home / ".academic-writer" / "courses" / "term"
    (term / "queue").mkdir(parents=True)
    repo = tmp_path / "repo"
    courses = repo / "src" / "scripts" / "courses" / "courses.py"
    courses.parent.mkdir(parents=True)
    courses.write_text("import sys\nsys.exit(5 if 'bookmarks' in sys.argv else 0)\n")
    (repo / "tools").mkdir()
    (repo / "tools" / "toc_audit.py").write_text("import sys\nsys.exit(0)\n")
    sync = home / ".academic-writer" / "bin" / "courses-sync-nanoclaw.sh"
    sync.parent.mkdir(parents=True)
    sync.write_text("#!/bin/sh\nexit 0\n")
    sync.chmod(0o755)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    pgrep = stubs / "pgrep"
    pgrep.write_text("#!/bin/sh\nexit 1\n")  # Chrome not running: no claude call, a chore is added instead
    pgrep.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "COURSES_TERM_DIR": str(term), "ACADEMIC_WRITER_REPO": str(repo),
           "PATH": f"{stubs}:{os.environ['PATH']}"}
    env.pop("COURSES_DRY", None)
    out = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)
    log = next((term / "logs").glob("daily-*.log"), None)
    return out, log.read_text() if log else ""


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="script hardcodes /usr/bin/python3")
def test_bookmarks_step_is_never_run(tmp_path):
    out, log = run_live_with_failing_bookmarks(tmp_path)  # the stub courses.py would exit 5 on `bookmarks`
    assert out.returncode == 0, out.stderr + log
    assert "bookmarks" not in log
    assert "-- nanoclaw-sync exit=0" in log
    assert log.index("-- digest") < log.index("-- nanoclaw-sync")
