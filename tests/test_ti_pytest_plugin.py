"""The test-integrity pytest lister marks skipped items: pytest marks and unittest skip decorators."""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _list(tmp_path):
    out = tmp_path / "list.jsonl"
    env = dict(os.environ, TI_OUT=str(out), PYTHONPATH=str(SCRIPTS))
    proc = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "ti_pytest_plugin",
                           "-p", "no:cacheprovider", str(tmp_path / "test_sample.py")],
                          cwd=tmp_path, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return {r["id"].split("::", 1)[1]: r["skipped"] for r in map(json.loads, out.read_text().splitlines())}


def test_skip_flags(tmp_path):
    (tmp_path / "test_sample.py").write_text(textwrap.dedent('''
        import unittest
        import pytest

        class Plain(unittest.TestCase):
            def test_runs(self): pass
            @unittest.skipIf(True, "no")
            def test_method_skipped(self): pass

        @unittest.skip("whole class")
        class Skipped(unittest.TestCase):
            def test_in_class(self): pass

        @pytest.mark.skip
        def test_marked(): pass

        @pytest.mark.skipif("1 == 1", reason="string condition is run-time")
        def test_string_cond(): pass

        def test_plain(): pass
    '''))
    got = _list(tmp_path)
    assert got["Plain::test_method_skipped"] is True
    assert got["Skipped::test_in_class"] is True
    assert got["test_marked"] is True
    assert got["Plain::test_runs"] is False
    assert got["test_string_cond"] is False
    assert got["test_plain"] is False
