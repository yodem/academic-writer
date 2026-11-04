"""The init baseline lookup must find the Hebrew Linguistic Reference in the
current `trove items list --json` shape ({"items": [...]}) and in the older bare array."""
import json
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
EXPECTED_ID = "cmomjonvy0fdmk30zwef79c48"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="jq not installed")


def _filter(doc: Path) -> str:
    m = re.search(r"BASELINE_ID=\$\(trove items list --json [^|]*\| jq -r --arg t \"\$BASELINE_TITLE\" '([^']+)'\)", doc.read_text())
    assert m, f"baseline lookup not found in {doc}"
    return m.group(1)


def _lookup(doc: Path, payload: str) -> str:
    done = subprocess.run(
        ["jq", "-r", "--arg", "t", "Hebrew Linguistic Reference", _filter(doc)],
        input=payload, capture_output=True, text=True, timeout=30,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


@pytest.mark.parametrize("doc", DOCS, ids=["src", "plugin"])
def test_lookup_current_object_shape(doc):
    assert _lookup(doc, FIXTURE.read_text()) == EXPECTED_ID


@pytest.mark.parametrize("doc", DOCS, ids=["src", "plugin"])
def test_lookup_legacy_array_shape(doc):
    items = json.loads(FIXTURE.read_text())["items"]
    assert _lookup(doc, json.dumps(items)) == EXPECTED_ID
