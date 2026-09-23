import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent.parent
G = ROOT / "evals/graders/applied_recall.py"


def _run(tmp_path, proofed, expected):
    p = tmp_path / "p.md"
    p.write_text(proofed, encoding="utf-8")
    e = tmp_path / "e.json"
    e.write_text(json.dumps(expected), encoding="utf-8")
    return subprocess.run([sys.executable, G, p, e], capture_output=True, text=True)


def test_counts_only_applied_after_text(tmp_path):
    exp = {"min_recall": {"typo": 1.0}, "items": [{"class": "typo", "after": "להרוס", "before": "לארוס"}], "protected": []}
    assert _run(tmp_path, "הוא ביקש להרוס", exp).returncode == 0
    assert _run(tmp_path, "הוא ביקש לארוס", exp).returncode == 1


def test_fails_when_protected_quote_changed(tmp_path):
    exp = {"min_recall": {}, "items": [], "protected": ["״ויאמר משה״"]}
    assert _run(tmp_path, "כתוב ״ויאמר משהה״", exp).returncode == 1

def test_context_anchor_handles_before_inside_after(tmp_path):
    exp = {"min_recall": {"names_terms": 1.0}, "protected": [],
           "items": [{"class": "names_terms", "context": "ר׳ יהודה הלווי, מצידו", "fixed": "ר׳ יהודה הלוי, מצידו",
                      "before": "הלווי", "after": "הלוי"}]}
    assert _run(tmp_path, "כתב ר׳ יהודה הלוי, מצידו, ביקורת", exp).returncode == 0

def test_word_correct_elsewhere_must_survive(tmp_path):
    exp = {"min_recall": {"typo": 1.0}, "protected": ["אין בכוונתי לארוס את בתו"],
           "items": [{"class": "typo", "context": "ביקש לארוס את התפיסה", "fixed": "ביקש להרוס את התפיסה",
                      "before": "לארוס", "after": "להרוס"}]}
    ok = "אין בכוונתי לארוס את בתו. מישהו ביקש להרוס את התפיסה."
    over = "אין בכוונתי להרוס את בתו. מישהו ביקש להרוס את התפיסה."
    assert _run(tmp_path, ok, exp).returncode == 0
    assert _run(tmp_path, over, exp).returncode == 1

def test_fixture_is_self_consistent(tmp_path):
    fx = ROOT/"evals/proofread-recall/fixture"
    exp = json.loads((fx/"expected.json").read_text(encoding="utf-8"))
    art = (fx/"article.md").read_text(encoding="utf-8")
    fixed = art
    for it in exp["items"]:
        assert art.count(it["context"]) == 1, it["context"]
        fixed = fixed.replace(it["context"], it["fixed"], 1)
    raw = subprocess.run([sys.executable, G, fx/"article.md", fx/"expected.json"], capture_output=True, text=True)
    assert raw.returncode == 1  # the unfixed article must fail
    p = tmp_path / "fixed.md"
    p.write_text(fixed, encoding="utf-8")
    good = subprocess.run([sys.executable, G, p, fx/"expected.json"], capture_output=True, text=True)
    assert good.returncode == 0, good.stdout  # a perfect proofread must pass
