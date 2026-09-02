#!/usr/bin/env bash
# check-mcp-dist-fresh.sh
#
# CI gate: the committed plugins/academic-writer/mcp/gemini-server/dist/index.js
# must be exactly what src/ currently builds.
#
# Why this exists now (and didn't before): until this change, release.yml ran on
# every push to main and its "Rebuild plugin at bumped version" step (`npm run
# build`) regenerated and committed dist/index.js on every release, so a stale
# bundle could not survive more than one release cycle. With the push trigger
# removed (release.yml is now workflow_dispatch-only — see that file's header),
# nothing rebuilds or commits dist/ automatically anymore. The committed
# dist/index.js is therefore the ONLY copy that ships to users from here on, and
# scripts/check-mcp-dist.sh only proves that file STARTS — it says nothing about
# whether it still matches src/. A src/ change landed without a matching rebuild
# would ship silently stale code forever. This gate closes that gap: it rebuilds
# from src/ in an isolated copy and fails if the result differs from what's
# committed.
#
# Determinism: esbuild's own output was verified byte-identical across three
# consecutive same-machine builds before this check was written (see CHANGELOG.md
# / the version-sync entry that introduced this gate for the exact command), and
# the bundle contains no embedded absolute paths, timestamps, or the plugin
# version string (grepped for at the time of writing) — the only volatile inputs
# esbuild could plausibly vary on. gemini-server/package-lock.json pins the exact
# esbuild version, and this script uses `npm ci` (never `npm install`, which can
# re-resolve) against a full copy of that lockfile, so a rebuild in CI uses the
# identical dependency graph as a rebuild on a maintainer's machine. Given all of
# that, a direct byte comparison (`cmp`) between the fresh rebuild and the
# committed file is used directly, rather than a hash-of-possibly-different-bytes
# scheme (which would not add any robustness — see the task note this script was
# written against). If esbuild's output ever does turn out to vary by
# environment, this script is the one place to change: swap the `cmp` call below
# for a normalized comparison, not a workaround at every call site.
#
# Exit 0 -> fresh rebuild from src/ is byte-identical to the committed dist/index.js
# Exit 1 -> they differ (stale artifact — rebuild and commit), or the rebuild itself failed
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MCP_DIR="$PROJECT_ROOT/plugins/academic-writer/mcp/gemini-server"
COMMITTED="$MCP_DIR/dist/index.js"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

fail() {
  echo -e "${RED}✗ check-mcp-dist-fresh: $1${NC}" >&2
  exit 1
}

[[ -f "$COMMITTED" ]] || fail "missing $COMMITTED — nothing committed to compare a rebuild against"
[[ -f "$MCP_DIR/package-lock.json" ]] || fail "missing $MCP_DIR/package-lock.json — \`npm ci\` needs it for a pinned, reproducible rebuild"
# tsconfig.json is a hard requirement, not an optional extra: esbuild.config.mjs
# doesn't read it directly, but tsc-affecting settings aside, a MISSING copy here
# would make this script build against a different config than build-mcp.sh does,
# which is exactly the kind of false "stale" failure this gate must never produce.
# It is tracked in this repo (verified), so its absence here would mean the copy
# step below broke, not that the committed dist/index.js is actually stale.
[[ -f "$MCP_DIR/tsconfig.json" ]] || fail "missing $MCP_DIR/tsconfig.json — required for a rebuild that matches build-mcp.sh's"
command -v node &>/dev/null || fail "node is required for this check"
command -v npm &>/dev/null || fail "npm is required for this check"

TMP_BUILD="$(mktemp -d)"
trap 'rm -rf "$TMP_BUILD"' EXIT

# Copy exactly the inputs esbuild.config.mjs's build depends on — the whole
# src/ tree (esbuild inlines everything it imports/requires from there,
# including the .md prompt files loaded via the `.md: 'text'` loader) plus the
# build config and a pinned dependency graph. Deliberately NOT a copy of
# node_modules or dist/ — this must be a build from scratch, not a reuse of
# whatever happens to already be on disk.
cp -R "$MCP_DIR/src" "$TMP_BUILD/src"
cp "$MCP_DIR/esbuild.config.mjs" "$TMP_BUILD/esbuild.config.mjs"
cp "$MCP_DIR/package.json" "$TMP_BUILD/package.json"
cp "$MCP_DIR/package-lock.json" "$TMP_BUILD/package-lock.json"
cp "$MCP_DIR/tsconfig.json" "$TMP_BUILD/tsconfig.json"

echo -e "${BLUE}    Installing pinned dependencies (npm ci) in an isolated copy...${NC}"
( cd "$TMP_BUILD" && npm ci --silent 2>&1 | sed 's/^/    /' ) || fail "npm ci failed in the isolated rebuild copy"

echo -e "${BLUE}    Rebuilding dist/index.js from src/ in the isolated copy...${NC}"
( cd "$TMP_BUILD" && node esbuild.config.mjs 2>&1 | sed 's/^/    /' ) || fail "esbuild rebuild failed"

REBUILT="$TMP_BUILD/dist/index.js"
[[ -f "$REBUILT" ]] || fail "rebuild did not produce dist/index.js"

if ! cmp -s "$COMMITTED" "$REBUILT"; then
  fail "committed dist/index.js does NOT match a fresh rebuild from src/ — the shipped
bundle is stale. Run \`bash scripts/build-mcp.sh\` (or \`npm run build:mcp\`), then
commit the regenerated plugins/academic-writer/mcp/gemini-server/dist/index.js.
committed: $COMMITTED ($(wc -c < "$COMMITTED") bytes, sha256 $(shasum -a 256 "$COMMITTED" | cut -d' ' -f1))
rebuilt:   $REBUILT ($(wc -c < "$REBUILT") bytes, sha256 $(shasum -a 256 "$REBUILT" | cut -d' ' -f1))"
fi

echo -e "${GREEN}✓ check-mcp-dist-fresh: committed dist/index.js matches a fresh rebuild from src/${NC}"
exit 0
