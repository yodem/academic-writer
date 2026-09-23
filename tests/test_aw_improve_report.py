import json, subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).parent.parent
def test_clusters_repeated_defects(tmp_path):
    rows = [{"ts":"2026-10-01","runId":"r1","step":"evidence.extract","authorWords":"wrong translation"}, {"ts":"2026-10-05","runId":"r2","step":"evidence.extract","authorWords":"wrong translation used"}, {"ts":"2026-10-06","runId":"r3","step":"write.draft","authorWords":"invented a structure"}]
    f = tmp_path/"l.jsonl"; f.write_text("\n".join(map(json.dumps, rows)))
    out = json.loads(subprocess.check_output([sys.executable, ROOT/"scripts/aw-improve-report.py", "--ledger", f, "--json"]))
    top = max(out["clusters"], key=lambda c: c["count"])
    assert top["count"] == 2 and top["key"].startswith("evidence.extract")

def test_jev_roster_promotes_120_agreeing_labels(tmp_path):
    f = tmp_path/"jev.jsonl"
    f.write_text("\n".join(json.dumps({"point":"proofread.verify","jevAnswer":"uphold","label":"uphold"}) for _ in range(120)))
    out = json.loads(subprocess.check_output([sys.executable, ROOT/"scripts/aw-improve-report.py", "--ledger", f, "--jev", "--json"]))
    assert out["agreement"]["proofread.verify"]["recommend"] == "promote"

def test_jev_roster_holds_below_label_minimum(tmp_path):
    f = tmp_path/"jev.jsonl"
    f.write_text("\n".join(json.dumps({"point":"proofread.verify","jevAnswer":"uphold","label":"uphold"}) for _ in range(50)))
    out = json.loads(subprocess.check_output([sys.executable, ROOT/"scripts/aw-improve-report.py", "--ledger", f, "--jev", "--json"]))
    assert out["agreement"]["proofread.verify"]["recommend"] == "hold"
