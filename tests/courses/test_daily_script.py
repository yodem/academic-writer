import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "courses-daily.sh.example"


def run_dry(tmp_path, chrome_running, extra_env=None, queue=False, handoff=False, extra_courses=()):
    home = tmp_path / "home"
    term = home / ".academic-writer" / "courses" / "term"
    (term / "queue").mkdir(parents=True)
    (term / "term.json").write_text(json.dumps({"term": "t"}))
    (term / "cohen.json").write_text(json.dumps({"slug": "cohen"}))
    for course in extra_courses:
        (term / f"{course['slug']}.json").write_text(json.dumps(course))
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
    keys = ["courses.py daily", "claude -p --chrome", "lemida-coverage-check", "courses.py wispr-scan", "refs.py --registry", "extract-queue", "lesson-notes --pending", "toc_audit.py --all",
            "chores digest", "courses-sync-nanoclaw.sh"]
    idx = [next(i for i, p in enumerate(plans) if k in p) for k in keys]
    assert idx == sorted(idx) and len(plans) == len(keys)
    watch = plans[1]
    assert "lemida-coverage-check --date" in plans[2] and "--run-id" in plans[2] and "courses.py" in plans[2]
    assert "courses.py wispr-scan" in plans[3]
    assert plans[4].endswith("fetch-queue") and "refs.py --registry" in plans[4]
    assert plans[5].endswith("extract-queue") and "refs.py --registry" in plans[5]
    assert "/academic-writer:courses watch-lemida --all --run-id " in watch
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
    assert any("lemida-coverage-check" in p for p in plans)  # the coverage check runs even when the watch was skipped
    assert not any("lesson-notes" in p for p in plans)  # no queued jobs


def test_courses_only_is_appended_to_the_prompt(tmp_path):
    _, plans = run_dry(tmp_path, True, {"COURSES_ONLY": "cohen kane"})
    assert "watch-lemida cohen kane --run-id " in next(p for p in plans if "claude -p --chrome" in p)
    coverage = next(p for p in plans if "lemida-coverage-check" in p)
    assert '--courses "cohen kane"' in coverage


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


def test_daily_dry_skips_finished(tmp_path):
    old = {"slug": "oldcourse", "status": "finished", "book_id": "BOOK-OLD-123"}
    out, plans = run_dry(tmp_path, True, queue=True, extra_courses=[old])
    assert out.returncode == 0, out.stderr
    assert "oldcourse" not in out.stdout and "BOOK-OLD-123" not in out.stdout
    assert any("courses.py daily" in p for p in plans)  # the run itself still plans its steps


def test_lemida_coverage_step_runs_right_after_watch(tmp_path):
    _, plans = run_dry(tmp_path, True)
    watch = next(i for i, p in enumerate(plans) if "claude -p --chrome" in p)
    coverage = next(i for i, p in enumerate(plans) if "lemida-coverage-check" in p)
    assert coverage == watch + 1
    assert "courses.py" in plans[coverage] and f"--date {datetime.now().strftime('%Y-%m-%d')}" in plans[coverage]


def _run_id_of(plan):
    tokens = plan.replace("'", " ").split()
    return tokens[tokens.index("--run-id") + 1]


def test_watch_and_coverage_share_one_run_id(tmp_path):
    _, plans = run_dry(tmp_path, True)
    watch = next(p for p in plans if "claude -p --chrome" in p)
    coverage = next(p for p in plans if "lemida-coverage-check" in p)
    run_id = _run_id_of(watch)
    assert run_id and run_id == _run_id_of(coverage)
    assert run_id.startswith(datetime.now().strftime("%Y-%m-%d"))  # date + time + pid, unique per run
    assert run_id.split("-")[-1].isdigit() and len(run_id) > len("2026-01-01T000000-1")


def test_coverage_is_unscoped_without_courses_only(tmp_path):
    _, plans = run_dry(tmp_path, True)
    coverage = next(p for p in plans if "lemida-coverage-check" in p)
    assert "--courses" not in coverage


