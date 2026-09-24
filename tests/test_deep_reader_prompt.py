"""The deep-reader agent exists for source registry work while CLI builds verified evidence."""
from pathlib import Path

DR = Path("src/agents/deep-reader.md")


def test_deep_reader_agent_exists_and_writes_sources_registry():
    text = DR.read_text(encoding="utf-8")
    assert "name: deep-reader" in text
    assert ".academic-helper/sources.json" in text


def test_deep_reader_defers_verified_evidence_to_cli():
    text = DR.read_text(encoding="utf-8")
    assert "aw evidence build" in text
    assert "does **not** write `.academic-helper/evidence.json`" in text


def test_research_skill_uses_verified_evidence_cli():
    text = Path("src/skills/research/SKILL.md").read_text(encoding="utf-8")
    assert "aw evidence build" in text
    assert "evidence.json" in text
