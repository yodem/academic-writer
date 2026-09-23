import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).parent.parent
SKILL_KEYS = {
    "name", "description", "allowed-tools", "user-invocable",
    "disable-model-invocation", "model", "effort", "context", "metadata",
    "argument-hint",
}
AGENT_KEYS = {
    "name", "description", "tools", "disallowedTools", "model",
    "omitClaudeMd", "color", "effort",
}


def _fm(path):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    return yaml.safe_load(match.group(1)) if match else {}


def check_skill(path) -> list[str]:
    fm = _fm(path)
    out = [f"unknown skill key {key}" for key in fm if key not in SKILL_KEYS]
    if "Use when" not in str(fm.get("description", "")):
        out.append("description lacks 'Use when'")
    if len(path.read_text(encoding="utf-8").splitlines()) > 500:
        out.append("SKILL.md > 500 lines")
    return out


def check_agent(path) -> list[str]:
    fm = _fm(path)
    out = [f"unknown agent key {key}" for key in fm if key not in AGENT_KEYS]
    if fm.get("omitClaudeMd") is not True:
        out.append("omitClaudeMd not true")
    return out


def test_bad_fixture_is_caught():
    assert check_skill(ROOT / "tests/fixtures/frontmatter/bad-skill/SKILL.md")


def test_all_skills_clean():
    bad = {
        str(path): check_skill(path)
        for path in (ROOT / "src/skills").glob("*/SKILL.md")
    }
    assert not {key: value for key, value in bad.items() if value}


def test_all_agents_clean_and_no_phantoms():
    agents = list((ROOT / "src/agents").glob("*.md"))
    # src/agents/memory/ is local, gitignored agent memory. What matters is that the shipped
    # plugin carries only top-level agent definitions: anything under agents/ loads as an agent.
    import subprocess
    shipped = subprocess.run(["git", "ls-files", "plugins/academic-writer/agents"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.split()
    assert shipped and all(p.count("/") == 3 and p.endswith(".md") for p in shipped), shipped
    bad = {str(path): check_agent(path) for path in agents}
    assert not {key: value for key, value in bad.items() if value}

def test_build_does_not_ship_agent_memory():
    # Pins the build: only top-level agent .md files are copied into the plugin.
    build = (ROOT/"scripts/build-plugins.sh").read_text(encoding="utf-8")
    assert 'cp -R "$SRC_DIR/agents"' not in build
    assert "-maxdepth 1 -name '*.md'" in build

def test_plugin_settings_has_only_supported_keys():
    import json
    s = json.loads((ROOT/"src/settings/academic-writer.settings.json").read_text())
    assert set(s) <= {"agent", "subagentStatusLine"}