def test_coverage_contract_documents_run_id_and_complete_notifications():
    skill = (SCRIPT.parents[1] / "src" / "skills" / "courses" / "SKILL.md").read_text(encoding="utf-8")
    watch = (SCRIPT.parents[1] / "src" / "skills" / "courses" / "references" / "lemida-watch.md").read_text(encoding="utf-8")
    assert '"run_id"' in skill and "--run-id" in skill
    assert '"complete": true' in skill and "notifications.complete" in skill
    assert "run_id" in watch and "complete" in watch


def run_extract_only(tmp_path, *, dry, jobs=0, handoff=False, refs_body="import sys\nsys.exit(0)\n", hold_lock=False,
                     lock_wait="0"):
    """`courses-daily.sh --extract-only` against a stub repo; claude is a stub that records its prompt."""
    home = tmp_path / "home"
    term = home / ".academic-writer" / "courses" / "term"
    (term / "queue" / "extract").mkdir(parents=True)
    for n in range(jobs):
        (term / "queue" / "extract" / f"2026102{n}T000000-cohen.json").write_text("{}")
    if handoff:
        (term / "queue" / "extract" / "ingest").mkdir()
        (term / "queue" / "extract" / "ingest" / "cohen-aaaaaaaa.json").write_text("{}")
    holder = None
    if hold_lock:  # another run holds the flock until this process exits
        (term / "locks").mkdir(parents=True)
        holder = subprocess.Popen([sys.executable, "-c", "import fcntl,sys,time\nf=open(sys.argv[1],'a')\n"
                                   "fcntl.flock(f, fcntl.LOCK_EX)\nprint('held', flush=True)\ntime.sleep(60)\n",
                                   str(term / "locks" / "extract.lock")], stdout=subprocess.PIPE, text=True)
        assert holder.stdout.readline().strip() == "held"
    repo = tmp_path / "repo"
    scripts = repo / "src" / "scripts" / "courses"
    scripts.mkdir(parents=True)
    (scripts / "courses.py").write_text("import sys\nsys.exit(0)\n")
    (scripts / "refs.py").write_text(refs_body)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    calls = tmp_path / "claude-calls"
    (stubs / "claude").write_text(f"#!/bin/sh\ncat >> {calls}\necho >> {calls}\nexit 0\n")
    (stubs / "claude").chmod(0o755)
    env = {**os.environ, "HOME": str(home), "COURSES_TERM_DIR": str(term), "ACADEMIC_WRITER_REPO": str(repo),
           "EXTRACT_PY": "/usr/bin/python3", "EXTRACT_LOCK_WAIT": lock_wait, "PATH": f"{stubs}:{os.environ['PATH']}"}
    env.pop("COURSES_DRY", None)
    if dry:
        env["COURSES_DRY"] = "1"
    try:
        out = subprocess.run(["bash", str(SCRIPT), "--extract-only"], env=env, capture_output=True, text=True, timeout=60)
    finally:
        if holder:
            holder.kill()
            holder.wait()
    log = next((term / "logs").glob("extract-now-*.log"), None) if (term / "logs").is_dir() else None
    return out, term, (log.read_text() if log else ""), (calls.read_text() if calls.exists() else "")


def test_extract_only_without_a_job_is_silent(tmp_path):
    out, term, log, calls = run_extract_only(tmp_path, dry=False, handoff=True)
    assert out.returncode == 0 and out.stdout == "" and log == "" and calls == ""  # an old ingest file alone never wakes Claude
    assert not (term / "logs").exists()


