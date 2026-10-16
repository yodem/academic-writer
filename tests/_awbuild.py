"""Bundle the `aw` CLI from src/cli into a temporary plugin folder, for tests that must run the real program.

The bundle uses the same entry point and options as src/cli/esbuild.config.mjs (ESM, node20, `.md` as text, the
same banner), but writes to a folder the caller chooses. It never reads `plugins/` (the built, committed plugin),
so a test that uses it passes on a clean checkout without `npm run build`. It needs `node` and the repo's own
esbuild (`cd src/cli && npm ci`).

    from _awbuild import bundle_aw, make_plugin_folder
    aw = bundle_aw(tmp_dir)                      # <tmp_dir>/bin/aw (executable)
    root = make_plugin_folder(other_dir, aw)     # a plugin folder around it: bin/aw plus scripts/pageindex and the judging page
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = ROOT / "src" / "cli"

# The banner of src/cli/esbuild.config.mjs: bundled CommonJS dependencies need a real `require` in an ESM file.
BANNER = (
    "#!/usr/bin/env node\n"
    "// ESM bundle: give bundled CommonJS deps a real require (else 'Dynamic require of child_process').\n"
    "import { createRequire as __awCreateRequire } from 'node:module'; const require = __awCreateRequire(import.meta.url);"
)

_BUILD_SCRIPT = """
import { build } from %(esbuild)s;
await build({
  entryPoints: [%(entry)s], outfile: %(outfile)s, bundle: true, platform: 'node', target: 'node20', format: 'esm',
  banner: { js: %(banner)s }, loader: { '.md': 'text' }, logLevel: 'error',
});
"""


class BuildError(RuntimeError):
    pass


def esbuild_entry() -> pathlib.Path:
    entry = CLI / "node_modules" / "esbuild" / "lib" / "main.js"
    if not entry.exists():
        raise BuildError("src/cli/node_modules/esbuild is missing: run `cd src/cli && npm ci` first")
    return entry


def bundle_aw(dest: pathlib.Path) -> pathlib.Path:
    """Bundle src/cli/src/main.ts into `<dest>/bin/aw` and return that path."""
    if shutil.which("node") is None:
        raise BuildError("node is not installed")
    outfile = pathlib.Path(dest) / "bin" / "aw"
    outfile.parent.mkdir(parents=True, exist_ok=True)
    script = _BUILD_SCRIPT % {
        "esbuild": json.dumps(esbuild_entry().as_uri()),
        "entry": json.dumps(str(CLI / "src" / "main.ts")),
        "outfile": json.dumps(str(outfile)),
        "banner": json.dumps(BANNER),
    }
    done = subprocess.run(["node", "--input-type=module", "-e", script], cwd=CLI, capture_output=True, text=True, timeout=180)
    if done.returncode != 0 or not outfile.exists():
        raise BuildError(f"esbuild failed (exit {done.returncode}): {(done.stderr or done.stdout)[-600:]}")
    outfile.chmod(0o755)
    return outfile


def make_plugin_folder(dest: pathlib.Path, aw: pathlib.Path) -> pathlib.Path:
    """A plugin folder `<dest>` around a bundled aw: bin/aw plus what aw reads next to itself.

    `aw` finds its own folder from `<root>/bin/aw`, then reads `<root>/scripts/pageindex` (the pilib source and
    PINNED.json) and, for the evaluation page, `<root>/skills/library-eval/references/judge-page.html`.
    The files come from src/, never from plugins/.
    """
    dest = pathlib.Path(dest)
    (dest / "bin").mkdir(parents=True, exist_ok=True)
    shutil.copy2(aw, dest / "bin" / "aw")
    (dest / "bin" / "aw").chmod(0o755)
    shutil.copytree(ROOT / "src" / "scripts" / "pageindex", dest / "scripts" / "pageindex", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    page = ROOT / "src" / "skills" / "library-eval" / "references" / "judge-page.html"
    if page.exists():
        (dest / "skills" / "library-eval" / "references").mkdir(parents=True, exist_ok=True)
        shutil.copy2(page, dest / "skills" / "library-eval" / "references" / "judge-page.html")
    return dest


def clean_env(**extra: str) -> dict:
    """The caller's environment without any AW_*, Google or Gemini setting, plus `extra`."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("AW_") and k not in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "JEV_API_KEY", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA")}
    env.update(extra)
    return env
