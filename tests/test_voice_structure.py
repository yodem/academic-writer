"""Structural tests for the voice subsystem."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def test_author_voice_at_root_exists():
    assert (ROOT / "AUTHOR_VOICE.md").is_file()

def test_voice_dir_exists():
    assert (ROOT / ".voice").is_dir()
    assert (ROOT / ".voice" / ".gitkeep").is_file()

def test_voice_artifacts_gitignored():
    gi = (ROOT / ".gitignore").read_text()
    assert ".voice/*" in gi
    assert "!.voice/.gitkeep" in gi
