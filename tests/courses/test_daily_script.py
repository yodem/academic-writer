import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "courses-daily.sh.example"


def run_dry(tmp_path, chrome_running, extra_env=None, queue=False, handoff=False):
    home = tmp_path / "home"
    term = home / ".academic-writer" / "courses" / "term"
    (term / "queue").mkdir(parents=True)
    (term / "term.json").write_text(json.dumps({"term": "t"}))
    (term / "cohen.json").write_text(json.dumps({"slug": "cohen"}))
    if queue:
        (term / "queue" / "job.json").write_text("{}")
    if handoff:
        (term / "queue" / "extract" / "handoff").mkdir(parents=True)
        (term / "queue" / "extract" / "handoff" / "cohen-source-aaaaaaaa.json").write_text("{}")
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
    keys = ["courses.py daily", "claude -p --chrome", "courses.py wispr-scan", "refs.py --registry", "extract-queue", "lesson-notes --pending", "toc_audit.py --all",
            "chores digest", "courses-sync-nanoclaw.sh"]
    idx = [next(i for i, p in enumerate(plans) if k in p) for k in keys]
    assert idx == sorted(idx) and len(plans) == len(keys)
    watch = plans[1]
    assert "courses.py wispr-scan" in plans[2]
    assert plans[3].endswith("fetch-queue") and "refs.py --registry" in plans[3]
    assert plans[4].endswith("extract-queue") and "refs.py --registry" in plans[4]
    assert "/academic-writer:courses watch-lemida --all'" in watch
    assert "--model sonnet" in watch and "--plugin-dir" in watch
    for tool in ("mcp__claude-in-chrome__*", "Bash(rclone:*)", "Bash(pdftoppm:*)", "Bash(screencapture:*)", "Bash(trove ms show:*)"):
        assert tool in watch
    for tool in ("pdftotext", "pandoc", "trove items", "tesseract", "aw:"):  # the watch only downloads: no extraction, no Trove upload
        assert tool not in watch
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


def run_live_with_failing_bookmarks(tmp_path, refs_exit=0):
    """Run the script for real (no COURSES_DRY) against a stub repo whose courses.py fails only `bookmarks`."""
    home = tmp_path / "home"
    term = home / ".academic-writer" / "courses" / "term"
    (term / "queue").mkdir(parents=True)
    repo = tmp_path / "repo"
    courses = repo / "src" / "scripts" / "courses" / "courses.py"
    courses.parent.mkdir(parents=True)
    courses.write_text("import sys\nsys.exit(5 if 'bookmarks' in sys.argv else 0)\n")
    (courses.parent / "refs.py").write_text(f"import sys\nsys.exit({refs_exit})\n")
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


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="script hardcodes /usr/bin/python3")
def test_fetch_queue_failure_is_counted_but_later_steps_run(tmp_path):
    out, log = run_live_with_failing_bookmarks(tmp_path, refs_exit=1)
    assert out.returncode == 1
    assert "-- fetch-queue exit=1" in log and "-- nanoclaw-sync exit=0" in log
    assert log.index("-- wispr-scan exit") < log.index("-- fetch-queue") < log.index("-- digest")


def test_extract_handoff_step_runs_only_when_python_left_something_for_claude(tmp_path):
    _, plans = run_dry(tmp_path / "none", True)
    assert not any("extract-handoff" in p for p in plans)
    _, plans = run_dry(tmp_path / "some", True, handoff=True)
    idx = [i for i, p in enumerate(plans) if "extract-queue" in p or "extract-handoff" in p]
    assert [("extract-queue" in plans[i]) for i in idx] == [True, False] and idx[1] == idx[0] + 1
    step = plans[idx[1]]
    assert "claude -p" in step and "--model sonnet" in step and "pdftotext" not in step and "Bash(pdftoppm:*)" in step


def test_subagent_model_is_set_near_academic_home_and_no_keychain_key_is_read():
    text = SCRIPT.read_text(encoding="utf-8")
    line = 'export CLAUDE_CODE_SUBAGENT_MODEL="${CLAUDE_CODE_SUBAGENT_MODEL:-sonnet}"'
    assert 0 < text.index(line) - text.index("export ACADEMIC_HOME=") < 200
    assert "security find-generic-password" not in text and "export ANNAS_ARCHIVE_KEY" not in text


def test_nothing_drains_queue_sources_by_default():
    """The add-source Trove jobs (queue/sources) wait until the student chooses that file on the dashboard."""
    script = SCRIPT.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in script.splitlines() if not ln.lstrip().startswith("#"))
    assert "queue/sources" not in code and "queue/\\*" not in code
    skill = (SCRIPT.parents[1] / "src" / "skills" / "courses" / "SKILL.md").read_text(encoding="utf-8")
    watch = (SCRIPT.parents[1] / "src" / "skills" / "courses" / "references" / "lemida-watch.md").read_text(encoding="utf-8")
    for text in (skill, watch):
        assert "queue/sources" in text  # documented ...
    assert "never drained" in skill and "only the file the student chose" in skill  # ... as waiting, not as a step to run
    assert "drain queue/sources" not in skill.lower() and "process queue/sources" not in skill.lower()
