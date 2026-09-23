"""End-to-end Stage 1: corpus → fingerprint → distiller seed → AUTHOR_VOICE.md."""

import subprocess, shutil, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "voice" / "sample-corpus"
LEGACY_PROFILE = ROOT / "tests" / "fixtures" / "voice" / "legacy-profile.json"


def test_stage1_seeds_author_voice(tmp_path):
    pa = tmp_path / "past-articles"
    shutil.copytree(FIXTURE, pa)
    # Set up legacy .academic-writer/profile.json so migration has something to convert
    # (also satisfies the profile-scope guard)
    aw_dir = tmp_path / ".academic-writer"
    aw_dir.mkdir()
    shutil.copy(LEGACY_PROFILE, aw_dir / "profile.json")
    # voice-migrate.sh is profile-scoped: it requires .academic-helper/profile.md to exist.
    # This also gives voice-sync.sh the author_key it now requires (loud-failure hardening).
    ah_dir = tmp_path / ".academic-helper"
    ah_dir.mkdir()
    (ah_dir / "profile.md").write_text(
        "# Academic Writer Profile\n\n---\nauthor_key: test-writer\n---\n"
    )
    # Run migration — should produce AUTHOR_VOICE.md from legacy profile
    subprocess.run(
        ["bash", str(ROOT / "src/skills/voice/voice-migrate.sh")],
        cwd=str(tmp_path),
        check=True,
    )
    # AUTHOR_VOICE.md should have been created by migration — not seeded by the test
    avo = tmp_path / "AUTHOR_VOICE.md"
    assert avo.exists(), "AUTHOR_VOICE.md was not created by migration"
    content = avo.read_text()
    assert "Voice Profile" in content
    assert "Test Writer" in content  # from legacy-profile.json fixture


def test_voice_sync_usage_and_legacy_form(tmp_path):
    """voice-sync.sh: bad args -> exit 2; legacy 1-arg form resolves defaults and reaches aw."""
    script = ROOT / "plugins/academic-writer/skills/voice/voice-sync.sh"
    bad = subprocess.run(["bash", str(script), "sideways"], capture_output=True, text=True)
    assert bad.returncode == 2 and "usage" in bad.stderr
    ok = subprocess.run(["bash", str(script), "pull", str(tmp_path / "data"), str(tmp_path)],
                        capture_output=True, text=True, cwd=str(tmp_path))
    assert "aw CLI not found" not in ok.stderr, ok.stderr  # built plugin has bin/aw
