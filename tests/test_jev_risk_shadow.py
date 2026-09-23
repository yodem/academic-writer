"""The former proofread-only Jev scorer now uses the shared decide ledger."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_risk_point_is_registered_in_decide_and_starts_shadow():
    source = (ROOT / "src/cli/src/decide.ts").read_text(encoding="utf-8")
    config = json.loads((ROOT / "src/thresholds.json").read_text(encoding="utf-8"))
    assert "proofread.risk" in source
    assert config["jev"]["points"]["proofread.risk"]["mode"] == "shadow"
    assert "jevShadow" not in config["proofread"]
    assert not (ROOT / "src/scripts/jev-risk-shadow.py").exists()


def test_candidate_risk_is_decided_through_shared_point():
    source = (ROOT / "src/cli/src/proofread.ts").read_text(encoding="utf-8")
    assert "point: 'proofread.risk'" in source
    assert "point: 'proofread.triage'" in source
    assert "point: 'proofread.verify'" in source
