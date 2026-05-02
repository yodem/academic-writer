"""Regression tests for the 2026-05-02 mikdashim failure modes."""
import re
from pathlib import Path

REF = Path("plugins/academic-writer/skills/write/references/anti-ai-patterns-hebrew.md")

def test_section_A_blocks_mibchinat_paragraph_opener():
    text = REF.read_text(encoding="utf-8")
    assert "מבחינת" in text
    assert "Per-paragraph cap: 0 as opener" in text

def test_section_A_enforces_opening_formula():
    text = REF.read_text(encoding="utf-8")
    assert "opening_formula" in text
    assert "במאמר זה" in text
    assert "Per-article cap: 0 violations" in text

def test_section_F_exists_with_meta_summary_patterns():
    text = REF.read_text(encoding="utf-8")
    assert "### F. Editorial Meta-Summary" in text
    for pat in [
        "מסכמ",
        "ומכאן עולה",
        "הראוי לבחינה מדוקדקת",
        "ניתן ללמוד כי",
    ]:
        assert pat in text, f"missing F pattern: {pat}"

def test_section_G_hard_rule_present():
    text = REF.read_text(encoding="utf-8")
    assert "### G. Unsourced Factual Assertions" in text
    assert "Per-article cap: 0" in text
    assert "[NEEDS REVIEW: source for" in text

def test_section_H_blocks_quantitative_padding():
    text = REF.read_text(encoding="utf-8")
    assert "### H. Topic Drift & Padding" in text
    assert "מאה עשרים ושמונה משוררים" in text or "Quantitative trivia" in text
