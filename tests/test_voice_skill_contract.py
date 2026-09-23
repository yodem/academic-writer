from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "src" / "skills" / "voice" / "SKILL.md"

def test_skill_frontmatter_and_store_workflow():
    text = SKILL.read_text()
    fm = yaml.safe_load(text.split("---")[1])
    assert fm["name"] == "voice"
    assert "Use when" in fm["description"]
    assert "${CLAUDE_PLUGIN_DATA}" in text
    for action in ("migrate", "exemplars", "moves", "push", "pull"):
        assert f"voice {action}" in text
    assert "7-session" not in text

def test_legacy_voice_agents_removed():
    for name in ("voice-interviewer", "voice-distiller", "voice-calibrator", "voice-miner"):
        assert not (ROOT / "src" / "agents" / f"{name}.md").exists()
