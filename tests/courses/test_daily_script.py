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
    keys = ["courses.py daily", "claude -p --chrome", "lesson-notes --pending", "toc_audit.py --all",
            "chores digest", "courses-sync-nanoclaw.sh"]
    idx = [next(i for i, p in enumerate(plans) if k in p) for k in keys]
    assert idx == sorted(idx) and len(plans) == len(keys)
    watch = plans[1]
    assert "/academic-writer:courses watch-lemida --all'" in watch
    assert "--model sonnet" in watch and "--plugin-dir" in watch
    for tool in ("mcp__claude-in-chrome__*", "Bash(rclone:*)", "Bash(pdftoppm:*)", "Bash(screencapture:*)", "Bash(trove ms show:*)"):
        assert tool in watch
    assert not any("chores add" in p for p in plans)


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
    assert "watch-lemida --all cohen kane'" in next(p for p in plans if "claude -p --chrome" in p)


@pytest.mark.parametrize("chrome", [True, False])
def test_dry_run_writes_no_log(tmp_path, chrome):
    run_dry(tmp_path, chrome)
    assert not list((tmp_path / "home").rglob("daily-*.log"))
