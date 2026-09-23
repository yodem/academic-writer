import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent.parent


def test_dedupes_streamed_rows(tmp_path):
    rows = [
        {"type": "assistant", "timestamp": "2026-09-15T10:00:00Z", "message": {"id": "m1", "model": "claude-opus-5", "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000, "output_tokens": 5}}},
        {"type": "assistant", "timestamp": "2026-09-15T10:00:01Z", "message": {"id": "m1", "model": "claude-opus-5", "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000, "output_tokens": 50}}},
    ]
    f = tmp_path / "s.jsonl"
    f.write_text("\n".join(map(json.dumps, rows)))
    out = json.loads(subprocess.check_output([sys.executable, ROOT / "scripts/measure-run.py", "--session", f, "--json"]))
    assert out["total_tokens"] == 10 + 100 + 1000 + 50
    assert abs(out["effective_units"] - (10 + 125 + 100 + 250)) < 1e-6
