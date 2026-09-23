"""The retired deep-reader prompt is replaced by CLI evidence extraction."""
from pathlib import Path

DR = Path("src/agents/deep-reader.md")

def test_deep_reader_prompt_is_retired():
    assert not DR.exists()

def test_research_skill_uses_verified_evidence_cli():
    text = Path("src/skills/research/SKILL.md").read_text(encoding="utf-8")
    assert "aw evidence build" in text
    assert "evidence.json" in text
