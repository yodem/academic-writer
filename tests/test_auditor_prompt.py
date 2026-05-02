"""Regression tests for the 2026-05-02 mikdashim failure modes."""
from pathlib import Path

AUD = Path("src/agents/auditor.md")

def test_auditor_checks_unsourced_factual_claims():
    text = AUD.read_text(encoding="utf-8")
    assert "Section G" in text or "Unsourced Factual" in text
    assert "[NEEDS REVIEW: source for" in text

def test_auditor_lists_factual_cue_categories():
    text = AUD.read_text(encoding="utf-8")
    for cue in ["dating", "dimensions", "technique", "scholarly consensus"]:
        assert cue in text.lower(), f"missing factual-cue category: {cue}"
