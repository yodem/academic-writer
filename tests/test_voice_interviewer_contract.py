from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def test_legacy_voice_agent_removed():
    assert not (ROOT / "src" / "agents" / "voice-interviewer.md").exists()
