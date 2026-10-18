import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "scripts"))
sys.path.insert(0, str(ROOT / "tests" / "courses"))
import home  # noqa: E402
import home_migrate  # noqa: E402
from test_dashboard import make_reg  # noqa: E402

STAMP = "20261018-1200"
DAILY = """#!/bin/bash
REPO="${ACADEMIC_WRITER_REPO:-$HOME/dev/academic-writer}"
COURSES="$REPO/src/scripts/courses/courses.py"
TERM_DIR="${COURSES_TERM_DIR:-$HOME/.academic-writer/courses/T1}"
echo "$TERM_DIR"
"""
PROFILE_A = """---
name: Dana Levi
role: student
citationStyle: chicago
fieldOfStudy: Jewish Philosophy
targetLanguage: he
abstractLanguages:
  - he
  - en
---

# Profile

## Sources

```json
[{"id": "s1"}]
```
"""
PROFILE_B = """---
name: Dana Levi
role: student
citationStyle: apa
fieldOfStudy: Jewish Philosophy
targetLanguage: he
abstractLanguages:
  - he
  - en
---
"""


def tree(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def setup(tmp_path):
    d, *_ = make_reg(tmp_path)
    legacy = d.parent
    ws_a, ws_b = tmp_path / "ws-a", tmp_path / "ws-b"
    for ws, text in ((ws_a, PROFILE_A), (ws_b, PROFILE_B)):
        (ws / ".academic-helper").mkdir(parents=True)
        (ws / ".academic-helper" / "profile.md").write_text(text, encoding="utf-8")
    daily = tmp_path / "bin" / "courses-daily.sh"
    daily.parent.mkdir()
    daily.write_text(DAILY, encoding="utf-8")
    acad = tmp_path / "Academic"
    return dict(home=acad, legacy=legacy, daily=daily, workspaces=[ws_a, ws_b], ws_a=ws_a, ws_b=ws_b, term=d)


def run(s, apply=False):
    return home_migrate.migrate(s["home"], legacy=s["legacy"], daily_script=s["daily"],
                                workspaces=s["workspaces"], apply=apply, stamp=STAMP)


def kinds(plan):
    return [(step["kind"], step["status"]) for step in plan["steps"]]


def test_preview_changes_nothing(tmp_path):
    s = setup(tmp_path)
    before = tree(tmp_path)
    plan = run(s)
    assert tree(tmp_path) == before
    assert not s["home"].exists()
    ks = {k for k, _ in kinds(plan)}
    assert ks == {"write-home", "copy-registry", "daily-script", "shrink-profile", "register"}
    assert all(st == "todo" for _, st in kinds(plan))
    assert any(step.get("diff") for step in plan["steps"] if step["kind"] == "daily-script")


def test_apply_copies_and_keeps_backup(tmp_path):
    s = setup(tmp_path)
    before_count = len(tree(tmp_path))
    legacy_files = tree(s["legacy"])
    run(s, apply=True)
    terms = s["home"] / ".academic-helper" / "terms"
    assert tree(terms) == legacy_files
    migrated = s["legacy"].parent / (s["legacy"].name + ".migrated-" + STAMP)
    assert migrated.is_dir() and tree(migrated) == legacy_files
    assert not s["legacy"].exists()
    assert len(tree(tmp_path)) >= before_count


def test_profile_shrunk_and_resolver_reads_merged(tmp_path):
    s = setup(tmp_path)
    pre = {w.name: home.resolve_profile(w, {}) for w in s["workspaces"]}
    run(s, apply=True)
    env = {"ACADEMIC_HOME": str(s["home"])}
    for w in s["workspaces"]:
        after = home.resolve_profile(w, env)
        expected = dict(pre[w.name].values)
        got = {k: v for k, v in after.values.items() if k != "workspace"}
        assert got == expected
        assert after.values["workspace"] in home.WORKSPACE_TYPES
        assert after.sections == pre[w.name].sections
        assert (w / ".academic-helper" / ("profile.md.bak-" + STAMP)).is_file()
    # ws-b keeps only what differs from the home identity
    shrunk = (s["ws_b"] / ".academic-helper" / "profile.md").read_text(encoding="utf-8")
    assert "citationStyle: apa" in shrunk and "name:" not in shrunk and "fieldOfStudy" not in shrunk
    assert (s["home"] / ".academic-helper" / "home.md").is_file()
    rows = home.list_workspaces(s["home"])
    assert sorted(r["path"] for r in rows) == sorted(str(w.resolve()) for w in s["workspaces"])


def test_daily_script_rewritten_with_backup(tmp_path):
    s = setup(tmp_path)
    run(s, apply=True)
    text = s["daily"].read_text(encoding="utf-8")
    assert "export ACADEMIC_HOME=" in text
    assert "$ACADEMIC_HOME/.academic-helper/terms/T1" in text
    assert ".academic-writer/courses" not in text
    assert (s["daily"].parent / ("courses-daily.sh.bak-" + STAMP)).read_text(encoding="utf-8") == DAILY
    assert subprocess.run(["bash", "-n", str(s["daily"])]).returncode == 0
    out = subprocess.run(["bash", str(s["daily"])], capture_output=True, text=True,
                         env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    assert out.stdout.strip() == str(s["home"] / ".academic-helper" / "terms" / "T1")


def test_migrate_is_idempotent(tmp_path):
    s = setup(tmp_path)
    run(s, apply=True)
    after_first = tree(tmp_path)
    plan = run(s)
    assert plan["steps"] and all(st == "done" for _, st in kinds(plan))
    run(s, apply=True)
    assert tree(tmp_path) == after_first


def test_apply_never_overwrites_a_different_destination_file(tmp_path):
    s = setup(tmp_path)
    terms = s["home"] / ".academic-helper" / "terms" / "T1"
    terms.mkdir(parents=True)
    (terms / "alpha.json").write_text("{\"slug\": \"different\"}", encoding="utf-8")
    try:
        run(s, apply=True)
    except home_migrate.MigrateError:
        pass
    else:
        raise AssertionError("expected MigrateError")
    assert (terms / "alpha.json").read_text(encoding="utf-8") == "{\"slug\": \"different\"}"
    assert s["legacy"].exists()
