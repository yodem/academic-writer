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
    # Run migration — should produce AUTHOR_VOICE.md from legacy profile
    subprocess.run(["bash", str(ROOT / "src/skills/voice/voice-migrate.sh")],
                   cwd=str(tmp_path), check=True)
    # Stage 1 is normally agent-driven; for the structural test we shell-emit a stub fingerprint
    # to assert the surrounding pipeline works.
    (tmp_path / ".voice").mkdir(exist_ok=True)
    (tmp_path / ".voice" / "fingerprint.md").write_text(
        "# Fingerprint\n- Corpus summary: 3 articles, 1500 words, Hebrew.\n"
    )
    # Inject a stub `ck` that exits 127 → voice-sync treats push as a no-op
    stub_bin = tmp_path / ".stub-bin"
    stub_bin.mkdir()
    stub_ck = stub_bin / "ck"
    stub_ck.write_text("#!/bin/bash\n# stub ck — not available\nexit 127\n")
    stub_ck.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = str(stub_bin) + ":" + env["PATH"]
    # Run sync push (stub ck exits 127 → script sees ck missing → no-op)
    r = subprocess.run(["bash", str(ROOT / "src/skills/voice/voice-sync.sh"), "push"],
                       cwd=str(tmp_path), capture_output=True, text=True, env=env)
    assert r.returncode == 0
    # AUTHOR_VOICE.md should have been created by migration — not seeded by the test
    avo = tmp_path / "AUTHOR_VOICE.md"
    assert avo.exists(), "AUTHOR_VOICE.md was not created by migration"
    content = avo.read_text()
    assert "Voice Profile" in content
    assert "Test Writer" in content  # from legacy-profile.json fixture
