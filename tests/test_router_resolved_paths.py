"""Each router exposes the resolved plugin variables and tells the model to bind them into phase commands."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ROUTERS = ["setup", "write", "library", "courses"]


@pytest.mark.parametrize("name", ROUTERS)
def test_router_exposes_resolved_paths(name):
    text = (ROOT / "src" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    sec = text.split("## Resolved paths", 1)
    assert len(sec) == 2, "no Resolved paths section"
    body = sec[1].split("\n## ", 1)[0]
    for var in ("CLAUDE_SKILL_DIR", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA"):
        assert "${%s}" % var in body
    assert "working directory" in body
    assert "subagent" in body
    assert "already correct" not in text
