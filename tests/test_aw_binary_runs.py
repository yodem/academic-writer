"""The BUILT aw binary must start. Unit tests import src/ modules directly, so a bundling defect
(e.g. 'Dynamic require of "child_process" is not supported' from an ESM bundle) passed every test
on 2026-09-23 while the shipped binary crashed on launch."""
import pathlib, subprocess, tempfile
AW = pathlib.Path(__file__).parent.parent / "plugins/academic-writer/bin/aw"

def _run(*args):
    return subprocess.run([str(AW), *args], capture_output=True, text=True, timeout=60)

def test_binary_starts_and_reports_usage():
    p = _run()
    assert "Dynamic require" not in p.stderr and "SyntaxError" not in p.stderr, p.stderr[-400:]
    assert "ERROR" in (p.stdout + p.stderr)  # usage error, not a crash trace

def test_binary_subcommands_load():
    with tempfile.TemporaryDirectory() as d:
        for args in (["ledger", "show", "none"], ["proofread", "--run", "x", "missing.md"], ["voice", "bundle"]):
            p = _run("--data-dir", d, "--project-dir", d, *args)
            assert "Dynamic require" not in p.stderr and "at file://" not in p.stderr.split("ERROR")[0], (args, p.stderr[-400:])

def test_built_scripts_find_their_config_without_flags(tmp_path):
    """Scripts shipped under <plugin>/scripts/ must resolve thresholds.json from the plugin
    layout; a repo-layout-only default broke the first live `aw proofread` (2026-09-23)."""
    art = tmp_path / "a.md"; art.write_text("פסקה ראשונה.\n\nפסקה שנייה.\n", encoding="utf-8")
    script = AW.parent.parent / "scripts/chunk-article.py"
    p = subprocess.run(["python3", str(script), "--input", str(art)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-300:]
