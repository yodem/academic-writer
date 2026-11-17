"""Regression tests for the 2026-05-02 mikdashim failure modes."""
from pathlib import Path

WS = Path("src/skills/write/phases/new.md")

def test_write_skill_has_existing_article_precondition():
    text = WS.read_text(encoding="utf-8")
    assert "articles/" in text
    assert "academic-writer:write edit" in text
    assert "already exists" in text.lower() or "test -f" in text or "[ -f" in text
