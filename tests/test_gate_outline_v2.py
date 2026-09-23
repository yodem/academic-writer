import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent.parent


def _files(tmp_path, *, approved=True, must=("p1",), ev_ids=("p1",), thesis="טענה"):
    intent = {"thesis": "טענה", "coreTextSourceId": "s1", "moves": [], "mustUse": list(must)}
    outline = {
        "thesis": thesis,
        "thesisSha256": hashlib.sha256(thesis.encode()).hexdigest(),
        "sections": [{"id": "S1", "title": "", "claim": "", "approved": approved,
                      "units": [{"id": "U1", "dependsOn": [], "paragraphs": [
                          {"move": "", "evidenceIds": list(ev_ids), "bridgeTo": ""}]}]}],
    }
    evidence = {"sources": [{"id": "s1"}], "passages": [{"id": "p1", "sourceId": "s1"}]}
    for name, value in (("i", intent), ("o", outline), ("e", evidence)):
        (tmp_path / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return [sys.executable, ROOT / "src/scripts/gate.py", "outline-v2", "--outline", tmp_path / "o.json",
            "--intent", tmp_path / "i.json", "--evidence", tmp_path / "e.json"]


def test_passes_when_consistent(tmp_path):
    assert subprocess.run(_files(tmp_path)).returncode == 0


def test_fails_unapproved(tmp_path):
    assert subprocess.run(_files(tmp_path, approved=False)).returncode == 1


def test_fails_thesis_drift(tmp_path):
    assert subprocess.run(_files(tmp_path, thesis="טענה אחרת")).returncode == 1


def test_fails_unresolved_evidence(tmp_path):
    assert subprocess.run(_files(tmp_path, ev_ids=("p9",))).returncode == 1


def test_fails_unplaced_must_use(tmp_path):
    assert subprocess.run(_files(tmp_path, ev_ids=())).returncode == 1


def test_fails_dependency_cycle(tmp_path):
    command = _files(tmp_path)
    outline_path = pathlib.Path(command[command.index("--outline") + 1])
    outline = json.loads(outline_path.read_text(encoding="utf-8"))
    outline["sections"][0]["units"].append({"id": "U2", "dependsOn": ["U1"], "paragraphs": []})
    outline["sections"][0]["units"][0]["dependsOn"] = ["U2"]
    outline_path.write_text(json.dumps(outline, ensure_ascii=False), encoding="utf-8")
    assert subprocess.run(command).returncode == 1
