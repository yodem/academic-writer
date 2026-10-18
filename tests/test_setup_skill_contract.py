"""Contract for the setup and init skills: home folder, workspace types, Python check, next steps."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "src" / "skills"
SETUP = (SKILLS / "setup" / "SKILL.md").read_text(encoding="utf-8")
INIT = (SKILLS / "init" / "SKILL.md").read_text(encoding="utf-8")


def test_setup_uses_setup_checks_and_home_set():
    assert "setup_checks.py" in SETUP
    assert "home.py set" in SETUP


def test_setup_has_what_you_can_do_now_section():
    assert re.search(r"^#+ .*What you can do now", SETUP, re.M)
    assert "/academic-writer:intro" in SETUP.split("What you can do now", 1)[1]


def test_setup_home_folder_choice_paths():
    assert "osascript" in SETUP
    assert "choose folder" in SETUP
    assert "~/Documents/Academic" in SETUP


def test_init_registers_workspace_inside_and_outside_home():
    assert "home.py register" in INIT
    assert re.search(r"inside (the )?home", INIT, re.I)
    assert re.search(r"outside (the )?home", INIT, re.I)
    assert "which course is this" in INIT.lower()
    assert "separate project" in INIT.lower()


def test_profile_schema_documents_home_and_workspace_fields():
    text = (SKILLS / "init" / "references" / "profile-schema.md").read_text(encoding="utf-8")
    for token in ("home.md", "workspace", "course", "term"):
        assert token in text


def test_no_skill_names_legacy_registry_except_migration():
    paths = list(SKILLS.rglob("*.md"))
    for path in paths:
        text = path.read_text(encoding="utf-8")
        if "~/.academic-writer/courses" not in text:
            continue
        for line in text.splitlines():
            if "~/.academic-writer/courses" in line:
                assert re.search(r"migrat|legacy|older", line, re.I), f"{path}: {line}"
