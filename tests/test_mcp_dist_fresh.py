"""The committed gemini-server dist/index.js must match a fresh rebuild from src/.

With release.yml's push trigger removed (see that file's header — releases are now
workflow_dispatch-only, cut deliberately via a version bump), nothing rebuilds and
commits dist/index.js automatically anymore. The committed bundle is therefore the
only copy that ever ships to users. scripts/check-mcp-dist.sh (test_mcp_dist.py)
only proves that file STARTS self-contained — it says nothing about whether it
still reflects src/. This wraps the companion gate, scripts/check-mcp-dist-fresh.sh,
which rebuilds from src/ in an isolated temp copy (npm ci against the pinned
package-lock.json, then the same esbuild.config.mjs build) and fails if the result
differs byte-for-byte from what's committed — so a src/ change that lands without a
matching rebuild is caught here instead of shipping stale code silently.

See scripts/check-mcp-dist-fresh.sh's header for the determinism reasoning (verified
byte-identical across repeated same-machine builds, no embedded absolute paths /
timestamps / version string, pinned lockfile) behind using a direct byte comparison
rather than a hash-recording scheme.

Matches this repo's convention (test_no_private_refs.py, test_version_consistency.py,
test_mcp_dist.py) of wiring every deterministic release gate into both CI and pytest.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MCP_DIR = REPO / "plugins" / "academic-writer" / "mcp" / "gemini-server"
SCRIPT = REPO / "scripts" / "check-mcp-dist-fresh.sh"


class TestMcpDistFresh(unittest.TestCase):
    def test_committed_dist_matches_fresh_rebuild(self) -> None:
        dist_index = MCP_DIR / "dist" / "index.js"
        self.assertTrue(
            dist_index.exists(),
            f"{dist_index} is missing — run `npm run build` (or `bash scripts/build-mcp.sh`) "
            "first.",
        )
        # npm ci + an esbuild rebuild in an isolated copy — allow real headroom.
        proc = subprocess.run(
            ["bash", str(SCRIPT)], cwd=REPO, capture_output=True, text=True, timeout=120
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"scripts/check-mcp-dist-fresh.sh failed — committed dist/index.js is stale "
            f"relative to src/:\nstdout: {proc.stdout}\nstderr: {proc.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
