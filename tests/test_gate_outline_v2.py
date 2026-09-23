import hashlib
import json
import os
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


def test_malformed_json_is_a_clean_error_not_a_traceback(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, ROOT / "src/scripts/gate.py", "outline-v2", "--outline", bad,
         "--intent", empty, "--evidence", empty, "--json"],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert "Traceback" not in result.stderr


def test_schema_violation_is_reported_not_crashed(tmp_path):
    outline = tmp_path / "o.json"
    outline.write_text("{}", encoding="utf-8")
    intent = tmp_path / "i.json"
    intent.write_text(json.dumps({"thesis": 123}), encoding="utf-8")
    evidence = tmp_path / "e.json"
    evidence.write_text("{}", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, ROOT / "src/scripts/gate.py", "outline-v2", "--outline", outline,
         "--intent", intent, "--evidence", evidence, "--json"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "fail"
    assert payload["violations"]


def test_built_plugin_contains_outline_schema():
    assert (ROOT / "plugins/academic-writer/schemas/outline.schema.json").is_file()


def test_semantic_checks_run_without_jsonschema(tmp_path):
    """The author's machine may lack jsonschema; the gate must still decide, not error."""
    blocker = tmp_path / "block"
    blocker.mkdir()
    (blocker / "jsonschema.py").write_text("raise ImportError('blocked for test')\n")
    env = {**os.environ, "PYTHONPATH": str(blocker)}
    assert subprocess.run(_files(tmp_path), env=env).returncode == 0
    assert subprocess.run(_files(tmp_path, approved=False), env=env).returncode == 1
