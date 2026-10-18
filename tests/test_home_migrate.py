import hashlib
import json
import plistlib
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
    return dict(home=acad, data=tmp_path / "plugin-data", legacy=legacy, daily=daily, workspaces=[ws_a, ws_b], ws_a=ws_a, ws_b=ws_b, term=d)


def run(s, apply=False, **kw):
    kw.setdefault("data_dir", s["data"])
    return home_migrate.migrate(s["home"], legacy=s["legacy"], daily_script=s["daily"],
                                workspaces=s["workspaces"], apply=apply, stamp=STAMP, **kw)


def kinds(plan):
    return [(step["kind"], step["status"]) for step in plan["steps"]]


def test_preview_changes_nothing(tmp_path):
    s = setup(tmp_path)
    before = tree(tmp_path)
    plan = run(s)
    assert tree(tmp_path) == before
    assert not s["home"].exists()
    ks = {k for k, _ in kinds(plan)}
    assert ks == {"write-home", "set-home-pointer", "copy-registry", "rewrite-registry", "daily-script",
                  "shrink-profile", "register"}
    assert {k for k, st in kinds(plan) if st == "done"} == {"rewrite-registry"}  # nothing legacy inside this registry
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


def test_home_md_takes_only_identity_equal_across_all_workspaces(tmp_path):
    s = setup(tmp_path)
    # ws-a has fieldOfStudy and citationStyle chicago; ws-b lacks fieldOfStudy and uses apa
    s["ws_b"].joinpath(".academic-helper", "profile.md").write_text(
        PROFILE_B.replace("fieldOfStudy: Jewish Philosophy\n", ""), encoding="utf-8")
    pre = {w.name: home.resolve_profile(w, {}) for w in s["workspaces"]}
    run(s, apply=True)
    home_values = home.read_frontmatter((s["home"] / ".academic-helper" / "home.md").read_text(encoding="utf-8"))
    assert "fieldOfStudy" not in home_values and "citationStyle" not in home_values
    assert home_values["name"] == "Dana Levi" and home_values["role"] == "student"
    env = {"ACADEMIC_HOME": str(s["home"])}
    for w in s["workspaces"]:
        got = {k: v for k, v in home.resolve_profile(w, env).values.items() if k != "workspace"}
        assert got == pre[w.name].values  # no workspace gained or lost a value
    assert "fieldOfStudy" not in home.resolve_profile(s["ws_b"], env).values
    assert "citationStyle: chicago" in s["ws_a"].joinpath(".academic-helper", "profile.md").read_text(encoding="utf-8")


# --- pointer, registry rewrite, helper scripts and launchd ------------------------------------------

def seed_paths(s):
    """Put legacy absolute paths in live registry files; return the pieces tests assert on."""
    legacy = s["legacy"]
    heb = legacy / "\u05e1\u05de\u05e1\u05d8\u05e8 \u05d0"
    heb.mkdir()
    (heb / "term.json").write_text(json.dumps({"term": "\u05e1\u05de\u05e1\u05d8\u05e8 \u05d0",
                                               "file": str(heb / "reading.pdf")}, ensure_ascii=False), encoding="utf-8")
    (heb / "reading.pdf").write_bytes(b"%PDF")
    term = s["term"]
    (term / "reading.pdf").write_bytes(b"%PDF")
    external = s["home"].parent / "elsewhere" / "audio.m4a"
    external.parent.mkdir()
    external.write_bytes(b"a")
    beta = json.loads((term / "beta.json").read_text(encoding="utf-8"))
    beta["sources"][0]["file"] = str(term / "reading.pdf")
    beta["sources"][0]["path"] = str(term / "reading.pdf") + ".missing"
    (term / "beta.json").write_text(json.dumps(beta, ensure_ascii=False), encoding="utf-8")
    lesson = term / "lessons" / "2026-10-16" / "meta.json"
    lesson.parent.mkdir(parents=True)
    lesson.write_text(json.dumps({"audio_path": str(term / "reading.pdf"), "ext": str(external),
                                  "other": str(legacy) + "-other/x", "name": "\u05e9\u05d9\u05e2\u05d5\u05e8"}),
                      encoding="utf-8")
    handoff = term / "LEAD-HANDOFF.md"
    handoff.write_text("See %s/beta.json and `%s/reading.pdf`.\n" % (term, term), encoding="utf-8")
    log = term / "logs" / "daily-1.log"
    log.parent.mkdir()
    log.write_text("ran %s/beta.json\n" % term, encoding="utf-8")
    done = term / "queue" / "done" / "r1.json"
    done.parent.mkdir(parents=True)
    done.write_text(json.dumps({"path": str(term / "beta.json")}), encoding="utf-8")
    return dict(heb=heb, external=external, lesson=lesson, handoff=handoff, log=log, done=done)


