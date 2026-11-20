"""The `setup` skill is a phase router: one listed skill, nine phase files loaded one at a time."""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SETUP = ROOT / "src" / "skills" / "setup"
ROUTER = SETUP / "SKILL.md"
PHASES = ["setup", "init", "health", "update-tools", "update-field", "voice", "learn", "help", "intro"]
BY_NAME_ONLY = ["setup", "init", "voice"]
TRIGGERS = ["just installed", "health", "trove", "field", "sound more like them", "what the plugin can do",
            "illustrated guide"]


def _parts():
    text = ROUTER.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    assert m, "router has no frontmatter"
    return yaml.safe_load(m.group(1)), m.group(2)


def _table(body):
    rows = {}
    in_table = False
    for line in body.splitlines():
        if re.match(r"^##\s+Phases\s*$", line):
            in_table = True
            continue
        if in_table and line.startswith("|"):
            m = re.match(r"^\|\s*`([a-z-]+)`\s*\|(.*)\|[^|]*\|\s*$", line)
            if m:
                rows[m.group(1)] = m.group(2)
        elif in_table and rows:
            break
    return rows


def test_router_has_nine_phases():
    _, body = _parts()
    assert list(_table(body)) == PHASES
    files = sorted(p.stem for p in (SETUP / "phases").glob("*.md"))
    assert files == sorted(PHASES)


def test_description_names_every_phase_trigger_and_hides_by_name_only_phases():
    fm, _ = _parts()
    text = (fm["description"] + " " + str(fm.get("when_to_use", ""))).lower()
    assert len(text) <= 1536
    for word in TRIGGERS:
        assert word.lower() in text, "description lacks trigger word %r" % word
    assert fm["argument-hint"] == "<phase> [args]"
    assert fm["user-invocable"] is True
    assert not fm.get("disable-model-invocation")


def test_by_name_only_phases_are_marked():
    _, body = _parts()
    rows = _table(body)
    for phase in PHASES:
        assert ("by name only" in rows[phase]) == (phase in BY_NAME_ONLY), phase


def test_light_phases_dispatch_haiku():
    fm, body = _parts()
    for phase in ("update-field", "help"):
        pat = r"`%s`[^\n]*model: haiku|model: haiku[^\n]*`%s`" % (phase, phase)
        assert re.search(pat, body), "router body must pair `%s` with model: haiku" % phase
    assert "Agent" in fm["allowed-tools"]
    assert "context" not in fm


def test_bare_setup_defaults_to_setup_phase():
    _, body = _parts()
    step = next(l for l in body.splitlines() if l.startswith("2. "))
    assert re.search(r"no arguments at all[^\n]*`/academic-writer:setup`[^\n]*run `setup`, always", step, re.I)
    assert "without asking" in step
    assert "${CLAUDE_SKILL_DIR}/phases/<phase>.md" in body
    assert (SETUP / "phases" / "setup.md").read_text(encoding="utf-8").startswith("# Academic Writer")


def test_help_phase_holds_the_generated_block():
    text = (SETUP / "phases" / "help.md").read_text(encoding="utf-8")
    assert "<!-- help:commands:start -->" in text and "<!-- help:commands:end -->" in text
    block = text.split("<!-- help:commands:start -->")[1].split("<!-- help:commands:end -->")[0]
    for phase in PHASES:
        cmd = "/academic-writer:setup" + ("" if phase == "setup" else " " + phase)
        assert "`%s`" % cmd in block, cmd


def test_phase_files_have_no_frontmatter():
    for phase in PHASES:
        text = (SETUP / "phases" / (phase + ".md")).read_text(encoding="utf-8")
        assert not text.lstrip().startswith("---"), phase


def test_old_names_have_no_skill_folder():
    for phase in PHASES[1:]:
        assert not (ROOT / "src" / "skills" / phase).exists(), phase


def _steps(body):
    return [l for l in body.splitlines() if re.match(r"^[1-5]\. ", l)]


def test_routing_steps_decision_order():
    _, body = _parts()
    s = _steps(body)
    assert len(s) == 5
    assert "first word" in s[0] and "phase in the table" in s[0] and "wins" in s[0]
    assert "No arguments at all" in s[1] and "without asking" in s[1]
    assert "single bare word" in s[2] and "print the table and stop" in s[2]
    assert "first word is not a phase" in s[3] and "infer" in s[3] and "ask the author" in s[3]
    assert s[4].startswith("5. Read exactly one file")


def test_update_field_collects_the_answer_in_the_parent_and_verifies():
    _, body = _parts()
    light = body.split("## Light phases", 1)[1].split("## Phases that were", 1)[0]
    assert "cannot talk to the author" in light
    assert "New field: <answer>" in light and "not to ask anything" in light
    assert "fieldOfStudy:" in light and "check" in light
    phase = (SETUP / "phases" / "update-field.md").read_text(encoding="utf-8")
    assert "`New field: <answer>`" in phase and "do not ask anything" in phase
