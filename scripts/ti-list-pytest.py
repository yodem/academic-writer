#!/usr/bin/env python3
"""Lists pytest tests as jsonl on stdout: ti-list-pytest.py <pytest args...> (run from the tree root).

pytest's own output goes to stderr; the plugin writes the ids to a temp file that is copied to stdout,
so nothing else can mix into the list. Exit code is pytest's (collection errors fail the lister).
"""
import os
import subprocess
import sys
import tempfile

here = os.path.dirname(os.path.abspath(__file__))
with tempfile.TemporaryDirectory() as tmp:
    out = os.path.join(tmp, "list.jsonl")
    env = dict(os.environ, TI_OUT=out, PYTHONPATH=here + os.pathsep + os.environ.get("PYTHONPATH", ""))
    proc = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "ti_pytest_plugin"] + sys.argv[1:],
                          env=env, stdout=sys.stderr, stderr=sys.stderr)
    if proc.returncode != 0:
        sys.exit(proc.returncode)
    with open(out, encoding="utf-8") as f:
        sys.stdout.write(f.read())