def seed_launchd(s):
    bin_dir = s["daily"].parent
    legacy = str(s["legacy"])
    sync = bin_dir / "courses-sync-nanoclaw.sh"
    sync.write_text('#!/bin/bash\nSRC="%s/T1"\nrsync -a "$SRC/" /dev/null\n' % legacy, encoding="utf-8")
    lock = bin_dir / "book-lock.sh"
    lock.write_text('#!/bin/bash\nDIR="%s/T1/.locks"\n' % legacy, encoding="utf-8")
    agents = s["home"].parent / "LaunchAgents"
    agents.mkdir()
    plist = agents / "com.example.courses-daily.plist"
    plist.write_bytes(plistlib.dumps({
        "Label": "com.example.courses-daily", "ProgramArguments": ["/bin/bash", str(s["daily"])],
        "StandardOutPath": legacy + "/T1/logs/launchd.log", "StandardErrorPath": legacy + "/T1/logs/launchd.log"}))
    unrelated = agents / "com.example.other.plist"
    unrelated.write_bytes(plistlib.dumps({"Label": "com.example.other", "ProgramArguments": ["/bin/true"]}))
    return dict(sync=sync, lock=lock, agents=agents, plist=plist, unrelated=unrelated)


def baks(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*.bak-*"))


def test_pointer_written_and_resolves(tmp_path):
    s = setup(tmp_path)
    plan = run(s, apply=True)
    step = [x for x in plan["steps"] if x["kind"] == "set-home-pointer"][0]
    assert step["status"] == "done"
    assert home.home_dir({"CLAUDE_PLUGIN_DATA": str(s["data"])}) == s["home"]
    assert not baks(s["data"])  # nothing existed to back up


def test_pointer_skipped_without_data_dir(tmp_path):
    s = setup(tmp_path)
    plan = run(s, apply=True, data_dir=None)
    step = [x for x in plan["steps"] if x["kind"] == "set-home-pointer"][0]
    assert step["status"] == "skipped" and step["note"]
    assert plan["warnings"]
    assert not s["data"].exists()


def test_different_pointer_is_backed_up(tmp_path):
    s = setup(tmp_path)
    s["data"].mkdir()
    (s["data"] / "home.json").write_text(json.dumps({"path": str(tmp_path / "old-home")}), encoding="utf-8")
    run(s, apply=True)
    assert home.home_dir({"CLAUDE_PLUGIN_DATA": str(s["data"])}) == s["home"]
    assert json.loads((s["data"] / ("home.json.bak-" + STAMP)).read_text(encoding="utf-8"))["path"] == str(tmp_path / "old-home")


def test_registry_paths_rewritten_with_backups(tmp_path):
    s = setup(tmp_path)
    seeds = seed_paths(s)
    legacy, term = str(s["legacy"]), str(s["term"])
    run(s, apply=True)
    terms = s["home"] / ".academic-helper" / "terms"
    beta = json.loads((terms / "T1" / "beta.json").read_text(encoding="utf-8"))
    assert beta["sources"][0]["file"] == str(terms / "T1" / "reading.pdf")
    assert beta["sources"][0]["path"] == str(terms / "T1" / "reading.pdf") + ".missing"
    meta = json.loads((terms / "T1" / "lessons" / "2026-10-16" / "meta.json").read_text(encoding="utf-8"))
    assert meta["audio_path"] == str(terms / "T1" / "reading.pdf")
    assert meta["ext"] == str(seeds["external"])  # outside the legacy prefix: untouched
    assert meta["other"] == legacy + "-other/x"  # lookalike prefix: untouched
    assert meta["name"] == "\u05e9\u05d9\u05e2\u05d5\u05e8"
    assert str(terms / "T1" / "beta.json") in (terms / "T1" / "LEAD-HANDOFF.md").read_text(encoding="utf-8")
    assert legacy not in (terms / "T1" / "LEAD-HANDOFF.md").read_text(encoding="utf-8")
    for name in ("beta.json", "LEAD-HANDOFF.md", "lessons/2026-10-16/meta.json"):
        assert (terms / "T1" / (name + ".bak-" + STAMP)).is_file()
    # logs and queue/done are history: untouched
    assert (terms / "T1" / "logs" / "daily-1.log").read_text(encoding="utf-8") == "ran %s/beta.json\n" % term
    assert json.loads((terms / "T1" / "queue" / "done" / "r1.json").read_text(encoding="utf-8"))["path"] == term + "/beta.json"


def test_hebrew_term_name_survives(tmp_path):
    s = setup(tmp_path)
    seeds = seed_paths(s)
    run(s, apply=True)
    heb = s["home"] / ".academic-helper" / "terms" / "\u05e1\u05de\u05e1\u05d8\u05e8 \u05d0"
    data = json.loads((heb / "term.json").read_text(encoding="utf-8"))
    assert data["term"] == "\u05e1\u05de\u05e1\u05d8\u05e8 \u05d0"
    assert data["file"] == str(heb / "reading.pdf") and (heb / "reading.pdf").is_file()


def test_ensure_ascii_escaped_prefix_is_rewritten(tmp_path):
    root = tmp_path / "\u05e2\u05d1\u05e8\u05d9\u05ea" / "courses"
    (root / "T1").mkdir(parents=True)
    (root / "T1" / "a.json").write_text(json.dumps({"file": str(root / "T1" / "x.pdf")}), encoding="utf-8")
    assert "\\u05e2" in (root / "T1" / "a.json").read_text(encoding="utf-8")
    acad = tmp_path / "Academic"
    home_migrate.migrate(acad, legacy=root, apply=True, stamp=STAMP)
    got = json.loads((acad / ".academic-helper" / "terms" / "T1" / "a.json").read_text(encoding="utf-8"))
    assert got["file"] == str(acad / ".academic-helper" / "terms" / "T1" / "x.pdf")


def test_missing_targets_are_listed(tmp_path):
    s = setup(tmp_path)
    seed_paths(s)
    plan = run(s, apply=True)
    step = [x for x in plan["steps"] if x["kind"] == "rewrite-registry"][0]
    terms = s["home"] / ".academic-helper" / "terms"
    assert step["missing"] == [str(terms / "T1" / "reading.pdf") + ".missing"]
    assert any("do not exist" in w for w in plan["warnings"])


def test_preview_counts_legacy_matches_and_changes_nothing(tmp_path):
    s = setup(tmp_path)
    seed_paths(s)
    before = tree(tmp_path)
    plan = run(s)
    assert tree(tmp_path) == before
    step = [x for x in plan["steps"] if x["kind"] == "rewrite-registry"][0]
    assert step["status"] == "todo" and step["files"] == 4 and step["matches"] >= 3


def test_broken_json_after_rewrite_writes_nothing(tmp_path, monkeypatch):
    s = setup(tmp_path)
    seed_paths(s)
    home_migrate_sub = home_migrate._subst
    def bad(text, subs):
        new, n = home_migrate_sub(text, subs)
        return (new + "}", n) if n and text.lstrip().startswith("{") else (new, n)
    monkeypatch.setattr(home_migrate, "_subst", bad)
    try:
        run(s, apply=True)
    except home_migrate.MigrateError:
        pass
    else:
        raise AssertionError("expected MigrateError")
    assert s["legacy"].exists() and not baks(tmp_path)  # nothing moved, nothing written


def test_helpers_and_plist_rewritten(tmp_path):
    s = setup(tmp_path)
    seed_paths(s)
    h = seed_launchd(s)
    plain_unrelated = h["unrelated"].read_bytes()
    plan = run(s, apply=True, launch_agents_dir=h["agents"])
    terms = str(s["home"] / ".academic-helper" / "terms")
    legacy = str(s["legacy"])
    assert 'SRC="%s/T1"' % terms in h["sync"].read_text(encoding="utf-8")
    assert 'DIR="%s/T1/.locks"' % terms in h["lock"].read_text(encoding="utf-8")
    for p in (h["sync"], h["lock"]):
        assert legacy not in p.read_text(encoding="utf-8")
        assert (p.parent / (p.name + ".bak-" + STAMP)).is_file()
    pl = plistlib.loads(h["plist"].read_bytes())
    assert pl["StandardOutPath"] == terms + "/T1/logs/launchd.log" and pl["StandardErrorPath"] == pl["StandardOutPath"]
    backup = h["agents"] / ("com.example.courses-daily.plist.bak-" + STAMP)
    assert backup.is_file() and not str(backup).endswith(".plist")
    assert h["unrelated"].read_bytes() == plain_unrelated
    assert not [p for p in h["agents"].glob("*.plist") if "other" in p.name and p.read_bytes() != plain_unrelated]
    item = plan["reload"][0]
    assert item["label"] == "com.example.courses-daily" and item["ran"] is False
    assert item["commands"][0][:2] == ["launchctl", "bootout"] and item["commands"][1][:2] == ["launchctl", "bootstrap"]
    assert item["commands"][1][-1] == str(h["plist"])


def test_daily_script_rest_of_file_rewritten(tmp_path):
    s = setup(tmp_path)
    s["daily"].write_text(DAILY + 'cp "%s/T1/x" /dev/null\n' % s["legacy"], encoding="utf-8")
    run(s, apply=True)
    text = s["daily"].read_text(encoding="utf-8")
    assert str(s["legacy"]) not in text and "export ACADEMIC_HOME=" in text
    assert str(s["home"] / ".academic-helper" / "terms") + "/T1/x" in text


def test_hand_fixed_export_with_leftover_prefix_is_fixed_then_done(tmp_path):
    s = setup(tmp_path)
    s["daily"].write_text('#!/bin/bash\nexport ACADEMIC_HOME="%s"\nLOG="%s/T1/logs/x"\n' % (s["home"], s["legacy"]),
                          encoding="utf-8")
    plan = run(s)
    assert [x["status"] for x in plan["steps"] if x["kind"] == "daily-script"] == ["todo"]
    run(s, apply=True)
    assert [x["status"] for x in run(s)["steps"] if x["kind"] == "daily-script"] == ["done"]


def test_reload_runner_only_with_flag(tmp_path):
    s = setup(tmp_path)
    h = seed_launchd(s)
    calls = []
    def runner(cmd):
        calls.append(cmd)
        return 0
    run(s, apply=True, launch_agents_dir=h["agents"], runner=runner)
    assert calls == []
    # fresh scenario with the flag
    t2 = tmp_path / "t2"
    t2.mkdir()
    s2 = setup(t2)
    h2 = seed_launchd(s2)
    plan = run(s2, apply=True, launch_agents_dir=h2["agents"], reload_launchd=True, runner=runner)
    assert [c[1] for c in calls] == ["bootout", "bootstrap"]
    assert calls[0][2].endswith("/com.example.courses-daily") and calls[1][-1] == str(h2["plist"])
    assert plan["reload"][0]["ran"] is True and plan["reload"][0]["returncodes"] == [0, 0]


def test_reload_not_run_in_preview(tmp_path):
    s = setup(tmp_path)
    h = seed_launchd(s)
    calls = []
    run(s, apply=False, launch_agents_dir=h["agents"], reload_launchd=True, runner=calls.append)
    assert calls == []


def test_second_apply_changes_nothing(tmp_path):
    s = setup(tmp_path)
    seed_paths(s)
    h = seed_launchd(s)
    run(s, apply=True, launch_agents_dir=h["agents"])
    after_first = tree(tmp_path)
    plan = run(s, launch_agents_dir=h["agents"])
    assert plan["steps"] and all(st == "done" for _, st in kinds(plan)), kinds(plan)
    assert not plan["reload"]
    plan = run(s, apply=True, launch_agents_dir=h["agents"])
    assert tree(tmp_path) == after_first


def test_hand_fixed_state_is_all_done(tmp_path):
    """A second run on state somebody already repaired by hand (pointer, export, no legacy prefix) changes nothing."""
    s = setup(tmp_path)
    run(s, apply=True)
    before = tree(tmp_path)
    again = home_migrate.migrate(
        s["home"], legacy=s["legacy"], daily_script=s["daily"], workspaces=s["workspaces"], apply=True,
        stamp="20991231-2359", data_dir=s["data"])
    assert all(st == "done" for _, st in kinds(again))
    assert tree(tmp_path) == before


def test_cli_data_dir_and_env_fallback(tmp_path):
    s = setup(tmp_path)
    cmd = [sys.executable, str(ROOT / "src" / "scripts" / "home_migrate.py"), "--home", str(s["home"]),
           "--legacy", str(s["legacy"]), "--daily-script", str(s["daily"]),
           "--launch-agents-dir", str(tmp_path / "no-agents")]
    for w in s["workspaces"]:
        cmd += ["--workspace", str(w)]
    env = {"PATH": "/usr/bin:/bin", "CLAUDE_PLUGIN_DATA": str(s["data"])}
    out = subprocess.run(cmd + ["--apply"], capture_output=True, text=True, env=env)
    assert out.returncode == 0, out.stderr
    assert home.home_dir({"CLAUDE_PLUGIN_DATA": str(s["data"])}) == s["home"]
    plan = json.loads(out.stdout)
    assert [x["status"] for x in plan["steps"] if x["kind"] == "set-home-pointer"] == ["done"]


def test_cli_warns_without_data_dir(tmp_path):
    s = setup(tmp_path)
    cmd = [sys.executable, str(ROOT / "src" / "scripts" / "home_migrate.py"), "--home", str(s["home"]),
           "--legacy", str(s["legacy"]), "--launch-agents-dir", str(tmp_path / "no-agents")]
    out = subprocess.run(cmd, capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert out.returncode == 0 and "warning:" in out.stderr and "pointer" in out.stderr


def test_cli_reload_flag_needs_apply(tmp_path):
    s = setup(tmp_path)
    cmd = [sys.executable, str(ROOT / "src" / "scripts" / "home_migrate.py"), "--home", str(s["home"]),
           "--legacy", str(s["legacy"]), "--reload-launchd"]
    out = subprocess.run(cmd, capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert out.returncode == 2


def test_binary_plist_rewritten_in_binary_form(tmp_path):
    s = setup(tmp_path)
    h = seed_launchd(s)
    data = plistlib.loads(h["plist"].read_bytes())
    h["plist"].write_bytes(plistlib.dumps(data, fmt=plistlib.FMT_BINARY))
    plan = run(s, apply=True, launch_agents_dir=h["agents"])
    raw = h["plist"].read_bytes()
    assert raw.startswith(b"bplist")
    pl = plistlib.loads(raw)
    terms = str(s["home"] / ".academic-helper" / "terms")
    assert pl["StandardOutPath"] == terms + "/T1/logs/launchd.log"
    assert (h["agents"] / ("com.example.courses-daily.plist.bak-" + STAMP)).is_file()
    assert plan["reload"] and plan["reload"][0]["label"] == "com.example.courses-daily"
    again = run(s, apply=True, launch_agents_dir=h["agents"])
    assert [x["status"] for x in again["steps"] if x["kind"] == "launchd-plist"] == ["done"]
