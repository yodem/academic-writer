"""Proofread finder and verifier prompts keep their JSON contracts explicit."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_prompts_define_batched_json_contracts_and_hebrew_examples():
    finder = (ROOT / "src/cli/src/prompts/proofread-find.md").read_text(encoding="utf-8")
    verifier = (ROOT / "src/cli/src/prompts/proofread-verify.md").read_text(encoding="utf-8")
    for text in (finder, verifier):
        assert "JSON" in text
        assert "אם/עם" in text or "אם" in text
        assert "גרש" in text or "geresh" in text or "gershayim" in text
    assert '"changes"' in finder
    assert '"verdicts"' in verifier
    assert '"uphold"' in verifier and '"refute"' in verifier
