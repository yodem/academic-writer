"""Contract for the setup and init skills: home folder, workspace types, Python check, next steps."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "src" / "skills"
SETUP = (SKILLS / "setup" / "SKILL.md").read_text(encoding="utf-8")
INIT = (SKILLS / "init" / "SKILL.md").read_text(encoding="utf-8")
FINISH = (SKILLS / "setup" / "references" / "finish.md").read_text(encoding="utf-8")


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
    assert re.search(r'home\.py"?(?: --data-dir "[^"]+")? set --path "[^"]+"[^\n]*--role', SETUP)
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


def _ask_blocks(text):
    """Every ```python fence in a skill that calls AskUserQuestion."""
    return [b for b in re.findall(r"```python\n(.*?)```", text, re.S) if "AskUserQuestion" in b]


def test_no_ask_user_question_block_has_empty_or_missing_options():
    bad = []
    for path in sorted(SKILLS.rglob("*.md")):
        for block in _ask_blocks(path.read_text(encoding="utf-8")):
            if re.search(r'"options"\s*:\s*\[\s*\]', block) or '"options"' not in block:
                bad.append(f"{path.relative_to(ROOT)}: {block.strip()[:80]}")
    assert not bad, bad


def test_ask_user_question_blocks_have_two_to_four_options():
    bad = []
    for path in sorted(SKILLS.rglob("SKILL.md")):
        for block in _ask_blocks(path.read_text(encoding="utf-8")):
            n = len(re.findall(r'\{"label"', block))
            if n and not 2 <= n <= 4:
                bad.append(f"{path.relative_to(ROOT)}: {n} options")
    assert not bad, bad


def test_setup_sample_paragraph_is_not_printed_then_asked_in_one_turn():
    block = FINISH.split("## Step 6", 1)[1].split("## Step 8", 1)[0]
    assert "references/finish.md" in SETUP.split("## Step 6", 1)[1].split("## Step 7", 1)[0]
    # the paragraph travels inside the question text, or the turn ends before asking
    assert "inside the question text" in block
    assert "<THE 2-4 SENTENCES>" in block
    assert "two turns" in block
    # the rule is stated once for the whole wizard
    assert re.search(r"Never print-then-ask in one turn", SETUP)
    assert "may not be shown" in SETUP


def test_setup_field_question_offers_options():
    block = SETUP.split("## Step 2", 1)[1].split("### 2b", 1)[0]
    first = block.split("```python", 1)[1].split("```", 1)[0]
    assert "Field of study" in first
    assert len(re.findall(r'\{"label"', first)) >= 2


def test_trove_option_matches_the_installer_that_runs():
    block = SETUP.split("### 4e", 1)[1].split("### 4f", 1)[0]
    assert "curl -fsSL https://heytrove.ai/install.sh | sh" in block
    assert "Homebrew" not in block


def test_manual_commands_have_a_typing_recipe_and_restart_steps():
    deps = (SKILLS / "setup" / "references" / "dependencies.md").read_text(encoding="utf-8")
    for heading in ("## Typing a command yourself", "## Opening the Terminal app", "## Restarting Claude Code"):
        assert heading in deps
    assert "prompt box" in deps and "! COMMAND" in deps
    assert "Your answers are saved" in deps
    key = (SKILLS / "setup" / "references" / "gemini-key.md").read_text(encoding="utf-8")
    assert "google_api_key" in key and "Installed" in key and "Configure" in key
    assert "Restarting Claude Code" in SETUP


def test_what_you_can_do_now_names_researcher_next_steps():
    block = FINISH.split("## Step 8", 1)[1]
    for token in ("past-articles", "/academic-writer:init", "/academic-writer:write", "/academic-writer:research"):
        assert token in block
