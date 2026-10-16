"""Every registered hook command must actually start its script.

Regression (2026-09-23): quoting "${CLAUDE_PLUGIN_ROOT}/hooks/bin/run-hook.mjs lifecycle/x" as ONE
shell word made node look for a file named "run-hook.mjs lifecycle/x"; every hook died with
MODULE_NOT_FOUND and no structural test noticed.
"""
import json, os, pathlib, shutil, subprocess, tempfile
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
            p = subprocess.run(["sh", "-c", cmd], input="{}", capture_output=True, text=True, env=env, cwd=project, timeout=30)
            assert "MODULE_NOT_FOUND" not in p.stderr and "Cannot find module" not in p.stderr, (event, cmd, p.stderr[-400:])


SRC_HOOKS = ROOT / "src/hooks"


def _session_env_command():
    hooks = json.loads((SRC_HOOKS / "hooks.json").read_text())["hooks"]
    return next(
        h["command"] for g in hooks["SessionStart"] for h in g["hooks"] if "lifecycle/session-env" in h.get("command", "")
    )


def _build_plugin_root(tmp):
    """A throwaway plugin root with the CURRENT src/hooks bundle (never touches plugins/)."""
    esbuild = SRC_HOOKS / "node_modules/.bin/esbuild"
    if not esbuild.exists():
        esbuild = ROOT / "node_modules/.bin/esbuild"
    assert esbuild.exists(), "esbuild not installed: run npm ci in src/hooks"
    root = pathlib.Path(tmp) / "plugin"
    (root / "hooks/dist").mkdir(parents=True)
    shutil.copytree(SRC_HOOKS / "bin", root / "hooks/bin")
    subprocess.run(
        [str(esbuild), "src/entries/lifecycle.ts", "--bundle", "--format=esm", "--platform=node", "--target=node20",
         f"--outfile={root / 'hooks/dist/lifecycle.mjs'}", "--log-level=error"],
        cwd=SRC_HOOKS, check=True, timeout=60,
    )
    return root


def _run_session_env(value, extra_env=None, var="AW_PAGEINDEX_COMMAND", capture=False):
    """Run the real SessionStart session-env command from src/hooks/hooks.json as a shell would, then source the env file it wrote."""
    cmd = _session_env_command()
    with tempfile.TemporaryDirectory() as tmp:
        plugin_root = _build_plugin_root(tmp)
        project = pathlib.Path(tmp) / "project"
        (project / ".academic-helper").mkdir(parents=True)
        (project / ".academic-helper/profile.md").write_text("profile")
        env_file = pathlib.Path(tmp) / "claude.env"
        env_file.write_text("")
        env = {
            k: v for k, v in os.environ.items()
            if "PAGEINDEX" not in k and k != "CLAUDE_PLUGIN_DATA" and not k.startswith(("CLAUDE_PLUGIN_OPTION_", "USER_CONFIG_"))
        }
        env.update({"CLAUDE_PLUGIN_ROOT": str(plugin_root), "CLAUDE_PROJECT_DIR": str(project), "CLAUDE_ENV_FILE": str(env_file)})
        env.update(extra_env if extra_env is not None else {"CLAUDE_PLUGIN_OPTION_PAGEINDEX_COMMAND": value})
        p = subprocess.run(["sh", "-c", cmd], input="{}", capture_output=True, text=True, env=env, cwd=project, timeout=30)
        assert p.returncode == 0, p.stderr[-400:]
        if capture:
            return p.stdout + p.stderr
        out = subprocess.run(
            ["sh", "-c", f'. "{env_file}"; printf %s "${var}"'], capture_output=True, text=True, env={"PATH": os.environ["PATH"]}
        )
        return out.stdout


def test_hooks_json_never_interpolates_a_plugin_option_into_the_shell():
    """Claude Code 2.1.300 refuses to run a shell-form hook whose command references ${user_config.*} (the value would be
    re-parsed by the shell). Options arrive as CLAUDE_PLUGIN_OPTION_<KEY> in the hook's environment instead."""
    assert "user_config." not in (SRC_HOOKS / "hooks.json").read_text()
    assert "user_config" not in _session_env_command()


def test_every_manifest_option_is_read_by_the_session_hook():
    manifest = json.loads((ROOT / "manifests/academic-writer.json").read_text())
    source = (SRC_HOOKS / "src/lifecycle/session-env.ts").read_text()
    for key in manifest["userConfig"]:
        assert f"pluginOption('{key}')" in source, key


def test_google_and_jev_keys_with_quote_dollar_and_semicolon_arrive_intact_and_are_not_printed():
    g = "AIza'sy $HOME; echo pwned \"x\""
    j = "jev'`id`;$(id)"
    env = {"CLAUDE_PLUGIN_OPTION_GOOGLE_API_KEY": g, "CLAUDE_PLUGIN_OPTION_JEV_API_KEY": j}
    assert _run_session_env("", env, var="GOOGLE_API_KEY") == g
    assert _run_session_env("", env, var="JEV_API_KEY") == j
    # the older USER_CONFIG_ names still work, and the new names win
    assert _run_session_env("", {"USER_CONFIG_GOOGLE_API_KEY": "old"}, var="GOOGLE_API_KEY") == "old"
    both = {"USER_CONFIG_GOOGLE_API_KEY": "old", "CLAUDE_PLUGIN_OPTION_GOOGLE_API_KEY": "new"}
    assert _run_session_env("", both, var="GOOGLE_API_KEY") == "new"
    # nothing set: nothing exported
    assert _run_session_env("", {}, var="GOOGLE_API_KEY") == ""


def test_the_hook_never_prints_a_secret():
    secret = "SECRET-KEY-VALUE-123"
    out = _run_session_env("", {"CLAUDE_PLUGIN_OPTION_GOOGLE_API_KEY": secret}, var="GOOGLE_API_KEY", capture=True)
    assert secret not in out


def test_pageindex_command_with_quote_space_dollar_and_semicolon_arrives_intact():
    nasty = "/path/to/it's wrapper $HOME; echo pwned"
    assert _run_session_env(nasty) == nasty


def test_pageindex_command_legacy_env_name_still_works_and_unset_exports_nothing():
    assert _run_session_env("", {"USER_CONFIG_PAGEINDEX_COMMAND": "pilib"}) == "pilib"
    assert _run_session_env("", {}) == ""


def test_pageindex_home_is_exported_only_once_the_built_in_helper_is_installed():
    """The Bash tool gets no CLAUDE_PLUGIN_DATA, so the hook tells `aw library` where the installed helper lives. Run through the real
    hook command; a path with a quote and a space must arrive intact."""
    with tempfile.TemporaryDirectory() as tmp:
        data = pathlib.Path(tmp) / "plugin data it's"
        (data / "pageindex").mkdir(parents=True)
        home = str(data / "pageindex")
        assert _run_session_env("", {"CLAUDE_PLUGIN_DATA": str(data)}, var="AW_PAGEINDEX_HOME") == ""
        (data / "pageindex" / "installed.json").write_text("{}")
        assert _run_session_env("", {"CLAUDE_PLUGIN_DATA": str(data)}, var="AW_PAGEINDEX_HOME") == home
        # a command the researcher supplied is still exported as before, next to the folder
        both = {"CLAUDE_PLUGIN_DATA": str(data), "CLAUDE_PLUGIN_OPTION_PAGEINDEX_COMMAND": "my-wrapper --x"}
        assert _run_session_env("", both, var="AW_PAGEINDEX_COMMAND") == "my-wrapper --x"
        assert _run_session_env("", both, var="AW_PAGEINDEX_HOME") == home
