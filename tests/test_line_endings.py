"""Shell scripts must stay LF on a Windows checkout (Git for Windows defaults to core.autocrlf=true).

.gitattributes pins eol=lf; these tests check the attribute git reports and that no shipped script holds a CR.
"""
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is needed to read attributes")

EXPLICIT = [
    "src/bin/aw-python",
    "plugins/academic-writer/bin/aw-python",
    "plugins/academic-writer/bin/aw",
    "src/hooks/bin/guard.sh",
    "plugins/academic-writer/hooks/bin/guard.sh",
]


def tracked():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p and (ROOT / p).is_file()]


def shebang_files():
    found = []
    for rel in tracked():
        with open(ROOT / rel, "rb") as handle:
            if handle.read(2) == b"#!":
                found.append(rel)
    return found


def eol_of(paths):
    out = subprocess.run(["git", "check-attr", "eol", "--", *paths], cwd=ROOT, capture_output=True, text=True,
                         check=True).stdout
    result = {}
    for line in out.splitlines():
        path, _, value = line.rsplit(": ", 2)
        result[path] = value
    return result


def test_explicit_shell_scripts_are_lf():
    got = eol_of(EXPLICIT)
    assert got == {p: "lf" for p in EXPLICIT}


def test_every_shebang_script_and_shell_file_is_lf():
    paths = sorted(set(shebang_files()) | {p for p in tracked() if p.endswith(".sh")})
    assert paths
    bad = {p: v for p, v in eol_of(paths).items() if v != "lf"}
    assert not bad, "not pinned to LF in .gitattributes: %s" % bad


def test_no_shipped_shell_script_contains_a_carriage_return():
    paths = sorted(set(shebang_files()) | {p for p in tracked() if p.endswith(".sh")})
    with_cr = [p for p in paths if b"\r" in (ROOT / p).read_bytes()]
    assert not with_cr, "CR found in: %s" % with_cr
