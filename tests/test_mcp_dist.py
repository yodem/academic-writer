"""The bundled Gemini MCP server must actually start once installed.

Regression guard for the CONNECTION_CLOSED bug: plugins/academic-writer/mcp/gemini-server/
dist/ was gitignored from v0.6.2 through v0.7.0, so a freshly-installed plugin declared the
`gemini-api` MCP server in plugin.json but shipped no dist/index.js — Claude Code's spawn
crashed immediately with `Cannot find module`. There is no install/build lifecycle hook (see
plugins/academic-writer/hooks/hooks.json), so whatever is committed to git is exactly what a
user's install gets.

dist/index.js is a fully self-contained bundle (esbuild.config.mjs sets `external: []` and
inlines @modelcontextprotocol/sdk and @google/genai, with a `createRequire(import.meta.url)`
banner shim so google-auth-library's internal dynamic `require()` calls still resolve under
ESM output) — it needs nothing from node_modules at runtime.

This wraps scripts/check-mcp-dist.sh (see that script for the full mechanism: it copies only
dist/index.js — plus the sibling scripts/ dir gemini_ocr's Python helpers live in — into an
isolated temp dir with no node_modules anywhere in its ancestry and starts it the way Claude
Code does) so the same guard also runs in local `pytest tests/`, matching this repo's
convention (test_no_private_refs.py, test_version_consistency.py) of wiring every
deterministic release gate into both CI and pytest.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MCP_DIR = REPO / "plugins" / "academic-writer" / "mcp" / "gemini-server"
SCRIPT = REPO / "scripts" / "check-mcp-dist.sh"


class TestMcpDist(unittest.TestCase):
    def test_dist_is_tracked(self) -> None:
        dist_index = MCP_DIR / "dist" / "index.js"
        self.assertTrue(
            dist_index.exists(),
            f"{dist_index} is missing — run `npm run build` (or `bash scripts/build-mcp.sh`) "
            "first. If this fails in CI, the release gate that ships dist/ has regressed.",
        )

    def test_dist_starts_clean_self_contained_with_no_node_modules(self) -> None:
        proc = subprocess.run(
            ["bash", str(SCRIPT)], cwd=REPO, capture_output=True, text=True, timeout=30
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"scripts/check-mcp-dist.sh failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
