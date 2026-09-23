"""Proofread verification is chunk-batched and retains refuted candidates."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_verification_is_batched_per_chunk_and_refutations_are_retained():
    source = (ROOT / "src/cli/src/proofread.ts").read_text(encoding="utf-8")
    assert "stubs.verify(changes)" in source
    assert "missing verdict" in source
    assert "status: decided.answer === 'refute' ? 'refuted' : 'verified'" in source
    assert "candidates.map((change) => statusMap.get(change.id)" in source


def test_must_catch_excluded_from_verify_candidates():
    source = (ROOT / "src/cli/src/proofread.ts").read_text(encoding="utf-8")
    assert "const verifiable = candidates.filter" in source
    assert "deterministic.map((change) => ({ ...change, status: change.status ?? (change.after === null ? 'flag' : 'must-catch'), applied: change.after !== null }))" in source
    assert "change.mustCatch" not in source[source.index("const verifiable"):source.index("const byChunk")]
