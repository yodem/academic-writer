import json, subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).parent.parent
def test_reads_all_review_kinds():
    out = json.loads(subprocess.check_output([sys.executable, ROOT/"src/scripts/docx-read-review.py", ROOT/"tests/fixtures/docx/review-sample.docx", "--json"]))
    kinds = sorted(i["kind"] for i in out["items"])
    assert kinds == ["comment", "comment", "delete", "move", "replace"]
    assert all(i["anchorText"] for i in out["items"])
