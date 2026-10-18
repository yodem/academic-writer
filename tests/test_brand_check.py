"""scripts/check-brand.py: colours, fonts, sizes and radii must come from the brand file."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK = ROOT / "scripts" / "check-brand.py"
FIX = ROOT / "tests" / "fixtures" / "brand"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECK), *args], capture_output=True, text=True, cwd=str(ROOT))


def test_good_passes():
    res = run(str(FIX / "good.css"))
    assert res.returncode == 0, res.stdout + res.stderr
    assert res.stdout == ""


def test_bad_reports_each_kind():
    res = run(str(FIX / "bad.css"))
    assert res.returncode == 1, res.stdout + res.stderr
    lines = res.stdout.strip().splitlines()
    kinds = [
        ("bad.css:2", "#ff0000", "colour literal"),
        ("bad.css:3", "rebeccapurple", "colour literal"),
        ("bad.css:4", "rgb(10, 20, 30)", "colour literal"),
        ("bad.css:5", "Comic Sans MS", "font-family"),
        ("bad.css:6", "17px", "font-size"),
        ("bad.css:7", "12px", "border-radius"),
        ("bad.css:8", "--m-not-a-token", "unknown token"),
    ]
    assert len(lines) == len(kinds), res.stdout
    for line, (where, value, reason) in zip(lines, kinds):
        assert where in line and value in line and reason in line, line


def test_repo_clean():
    res = run("--surface", "site")
    assert res.returncode == 0, res.stdout + res.stderr
