import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent.parent


def test_terms_style_and_caps(tmp_path):
    (tmp_path / "a.md").write_text("שמואל אבן תבון כתב.\nכמו כן הוא טען. כמו כן הוא הוסיף.\nיתרה מזאת, זה.\n", encoding="utf-8")
    (tmp_path / "s.json").write_text(json.dumps({"banned": [{"word": "יתרה מזאת", "replacement": "זאת ועוד"}], "capped": [{"word": "כמו כן", "maxPer": "paragraph", "max": 1}], "filler": []}), encoding="utf-8")
    (tmp_path / "t.json").write_text(json.dumps({"canon": [{"form": "אבן תיבון", "variants": ["אבן תבון"]}]}), encoding="utf-8")
    out = json.loads(subprocess.check_output([sys.executable, ROOT / "src/scripts/must-catch.py", "--text", tmp_path / "a.md", "--style-words", tmp_path / "s.json", "--terms", tmp_path / "t.json", "--json"]))
    classes = sorted(c["class"] for c in out["changes"])
    assert classes == ["names_terms", "style_words", "style_words"]
    assert all(c["mustCatch"] for c in out["changes"])

def test_capped_word_beyond_cap_takes_replacement(tmp_path):
    (tmp_path/"a.md").write_text("כמו כן הוא טען. כמו כן הוא הוסיף.\n", encoding="utf-8")
    (tmp_path/"s.json").write_text(json.dumps({"banned":[],"filler":[],
        "capped":[{"word":"כמו כן","maxPer":"paragraph","max":1,"replacement":"נוסף על כך"}]}), encoding="utf-8")
    (tmp_path/"t.json").write_text(json.dumps({"canon":[]}), encoding="utf-8")
    out = json.loads(subprocess.check_output([sys.executable, ROOT/"src/scripts/must-catch.py", "--text", tmp_path/"a.md",
        "--style-words", tmp_path/"s.json", "--terms", tmp_path/"t.json", "--json"]))
    assert [c["after"] for c in out["changes"]] == ["נוסף על כך"]  # first use kept, second replaced
