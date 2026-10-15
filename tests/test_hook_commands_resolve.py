"""Every registered hook command must actually start its script.

Regression (2026-09-23): quoting "${CLAUDE_PLUGIN_ROOT}/hooks/bin/run-hook.mjs lifecycle/x" as ONE
shell word made node look for a file named "run-hook.mjs lifecycle/x"; every hook died with
MODULE_NOT_FOUND and no structural test noticed.
"""
import json, os, pathlib, subprocess, tempfile
ROOT = pathlib.Path(__file__).parent.parent
PLUGIN = ROOT / "plugins/academic-writer"

def _commands():
    hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
    for event, groups in hooks.items():
        for g in groups:
            for h in g.get("hooks", []):
                if h.get("type") == "command":
                    yield event, h["command"]

def test_every_hook_command_resolves_its_script():
    cmds = list(_commands())
    assert cmds
    with tempfile.TemporaryDirectory() as project:  # no .academic-helper: hooks must no-op
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN), "CLAUDE_PROJECT_DIR": project}
        for event, cmd in cmds:
            cmd = cmd.replace("${user_config.google_api_key}", "").replace("${user_config.jev_api_key}", "")
            p = subprocess.run(["sh", "-c", cmd], input="{}", capture_output=True, text=True, env=env, cwd=project, timeout=30)
            assert "MODULE_NOT_FOUND" not in p.stderr and "Cannot find module" not in p.stderr, (event, cmd, p.stderr[-400:])


def _session_env_command():
    return next(c for e, c in _commands() if e == "SessionStart" and "lifecycle/session-env" in c)


def _run_session_env(value, extra_env=None):
    """Run the real SessionStart session-env command as a shell would, then source the env file it wrote."""
    cmd = _session_env_command()
    # Claude Code substitutes the two key placeholders itself; leave them empty here.
    cmd = cmd.replace("${user_config.google_api_key}", "").replace("${user_config.jev_api_key}", "")
    with tempfile.TemporaryDirectory() as project:
        (pathlib.Path(project) / ".academic-helper").mkdir()
        (pathlib.Path(project) / ".academic-helper/profile.md").write_text("profile")
        env_file = pathlib.Path(project) / "claude.env"
        env_file.write_text("")
        env = {k: v for k, v in os.environ.items() if "PAGEINDEX" not in k}
        env.update({"CLAUDE_PLUGIN_ROOT": str(PLUGIN), "CLAUDE_PROJECT_DIR": project, "CLAUDE_ENV_FILE": str(env_file)})
        env.update(extra_env if extra_env is not None else {"CLAUDE_PLUGIN_OPTION_PAGEINDEX_COMMAND": value})
        p = subprocess.run(["sh", "-c", cmd], input="{}", capture_output=True, text=True, env=env, cwd=project, timeout=30)
        assert p.returncode == 0, p.stderr[-400:]
        out = subprocess.run(
            ["sh", "-c", f'. "{env_file}"; printf %s "$AW_PAGEINDEX_COMMAND"'], capture_output=True, text=True, env={"PATH": os.environ["PATH"]}
        )
        return out.stdout


def test_hooks_json_never_interpolates_the_pageindex_setting_into_the_shell():
    """Claude Code warns that a ${user_config.*} value in a shell-form command is re-parsed by the shell;
    the setting arrives as CLAUDE_PLUGIN_OPTION_PAGEINDEX_COMMAND in the hook's environment instead."""
    assert "pageindex_command" not in _session_env_command()


def test_pageindex_command_with_quote_space_dollar_and_semicolon_arrives_intact():
    nasty = "/path/to/it's wrapper $HOME; echo pwned"
    assert _run_session_env(nasty) == nasty


def test_pageindex_command_legacy_env_name_still_works_and_unset_exports_nothing():
    assert _run_session_env("", {"USER_CONFIG_PAGEINDEX_COMMAND": "pilib"}) == "pilib"
    assert _run_session_env("", {}) == ""
