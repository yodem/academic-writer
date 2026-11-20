"""No file in the repo may name a /academic-writer:<name> command that no longer exists.

0.24.0 ships four commands (write, setup, library, courses); the older names were forwarding
stubs and are deleted. CHANGELOG.md (history) and plugins/ (build output) are exempt, as are the
zz-* names the guide-sync tests invent inside a temporary copy of the tree.
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTERS = {"write", "setup", "library", "courses"}
PATTERN = re.compile(rb"/academic-writer:([A-Za-z][A-Za-z0-9-]*)")
EXEMPT_FILES = {"CHANGELOG.md", "tests/test_no_old_command_names.py"}


def _repo_files():
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT, check=True, capture_output=True).stdout
    for rel in out.decode("utf-8").split("\0"):
        if not rel or rel in EXEMPT_FILES or rel.startswith("plugins/"):
            continue
        path = ROOT / rel
        if path.is_file():
            yield rel, path


def test_scan_sees_files():
    assert sum(1 for _ in _repo_files()) > 50


def test_only_the_four_routers_are_named():
    bad = []
    for rel, path in _repo_files():
        for n, line in enumerate(path.read_bytes().splitlines(), 1):
            for m in PATTERN.finditer(line):
                name = m.group(1).decode()
                if name not in ROUTERS and not name.startswith("zz-"):
                    bad.append(f"{rel}:{n}: /academic-writer:{name}")
    assert not bad, "old command names:\n" + "\n".join(bad)
