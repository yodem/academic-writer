from pathlib import Path

A = Path("src/agents/architect.md")

def test_architect_checks_chapter_coverage():
    text = A.read_text(encoding="utf-8")
    assert "chapter_coverage" in text
    assert "reject" in text.lower() or "re-spawn" in text.lower() or "return to deep-reader" in text.lower()
