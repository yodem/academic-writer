import json
import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).parent.parent


def test_same_author_closer_than_other(tmp_path):
    a = tmp_path / "author"
    a.mkdir()
    (a / "1.md").write_text("אני טוען כי הטקסט אינו רק פרשנות אלא הכרעה. " * 30, encoding="utf-8")
    (a / "2.md").write_text("אני סבור כי המקור אינו רק עדות אלא טענה. " * 30, encoding="utf-8")
    near = tmp_path / "near.md"
    near.write_text("אני טוען כי המהלך אינו רק תיאור אלא הכרעה. " * 30, encoding="utf-8")
    far = tmp_path / "far.md"
    far.write_text("Moreover, it is important to note that, furthermore, the text. " * 30, encoding="utf-8")
    run = lambda p: json.loads(subprocess.check_output([sys.executable, ROOT / "src/scripts/voice-score.py", "--drafts", p, "--author", a, "--json"]))
    assert run(near)["median_distance"] < run(far)["median_distance"]
