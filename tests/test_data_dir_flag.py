"""Skills reach home.py, setup_checks.py and courses.py through the Bash tool, which gets no
CLAUDE_PLUGIN_DATA. They pass --data-dir "${CLAUDE_PLUGIN_DATA}" instead, as they do for aw."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src" / "scripts"


def _env(tmp_path: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PLUGIN_DATA", "ACADEMIC_HOME", "ACADEMIC_COURSES_DIR")}
    env["HOME"] = str(tmp_path / "userhome")
    return env


def _run(args: list, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable] + args, env=env, capture_output=True, text=True)


def test_home_set_and_show_with_data_dir_and_no_env(tmp_path):
    env = _env(tmp_path)
    data, home = tmp_path / "data", tmp_path / "Academic"
    home.mkdir()
    r = _run([str(SCRIPTS / "home.py"), "--data-dir", str(data), "set", "--path", str(home), "--role", "student", "--name", "Ada"], env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "role: student" in (home / ".academic-helper" / "home.md").read_text(encoding="utf-8")
    shown = json.loads(_run([str(SCRIPTS / "home.py"), "--data-dir", str(data), "show"], env).stdout)
    assert shown["home"] == str(home) and shown["exists"] is True


def test_home_set_rejects_multiline_value_before_writing_anything(tmp_path):
    env = _env(tmp_path)
    data, home = tmp_path / "data", tmp_path / "Academic"
    home.mkdir()
    r = _run([str(SCRIPTS / "home.py"), "--data-dir", str(data), "set", "--path", str(home), "--name", "a\nb"], env)
    assert r.returncode == 2
    assert "error" in json.loads(r.stdout)
    assert "Traceback" not in r.stderr
    assert not (data / "home.json").exists()


def test_setup_checks_sees_home_through_data_dir(tmp_path):
    env = _env(tmp_path)
    data, home = tmp_path / "data", tmp_path / "Academic"
    home.mkdir()
    _run([str(SCRIPTS / "home.py"), "--data-dir", str(data), "set", "--path", str(home), "--role", "lecturer", "--name", "Ada"], env)
    checks = json.loads(_run([str(SCRIPTS / "setup_checks.py"), "--data-dir", str(data), "--json"], env).stdout)
    row = next(c for c in checks if c["id"] == "home")
    assert row["ok"] is True, row


def test_courses_accepts_data_dir(tmp_path):
    env = _env(tmp_path)
    r = _run([str(SCRIPTS / "courses" / "courses.py"), "--data-dir", str(tmp_path / "data"), "--help"], env)
    assert r.returncode == 0 and "--data-dir" in r.stdout


def test_skills_pass_data_dir_to_home_tools():
    offenders = []
    for md in (ROOT / "src" / "skills").rglob("*.md"):
        for n, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            for tool in ("scripts/home.py\"", "scripts/setup_checks.py\"", "scripts/courses/courses.py\" dashboard"):
                if "python3" in line and tool in line and "--data-dir \"${CLAUDE_PLUGIN_DATA}\"" not in line:
                    offenders.append("%s:%d" % (md.relative_to(ROOT), n))
    assert not offenders, offenders
