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


def test_setup_writes_home_md_with_role_and_identity():
    assert re.search(r'home\.py"? set --path "[^"]+"[^\n]*--role', SETUP)
    for flag in ("--name", "--field", "--target-language", "--citation-style"):
        assert flag in SETUP


def test_setup_role_vocabulary_is_the_canonical_set():
    block = SETUP.split("### 2b", 1)[1].split("### 2c", 1)[0]
    options = block.split("```python", 1)[1].split("```", 1)[0]
    assert "teach" not in options.lower().replace("you teach courses", "")
    assert "Lecturer" in block and "Student" in block and "Researcher" in block
    assert "`student`, `lecturer` or `researcher`" in block
    assert "Teacher" not in SETUP


def test_setup_checks_python_before_the_first_home_py_call():
    first_home = SETUP.index("scripts/home.py")
    before = SETUP[:first_home]
    assert "python3 --version" in before
    assert "setup_checks.py" in before or "Python 3" in before
    assert "Python is not installed" in before or "isn't installed" in before


def test_profile_keeps_only_workspace_overrides():
    block = SETUP.split("**Save the folder profile now**", 1)[1].split("---", 1)[0]
    assert "home.md" in block and "override" in block.lower()


def test_init_writes_home_md_when_the_home_has_none():
    assert re.search(r"home\.py\"? profile ", INIT)


def test_no_skill_text_offers_teaching_as_a_role():
    for path in SKILLS.rglob("*.md"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.search(r"not a role|never a role|is not$", line, re.I):
                continue
            assert not re.search(r"\brole\b[^\n]*\bteaching\b", line, re.I), f"{path}: {line}"
