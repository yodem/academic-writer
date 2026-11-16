"""bin/aw-python (the Python resolver) and hooks/bin/guard.sh, run with fake executables on a temp PATH.

These are what a Windows newcomer hits first: the Microsoft Store python stub, no Python at all, no Node.
"""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
AW_PYTHON = ROOT / "src" / "bin" / "aw-python"
GUARD = ROOT / "src" / "hooks" / "bin" / "guard.sh"
SH = shutil.which("sh") or "/bin/sh"

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX sh fixtures; the Windows CI job runs the shell steps")


def fake(dirpath, name, body):
    path = pathlib.Path(dirpath) / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)


def resolver(path_dirs, *args):
    env = {"PATH": os.pathsep.join(str(d) for d in path_dirs) + os.pathsep + "/usr/bin:/bin"}
    # /usr/bin may hold a real python3: hide it by shadowing every candidate name in the first directory.
    return subprocess.run([SH, str(AW_PYTHON), *args], capture_output=True, text=True, env=env, timeout=30)


@pytest.fixture
def empty_candidates():
    """A directory whose python3, python and py all fail, so a real interpreter in /usr/bin never answers."""
    with tempfile.TemporaryDirectory() as d:
        for name in ("python3", "python", "py"):
            fake(d, name, "echo 'Python was not found; run without arguments to install from the Microsoft Store' >&2; exit 9")
        yield pathlib.Path(d)


def test_store_stub_is_skipped_and_python_is_used(empty_candidates):
    with tempfile.TemporaryDirectory() as good:
        fake(good, "python", 'if [ "$1" = "--version" ]; then echo "Python 3.12.1"; else echo "ran:$*"; fi')
        p = resolver([good, empty_candidates], "script.py", "--flag")  # `good` comes first for `python` only
        # python3 is the Store stub in empty_candidates; python in `good` shadows its python
        assert p.returncode == 0, p.stderr
        assert p.stdout.strip() == "ran:script.py --flag"


def test_python3_is_preferred_when_it_works(empty_candidates):
    with tempfile.TemporaryDirectory() as good:
        fake(good, "python3", 'if [ "$1" = "--version" ]; then echo "Python 3.11.0"; else echo "p3:$*"; fi')
        fake(good, "python", 'if [ "$1" = "--version" ]; then echo "Python 3.9.0"; else echo "p:$*"; fi')
        p = resolver([good, empty_candidates], "x")
        assert p.stdout.strip() == "p3:x"


def test_python_2_is_not_accepted(empty_candidates):
    with tempfile.TemporaryDirectory() as old:
        fake(old, "python", 'echo "Python 2.7.18" >&2')  # Python 2 prints its version on stderr
        p = resolver([old, empty_candidates], "x")
        assert p.returncode == 127


def test_py_launcher_is_the_last_resort(empty_candidates):
    with tempfile.TemporaryDirectory() as good:
        fake(good, "py", 'if [ "$2" = "--version" ]; then echo "Python 3.12.0"; else echo "py:$*"; fi')
        p = resolver([good, empty_candidates], "script.py")
        assert p.returncode == 0, p.stderr
        assert p.stdout.strip() == "py:-3 script.py"


def test_none_found_exits_127_with_one_plain_line(empty_candidates):
    p = resolver([empty_candidates], "script.py")
    assert p.returncode == 127
    lines = [ln for ln in p.stderr.splitlines() if ln.strip()]
    assert len(lines) == 1 and "Python 3" in lines[0] and "/academic-writer:setup" in lines[0]
    assert p.stdout == ""


def test_exit_code_and_arguments_pass_through(empty_candidates):
    with tempfile.TemporaryDirectory() as good:
        fake(good, "python3", 'if [ "$1" = "--version" ]; then echo "Python 3.12.0"; else exit 7; fi')
        assert resolver([good, empty_candidates], "x").returncode == 7


def run_guard(env_extra, stdin="{}", args=("lifecycle/session-env",)):
    # A PATH with sh and the coreutils the script uses, and no node.
    env = {"PATH": "/usr/bin:/bin", **env_extra}
    return subprocess.run([SH, str(GUARD), *args], input=stdin, capture_output=True, text=True, env=env, timeout=30)


@pytest.mark.skipif(shutil.which("node", path="/usr/bin:/bin") is not None, reason="node is in /usr/bin here")
def test_guard_without_node_prints_once_per_session():
    with tempfile.TemporaryDirectory() as data:
        env = {"CLAUDE_PLUGIN_DATA": data}
        first = run_guard(env, json.dumps({"session_id": "s-1"}))
        assert first.returncode == 0
        assert "Academic Writer needs Node.js: run /academic-writer:setup" in first.stdout + first.stderr
        again = run_guard(env, json.dumps({"session_id": "s-1"}))
        assert again.returncode == 0 and again.stdout.strip() == ""
        other = run_guard(env, json.dumps({"session_id": "s-2"}))
        assert "Node.js" in other.stdout + other.stderr