def test_extract_only_dry_plans_c4_and_c5_and_nothing_else(tmp_path):
    out, _, _, _ = run_extract_only(tmp_path, dry=True, jobs=1, handoff=True)
    plans = [ln for ln in out.stdout.splitlines() if ln.startswith("PLAN: ")]
    assert out.returncode == 0, out.stderr
    assert len(plans) == 2 and plans[0].endswith("extract-queue") and "extract-handoff" in plans[1]


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="script hardcodes /usr/bin/python3")
def test_extract_only_runs_c4_then_c5_and_releases_the_lock(tmp_path):
    drain = ("import pathlib,sys\nreg=pathlib.Path(sys.argv[2])\nq=reg/'queue'/'extract'\n(q/'done').mkdir(exist_ok=True)\n"
             "(q/'ingest').mkdir(exist_ok=True)\nfor j in q.glob('*.json'):\n    (q/'ingest'/j.name).write_text('{}')\n"
             "    j.rename(q/'done'/j.name)\n")
    out, term, log, calls = run_extract_only(tmp_path, dry=False, jobs=2, refs_body=drain)
    assert out.returncode == 0, out.stderr + log
    assert log.index("-- extract-queue exit=0") < log.index("-- extract-handoff exit=0")
    assert log.count("-- extract-queue exit") == 1  # the queue emptied: one round
    assert calls.count("/academic-writer:courses extract-handoff") == 1
    assert_lock_free(term)


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="script hardcodes /usr/bin/python3")
def test_extract_only_does_not_loop_on_a_job_c4_cannot_finish(tmp_path):
    out, _, log, _ = run_extract_only(tmp_path, dry=False, jobs=1, refs_body="import sys\nsys.exit(1)\n")
    assert out.returncode == 1
    assert log.count("-- extract-queue exit=1") == 1


def assert_lock_free(term):
    """The script released its flock: a fresh process can take it without waiting."""
    probe = subprocess.run([sys.executable, "-c", "import fcntl,sys\nf=open(sys.argv[1],'a')\n"
                            "fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)\n", str(term / "locks" / "extract.lock")])
    assert probe.returncode == 0


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="script hardcodes /usr/bin/python3")
def test_extract_only_skips_while_another_run_holds_the_lock(tmp_path):
    out, _, log, calls = run_extract_only(tmp_path, dry=False, jobs=1, hold_lock=True)
    assert out.returncode == 1 and "c4/c5 skipped" in log and calls == ""
    assert "-- extract-queue" not in log


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="script hardcodes /usr/bin/python3")
def test_a_lock_file_left_by_a_dead_run_does_not_block(tmp_path):
    term = tmp_path / "home" / ".academic-writer" / "courses" / "term"
    (term / "locks").mkdir(parents=True)
    (term / "locks" / "extract.lock").write_text("")
    (term / "locks" / "extract.lock.owner").write_text("99999 earlier")
    out, _, log, _ = run_extract_only(tmp_path, dry=False, jobs=1)
    assert out.returncode == 0 and "-- extract-queue exit=0" in log


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="script hardcodes /usr/bin/python3")
def test_a_stuck_job_left_beside_a_finished_one_is_not_retried(tmp_path):
    finish_first = ("import pathlib,sys\nq=pathlib.Path(sys.argv[2])/'queue'/'extract'\n(q/'done').mkdir(exist_ok=True)\n"
                    "(q/'ingest').mkdir(exist_ok=True)\n(q/'ingest'/'x.json').write_text('{}')\n"
                    "j=sorted(q.glob('*.json'))[0]\nj.rename(q/'done'/j.name)\n")
    out, _, log, calls = run_extract_only(tmp_path, dry=False, jobs=2, refs_body=finish_first)
    assert out.returncode == 0, out.stderr + log
    assert log.count("-- extract-queue exit") == 1 and calls.count("extract-handoff") == 1


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="script hardcodes /usr/bin/python3")
def test_a_job_that_arrives_during_a_round_gets_a_second_round(tmp_path):
    late = ("import pathlib,sys\nq=pathlib.Path(sys.argv[2])/'queue'/'extract'\n(q/'done').mkdir(exist_ok=True)\n"
            "first=not (q/'done'/'late.json').exists() and not (q/'late.json').exists()\n"
            "[j.rename(q/'done'/j.name) for j in q.glob('*.json')]\n"
            "first and (q/'late.json').write_text('{}')\n")
    out, _, log, _ = run_extract_only(tmp_path, dry=False, jobs=1, refs_body=late)
    assert out.returncode == 0, out.stderr + log
    assert log.count("-- extract-queue exit=0") == 2


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="script hardcodes /usr/bin/python3")
def test_nightly_takes_the_extract_lock_around_c4(tmp_path):
    out, log = run_live_with_failing_bookmarks(tmp_path)
    assert out.returncode == 0, out.stderr + log
    assert "-- extract-queue exit=0" in log
    assert_lock_free(tmp_path / "home" / ".academic-writer" / "courses" / "term")
