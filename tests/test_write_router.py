"""The `write` skill is a phase router: one listed skill, ten phase files loaded one at a time."""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WRITE = ROOT / "src" / "skills" / "write"
ROUTER = WRITE / "SKILL.md"
PHASES = ["new", "ideate", "edit", "edit-section", "revise", "proofread", "review", "research", "present", "watch"]
TRIGGERS = ["brainstorm", "write", "edit", "section", "Word comments", "proofread", "score",
            "check a claim", "talk", "abstract", "progress"]


def _parts():
    text = ROUTER.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    assert m, "router has no frontmatter"
    return yaml.safe_load(m.group(1)), m.group(2)


def _table_phases(body):
    phases = []
    in_table = False
    for line in body.splitlines():
        if re.match(r"^##\s+Phases\s*$", line):
            in_table = True
            continue
        if in_table and line.startswith("|"):
            m = re.match(r"^\|\s*`([a-z-]+)`\s*\|", line)
            if m:
                phases.append(m.group(1))
        elif in_table and phases:
            break
    return phases


def test_router_has_ten_phases():
    _, body = _parts()
    assert _table_phases(body) == PHASES
    files = sorted(p.stem for p in (WRITE / "phases").glob("*.md"))
    assert files == sorted(PHASES)


def test_description_names_every_phase_trigger():
    fm, _ = _parts()
    text = (fm["description"] + " " + str(fm.get("when_to_use", ""))).lower()
    for word in TRIGGERS:
        assert word.lower() in text, "description lacks trigger word %r" % word


def test_forked_phases_dispatch_sonnet():
    fm, body = _parts()
    assert "context" not in fm  # the old write skill was not forked
    for phase in ("proofread", "research"):
        pat = r"`%s`[^\n]*model: sonnet|model: sonnet[^\n]*`%s`" % (phase, phase)
        assert re.search(pat, body), "router body must pair `%s` with model: sonnet" % phase
    assert "Agent" in fm["allowed-tools"]


def test_bare_write_defaults_to_new():
    _, body = _parts()
    step = next(l for l in body.splitlines() if l.startswith("2. "))
    assert re.search(r"no arguments at all[^\n]*`/academic-writer:write`[^\n]*run `new`, always", step, re.I)
    assert "without asking" in step
    assert "${CLAUDE_SKILL_DIR}/phases/<phase>.md" in body


def test_phase_files_have_no_frontmatter():
    for phase in PHASES:
        text = (WRITE / "phases" / (phase + ".md")).read_text(encoding="utf-8")
        assert not text.lstrip().startswith("---"), phase


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