def test_guard_with_node_passes_arguments_and_stdin_through():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    with tempfile.TemporaryDirectory() as root:
        hooks_bin = pathlib.Path(root) / "hooks" / "bin"
        hooks_bin.mkdir(parents=True)
        (hooks_bin / "run-hook.mjs").write_text(
            "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{console.log(JSON.stringify({args:process.argv.slice(2),stdin:s}));process.exit(3)})\n")
        env = {"PATH": os.path.dirname(node) + ":/usr/bin:/bin", "CLAUDE_PLUGIN_ROOT": root}
        p = subprocess.run([SH, str(GUARD), "lifecycle/x", "extra"], input='{"a":1}', capture_output=True, text=True,
                           env=env, timeout=30)
        assert p.returncode == 3  # the hook's own exit status is kept
        assert json.loads(p.stdout) == {"args": ["lifecycle/x", "extra"], "stdin": '{"a":1}'}


def test_obsolete_python3_is_skipped_for_a_supported_python(empty_candidates):
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as good:
        fake(old, "python3", 'if [ "$1" = "--version" ]; then echo "Python 3.6.15"; else echo "old:$*"; fi')
        fake(good, "python", 'if [ "$1" = "--version" ]; then echo "Python 3.12.1"; else echo "ran:$*"; fi')
        p = resolver([old, good, empty_candidates], "script.py")
        assert p.returncode == 0, p.stderr
        assert p.stdout.strip() == "ran:script.py"


def test_only_an_obsolete_python_exits_127(empty_candidates):
    with tempfile.TemporaryDirectory() as old:
        fake(old, "python3", 'echo "Python 3.8.18"')
        p = resolver([old, empty_candidates], "script.py")
        assert p.returncode == 127
        assert "3.9" in p.stderr


def test_minimum_matches_setup_checks():
    import re
    script = AW_PYTHON.read_text()
    checks = (ROOT / "src" / "scripts" / "setup_checks.py").read_text(encoding="utf-8")
    shell_minor = int(re.search(r"^MIN_MINOR=(\d+)", script, re.M).group(1))
    major, minor = re.search(r"^MIN_PYTHON = \((\d+), (\d+)\)", checks, re.M).groups()
    assert (3, shell_minor) == (int(major), int(minor))
    cli = (ROOT / "src" / "cli" / "src" / "python.ts").read_text(encoding="utf-8")
    assert int(re.search(r"MIN_PYTHON_MINOR = (\d+)", cli).group(1)) == int(minor)


def test_aw_python_runs_python_in_utf8_mode():
    # A real interpreter is needed for sys.flags; the host PATH has one in CI and on a developer machine.
    if shutil.which("python3") is None and shutil.which("python") is None:
        pytest.skip("no Python on PATH")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    p = subprocess.run([SH, str(AW_PYTHON), "-c",
                        "import sys,os;print(os.environ.get('PYTHONUTF8'), sys.flags.utf8_mode, os.environ.get('PYTHONIOENCODING'))"],
                       capture_output=True, text=True, env=env, timeout=30)
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == "1 1 utf-8"


def test_a_hung_candidate_is_skipped_within_the_probe_bound(empty_candidates):
    import time
    with tempfile.TemporaryDirectory() as hung, tempfile.TemporaryDirectory() as good:
        # python3 never answers --version (and leaves a child behind holding its output); python works.
        fake(hung, "python3", 'if [ "$1" = "--version" ]; then sleep 40; echo "Python 3.12.0"; else echo "hung:$*"; fi')
        fake(good, "python", 'if [ "$1" = "--version" ]; then echo "Python 3.12.1"; else echo "ran:$*"; fi')
        start = time.monotonic()
        p = resolver([hung, good, empty_candidates], "script.py")
        elapsed = time.monotonic() - start
        assert p.returncode == 0, p.stderr
        assert p.stdout.strip() == "ran:script.py"
        assert elapsed < 15, f"resolver took {elapsed:.1f}s with a hung candidate"


def test_a_working_python_is_not_slowed_by_the_probe_bound(empty_candidates):
    import time
    with tempfile.TemporaryDirectory() as good:
        fake(good, "python3", 'if [ "$1" = "--version" ]; then echo "Python 3.12.0"; else echo "p3:$*"; fi')
        start = time.monotonic()
        p = resolver([good, empty_candidates], "x")
        assert p.stdout.strip() == "p3:x"
        assert time.monotonic() - start < 3


@pytest.mark.skipif(shutil.which("node", path="/usr/bin:/bin") is not None, reason="node is in /usr/bin here")
def test_guard_concurrent_runs_print_once():
    with tempfile.TemporaryDirectory() as data:
        env = {"PATH": "/usr/bin:/bin", "CLAUDE_PLUGIN_DATA": data}
        stdin = json.dumps({"session_id": "race"})
        procs = [subprocess.Popen([SH, str(GUARD), "lifecycle/session-env"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
                 for _ in range(16)]
        for p in procs:  # hand every run its input before reading any output, so they overlap
            p.stdin.write(stdin)
        for p in procs:
            p.stdin.close()
        outs = [(p.stdout.read(), p.stderr.read()) for p in procs]
        for p in procs:
            p.wait(timeout=30)
        assert all(p.returncode == 0 for p in procs)
        printed = sum((o + e).count("needs Node.js") for o, e in outs)
        assert printed == 1, outs
