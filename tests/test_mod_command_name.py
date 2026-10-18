"""The activity-pane mod must not register a command a plugin skill already owns: Claude Code refuses it, and the
refusal used to abort the whole session.start handler (the pane never opened)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mod_command_is_not_a_skill_name():
    src = (ROOT / "src" / "mod" / "register.tsx").read_text(encoding="utf-8")
    name = re.search(r"const COMMAND = '([^']+)'", src).group(1)
    skills = {p.name for p in (ROOT / "src" / "skills").iterdir() if (p / "SKILL.md").is_file()}
    assert name not in skills, "mod command /%s collides with the /academic-writer:%s skill" % (name, name)


def test_command_register_refusal_does_not_abort_session_start():
    src = (ROOT / "src" / "mod" / "register.tsx").read_text(encoding="utf-8")
    line = next(l for l in src.splitlines() if "$.command.register(" in l)
    assert ".catch(" in line
