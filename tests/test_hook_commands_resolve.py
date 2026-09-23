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
