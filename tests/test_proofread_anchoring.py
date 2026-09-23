import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location("ac", pathlib.Path(__file__).parent.parent / "src/scripts/apply-changes.py")
ac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ac)
BASE = "שורה א\nהוא ביקש לארוס\nשורה ג\nשורה ד\nשורה ה\nהוא ביקש לארוס\n"


def _apply(changes):
    return ac.apply_changes({"changes": changes}, BASE)


def test_wrong_line_resolves_to_nearest():
    _, out = _apply([{"id": "c1", "line": 3, "before": "לארוס", "after": "להרוס", "meaningRisk": "low"}])
    assert out.splitlines()[1] == "הוא ביקש להרוס" and out.splitlines()[5] == "הוא ביקש לארוס"


def test_tie_is_ambiguous_not_applied():
    rep, out = _apply([{"id": "c1", "line": 4, "before": "לארוס", "after": "להרוס", "meaningRisk": "low"}])
    assert out == BASE and rep["changes"][0]["skipReason"] == "ambiguous-anchor"


def test_must_catch_applies_despite_medium_risk_and_refute():
    _, out = _apply([{"id": "c1", "line": 2, "before": "לארוס", "after": "להרוס", "meaningRisk": "medium", "mustCatch": True, "status": "refuted"}])
    assert "להרוס" in out.splitlines()[1]
