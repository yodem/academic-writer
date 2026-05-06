"""voice-migrate.sh end-to-end test."""
import subprocess, json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "src" / "skills" / "voice" / "voice-migrate.sh"
FIXTURE = ROOT / "tests" / "fixtures" / "voice" / "legacy-profile.json"

def test_migrate_strips_voice_fields_and_archives(tmp_path):
    aw_dir = tmp_path / ".academic-writer"
    aw_dir.mkdir()
    (aw_dir / "profile.json").write_text(FIXTURE.read_text())
    r = subprocess.run([str(SCRIPT)], cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    new = json.loads((aw_dir / "profile.json").read_text())
    # voice and style_fingerprint should be replaced with pointer comments
    assert isinstance(new.get("voice"), str) and "AUTHOR_VOICE.md" in new["voice"]
    assert "style_fingerprint" not in new or "AUTHOR_VOICE.md" in str(new["style_fingerprint"])
    assert new["writer_name"] == "Test Writer"
    # AUTHOR_VOICE.md should be at root and contain seeded content
    avo = (tmp_path / "AUTHOR_VOICE.md").read_text()
    assert "Test Writer" in avo
    assert "מבחינה זו" in avo
    # Legacy archive intact
    legacy = tmp_path / ".voice" / "legacy" / "profile.json"
    assert legacy.is_file()
    assert json.loads(legacy.read_text()) == json.loads(FIXTURE.read_text())
    # Idempotent
    r2 = subprocess.run([str(SCRIPT)], cwd=str(tmp_path), capture_output=True, text=True)
    assert r2.returncode == 0
    assert "already migrated" in (r2.stdout + r2.stderr).lower()
