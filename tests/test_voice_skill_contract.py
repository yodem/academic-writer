from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "src" / "skills" / "voice" / "SKILL.md"

def test_skill_exists():
    assert SKILL.is_file()

def test_skill_frontmatter_complete():
    text = SKILL.read_text()
    fm = yaml.safe_load(text.split("---")[1])
    assert fm["name"] == "voice"
    assert fm["user-invocable"] is True
    for k in ("description", "allowed-tools"):
        assert k in fm

def test_skill_lists_subactions():
    text = SKILL.read_text()
    for sub in ("init", "continue", "recompress", "audit", "quick", "sync", "status"):
        assert f":voice {sub}" in text or f"`{sub}`" in text

def test_skill_invokes_correct_agents():
    text = SKILL.read_text()
    assert "voice-interviewer" in text
    assert "voice-distiller" in text
    assert "voice-calibrator" in text
    # Calibrator only on sessions 3 and 7
    assert "session 3" in text.lower() and "session 7" in text.lower()

def test_voice_sync_invocations_are_resolvable_and_check_exit_code():
    # A bare `voice-sync push` or `voice-sync.sh pull` is not on PATH and not
    # in cwd -- an agent literally running that instruction gets a
    # command-not-found failure, and nothing in the old instruction text told
    # it to check the exit code, so the failure (and the fact the pull/push
    # never happened) went unreported. Every "Run voice-sync..." instruction
    # must give the resolvable plugin-root path and tell the caller to check
    # the exit code.
    import re

    text = SKILL.read_text()
    invocations = re.findall(r"Run `([^`]*voice-sync[^`]*)`", text)
    assert len(invocations) >= 4, "expected at least the init/recompress/sync pull+push call sites"
    for inv in invocations:
        assert inv.startswith("${CLAUDE_PLUGIN_ROOT}/skills/voice/voice-sync.sh"), (
            f"unresolvable voice-sync invocation (no plugin-root path): {inv!r}"
        )
    assert "check its exit code" in text

def test_write_skill_voice_load_step_is_resolvable_and_checks_exit_code():
    write_skill = ROOT / "src" / "skills" / "write" / "SKILL.md"
    text = write_skill.read_text()
    assert "${CLAUDE_PLUGIN_ROOT}/skills/voice/voice-sync.sh pull" in text
    assert "Check its exit code" in text or "check its exit code" in text
