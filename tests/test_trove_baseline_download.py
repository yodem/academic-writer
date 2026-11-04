"""The init baseline step must not leave a baseline file behind when the
download fails or returns nothing; only a successful, non-empty download counts."""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests/fixtures/trove/items-list.json"
DOCS = [
    ROOT / "src/skills/init/references/style-analysis.md",
    ROOT / "plugins/academic-writer/skills/init/references/style-analysis.md",
]
BASELINE = ".ctx/hebrew-linguistic-reference.md"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="jq not installed")


def _snippet(doc: Path) -> str:
    m = re.search(r"```bash\n(mkdir -p \.ctx\nBASELINE_TITLE=.*?\nfi\n)```", doc.read_text(), re.S)
    assert m, f"baseline step not found in {doc}"
    return m.group(1)


def _run(doc: Path, tmp_path: Path, get_body: str) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "trove"
    fake.write_text(
        "#!/bin/sh\n"
        f'if [ "$2" = list ]; then cat "{FIXTURE}"; exit 0; fi\n'
        f"{get_body}\n"
    )
    fake.chmod(0o755)
    work = tmp_path / "work"
    work.mkdir()
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"}
    done = subprocess.run(["bash", "-c", _snippet(doc)], cwd=work, env=env,
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return work


@pytest.mark.parametrize("doc", DOCS, ids=["src", "plugin"])
def test_failed_download_leaves_no_baseline(doc, tmp_path):
    work = _run(doc, tmp_path, 'echo "error: not found" >&2; exit 1')
    assert not (work / BASELINE).exists()
    assert not (work / (BASELINE + ".tmp")).exists()


@pytest.mark.parametrize("doc", DOCS, ids=["src", "plugin"])
def test_empty_download_leaves_no_baseline(doc, tmp_path):
    work = _run(doc, tmp_path, "exit 0")
    assert not (work / BASELINE).exists()


@pytest.mark.parametrize("doc", DOCS, ids=["src", "plugin"])
def test_good_download_writes_baseline(doc, tmp_path):
    work = _run(doc, tmp_path, 'echo "# Hebrew Linguistic Reference"; exit 0')
    assert (work / BASELINE).read_text().startswith("# Hebrew Linguistic Reference")
