"""Skill and agent frontmatter follow the plugin's authoring rules.

A skill's description is how Claude decides when to load it, so every one needs a concrete
"Use when ..." trigger, never the old filler sentence that matched nothing. SKILL.md stays under
500 lines (detail goes to references/). Agents need name/description/tools and omitClaudeMd so the
researcher's own CLAUDE.md never leaks into a subagent.
"""
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = sorted((ROOT / "src/skills").glob("*/SKILL.md"))
AGENTS = sorted((ROOT / "src/agents").glob("*.md"))
BOILERPLATE = "Use when this skill's command or workflow is needed."
MAX_SKILL_LINES = 500
MAX_DESCRIPTION_CHARS = 1024  # Claude Code's documented cap on a skill description


def _frontmatter(path: pathlib.Path) -> dict:
    match = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    assert match, f"{path} has no YAML frontmatter"
    return yaml.safe_load(match.group(1)) or {}


def _id(path: pathlib.Path) -> str:
    return path.parent.name if path.name == "SKILL.md" else path.stem


def test_there_are_skills_and_agents():
    assert SKILLS and AGENTS


@pytest.mark.parametrize("path", SKILLS, ids=_id)
def test_skill_description_has_concrete_trigger(path):
    description = str(_frontmatter(path).get("description", ""))
    assert "Use when" in description, f"{_id(path)}: description lacks 'Use when'"
    assert BOILERPLATE not in description, f"{_id(path)}: boilerplate trigger sentence"
    assert len(description) <= MAX_DESCRIPTION_CHARS, f"{_id(path)}: description too long"


@pytest.mark.parametrize("path", SKILLS, ids=_id)
def test_skill_body_has_no_boilerplate(path):
    assert BOILERPLATE not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", SKILLS, ids=_id)
def test_skill_md_line_budget(path):
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines <= MAX_SKILL_LINES, f"{_id(path)}: {lines} lines > {MAX_SKILL_LINES}"


@pytest.mark.parametrize("path", AGENTS, ids=_id)
def test_agent_frontmatter(path):
    fm = _frontmatter(path)
    for key in ("name", "description", "tools"):
        assert fm.get(key), f"{_id(path)}: missing {key}"
    assert fm.get("omitClaudeMd") is True, f"{_id(path)}: omitClaudeMd must be true"
    assert fm["name"] == path.stem


def test_boilerplate_check_can_fail(tmp_path):
    bad = tmp_path / "bad" / "SKILL.md"
    bad.parent.mkdir()
    bad.write_text(f'---\nname: bad\ndescription: "Does things. {BOILERPLATE}"\n---\n\n# Bad\n',
                   encoding="utf-8")
    with pytest.raises(AssertionError):
        test_skill_description_has_concrete_trigger(bad)
