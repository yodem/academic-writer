import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_private_dirs_ignored():
    for rel in (".superpowers/x", ".playwright-mcp/x", "test-results/x", "playwright-report/x"):
        res = subprocess.run(["git", "check-ignore", "-q", rel], cwd=ROOT)
        assert res.returncode == 0, f"{rel} is not git-ignored"
