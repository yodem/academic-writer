"""Regression tests for the 2026-05-02 mikdashim failure modes."""
from pathlib import Path

SW = Path("src/agents/section-writer.md")

def test_section_writer_loads_banned_terms():
    text = SW.read_text(encoding="utf-8")
    assert "bannedTerms" in text

def test_section_writer_skill_2_rewrites_banned_terms():
    text = SW.read_text(encoding="utf-8")
    assert "Skill 2" in text
    assert "replacement" in text.lower()
