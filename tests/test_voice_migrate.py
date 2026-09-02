"""voice-migrate.sh end-to-end test."""

import re
import subprocess, json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "src" / "skills" / "voice" / "voice-migrate.sh"
FIXTURE = ROOT / "tests" / "fixtures" / "voice" / "legacy-profile.json"


def _write_academic_helper_profile(tmp_path, *, target_language="Hebrew", gemini_json=None):
    """Write a minimal .academic-helper/profile.md fixture for the Gemini migration tests."""
    ah_dir = tmp_path / ".academic-helper"
    ah_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Academic Writer Profile",
        "",
        "---",
        "name: Test Writer",
        "author_key: test-writer",
        f"targetLanguage: {target_language}",
        "---",
        "",
    ]
    if gemini_json is not None:
        lines += [
            "## Gemini",
            "",
            "```json",
            json.dumps(gemini_json, indent=2),
            "```",
            "",
        ]
    (ah_dir / "profile.md").write_text("\n".join(lines))
    return ah_dir / "profile.md"


def _extract_gemini_block(profile_text):
    m = re.search(r"## Gemini\n+```json\n(.*?)\n```", profile_text, re.DOTALL)
    assert m, "no ## Gemini json block found in profile"
    return json.loads(m.group(1))


def test_gemini_migration_fires_once_on_enabled_but_empty_profile(tmp_path):
    """gemini.enabled=true with an empty approvedLanguages gets targetLanguage seeded, once."""
    profile_path = _write_academic_helper_profile(
        tmp_path,
        target_language="Hebrew",
        gemini_json={"enabled": True, "approvedLanguages": [], "models": {}},
    )
    r = subprocess.run([str(SCRIPT)], cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    combined = r.stdout + r.stderr
    assert "migrated" in combined.lower()
    assert "hebrew" in combined.lower()

    data = _extract_gemini_block(profile_path.read_text())
    assert data["approvedLanguages"] == ["Hebrew"]
    assert data["enabled"] is True


def test_gemini_migration_is_noop_on_second_run(tmp_path):
    """Re-running the hook after a successful migration changes nothing further."""
    profile_path = _write_academic_helper_profile(
        tmp_path,
        target_language="Hebrew",
        gemini_json={"enabled": True, "approvedLanguages": [], "models": {}},
    )
    r1 = subprocess.run([str(SCRIPT)], cwd=str(tmp_path), capture_output=True, text=True)
    assert r1.returncode == 0, r1.stderr
    after_first = profile_path.read_text()

    r2 = subprocess.run([str(SCRIPT)], cwd=str(tmp_path), capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    combined2 = r2.stdout + r2.stderr
    assert "already migrated" in combined2.lower()
    assert profile_path.read_text() == after_first

    data = _extract_gemini_block(profile_path.read_text())
    assert data["approvedLanguages"] == ["Hebrew"]


def test_gemini_migration_leaves_disabled_profile_untouched(tmp_path):
    """A profile with gemini.enabled=false is never seeded with a language."""
    profile_path = _write_academic_helper_profile(
        tmp_path,
        target_language="Hebrew",
        gemini_json={"enabled": False, "approvedLanguages": []},
    )
    before = profile_path.read_text()
    r = subprocess.run([str(SCRIPT)], cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "disabled" in (r.stdout + r.stderr).lower()
    assert profile_path.read_text() == before

    data = _extract_gemini_block(profile_path.read_text())
    assert data["approvedLanguages"] == []
    assert data["enabled"] is False


def test_gemini_migration_leaves_already_populated_list_untouched(tmp_path):
    """A profile whose approvedLanguages is already non-empty is left exactly as-is."""
    profile_path = _write_academic_helper_profile(
        tmp_path,
        target_language="Hebrew",
        gemini_json={"enabled": True, "approvedLanguages": ["English"], "models": {}},
    )
    before = profile_path.read_text()
    r = subprocess.run([str(SCRIPT)], cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "already populated" in (r.stdout + r.stderr).lower()
    assert profile_path.read_text() == before

    data = _extract_gemini_block(profile_path.read_text())
    assert data["approvedLanguages"] == ["English"]


def test_migrate_strips_voice_fields_and_archives(tmp_path):
    aw_dir = tmp_path / ".academic-writer"
    aw_dir.mkdir()
    (aw_dir / "profile.json").write_text(FIXTURE.read_text())
    # voice-migrate.sh is profile-scoped: it requires .academic-helper/profile.md
    # to exist (guard added in bca2417) before it will run at all.
    ah_dir = tmp_path / ".academic-helper"
    ah_dir.mkdir()
    (ah_dir / "profile.md").write_text(
        "# Academic Writer Profile\n\n---\nauthor_key: test-writer\n---\n"
    )
    r = subprocess.run([str(SCRIPT)], cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    new = json.loads((aw_dir / "profile.json").read_text())
    # voice and style_fingerprint should be replaced with pointer comments
    assert isinstance(new.get("voice"), str) and "AUTHOR_VOICE.md" in new["voice"]
    assert "style_fingerprint" not in new or "AUTHOR_VOICE.md" in str(
        new["style_fingerprint"]
    )
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
    r2 = subprocess.run(
        [str(SCRIPT)], cwd=str(tmp_path), capture_output=True, text=True
    )
    assert r2.returncode == 0
    assert "already migrated" in (r2.stdout + r2.stderr).lower()


def test_migrate_recognizes_academic_writer_legacy_path(tmp_path):
    """Regression test for the legacy-path bug fixed alongside this test.

    Commit 806c962 ("fix: resolve 6 audit findings") blanket-renamed
    .academic-writer -> .academic-helper across the repo, but incorrectly
    applied that rename to the two references in voice-migrate.sh that were
    meant to keep pointing at the LEGACY pre-rename directory
    (.academic-writer/profile.json). That made the legacy-profile detection
    path dead code: the profile-scope guard and the aw_profile lookup both
    checked .academic-helper/profile.json, which never exists for a legacy
    project, so migration silently no-op'd for every real .academic-writer
    user. This test isolates just the "does the script even recognize a
    legacy .academic-writer profile" question, independent of the fuller
    content-stripping assertions above, so a future accidental rename of
    this specific path is caught even if the bigger end-to-end test changes.

    NOTE: this test relies on .academic-helper/profile.md existing purely
    because voice-migrate.sh's unrelated profile-scope guard (added in
    bca2417) requires it; that guard is orthogonal to the legacy-path bug
    this test targets.
    """
    aw_dir = tmp_path / ".academic-writer"
    aw_dir.mkdir()
    (aw_dir / "profile.json").write_text(FIXTURE.read_text())
    ah_dir = tmp_path / ".academic-helper"
    ah_dir.mkdir()
    (ah_dir / "profile.md").write_text(
        "# Academic Writer Profile\n\n---\nauthor_key: test-writer\n---\n"
    )
    r = subprocess.run([str(SCRIPT)], cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # If the legacy path were dead code, the script would exit 0 without
    # doing anything: AUTHOR_VOICE.md would never be created and the
    # legacy profile.json would never be archived.
    assert (tmp_path / "AUTHOR_VOICE.md").is_file(), (
        "AUTHOR_VOICE.md was not created — voice-migrate.sh failed to "
        "detect the legacy .academic-writer/profile.json"
    )
    assert (tmp_path / ".voice" / "legacy" / "profile.json").is_file()
