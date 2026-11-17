"""Contract checks for the CLI based proofread pipeline."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_workflow_is_retired_and_skill_invokes_cli():
    assert not (ROOT / "src/workflows/proofread.js").exists()
    skill = (ROOT / "src/skills/write/phases/proofread.md").read_text(encoding="utf-8")
    router = (ROOT / "src/skills/write/SKILL.md").read_text(encoding="utf-8")
    assert "ONE subagent" in router and "`proofread` and `research`" in router
    assert "model: sonnet" in router
    assert "effort: medium" in router
    assert "aw proofread" in skill
    assert "build-tracked-docx.py" in skill
    assert len(skill.splitlines()) <= 200


def test_cli_orders_must_catch_find_verify_memo_and_apply():
    source = (ROOT / "src/cli/src/proofread.ts").read_text(encoding="utf-8")
    points = [source.index("mustCatch"), source.index("const found"), source.index("const verified"), source.index("const memo"), source.index("apply-changes.py")]
    assert points == sorted(points)
    assert "proofread.verify" in source


def test_routes_and_budget_are_configured():
    config = json.loads((ROOT / "src/thresholds.json").read_text(encoding="utf-8"))
    assert config["models"]["proofread.find"]["provider"] == "gemini"
    assert config["models"]["proofread.verify"]["provider"] == "gemini"
    assert config["budget"]["proofread"]["maxUsd"] > 0
