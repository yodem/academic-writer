"""The `library` (and, in step 3, `courses`) skills are phase routers like `write` and `setup`."""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "src" / "skills"

# router -> (phases in table order, default phase or None)
ROUTERS = {
    "library": (["ingest", "ingest-book", "ocr", "kotar-fetch", "library-eval"], None),
}
ADDRESS = re.compile(r"/academic-writer:([a-z-]+)(?: ([a-z-]+))?")
SIBLING = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/phases/([a-z-]+)\.md")


def _parts(router):
    text = (SKILLS / router / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    assert m, "router has no frontmatter"
    return yaml.safe_load(m.group(1)), m.group(2)


def _table(body):
    rows, in_table = [], False
    for line in body.splitlines():
        if re.match(r"^##\s+Phases\s*$", line):
            in_table = True
        elif in_table and line.startswith("|"):
            m = re.match(r"^\|\s*`([a-z-]+)`\s*\|", line)
            if m:
                rows.append(m.group(1))
        elif in_table and rows:
            break
    return rows


def test_routers_list_their_phases_and_files():
    for router, (phases, _) in ROUTERS.items():
        fm, body = _parts(router)
        assert _table(body) == phases
        files = sorted(p.stem for p in (SKILLS / router / "phases").glob("*.md"))
        assert files == sorted(phases)
        assert fm["name"] == router and fm["user-invocable"] is True
        assert fm["argument-hint"] == "<phase> [args]"
        assert "Use when" in fm["description"] and len(fm["description"]) <= 1536
        assert not fm.get("disable-model-invocation")


def test_library_has_no_default_phase():
    _, body = _parts("library")
    step = next(l for l in body.splitlines() if l.startswith("2. "))
    assert "no default phase" in step and "Print the table" in step


def test_rule_5_allows_a_named_sibling_phase_in_every_router():
    for router in ("write", "setup", *ROUTERS):
        _, body = _parts(router)
        rule = next(l for l in body.splitlines() if l.startswith("5. "))
        assert "sibling phase file" in rule, router


def test_phase_files_have_no_frontmatter_and_old_folders_are_gone():
    for router, (phases, _) in ROUTERS.items():
        for ph in phases:
            assert not (SKILLS / router / "phases" / (ph + ".md")).read_text(encoding="utf-8").startswith("---")
    for old in ("ingest", "ingest-book", "ocr", "kotar-fetch", "library-eval"):
        assert not (SKILLS / old).exists(), old


def test_cross_phase_references_are_siblings_or_router_addresses():
    for router, (phases, _) in ROUTERS.items():
        for path in (SKILLS / router / "phases").glob("*.md"):
            text = path.read_text(encoding="utf-8")
            for ph in SIBLING.findall(text):
                assert ph in phases, "%s names missing sibling phase %s" % (path.name, ph)
            for name, phase in ADDRESS.findall(text):
                if name in ("write", "setup", "library", "courses"):
                    if phase and name == router:
                        assert phase in phases, "%s: bad address %s %s" % (path.name, name, phase)
                else:
                    raise AssertionError("%s: address to a name that no longer exists: %s" % (path.name, name))
