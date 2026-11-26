"""Runs the test-integrity gate's own fixture tests (scripts/tests) so `pytest tests/` covers them."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_gate_fixture_tests_pass():
    proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "scripts/tests"],
                          cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
