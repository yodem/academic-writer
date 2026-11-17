"""Tests for scripts/skill_budget.py. Every case runs with PyYAML and with the
stdlib fallback parser (SKILL_BUDGET_NO_YAML=1)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "skill_budget.py"
BASELINE = Path(__file__).resolve().parent / "fixtures" / "skill_budget_baseline.json"


@pytest.fixture(params=["yaml", "fallback"])
def run(request, tmp_path):
    def _run(*args, stdin=""):
        env = dict(os.environ)
        env.pop("SKILL_BUDGET_NO_YAML", None)
        if request.param == "fallback":
            env["SKILL_BUDGET_NO_YAML"] = "1"
        return subprocess.run(
            [sys.executable, str(SCRIPT)] + [str(a) for a in args],
            input=stdin, capture_output=True, text=True, env=env,
        )
    return _run


def skill(root, name, fm, body="Body $ARGUMENTS\n"):
    d = Path(root) / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("---\n%s\n---\n%s" % (fm, body), encoding="utf-8")
    return d


def router(root, name="write", phases=("ideate", "draft"), table=None, extra_fm="", body_extra=""):
    table = phases if table is None else table
    rows = "\n".join("| `%s` | does %s |" % (p, p) for p in table)
    fm = 'name: %s\ndescription: "Route %s work. Use when writing."\nargument-hint: "<phase> [args]"\n%s' % (
        name, name, extra_fm)
    d = skill(root, name, fm.strip(), "# R\n\n## Phases\n\n| Phase | What |\n|---|---|\n%s\n%s" % (rows, body_extra))
    (d / "phases").mkdir(exist_ok=True)
    for p in phases:
        (d / "phases" / (p + ".md")).write_text("# %s\n" % p)
    return d


def stub(root, name, moved, fm_style="flow", body="Run it $ARGUMENTS\n"):
    if fm_style == "flow":
        meta = 'metadata: {moved-to: "%s"}' % moved
    else:
        meta = 'metadata:\n  moved-to: "%s"' % moved
    return skill(root, name, 'name: %s\ndescription: "old"\ndisable-model-invocation: true\n%s' % (name, meta), body)


# ---- measure -------------------------------------------------------------

def test_measure_ignores_hidden_skills(run, tmp_path):
    skill(tmp_path, "a", 'name: a\ndescription: "12345"\nwhen_to_use: "123"')
    skill(tmp_path, "b", 'name: b\ndescription: "should not count"\ndisable-model-invocation: true')
    stub(tmp_path, "c", "write ideate", fm_style="block")
    r = run("measure", tmp_path)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {"listed_chars": 8, "listed_skills": 1, "stubs": 1}
    r = run("measure", tmp_path, "--field", "listed_chars")
    assert r.stdout.strip() == "8"


def test_measure_counts_folded_description(run, tmp_path):
    skill(tmp_path, "a", "name: a\ndescription: >\n  alpha beta\n  gamma\nwhen_to_use: |-\n  one\n  two")
    # folded clip: "alpha beta gamma\n" = 17; literal strip: "one\ntwo" = 7
    r = run("measure", tmp_path, "--field", "listed_chars")
    assert r.stdout.strip() == "24", r.stderr


def test_measure_commands_dir(run, tmp_path):
    sk = tmp_path / "skills"
    cm = tmp_path / "commands"
    cm.mkdir()
    skill(sk, "a", 'name: a\ndescription: "abc"')
    (cm / "x.md").write_text('---\ndescription: "abcd"\n---\nBody\n')
    (cm / "y.md").write_text('---\ndescription: "hidden"\ndisable-model-invocation: true\nmetadata: {moved-to: "w p"}\n---\n$ARGUMENTS\n')
    r = run("measure", sk, "--commands", cm)
    assert json.loads(r.stdout) == {"listed_chars": 7, "listed_skills": 2, "stubs": 1}


def test_fallback_handles_quotes_and_flow(run, tmp_path):
    skill(tmp_path, "a", "name: a\ndescription: 'it''s \"ok\"'\nmetadata: {author: \"Y\", version: \"1\"}")
    r = run("measure", tmp_path, "--field", "listed_chars")
    assert r.stdout.strip() == str(len('it\'s "ok"')), r.stderr


# ---- check-routers -------------------------------------------------------

def test_check_routers_clean_tree_exits_0(run, tmp_path):
    router(tmp_path)
    stub(tmp_path, "old", "write ideate")
    r = run("check-routers", tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout == ""


def test_phase_row_without_file(run, tmp_path):
    router(tmp_path, phases=("ideate",), table=("ideate", "ghost"))
    r = run("check-routers", tmp_path)
    assert r.returncode == 1
    assert "ghost" in r.stdout and "no phases/ghost.md" in r.stdout


def test_phase_file_missing_from_table(run, tmp_path):
    router(tmp_path, phases=("ideate", "extra"), table=("ideate",))
    r = run("check-routers", tmp_path)
    assert r.returncode == 1
    assert "phases/extra.md is missing from" in r.stdout


def test_phases_heading_after_line_60(run, tmp_path):
    router(tmp_path)
    p = tmp_path / "write" / "SKILL.md"
    text = p.read_text().replace("# R\n", "# R\n" + "filler\n" * 70)
    p.write_text(text)
    r = run("check-routers", tmp_path)
    assert r.returncode == 1
    assert "at line" in r.stdout and "must be at or before line 60" in r.stdout


def test_skill_over_150_lines(run, tmp_path):
    router(tmp_path, body_extra="x\n" * 160)
    r = run("check-routers", tmp_path)
    assert r.returncode == 1
    assert "lines (max 150)" in r.stdout


def test_description_over_1536(run, tmp_path):
    d = router(tmp_path)
    p = d / "SKILL.md"
    p.write_text(p.read_text().replace("Route write work. Use when writing.", "x" * 1537))
    r = run("check-routers", tmp_path)
    assert r.returncode == 1
    assert "1537 chars (max 1536)" in r.stdout


def test_missing_argument_hint(run, tmp_path):
    d = router(tmp_path)
    p = d / "SKILL.md"
    p.write_text(p.read_text().replace('argument-hint: "<phase> [args]"\n', ""))
    r = run("check-routers", tmp_path)
    assert r.returncode == 1
    assert "missing argument-hint" in r.stdout


def test_stub_moved_to_missing_router_or_phase(run, tmp_path):
    router(tmp_path)
    stub(tmp_path, "s1", "nope ideate")
    stub(tmp_path, "s2", "write nophase", fm_style="block")
    r = run("check-routers", tmp_path)
    assert r.returncode == 1
    assert "router 'nope' does not exist" in r.stdout
    assert "phase 'write nophase' does not exist" in r.stdout


def test_stub_body_without_arguments(run, tmp_path):
    router(tmp_path)
    stub(tmp_path, "s1", "write ideate", body="no placeholder here\n")
    r = run("check-routers", tmp_path)
    assert r.returncode == 1
    assert "no $ARGUMENTS" in r.stdout


def test_phase_file_unresolved_paths(run, tmp_path):
    d = router(tmp_path)
    (d / "refs").mkdir()
    (d / "refs" / "ok.md").write_text("ok")
    (d / "phases" / "ideate.md").write_text(
        "See [a](missing.md) and `../refs/ok.md` and ${CLAUDE_SKILL_DIR}/refs/gone.md "
        "and ${CLAUDE_PLUGIN_ROOT}/nothing/here.md and ${CLAUDE_SKILL_DIR}/refs/ok.md\n")
    r = run("check-routers", tmp_path)
    assert r.returncode == 1
    out = r.stdout
    assert "relative path missing.md does not resolve" in out
    assert "${CLAUDE_SKILL_DIR}/refs/gone.md does not resolve" in out
    assert "${CLAUDE_PLUGIN_ROOT}/nothing/here.md does not resolve" in out
    assert "../refs/ok.md" not in out
    assert out.count("\n") == 3


def test_description_plus_when_to_use_over_1536(run, tmp_path):
    d = router(tmp_path, extra_fm='when_to_use: "%s"' % ("w" * 1530))
    r = run("check-routers", tmp_path)
    assert r.returncode == 1
    assert "description + when_to_use is" in r.stdout and "(max 1536)" in r.stdout


def test_trailing_punctuation_not_part_of_path(run, tmp_path):
    d = router(tmp_path)
    (d / "refs").mkdir()
    (d / "refs" / "x.md").write_text("x")
    (d / "phases" / "ideate.md").write_text(
        "Read ${CLAUDE_SKILL_DIR}/refs/x.md. Also ${CLAUDE_SKILL_DIR}/refs/x.md, and (${CLAUDE_SKILL_DIR}/refs/x.md); "
        "and ${CLAUDE_SKILL_DIR}/refs/x.md: ok\n")
    r = run("check-routers", tmp_path)
    assert r.returncode == 0, r.stdout


def test_phases_dir_without_skill_md(run, tmp_path):
    (tmp_path / "orphan" / "phases").mkdir(parents=True)
    r = run("check-routers", tmp_path)
    assert r.returncode == 1
    assert "orphan: has phases/ but no SKILL.md" in r.stdout


def test_check_routers_commands_dir(run, tmp_path):
    sk = tmp_path / "skills"
    cm = tmp_path / "commands"
    cm.mkdir()
    router(sk)
    (cm / "good.md").write_text('---\ndescription: x\ndisable-model-invocation: true\nmetadata: {moved-to: "write ideate"}\n---\n$ARGUMENTS\n')
    assert run("check-routers", sk, "--commands", cm).returncode == 0
    (cm / "bad.md").write_text('---\ndescription: x\ndisable-model-invocation: true\nmetadata: {moved-to: "write nope"}\n---\nno args\n')
    r = run("check-routers", sk, "--commands", cm)
    assert r.returncode == 1
    assert "bad.md" in r.stdout and "does not exist" in r.stdout and "no $ARGUMENTS" in r.stdout


def test_measure_field_stubs(run, tmp_path):
    stub(tmp_path, "a", "write ideate")
    stub(tmp_path, "b", "write draft", fm_style="block")
    skill(tmp_path, "c", 'name: c\ndescription: "x"')
    assert run("measure", tmp_path, "--field", "stubs").stdout.strip() == "2"
    assert run("measure", tmp_path, "--field", "listed_skills").stdout.strip() == "1"


def test_fallback_unindented_block_list(run, tmp_path):
    skill(tmp_path, "a", 'name: a\nallowed-tools:\n- Read\n- Bash\ndescription: "abc"\nargument-hint: x')
    r = run("measure", tmp_path, "--field", "listed_chars")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "3"


# ---- gate ----------------------------------------------------------------

def test_gate_passes_at_60_fails_at_59(run, tmp_path):
    base = tmp_path / "base.json"
    base.write_text(json.dumps({"listed_chars": 1000, "listed_skills": 3, "stubs": 0}))
    sk = tmp_path / "s"
    skill(sk, "a", 'name: a\ndescription: "%s"' % ("x" * 400))
    r = run("gate", sk, "--baseline", base, "--min-cut", 60)
    assert r.returncode == 0, r.stdout
    assert "400" in r.stdout and "1000" in r.stdout and "60.0%" in r.stdout
    sk2 = tmp_path / "s2"
    skill(sk2, "a", 'name: a\ndescription: "%s"' % ("x" * 410))
    r = run("gate", sk2, "--baseline", base, "--min-cut", 60)
    assert r.returncode == 1
    assert "59.0%" in r.stdout


def test_gate_bad_baseline_exits_2(run, tmp_path):
    skill(tmp_path / "s", "a", 'name: a\ndescription: "x"')
    r = run("gate", tmp_path / "s", "--baseline", tmp_path / "nope.json", "--min-cut", 60)
    assert r.returncode == 2


# ---- reads / final-text --------------------------------------------------

def _stream(subtype="success", extra=()):
    lines = [
        "not json at all",
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "I will read /mentioned/only.md"},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/a/one.md"}},
            {"type": "tool_use", "name": "Grep", "input": {"pattern": "x", "file_path": "/not/read.md"}},
        ]}}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/b/two.md"}}]}}),
    ]
    lines += list(extra)
    lines.append(json.dumps({"type": "result", "subtype": subtype, "result": "Academic Writer final"}))
    return "\n".join(lines) + "\n"


def test_reads_lists_only_read_tool_calls(run):
    r = run("reads", stdin=_stream())
    assert r.returncode == 0
    assert r.stdout.split("\n")[:-1] == ["/a/one.md", "/b/two.md"]


def test_reads_require_success_exits_2_on_error_stream(run):
    assert run("reads", "--require-success", stdin=_stream("error_max_turns")).returncode == 2
    assert run("reads", "--require-success", stdin="garbage\n").returncode == 2
    ok = run("reads", "--require-success", stdin=_stream())
    assert ok.returncode == 0


def test_final_text(run):
    r = run("final-text", stdin=_stream())
    assert r.returncode == 0 and r.stdout.strip() == "Academic Writer final"
    assert run("final-text", stdin="nothing\n").returncode == 2


def test_reads_empty_stdin_exits_2(run):
    assert run("reads", stdin="").returncode == 2
    assert run("reads", "--require-success", stdin="").returncode == 2


# ---- errors --------------------------------------------------------------

def test_parse_error_exits_2(run, tmp_path):
    d = tmp_path / "bad"
    d.mkdir()
    (d / "SKILL.md").write_text("no frontmatter here\n")
    for cmd in (("measure",), ("check-routers",)):
        assert run(*cmd, tmp_path).returncode == 2
    assert run("measure", tmp_path / "missing").returncode == 2
    assert run("bogus").returncode == 2
    assert run("gate", tmp_path).returncode == 2  # missing required args


def test_unterminated_frontmatter_exits_2(run, tmp_path):
    d = tmp_path / "bad"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: x\n")
    assert run("measure", tmp_path).returncode == 2


# ---- baseline fixture ----------------------------------------------------

def test_baseline_fixture_is_well_formed():
    data = json.loads(BASELINE.read_text())
    assert set(data) == {"listed_chars", "listed_skills", "stubs"}
    assert data["listed_chars"] > 1000


# ---- check-routers: plugin-root path rules ---------------------------------

def _phase_with(tmp_path, text):
    d = router(tmp_path)
    (d / "phases" / "ideate.md").write_text(text)
    return d


def test_plugin_root_build_generated_bin_aw_is_allowed(run, tmp_path):
    _phase_with(tmp_path, "Run `${CLAUDE_PLUGIN_ROOT}/bin/aw` now.\n")
    assert run("check-routers", tmp_path).returncode == 0


def test_plugin_root_other_bin_file_still_checked(run, tmp_path):
    _phase_with(tmp_path, "Run `${CLAUDE_PLUGIN_ROOT}/bin/other` now.\n")
    r = run("check-routers", tmp_path)
    assert r.returncode == 1 and "bin/other does not resolve" in r.stdout


def test_runtime_variable_path_with_existing_dir_is_allowed(run, tmp_path):
    skills = tmp_path / "plugin" / "skills"
    skills.mkdir(parents=True)
    router(skills)
    (tmp_path / "plugin" / "refs").mkdir()
    (skills / "write" / "phases" / "ideate.md").write_text('F="${CLAUDE_PLUGIN_ROOT}/refs/words-${LANG}.md"\n')
    assert run("check-routers", skills).returncode == 0


def test_runtime_variable_path_with_missing_dir_fails(run, tmp_path):
    skills = tmp_path / "plugin" / "skills"
    skills.mkdir(parents=True)
    router(skills)
    (skills / "write" / "phases" / "ideate.md").write_text('F="${CLAUDE_PLUGIN_ROOT}/nodir/words-${LANG}.md"\n')
    r = run("check-routers", skills)
    assert r.returncode == 1 and "nodir/words-${LANG}.md does not resolve" in r.stdout


def test_skill_dir_link_still_verified(run, tmp_path):
    _phase_with(tmp_path, "See ${CLAUDE_SKILL_DIR}/references/none.md\n")
    r = run("check-routers", tmp_path)
    assert r.returncode == 1 and "references/none.md does not resolve" in r.stdout
